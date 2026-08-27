import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverProfile
from app.models.payout import PayoutCalculation
from app.models.trip import (
    LocationPing,
    LocationPingBatch,
    QuarantinedPingBatch,
    QuarantinedPingBatchStatus,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.models.vehicle import Vehicle
from app.schemas.trips import (
    LocationPingBatchCreate,
    LocationPingCreate,
    TripEndRequest,
    TripStartRequest,
)
from app.services.audit import create_audit_event
from app.services.billing import assert_new_work_authorized
from app.services.campaign_assignments import (
    as_aware_utc,
    ensure_active_driver_profile,
    ensure_active_vehicle,
    ensure_current_activation_snapshot,
    ensure_vehicle_belongs_to_driver,
    get_driver_profile_for_user,
)
from app.services.campaign_cancellations import campaign_financial_cutoff
from app.services.installation_evidence import ensure_current_display_proof
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.vehicle_onboarding import (
    acquire_work_eligibility_lock,
    ensure_current_driver_vehicle_eligibility,
)

# FND-07 (RM7): a lost race on either trip-exclusivity index returns the same
# stable 409 code as the pre-check that guards it, never a 500.
TRIP_CONFLICT_ENVELOPES = {
    "uq_trip_sessions_driver_profile_active": (
        "ACTIVE_TRIP_EXISTS_FOR_DRIVER",
        "An active trip already exists for this driver",
    ),
    "uq_trip_sessions_vehicle_active": (
        "ACTIVE_TRIP_EXISTS_FOR_VEHICLE",
        "An active trip already exists for this vehicle",
    ),
}


@dataclass(frozen=True)
class TripSummary:
    trip: TripSession
    ping_count: int
    first_ping_at: datetime | None
    last_ping_at: datetime | None


@dataclass(frozen=True)
class PingBatchResult:
    batch: LocationPingBatch | None
    duplicate: bool
    quarantine: QuarantinedPingBatch | None = None
    # Set when this ingest completed the trip's watermark and sealed it —
    # the route enqueues processing after commit (fail-open, §14.3.2).
    sealed_now: bool = False

    @property
    def quarantined(self) -> bool:
        return self.quarantine is not None


@dataclass(frozen=True)
class TripEndResult:
    trip: TripSession
    sealed_now: bool


def utc_now() -> datetime:
    return datetime.now(UTC)


def trip_not_found() -> AppError:
    return AppError(
        "TRIP_NOT_FOUND",
        "Trip was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def ensure_campaign_active_for_trip(campaign: Campaign, now: datetime) -> None:
    if campaign.status != CampaignStatus.ACTIVE.value:
        raise AppError(
            "CAMPAIGN_NOT_ACTIVE",
            "Campaign must be active for trip tracking",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if campaign.start_at is not None and as_aware_utc(campaign.start_at) > now:
        raise AppError(
            "CAMPAIGN_NOT_STARTED",
            "Campaign start_at is in the future",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if campaign.end_at is not None and as_aware_utc(campaign.end_at) < now:
        raise AppError(
            "CAMPAIGN_EXPIRED",
            "Campaign end_at is in the past",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def ensure_assignment_active(assignment: CampaignAssignment) -> None:
    if assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE",
            "Campaign assignment must be active for trip tracking",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def get_driver_assignment_for_trip_start(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
) -> tuple[DriverProfile, CampaignAssignment]:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    result = await session.execute(
        select(CampaignAssignment).where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return driver_profile, assignment


async def ensure_no_active_trip_for_driver_or_vehicle(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    vehicle_id: UUID,
) -> None:
    driver_trip_id = await session.scalar(
        select(TripSession.id).where(
            TripSession.driver_profile_id == driver_profile_id,
            TripSession.status == TripSessionStatus.ACTIVE.value,
        )
    )
    if driver_trip_id is not None:
        raise AppError(
            "ACTIVE_TRIP_EXISTS_FOR_DRIVER",
            "An active trip already exists for this driver",
            status_code=status.HTTP_409_CONFLICT,
        )
    vehicle_trip_id = await session.scalar(
        select(TripSession.id).where(
            TripSession.vehicle_id == vehicle_id,
            TripSession.status == TripSessionStatus.ACTIVE.value,
        )
    )
    if vehicle_trip_id is not None:
        raise AppError(
            "ACTIVE_TRIP_EXISTS_FOR_VEHICLE",
            "An active trip already exists for this vehicle",
            status_code=status.HTTP_409_CONFLICT,
        )


async def start_driver_trip(
    session: AsyncSession,
    *,
    user_id: UUID,
    payload: TripStartRequest,
    settings: Settings | None = None,
) -> TripSession:
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    # The profile lookup establishes ownership without locking it.  The
    # mutation path below then takes the shared terms authority, campaign,
    # assignment, profile, and vehicle locks in that single deterministic
    # order.  Terminal assignment transitions use the same order.
    driver_profile = await get_driver_profile_for_user(session, user_id)
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(
            CampaignAssignment.id == payload.assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    if campaign_id is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await acquire_campaign_terms_lock(session, campaign_id)
    eligibility_row = (
        await session.execute(
            select(
                CampaignAssignment.driver_profile_id,
                CampaignAssignment.vehicle_id,
            ).where(
                CampaignAssignment.id == payload.assignment_id,
                CampaignAssignment.driver_profile_id == driver_profile.id,
            )
        )
    ).one_or_none()
    if eligibility_row is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await acquire_work_eligibility_lock(
        session,
        driver_profile_id=eligibility_row[0],
        vehicle_id=eligibility_row[1],
    )
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    assignment = await session.scalar(
        select(CampaignAssignment)
        .where(
            CampaignAssignment.id == payload.assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
        .with_for_update()
    )
    if campaign is None or assignment is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == assignment.driver_profile_id)
        .with_for_update()
    )
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == assignment.vehicle_id).with_for_update()
    )
    if driver_profile is None or vehicle is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    now = await database_clock(session)

    ensure_assignment_active(assignment)
    ensure_campaign_active_for_trip(campaign, now)
    ensure_active_driver_profile(driver_profile)
    ensure_active_vehicle(vehicle)
    ensure_vehicle_belongs_to_driver(vehicle, driver_profile)
    await ensure_current_driver_vehicle_eligibility(
        session,
        driver_profile=driver_profile,
        vehicle=vehicle,
        now=now,
        lock=True,
    )
    await assert_new_work_authorized(
        session, campaign_id=campaign.id, assignment_id=assignment.id
    )
    await ensure_current_activation_snapshot(session, assignment=assignment, lock=True)
    await ensure_no_active_trip_for_driver_or_vehicle(
        session,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
    )
    display_proof = await ensure_current_display_proof(
        session,
        assignment=assignment,
        settings=settings,
        now=now,
        lock=True,
    )

    trip = TripSession(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
        display_proof_id=display_proof.id,
        started_by_user_id=user_id,
        status=TripSessionStatus.ACTIVE.value,
        started_at=now,
        trip_metadata=payload.metadata,
    )
    session.add(trip)
    try:
        await session.flush()
    except IntegrityError as exc:
        # FND-07 (RM7): a lost race on either trip-exclusivity index returns
        # the same stable 409 code as the pre-check; anything else re-raises.
        envelope = TRIP_CONFLICT_ENVELOPES.get(integrity_constraint_name(exc) or "")
        if envelope is None:
            raise
        await session.rollback()
        code, message = envelope
        raise AppError(code, message, status_code=status.HTTP_409_CONFLICT) from exc
    await session.refresh(trip)
    return trip


async def get_current_driver_trip(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> TripSession | None:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    result = await session.execute(
        select(TripSession).where(
            TripSession.driver_profile_id == driver_profile.id,
            TripSession.status == TripSessionStatus.ACTIVE.value,
        )
    )
    trips = list(result.scalars().all())
    if len(trips) > 1:
        raise AppError(
            "MULTIPLE_ACTIVE_TRIPS",
            "Multiple active trips were found for the current driver",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return trips[0] if trips else None


async def get_driver_trip(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
) -> TripSession:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    result = await session.execute(
        select(TripSession).where(
            TripSession.id == trip_id,
            TripSession.driver_profile_id == driver_profile.id,
        )
    )
    trip = result.scalar_one_or_none()
    if trip is None:
        raise trip_not_found()
    return trip


async def summarize_trip(session: AsyncSession, trip: TripSession) -> TripSummary:
    result = await session.execute(
        select(
            func.count(LocationPing.id),
            func.min(LocationPing.recorded_at),
            func.max(LocationPing.recorded_at),
        ).where(LocationPing.trip_session_id == trip.id)
    )
    ping_count, first_ping_at, last_ping_at = result.one()
    return TripSummary(
        trip=trip,
        ping_count=int(ping_count or 0),
        first_ping_at=first_ping_at,
        last_ping_at=last_ping_at,
    )


async def count_trip_batches(session: AsyncSession, trip_id: UUID) -> int:
    count = await session.scalar(
        select(func.count(LocationPingBatch.id)).where(
            LocationPingBatch.trip_session_id == trip_id
        )
    )
    return int(count or 0)


def watermark_satisfied(trip: TripSession, server_batch_count: int) -> bool:
    """The seal predicate (RM3): the server holds every batch the client cut.

    Batches are the durable idempotent unit, so the batch count is the
    watermark; client_ping_count and client_complete are diagnostic evidence
    only (individual pings may be legitimately rejected by bounds checks).
    """
    return trip.client_batch_count is not None and server_batch_count >= trip.client_batch_count


async def try_seal_trip(
    session: AsyncSession,
    trip: TripSession,
    *,
    reason: TripSealReason,
    now: datetime,
    actor_user_id: UUID | None = None,
) -> bool:
    """One-way ended -> sealed transition, safe under concurrent attempts.

    Guarded UPDATE (§14.3 rule 1): exactly one caller wins the transition;
    every other concurrent seal attempt sees rowcount 0 and must not audit,
    enqueue, or re-seal. The winner writes the audit event here so every seal
    path (end fast-path, late-batch ingest, grace sweep) is audited once.
    """
    result = await session.execute(
        update(TripSession)
        .where(
            TripSession.id == trip.id,
            TripSession.status == TripSessionStatus.ENDED.value,
        )
        .values(
            status=TripSessionStatus.SEALED.value,
            sealed_at=now,
            seal_reason=reason.value,
            updated_at=now,
        )
    )
    sealed = result.rowcount == 1
    if sealed:
        await session.refresh(trip)
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="trip.sealed",
            entity_type="trip_session",
            entity_id=str(trip.id),
            metadata={
                "seal_reason": reason.value,
                "client_batch_count": trip.client_batch_count,
                "client_ping_count": trip.client_ping_count,
                "client_complete": trip.client_complete,
            },
        )
    return sealed


async def end_driver_trip(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
    payload: TripEndRequest,
) -> TripEndResult:
    trip = await get_driver_trip(session, user_id=user_id, trip_id=trip_id)
    await acquire_campaign_terms_lock(session, trip.campaign_id)
    now = utc_now()
    # Guarded transition (like ended -> sealed): two concurrent end requests
    # must not both pass a read-then-write check — the loser would overwrite
    # a seal and trip the sealed-fields constraint as a 500.
    result = await session.execute(
        update(TripSession)
        .where(
            TripSession.id == trip.id,
            TripSession.status == TripSessionStatus.ACTIVE.value,
        )
        .values(
            status=TripSessionStatus.ENDED.value,
            ended_at=now,
            end_reason=payload.end_reason,
            client_batch_count=payload.client_batch_count,
            client_ping_count=payload.client_ping_count,
            client_complete=payload.client_complete,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        raise AppError(
            "TRIP_ALREADY_ENDED",
            "Trip is already ended",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    await session.refresh(trip)

    # Fast path: the watermark is already satisfied at end time — seal in the
    # same transaction so complete trips reach the money chain with no grace
    # delay. Incomplete/legacy ends stay `ended` for the recovery window.
    sealed_now = False
    if watermark_satisfied(trip, await count_trip_batches(session, trip.id)):
        sealed_now = await try_seal_trip(
            session,
            trip,
            reason=TripSealReason.CLIENT_COMPLETE,
            now=now,
            actor_user_id=user_id,
        )
    await session.refresh(trip)
    return TripEndResult(trip=trip, sealed_now=sealed_now)


def canonical_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_ping_payload(payload: LocationPingBatchCreate) -> dict[str, Any]:
    return {
        "pings": [
            {
                "recorded_at": canonical_datetime(ping.recorded_at),
                "lat": ping.lat,
                "lon": ping.lon,
                "accuracy_m": ping.accuracy_m,
                "speed_mps": ping.speed_mps,
                "heading_degrees": ping.heading_degrees,
                "altitude_m": ping.altitude_m,
                "sequence_number": ping.sequence_number,
                "metadata": ping.metadata,
            }
            for ping in payload.pings
        ],
        "metadata": payload.metadata,
    }


def payload_hash(payload: LocationPingBatchCreate) -> str:
    canonical_json = json.dumps(
        canonical_ping_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def ensure_ping_batch_size(payload: LocationPingBatchCreate, settings: Settings) -> None:
    if len(payload.pings) > settings.max_location_pings_per_batch:
        raise AppError(
            "LOCATION_PING_BATCH_TOO_LARGE",
            "Location ping batch exceeds the configured maximum",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_location_pings_per_batch": settings.max_location_pings_per_batch},
        )


def ensure_ping_bounds(
    *,
    trip: TripSession,
    ping: LocationPingCreate,
    now: datetime,
    settings: Settings,
) -> None:
    recorded_at = as_aware_utc(ping.recorded_at)
    if recorded_at > now + timedelta(seconds=settings.location_ping_future_skew_seconds):
        raise AppError(
            "INVALID_RECORDED_AT",
            "Location ping recorded_at is too far in the future",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    earliest = as_aware_utc(trip.started_at) - timedelta(
        seconds=settings.location_ping_start_skew_seconds
    )
    if recorded_at < earliest:
        raise AppError(
            "INVALID_RECORDED_AT",
            "Location ping recorded_at is before the allowed trip start skew",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if trip.ended_at is not None:
        # Late (post-end) delivery window: only points recorded during the
        # trip are ingestible. Skew matches the future-skew tolerance so a
        # fast client clock cannot poison its own final batch (RM3).
        latest = as_aware_utc(trip.ended_at) + timedelta(
            seconds=settings.location_ping_end_skew_seconds
        )
        if recorded_at > latest:
            raise AppError(
                "INVALID_RECORDED_AT",
                "Location ping recorded_at is after the trip ended",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    if ping.accuracy_m is not None and ping.accuracy_m > settings.max_location_accuracy_m:
        raise AppError(
            "INVALID_ACCURACY",
            "Location ping accuracy exceeds the configured maximum",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_location_accuracy_m": settings.max_location_accuracy_m},
        )
    if ping.speed_mps is not None and ping.speed_mps > settings.max_location_speed_mps:
        raise AppError(
            "INVALID_SPEED",
            "Location ping speed exceeds the configured maximum",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_location_speed_mps": settings.max_location_speed_mps},
        )


def point_value(session: AsyncSession, *, lon: float, lat: float):
    if session.get_bind().dialect.name == "postgresql":
        return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    return f"POINT({lon} {lat})"


async def ingest_location_ping_batch(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
    payload: LocationPingBatchCreate,
    settings: Settings,
) -> PingBatchResult:
    trip = await get_driver_trip(session, user_id=user_id, trip_id=trip_id)
    # Cancellation owns this same campaign authority. Whichever transaction
    # wins establishes whether this batch is pre- or post-cutoff evidence.
    await acquire_campaign_terms_lock(session, trip.campaign_id)
    # Lock the trip row and re-read status before deciding live vs quarantine:
    # under READ COMMITTED a concurrent seal (grace sweep or a racing end
    # request) must not land while this insert is mid-flight, or live pings
    # would silently join a sealed trip's already-fingerprinted money inputs.
    trip = await session.scalar(
        select(TripSession).where(TripSession.id == trip.id).with_for_update()
    )
    if trip is None:
        raise trip_not_found()
    financial_cutoff = await campaign_financial_cutoff(session, trip.campaign_id)
    if trip.status == TripSessionStatus.ACTIVE.value:
        assignment = await session.get(CampaignAssignment, trip.assignment_id)
        if assignment is None:
            raise trip_not_found()
        if financial_cutoff is None:
            ensure_assignment_active(assignment)
    # `ended` = the RM3 recovery window: late batches are accepted, and the
    # assignment-active gate is deliberately skipped — delivery of evidence
    # already recorded must not depend on the assignment still being active.
    # `sealed` falls through to the quarantine path below.

    digest = payload_hash(payload)
    # Live-batch dedup first, for every status: a batch uploaded pre-seal
    # whose response was lost and is retried post-seal must return its
    # original ACK, never a conflict and never a quarantine row.
    existing_batch = await session.scalar(
        select(LocationPingBatch).where(
            LocationPingBatch.trip_session_id == trip.id,
            LocationPingBatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_batch is not None:
        if existing_batch.payload_hash != digest:
            raise AppError(
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotency key was already used with a different payload",
                status_code=status.HTTP_409_CONFLICT,
            )
        return PingBatchResult(batch=existing_batch, duplicate=True)

    ensure_ping_batch_size(payload, settings)
    received_at = utc_now()

    if trip.status == TripSessionStatus.SEALED.value:
        return await quarantine_ping_batch(
            session,
            trip=trip,
            payload=payload,
            digest=digest,
            received_at=received_at,
        )

    for ping in payload.pings:
        ensure_ping_bounds(trip=trip, ping=ping, now=received_at, settings=settings)

    batch_metadata = dict(payload.metadata)
    if financial_cutoff is not None:
        batch_metadata["financial_cutoff_at"] = financial_cutoff.isoformat()
        batch_metadata["post_cutoff_ping_count"] = sum(
            1 for ping in payload.pings if as_aware_utc(ping.recorded_at) > financial_cutoff
        )
    batch = LocationPingBatch(
        trip_session_id=trip.id,
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        pings_accepted=len(payload.pings),
        received_at=received_at,
        batch_metadata=batch_metadata,
    )
    session.add(batch)
    await session.flush()

    for ping in payload.pings:
        session.add(
            LocationPing(
                trip_session_id=trip.id,
                batch_id=batch.id,
                recorded_at=ping.recorded_at,
                received_at=received_at,
                sequence_number=ping.sequence_number,
                latitude=ping.lat,
                longitude=ping.lon,
                accuracy_m=ping.accuracy_m,
                speed_mps=ping.speed_mps,
                heading_degrees=ping.heading_degrees,
                altitude_m=ping.altitude_m,
                geom=point_value(session, lon=ping.lon, lat=ping.lat),
                ping_metadata=ping.metadata,
            )
        )
    trip.updated_at = received_at
    await session.flush()
    await session.refresh(batch)

    # A late batch may complete the watermark of an ended trip: the data is
    # now complete by the client's own accounting, so seal without waiting
    # for grace (RM3; decision recorded in decisions-log).
    sealed_now = False
    if trip.status == TripSessionStatus.ENDED.value and watermark_satisfied(
        trip, await count_trip_batches(session, trip.id)
    ):
        sealed_now = await try_seal_trip(
            session,
            trip,
            reason=TripSealReason.LATE_DATA_COMPLETE,
            now=received_at,
            actor_user_id=user_id,
        )
    return PingBatchResult(batch=batch, duplicate=False, sealed_now=sealed_now)


async def quarantine_ping_batch(
    session: AsyncSession,
    *,
    trip: TripSession,
    payload: LocationPingBatchCreate,
    digest: str,
    received_at: datetime,
) -> PingBatchResult:
    existing = await session.scalar(
        select(QuarantinedPingBatch).where(
            QuarantinedPingBatch.trip_session_id == trip.id,
            QuarantinedPingBatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != digest:
            raise AppError(
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotency key was already used with a different payload",
                status_code=status.HTTP_409_CONFLICT,
            )
        return PingBatchResult(batch=None, duplicate=True, quarantine=existing)

    quarantine = QuarantinedPingBatch(
        trip_session_id=trip.id,
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        payload=canonical_ping_payload(payload),
        ping_count=len(payload.pings),
        received_at=received_at,
        status=QuarantinedPingBatchStatus.QUARANTINED.value,
    )
    session.add(quarantine)
    await session.flush()
    await session.refresh(quarantine)
    return PingBatchResult(batch=None, duplicate=False, quarantine=quarantine)


# --- post-seal quarantine review (admin, RM3 controlled reopen) ---------------

LAGOS_TZ = ZoneInfo("Africa/Lagos")


def quarantine_not_found() -> AppError:
    return AppError(
        "QUARANTINED_BATCH_NOT_FOUND",
        "Quarantined ping batch was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def list_quarantined_ping_batches(
    session: AsyncSession,
    *,
    trip_id: UUID | None,
    batch_status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[QuarantinedPingBatch], int]:
    conditions = []
    if trip_id is not None:
        conditions.append(QuarantinedPingBatch.trip_session_id == trip_id)
    if batch_status is not None:
        conditions.append(QuarantinedPingBatch.status == batch_status)
    total = await session.scalar(
        select(func.count(QuarantinedPingBatch.id)).where(*conditions)
    )
    result = await session.execute(
        select(QuarantinedPingBatch)
        .where(*conditions)
        .order_by(QuarantinedPingBatch.created_at.asc(), QuarantinedPingBatch.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_quarantined_batch_for_review(
    session: AsyncSession,
    *,
    trip_id: UUID,
    quarantine_id: UUID,
) -> tuple[QuarantinedPingBatch, TripSession]:
    # FOR UPDATE: apply and discard must serialize on the row — otherwise two
    # admins can both observe `quarantined` and produce a discarded row whose
    # pings were nevertheless applied (with both audit events written).
    quarantine = await session.scalar(
        select(QuarantinedPingBatch)
        .where(
            QuarantinedPingBatch.id == quarantine_id,
            QuarantinedPingBatch.trip_session_id == trip_id,
        )
        .with_for_update()
    )
    if quarantine is None:
        raise quarantine_not_found()
    if quarantine.status != QuarantinedPingBatchStatus.QUARANTINED.value:
        raise AppError(
            "QUARANTINED_BATCH_ALREADY_RESOLVED",
            "Quarantined ping batch was already resolved",
            status_code=status.HTTP_409_CONFLICT,
        )
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    return quarantine, trip


@dataclass(frozen=True)
class QuarantineApplyResult:
    quarantine: QuarantinedPingBatch
    batch: LocationPingBatch
    affected_lagos_days: list[str]


async def apply_quarantined_ping_batch(
    session: AsyncSession,
    *,
    trip_id: UUID,
    quarantine_id: UUID,
    admin_user_id: UUID,
    note: str,
    settings: Settings,
) -> QuarantineApplyResult:
    """Insert a quarantined batch's pings as live evidence (audited).

    Money is deliberately NOT recomputed here: payout_v2 is write-once and the
    corrective path is the admin recompute-day tool (§16.1). The result names
    the affected Africa/Lagos days so the admin can run it per day.

    Apply is allowed only AFTER the trip's initial payout calculation exists:
    a sealed-but-not-yet-processed trip would otherwise silently include the
    applied pings in its first (write-once) computation, making initial money
    depend on admin timing instead of flowing through recompute-day.
    """
    quarantine, trip = await get_quarantined_batch_for_review(
        session, trip_id=trip_id, quarantine_id=quarantine_id
    )
    calculation_exists = await session.scalar(
        select(PayoutCalculation.id)
        .where(PayoutCalculation.trip_session_id == trip.id)
        .limit(1)
    )
    if calculation_exists is None:
        raise AppError(
            "QUARANTINE_APPLY_BLOCKED",
            "The trip's initial payout has not been computed yet — wait for the"
            " worker to process the sealed trip, then apply and run recompute-day",
            status_code=status.HTTP_409_CONFLICT,
        )
    payload = LocationPingBatchCreate(
        idempotency_key=quarantine.idempotency_key,
        pings=quarantine.payload.get("pings", []),
        metadata=quarantine.payload.get("metadata") or {},
    )
    ensure_ping_batch_size(payload, settings)
    now = utc_now()
    for ping in payload.pings:
        ensure_ping_bounds(trip=trip, ping=ping, now=now, settings=settings)

    batch = LocationPingBatch(
        trip_session_id=trip.id,
        idempotency_key=quarantine.idempotency_key,
        payload_hash=quarantine.payload_hash,
        pings_accepted=len(payload.pings),
        received_at=quarantine.received_at,
        batch_metadata=dict(payload.metadata),
    )
    session.add(batch)
    await session.flush()
    lagos_days: set[str] = set()
    for ping in payload.pings:
        session.add(
            LocationPing(
                trip_session_id=trip.id,
                batch_id=batch.id,
                recorded_at=ping.recorded_at,
                received_at=now,
                sequence_number=ping.sequence_number,
                latitude=ping.lat,
                longitude=ping.lon,
                accuracy_m=ping.accuracy_m,
                speed_mps=ping.speed_mps,
                heading_degrees=ping.heading_degrees,
                altitude_m=ping.altitude_m,
                geom=point_value(session, lon=ping.lon, lat=ping.lat),
                ping_metadata=ping.metadata,
            )
        )
        lagos_days.add(
            as_aware_utc(ping.recorded_at).astimezone(LAGOS_TZ).date().isoformat()
        )
    quarantine.status = QuarantinedPingBatchStatus.APPLIED.value
    quarantine.resolved_at = now
    quarantine.resolved_by_user_id = admin_user_id
    quarantine.resolution_note = note
    quarantine.applied_batch_id = batch.id
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=admin_user_id,
        action="admin.trip.quarantined_batch.applied",
        entity_type="quarantined_ping_batch",
        entity_id=str(quarantine.id),
        metadata={
            "trip_session_id": str(trip.id),
            "applied_batch_id": str(batch.id),
            "ping_count": quarantine.ping_count,
            "affected_lagos_days": sorted(lagos_days),
            "note": note,
        },
    )
    await session.refresh(quarantine)
    await session.refresh(batch)
    return QuarantineApplyResult(
        quarantine=quarantine,
        batch=batch,
        affected_lagos_days=sorted(lagos_days),
    )


async def discard_quarantined_ping_batch(
    session: AsyncSession,
    *,
    trip_id: UUID,
    quarantine_id: UUID,
    admin_user_id: UUID,
    note: str,
) -> QuarantinedPingBatch:
    quarantine, trip = await get_quarantined_batch_for_review(
        session, trip_id=trip_id, quarantine_id=quarantine_id
    )
    now = utc_now()
    quarantine.status = QuarantinedPingBatchStatus.DISCARDED.value
    quarantine.resolved_at = now
    quarantine.resolved_by_user_id = admin_user_id
    quarantine.resolution_note = note
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=admin_user_id,
        action="admin.trip.quarantined_batch.discarded",
        entity_type="quarantined_ping_batch",
        entity_id=str(quarantine.id),
        metadata={
            "trip_session_id": str(trip.id),
            "ping_count": quarantine.ping_count,
            "note": note,
        },
    )
    await session.refresh(quarantine)
    return quarantine
