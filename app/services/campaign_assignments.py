import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRuleRevision
from app.models.trip_analytics import TripAnalytics, TripAnalyticsStatus
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.campaign_assignments import (
    CampaignAssignmentCancel,
    CampaignAssignmentCreate,
    CampaignAssignmentRecommendation,
    CampaignAssignmentRecommendationComponents,
    CampaignAssignmentTransition,
)
from app.schemas.drivers import normalize_optional_text
from app.services.billing import reserve_assignment_liability
from app.services.campaigns import comparable_campaign_datetime
from app.services.drivers import get_driver_profile_by_user_id
from app.services.payout_eligibility import (
    D22_ROLLING_CONFIRMATION_WINDOWS,
    D22_ROLLING_MAX_DISPLACEMENT_M,
    D22_ROLLING_RELEASE_WINDOWS,
    D22_ROLLING_STRIDE_SECONDS,
    D22_ROLLING_WINDOW_SECONDS,
    STATIONARY_POLICY_V1,
)
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
    database_clock,
)

# FND-07 (RM7): a lost race on either assignment-exclusivity index returns the
# same stable 409 code as the pre-check that guards it, never a 500.
ASSIGNMENT_CONFLICT_ENVELOPES = {
    "uq_campaign_assignments_campaign_vehicle_non_terminal": (
        "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT",
        "A non-terminal assignment already exists for this campaign and vehicle",
    ),
    "uq_campaign_assignments_vehicle_active": (
        "ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE",
        "Another assignment is already active for this vehicle",
    ),
}

NON_TERMINAL_ASSIGNMENT_STATUSES = {
    CampaignAssignmentStatus.OFFERED.value,
    CampaignAssignmentStatus.ACCEPTED.value,
    CampaignAssignmentStatus.ACTIVE.value,
    CampaignAssignmentStatus.DEACTIVATED.value,
}

MATCHING_VERSION = "matching_v1"


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(value: datetime) -> datetime:
    return comparable_campaign_datetime(value)


