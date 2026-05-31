import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverProfile
from app.models.trip import LocationPing, LocationPingBatch, TripSession, TripSessionStatus
from app.models.vehicle import Vehicle
from app.schemas.trips import (
    LocationPingBatchCreate,
    LocationPingCreate,
    TripEndRequest,
    TripStartRequest,
)
from app.services.campaign_assignments import (
    as_aware_utc,
    ensure_active_driver_profile,
    ensure_active_vehicle,
    ensure_vehicle_belongs_to_driver,
    get_driver_profile_for_user,
)


@dataclass(frozen=True)
class TripSummary:
    trip: TripSession
    ping_count: int
    first_ping_at: datetime | None
    last_ping_at: datetime | None


@dataclass(frozen=True)
class PingBatchResult:
    batch: LocationPingBatch
    duplicate: bool


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
) -> TripSession:
    now = utc_now()
    driver_profile, assignment = await get_driver_assignment_for_trip_start(
        session,
        user_id=user_id,
        assignment_id=payload.assignment_id,
    )
    campaign = await session.get(Campaign, assignment.campaign_id)
    vehicle = await session.get(Vehicle, assignment.vehicle_id)
    if campaign is None or vehicle is None:
        raise AppError(
            "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
            "Campaign assignment was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    ensure_assignment_active(assignment)
    ensure_campaign_active_for_trip(campaign, now)
    ensure_active_driver_profile(driver_profile)
    ensure_active_vehicle(vehicle)
    ensure_vehicle_belongs_to_driver(vehicle, driver_profile)
    await ensure_no_active_trip_for_driver_or_vehicle(
        session,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
    )

    trip = TripSession(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=user_id,
        status=TripSessionStatus.ACTIVE.value,
        started_at=now,
        trip_metadata=payload.metadata,
    )
    session.add(trip)
    await session.flush()
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


async def end_driver_trip(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
    payload: TripEndRequest,
) -> TripSession:
    trip = await get_driver_trip(session, user_id=user_id, trip_id=trip_id)
    if trip.status != TripSessionStatus.ACTIVE.value:
        raise AppError(
            "TRIP_ALREADY_ENDED",
            "Trip is already ended",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    now = utc_now()
    trip.status = TripSessionStatus.ENDED.value
    trip.ended_at = now
    trip.end_reason = payload.end_reason
    trip.updated_at = now
    await session.flush()
    await session.refresh(trip)
    return trip


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
    if trip.status != TripSessionStatus.ACTIVE.value:
        raise AppError(
            "TRIP_NOT_ACTIVE",
            "Location pings can only be accepted for an active trip",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    assignment = await session.get(CampaignAssignment, trip.assignment_id)
    if assignment is None:
        raise trip_not_found()
    ensure_assignment_active(assignment)

    digest = payload_hash(payload)
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
    for ping in payload.pings:
        ensure_ping_bounds(trip=trip, ping=ping, now=received_at, settings=settings)

    batch = LocationPingBatch(
        trip_session_id=trip.id,
        idempotency_key=payload.idempotency_key,
        payload_hash=digest,
        pings_accepted=len(payload.pings),
        received_at=received_at,
        batch_metadata=payload.metadata,
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
    return PingBatchResult(batch=batch, duplicate=False)