def ensure_not_expired(campaign: Campaign, now: datetime, *, code: str) -> None:
    if campaign.end_at is not None and as_aware_utc(campaign.end_at) < now:
        raise AppError(
            code,
            "Campaign end_at is in the past",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def get_campaign(session: AsyncSession, campaign_id: UUID) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


async def get_driver_profile(session: AsyncSession, driver_profile_id: UUID) -> DriverProfile:
    driver_profile = await session.get(DriverProfile, driver_profile_id)
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return driver_profile


async def get_vehicle(session: AsyncSession, vehicle_id: UUID) -> Vehicle:
    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return vehicle


async def ensure_no_duplicate_non_terminal_assignment(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    vehicle_id: UUID,
) -> None:
    existing_assignment_id = await session.scalar(
        select(CampaignAssignment.id).where(
            CampaignAssignment.campaign_id == campaign_id,
            CampaignAssignment.vehicle_id == vehicle_id,
            CampaignAssignment.status.in_(NON_TERMINAL_ASSIGNMENT_STATUSES),
        )
    )
    if existing_assignment_id is not None:
        raise AppError(
            "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT",
            "A non-terminal assignment already exists for this campaign and vehicle",
            status_code=status.HTTP_409_CONFLICT,
        )


async def ensure_no_other_active_assignment_for_vehicle(
    session: AsyncSession,
    *,
    vehicle_id: UUID,
    assignment_id: UUID,
) -> None:
    existing_assignment_id = await session.scalar(
        select(CampaignAssignment.id).where(
            CampaignAssignment.vehicle_id == vehicle_id,
            CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value,
            CampaignAssignment.id != assignment_id,
        )
    )
    if existing_assignment_id is not None:
        raise AppError(
            "ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE",
            "Another assignment is already active for this vehicle",
            status_code=status.HTTP_409_CONFLICT,
        )


async def flush_translating_exclusivity_conflict(session: AsyncSession) -> None:
    """Flush, mapping a lost exclusivity race to its stable 409 envelope.

    Any other integrity failure re-raises untouched: unrelated constraint
    violations must stay unexpected (FND-07 acceptance).
    """
    try:
        await session.flush()
    except IntegrityError as exc:
        envelope = ASSIGNMENT_CONFLICT_ENVELOPES.get(integrity_constraint_name(exc) or "")
        if envelope is None:
            raise
        await session.rollback()
        code, message = envelope
        raise AppError(code, message, status_code=status.HTTP_409_CONFLICT) from exc


def ensure_campaign_assignable(campaign: Campaign, now: datetime) -> None:
    if campaign.status not in {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.ACTIVE.value,
        CampaignStatus.PAUSED.value,
    }:
        raise AppError(
            "CAMPAIGN_NOT_ASSIGNABLE",
            "Campaign is not assignable",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    ensure_not_expired(campaign, now, code="CAMPAIGN_EXPIRED")


def ensure_campaign_acceptable(campaign: Campaign, now: datetime) -> None:
    if campaign.status in {CampaignStatus.COMPLETED.value, CampaignStatus.CANCELLED.value}:
        raise AppError(
            "CAMPAIGN_NOT_ACCEPTABLE",
            "Campaign can no longer be accepted",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    ensure_not_expired(campaign, now, code="CAMPAIGN_EXPIRED")


def ensure_campaign_activatable(campaign: Campaign, now: datetime) -> None:
    if campaign.status != CampaignStatus.ACTIVE.value:
        raise AppError(
            "CAMPAIGN_NOT_ACTIVE",
            "Campaign must be active before activation",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if campaign.start_at is not None and as_aware_utc(campaign.start_at) > now:
        raise AppError(
            "CAMPAIGN_NOT_STARTED",
            "Campaign start_at is in the future",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    ensure_not_expired(campaign, now, code="CAMPAIGN_EXPIRED")


def ensure_active_driver_profile(driver_profile: DriverProfile) -> None:
    if driver_profile.onboarding_status != DriverOnboardingStatus.ACTIVE.value:
        raise AppError(
            "DRIVER_PROFILE_NOT_ACTIVE",
            "Driver profile is not active",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def ensure_active_vehicle(vehicle: Vehicle) -> None:
    if vehicle.status != VehicleStatus.ACTIVE.value:
        raise AppError(
            "VEHICLE_NOT_ACTIVE",
            "Vehicle is not active",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def ensure_vehicle_belongs_to_driver(vehicle: Vehicle, driver_profile: DriverProfile) -> None:
    if vehicle.driver_profile_id != driver_profile.id:
        raise AppError(
            "VEHICLE_DRIVER_PROFILE_MISMATCH",
            "Vehicle does not belong to the assigned driver profile",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def create_activation_event(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    actor_user_id: UUID | None,
    event_type: CampaignActivationEventType,
    previous_status: str | None,
    metadata: dict | None,
    occurred_at: datetime,
) -> CampaignActivationEvent:
    event = CampaignActivationEvent(
        assignment_id=assignment.id,
        actor_user_id=actor_user_id,
        event_type=event_type.value,
        previous_status=previous_status,
        new_status=assignment.status,
        occurred_at=occurred_at,
        event_metadata=metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


async def create_campaign_assignment(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    payload: CampaignAssignmentCreate,
) -> CampaignAssignment:
    now = utc_now()
    if payload.recommendation_context is not None:
        await ensure_recommendation_context_current(session, payload=payload, now=now)
    campaign = await get_campaign(session, payload.campaign_id)
    driver_profile = await get_driver_profile(session, payload.driver_profile_id)
    vehicle = await get_vehicle(session, payload.vehicle_id)
    ensure_campaign_assignable(campaign, now)
    ensure_active_driver_profile(driver_profile)
    ensure_active_vehicle(vehicle)
    ensure_vehicle_belongs_to_driver(vehicle, driver_profile)
    await ensure_no_duplicate_non_terminal_assignment(
        session,
        campaign_id=campaign.id,
        vehicle_id=vehicle.id,
    )

    assignment = CampaignAssignment(
        campaign_id=campaign.id,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin_user_id,
        status=CampaignAssignmentStatus.OFFERED.value,
        offered_at=now,
        notes=payload.notes,
        assignment_metadata=payload.metadata,
    )
    session.add(assignment)
    await flush_translating_exclusivity_conflict(session)
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=admin_user_id,
        event_type=CampaignActivationEventType.ASSIGNED,
        previous_status=None,
        metadata=payload.metadata,
        occurred_at=now,
    )
    await session.refresh(assignment)
    return assignment


def normalized_service_city(value: str) -> str:
    """Compare city values case-insensitively after the public trim normalization."""
    normalized = normalize_optional_text(value)
    if normalized is None:
        raise ValueError("service city must be non-empty")
    return normalized.casefold()


def recommendation_fingerprint(
    *,
    campaign: Campaign,
    driver_profile: DriverProfile,
    vehicle: Vehicle,
    service_city: str,
    vehicle_load: int,
    driver_load: int,
    active_tracking_seconds: int,
    latest_computed_at: datetime | None,
) -> str:
    facts = {
        "matching_version": MATCHING_VERSION,
        "campaign_id": str(campaign.id),
        "campaign_status": campaign.status,
        "driver_profile_id": str(driver_profile.id),
        "driver_onboarding_status": driver_profile.onboarding_status,
        "service_city": service_city,
        "vehicle_id": str(vehicle.id),
        "vehicle_status": vehicle.status,
        "vehicle_type": vehicle.vehicle_type,
        "same_campaign_vehicle_non_terminal": False,
        "vehicle_load": vehicle_load,
        "driver_load": driver_load,
        "active_tracking_seconds": active_tracking_seconds,
        "latest_computed_at": latest_computed_at.isoformat() if latest_computed_at else None,
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


async def list_assignment_recommendations(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    service_city: str,
    limit: int,
    offset: int,
    driver_profile_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    now: datetime | None = None,
) -> tuple[list[CampaignAssignmentRecommendation], int]:
    """Read-only, deterministic current-assignment candidates for an admin choice."""
    now = now or utc_now()
    city = normalized_service_city(service_city)
    vehicle_loads = (
        select(
            CampaignAssignment.vehicle_id.label("vehicle_id"),
            func.count().label("vehicle_load"),
        )
        .where(CampaignAssignment.status.in_(NON_TERMINAL_ASSIGNMENT_STATUSES))
        .group_by(CampaignAssignment.vehicle_id)
        .subquery()
    )
    driver_loads = (
        select(
            CampaignAssignment.driver_profile_id.label("driver_profile_id"),
            func.count().label("driver_load"),
        )
        .where(CampaignAssignment.status.in_(NON_TERMINAL_ASSIGNMENT_STATUSES))
        .group_by(CampaignAssignment.driver_profile_id)
        .subquery()
    )
    activity = (
        select(
            TripAnalytics.driver_profile_id.label("driver_profile_id"),
            func.coalesce(func.sum(TripAnalytics.active_tracking_seconds), 0).label(
                "active_tracking_seconds"
            ),
            func.max(TripAnalytics.computed_at).label("latest_computed_at"),
        )
        .where(TripAnalytics.status == TripAnalyticsStatus.COMPUTED.value)
        .group_by(TripAnalytics.driver_profile_id)
        .subquery()
    )
    same_campaign_vehicle_assignment = (
        select(CampaignAssignment.id)
        .where(
            CampaignAssignment.campaign_id == campaign_id,
            CampaignAssignment.vehicle_id == Vehicle.id,
            CampaignAssignment.status.in_(NON_TERMINAL_ASSIGNMENT_STATUSES),
        )
        .exists()
    )
    filters = [
        Campaign.id == campaign_id,
        Campaign.status.in_(
            {
                CampaignStatus.SCHEDULED.value,
                CampaignStatus.ACTIVE.value,
                CampaignStatus.PAUSED.value,
            }
        ),
        (Campaign.end_at.is_(None)) | (Campaign.end_at >= now),
        DriverProfile.onboarding_status == DriverOnboardingStatus.ACTIVE.value,
        func.lower(func.trim(DriverProfile.service_city)) == city,
        Vehicle.status == VehicleStatus.ACTIVE.value,
        Vehicle.vehicle_type == VehicleType.CAR.value,
        ~same_campaign_vehicle_assignment,
    ]
    if driver_profile_id is not None:
        filters.append(DriverProfile.id == driver_profile_id)
    if vehicle_id is not None:
        filters.append(Vehicle.id == vehicle_id)

    vehicle_load = func.coalesce(vehicle_loads.c.vehicle_load, 0)
    driver_load = func.coalesce(driver_loads.c.driver_load, 0)
    active_tracking_seconds = func.coalesce(activity.c.active_tracking_seconds, 0)
    statement = (
        select(
            Campaign,
            DriverProfile,
            User,
            Vehicle,
            vehicle_load.label("vehicle_load"),
            driver_load.label("driver_load"),
            active_tracking_seconds.label("active_tracking_seconds"),
            activity.c.latest_computed_at,
        )
        .select_from(Vehicle)
        .join(DriverProfile, DriverProfile.id == Vehicle.driver_profile_id)
        .join(User, User.id == DriverProfile.user_id)
        .join(Campaign, Campaign.id == campaign_id)
        .outerjoin(vehicle_loads, vehicle_loads.c.vehicle_id == Vehicle.id)
        .outerjoin(driver_loads, driver_loads.c.driver_profile_id == DriverProfile.id)
        .outerjoin(activity, activity.c.driver_profile_id == DriverProfile.id)
        .where(*filters)
    )
    total = int(
        await session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    rows = (
        await session.execute(
            statement.order_by(
                vehicle_load,
                driver_load,
                active_tracking_seconds.desc(),
                activity.c.latest_computed_at.desc().nulls_last(),
                DriverProfile.id,
                Vehicle.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    candidates = []
    for index, row in enumerate(rows, start=offset + 1):
        (
            candidate_campaign,
            driver_profile,
            driver_user,
            vehicle,
            vehicle_count,
            driver_count,
            signal,
            latest,
        ) = row
        candidates.append(
            CampaignAssignmentRecommendation(
                rank=index,
                driver_profile_id=driver_profile.id,
                driver_name=driver_user.full_name,
                vehicle_id=vehicle.id,
                vehicle_plate_number=vehicle.plate_number,
                vehicle_make=vehicle.make,
                vehicle_model=vehicle.model,
                service_city=service_city.strip(),
                vehicle_type=VehicleType.CAR.value,
                matching_version=MATCHING_VERSION,
                fingerprint=recommendation_fingerprint(
                    campaign=candidate_campaign,
                    driver_profile=driver_profile,
                    vehicle=vehicle,
                    service_city=city,
                    vehicle_load=int(vehicle_count),
                    driver_load=int(driver_count),
                    active_tracking_seconds=int(signal),
                    latest_computed_at=latest,
                ),
                components=CampaignAssignmentRecommendationComponents(
                    vehicle_load=int(vehicle_count),
                    driver_load=int(driver_count),
                    active_tracking_seconds=int(signal),
                    latest_computed_at=latest,
                ),
            )
        )
    return candidates, total


async def ensure_recommendation_context_current(
    session: AsyncSession,
    *,
    payload: CampaignAssignmentCreate,
    now: datetime,
) -> None:
    context = payload.recommendation_context
    assert context is not None
    # Serialize the selected facts in the same stable order as the write path.
    # In PostgreSQL, FOR UPDATE also makes concurrent FK-backed assignment or
    # analytics inserts wait, closing the recommendation-check/create window.
    for model, identifier in (
        (Campaign, payload.campaign_id),
        (DriverProfile, payload.driver_profile_id),
        (Vehicle, payload.vehicle_id),
    ):
        locked = await session.scalar(
            select(model).where(model.id == identifier).with_for_update()
        )
        if locked is None:
            raise stale_recommendation_error()
    # Lock every existing row that can enter, leave, or change either aggregate.
    # The parent locks above make concurrent inserts targeting this candidate
    # wait on their foreign-key checks; these row locks cover existing updates.
    await session.execute(
        select(CampaignAssignment.id)
        .where(
            or_(
                CampaignAssignment.driver_profile_id == payload.driver_profile_id,
                CampaignAssignment.vehicle_id == payload.vehicle_id,
            )
        )
        .order_by(CampaignAssignment.id)
        .with_for_update()
    )
    await session.execute(
        select(TripAnalytics.id)
        .where(TripAnalytics.driver_profile_id == payload.driver_profile_id)
        .order_by(TripAnalytics.id)
        .with_for_update()
    )
    candidates, _ = await list_assignment_recommendations(
        session,
        campaign_id=payload.campaign_id,
        service_city=context.service_city,
        limit=1,
        offset=0,
        driver_profile_id=payload.driver_profile_id,
        vehicle_id=payload.vehicle_id,
        now=now,
    )
    if len(candidates) != 1 or candidates[0].fingerprint != context.fingerprint:
        raise stale_recommendation_error()


def stale_recommendation_error() -> AppError:
    return AppError(
        "STALE_RECOMMENDATION",
        "The selected recommendation has changed; refresh ranked candidates before offering.",
        status_code=status.HTTP_409_CONFLICT,
    )


def assignment_not_found() -> AppError:
    return AppError(
        "CAMPAIGN_ASSIGNMENT_NOT_FOUND",
        "Campaign assignment was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


async def get_admin_assignment(
    session: AsyncSession,
    assignment_id: UUID,
) -> CampaignAssignment:
    assignment = await session.get(CampaignAssignment, assignment_id)
    if assignment is None:
        raise assignment_not_found()
    return assignment


async def get_driver_profile_for_user(session: AsyncSession, user_id: UUID) -> DriverProfile:
    driver_profile = await get_driver_profile_by_user_id(session, user_id)
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return driver_profile


async def get_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
) -> CampaignAssignment:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    result = await session.execute(
        select(CampaignAssignment).where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise assignment_not_found()
    return assignment


async def list_admin_assignments(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    assignment_status: str | None,
    campaign_id: UUID | None,
    driver_profile_id: UUID | None,
    vehicle_id: UUID | None,
) -> tuple[list[CampaignAssignment], int]:
    filters = []
    if assignment_status is not None:
        filters.append(CampaignAssignment.status == assignment_status)
    if campaign_id is not None:
        filters.append(CampaignAssignment.campaign_id == campaign_id)
    if driver_profile_id is not None:
        filters.append(CampaignAssignment.driver_profile_id == driver_profile_id)
    if vehicle_id is not None:
        filters.append(CampaignAssignment.vehicle_id == vehicle_id)

    statement = select(CampaignAssignment)
    count_statement = select(func.count()).select_from(CampaignAssignment)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignAssignment.created_at.desc(), CampaignAssignment.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_driver_assignments(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
    assignment_status: str | None,
) -> tuple[list[CampaignAssignment], int]:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    filters = [CampaignAssignment.driver_profile_id == driver_profile.id]
    if assignment_status is not None:
        filters.append(CampaignAssignment.status == assignment_status)

    statement = select(CampaignAssignment)
    count_statement = select(func.count()).select_from(CampaignAssignment)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignAssignment.created_at.desc(), CampaignAssignment.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_assignment_events(
    session: AsyncSession,
    assignment_id: UUID,
) -> list[CampaignActivationEvent]:
    result = await session.execute(
        select(CampaignActivationEvent)
        .where(CampaignActivationEvent.assignment_id == assignment_id)
        .order_by(CampaignActivationEvent.occurred_at, CampaignActivationEvent.id)
    )
    return list(result.scalars().all())


def frozen_zone_geometry_hash(rows: list[tuple]) -> str:
    """Deterministic hash of a frozen zone set's sorted (id, geometry) pairs."""
    return hashlib.sha256("\n".join(f"{row[0]}:{row[1]}" for row in rows).encode()).hexdigest()


# Backwards-compatible name retained for the B2 tests/imports.
premium_zone_geometry_hash = frozen_zone_geometry_hash


def resolved_eligibility_snapshot(settings: Settings, overlay: dict | None) -> dict:
    """Freeze every classifier value effective at acceptance.

    Existing common values retain their configured fallbacks. D22's rolling
    values are fixed policy defaults: only an effective revision overlay may
    tune them for later acceptances.
    """
    overlay = overlay or {}

    def value(key: str, fallback: float) -> float:
        return float(overlay.get(key, fallback))

    return {
        "stationary_radius_m": value(
            "stationary_radius_m", settings.payout_eligibility_stationary_radius_m
        ),
        "stationary_window_seconds": int(
            value(
                "stationary_window_min",
                settings.payout_eligibility_stationary_window_min,
            )
            * 60
        ),
        "stationary_grace_seconds": int(
            value(
                "stationary_grace_min",
                settings.payout_eligibility_stationary_grace_min,
            )
            * 60
        ),
        "max_accuracy_m": value("max_accuracy_m", settings.payout_eligibility_max_accuracy_m),
        "teleport_kmh": value("teleport_kmh", settings.payout_eligibility_teleport_kmh),
        "max_ping_gap_seconds": int(
            value(
                "max_ping_gap_seconds",
                settings.payout_eligibility_max_ping_gap_seconds,
            )
        ),
        "rolling_window_seconds": int(
            value(
                "rolling_window_seconds",
                D22_ROLLING_WINDOW_SECONDS,
            )
        ),
        "rolling_stride_seconds": int(
            value(
                "rolling_stride_seconds",
                D22_ROLLING_STRIDE_SECONDS,
            )
        ),
        "rolling_max_displacement_m": value(
            "rolling_max_displacement_m",
            D22_ROLLING_MAX_DISPLACEMENT_M,
        ),
        "rolling_confirmation_windows": int(
            value(
                "rolling_confirmation_windows",
                D22_ROLLING_CONFIRMATION_WINDOWS,
            )
        ),
        "rolling_release_windows": int(
            value(
                "rolling_release_windows",
                D22_ROLLING_RELEASE_WINDOWS,
            )
        ),
    }


async def create_rule_binding_for_accept(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    now: datetime,
    campaign: Campaign,
    settings: Settings,
) -> AssignmentRuleBinding | None:
    """Freeze the campaign's effective revision onto the accepted assignment
    (MNY-06B). Resolved at the accept transaction's snapshot read (PR10): the
    revision with the greatest effective_from <= now. A campaign without an
    effective revision gets NO binding — the assignment stays payout_v2."""
    revision = await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(
            CampaignPayoutRuleRevision.campaign_id == assignment.campaign_id,
            CampaignPayoutRuleRevision.effective_from <= now,
        )
        .order_by(CampaignPayoutRuleRevision.effective_from.desc())
        .limit(1)
    )
    if revision is None:
        return None
    premium_zone_rows = (
        await session.execute(
            select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
            .where(
                CampaignZone.campaign_id == assignment.campaign_id,
                CampaignZone.zone_type == CampaignZoneType.TARGET.value,
            )
            .order_by(CampaignZone.id)
        )
    ).all()
    exclusion_zone_rows = (
        await session.execute(
            select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
            .where(
                CampaignZone.campaign_id == assignment.campaign_id,
                CampaignZone.zone_type == CampaignZoneType.EXCLUSION.value,
            )
            .order_by(CampaignZone.id)
        )
    ).all()
    resolved_params = resolved_eligibility_snapshot(settings, revision.eligibility_params)
    binding = AssignmentRuleBinding(
        assignment_id=assignment.id,
        revision_id=revision.id,
        hourly_rate_naira=revision.hourly_rate_naira,
        premium_hourly_rate_naira=revision.premium_hourly_rate_naira,
        daily_payable_hours_cap=revision.daily_payable_hours_cap,
        eligibility_params=revision.eligibility_params or {},
        resolved_eligibility_params=resolved_params,
        formula_version=revision.formula_version,
        premium_zone_ids=[str(row[0]) for row in premium_zone_rows],
        premium_zone_geometry_hash=frozen_zone_geometry_hash(premium_zone_rows),
        premium_zone_geometry_wkts=[str(row[1]) for row in premium_zone_rows],
        exclusion_zone_ids=[str(row[0]) for row in exclusion_zone_rows],
        exclusion_zone_geometry_hash=frozen_zone_geometry_hash(exclusion_zone_rows),
        exclusion_zone_geometry_wkts=[str(row[1]) for row in exclusion_zone_rows],
        stationary_policy_marker=STATIONARY_POLICY_V1,
        campaign_window_start_at=campaign.start_at,
        campaign_window_end_at=campaign.end_at,
        campaign_window_frozen=True,
        bound_at=now,
    )
    session.add(binding)
    await session.flush()
    return binding


async def accept_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    settings: Settings,
) -> CampaignAssignment:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    if campaign_id is None:
        raise assignment_not_found()
    # One campaign-scoped authority boundary: publication and acceptance
    # cannot observe different clocks or interleave their revision reads.
    await acquire_campaign_terms_lock(session, campaign_id)
    now = await database_clock(session)
    # PR2: lock the assignment row BEFORE the status check so a concurrent
    # accept serializes here — the loser re-reads ACCEPTED and gets the
    # existing deterministic 400, and the binding insert below can never hit
    # uq(assignment_id) from a live race.
    assignment = await session.scalar(
        select(CampaignAssignment)
        .where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise assignment_not_found()
    if assignment.status != CampaignAssignmentStatus.OFFERED.value:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only offered assignments can be accepted",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    campaign = await get_campaign(session, assignment.campaign_id)
    ensure_campaign_acceptable(campaign, now)
    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.ACCEPTED.value
    assignment.accepted_at = now
    await session.flush()
    binding = await create_rule_binding_for_accept(
        session,
        assignment=assignment,
        now=now,
        campaign=campaign,
        settings=settings,
    )
    if (
        binding is not None
        and binding.campaign_window_start_at is not None
        and binding.campaign_window_end_at is not None
    ):
        await reserve_assignment_liability(
            session,
            assignment_id=assignment.id,
            actor_user_id=user_id,
            require_admin=False,
        )
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=user_id,
        event_type=CampaignActivationEventType.ACCEPTED,
        previous_status=previous_status,
        metadata=payload.metadata,
        occurred_at=now,
    )
    await session.refresh(assignment)
    return assignment


async def activate_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
) -> CampaignAssignment:
    now = utc_now()
    assignment = await get_driver_assignment(session, user_id=user_id, assignment_id=assignment_id)
    if assignment.status not in {
        CampaignAssignmentStatus.ACCEPTED.value,
        CampaignAssignmentStatus.DEACTIVATED.value,
    }:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only accepted or deactivated assignments can be activated",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    campaign = await get_campaign(session, assignment.campaign_id)
    driver_profile = await get_driver_profile(session, assignment.driver_profile_id)
    vehicle = await get_vehicle(session, assignment.vehicle_id)
    ensure_campaign_activatable(campaign, now)
    ensure_active_driver_profile(driver_profile)
    ensure_active_vehicle(vehicle)
    ensure_vehicle_belongs_to_driver(vehicle, driver_profile)
    await ensure_no_other_active_assignment_for_vehicle(
        session,
        vehicle_id=vehicle.id,
        assignment_id=assignment.id,
    )

    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.ACTIVE.value
    assignment.activated_at = now
    await flush_translating_exclusivity_conflict(session)
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=user_id,
        event_type=CampaignActivationEventType.ACTIVATED,
        previous_status=previous_status,
        metadata=payload.metadata,
        occurred_at=now,
    )
    await session.refresh(assignment)
    return assignment


async def deactivate_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
) -> CampaignAssignment:
    now = utc_now()
    assignment = await get_driver_assignment(session, user_id=user_id, assignment_id=assignment_id)
    if assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only active assignments can be deactivated",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.DEACTIVATED.value
    assignment.deactivated_at = now
    await session.flush()
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=user_id,
        event_type=CampaignActivationEventType.DEACTIVATED,
        previous_status=previous_status,
        metadata=payload.metadata,
        occurred_at=now,
    )
    await session.refresh(assignment)
    return assignment


async def cancel_admin_assignment(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentCancel,
) -> CampaignAssignment:
    now = utc_now()
    assignment = await get_admin_assignment(session, assignment_id)
    if assignment.status in {
        CampaignAssignmentStatus.CANCELLED.value,
        CampaignAssignmentStatus.COMPLETED.value,
    }:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Cancelled or completed assignments cannot be cancelled",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.CANCELLED.value
    assignment.cancelled_at = now
    event_metadata = dict(payload.metadata)
    if payload.reason is not None:
        event_metadata["reason"] = payload.reason
    await session.flush()
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=admin_user_id,
        event_type=CampaignActivationEventType.CANCELLED,
        previous_status=previous_status,
        metadata=event_metadata,
        occurred_at=now,
    )
    await session.refresh(assignment)
    return assignment


async def get_current_active_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> CampaignAssignment | None:
    driver_profile = await get_driver_profile_for_user(session, user_id)
    result = await session.execute(
        select(CampaignAssignment).where(
            CampaignAssignment.driver_profile_id == driver_profile.id,
            CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value,
        )
    )
    assignments = list(result.scalars().all())
    if len(assignments) > 1:
        raise AppError(
            "MULTIPLE_ACTIVE_ASSIGNMENTS",
            "Multiple active assignments were found for the current driver",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if not assignments:
        return None
    return assignments[0]


async def get_assignment_context(
    session: AsyncSession,
    assignment: CampaignAssignment,
) -> tuple[Campaign | None, DriverProfile | None, Vehicle | None, User | None]:
    campaign = await session.get(Campaign, assignment.campaign_id)
    driver_profile = await session.get(DriverProfile, assignment.driver_profile_id)
    vehicle = await session.get(Vehicle, assignment.vehicle_id)
    assigned_by = await session.get(User, assignment.assigned_by_user_id)
    return campaign, driver_profile, vehicle, assigned_by
