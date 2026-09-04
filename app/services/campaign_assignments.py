import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.billing import CampaignLiabilityReservation, ProductionStart
from app.models.campaign import (
    Campaign,
    CampaignCreative,
    CampaignReviewEvent,
    CampaignStatus,
    CreativeReviewEvent,
    CreativeStatus,
)
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRuleRevision
from app.models.stored_file import FilePurpose, FileScanStatus
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
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing import (
    assert_campaign_production_authorized,
    assert_new_work_authorized,
    reserve_assignment_liability,
)
from app.services.campaigns import comparable_campaign_datetime
from app.services.drivers import get_driver_profile_by_user_id
from app.services.installation_evidence import ensure_current_approved_installation_evidence
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
from app.services.vehicle_onboarding import (
    acquire_work_eligibility_lock,
    ensure_current_driver_vehicle_eligibility,
)

# FND-07 (RM7): a lost race on any assignment-exclusivity index returns the
# same stable 409 code as the pre-check that guards it, never a 500.
ASSIGNMENT_CONFLICT_ENVELOPES = {
    "uq_campaign_assignments_driver_active": (
        "ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER",
        "Another assignment is already active for this driver",
    ),
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

TERMINAL_DECISION_STATUSES = {
    CampaignAssignmentStatus.ACCEPTED.value,
    CampaignAssignmentStatus.DECLINED.value,
    CampaignAssignmentStatus.EXPIRED.value,
}

OFFER_TERMS_VERSION = "campaign-assignment-offer-v1"
PAYOUT_V3 = "payout_v3"
ACTIVATION_SNAPSHOT_VERSION = "assignment-activation-v1"


class OfferExpiredError(AppError):
    """A due offer was newly materialized in the caller's transaction."""

    def __init__(self, message: str) -> None:
        super().__init__(
            "OFFER_EXPIRED",
            message,
            status_code=status.HTTP_409_CONFLICT,
        )


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


async def ensure_no_other_active_assignment_for_driver(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    assignment_id: UUID,
) -> None:
    existing_assignment_id = await session.scalar(
        select(CampaignAssignment.id).where(
            CampaignAssignment.driver_profile_id == driver_profile_id,
            CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value,
            CampaignAssignment.id != assignment_id,
        )
    )
    if existing_assignment_id is not None:
        raise AppError(
            "ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER",
            "Another assignment is already active for this driver",
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


async def ensure_campaign_review_approved(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignReviewEvent:
    """Require the built admin campaign-review authority before activation."""
    approved = await session.scalar(
        select(CampaignReviewEvent)
        .where(
            CampaignReviewEvent.campaign_id == campaign_id,
            CampaignReviewEvent.new_status == CampaignStatus.APPROVED.value,
        )
        .order_by(CampaignReviewEvent.created_at.desc(), CampaignReviewEvent.id.desc())
        .limit(1)
        .with_for_update()
    )
    if approved is None:
        raise AppError(
            "CAMPAIGN_REVIEW_APPROVAL_REQUIRED",
            "An approved campaign review is required before assignment activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    return approved


def activation_snapshot_digest(snapshot: dict[str, object]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _activation_snapshot_error() -> AppError:
    return AppError(
        "VALID_ACTIVATION_SNAPSHOT_REQUIRED",
        "A valid immutable admin activation snapshot is required before earning can start",
        status_code=status.HTTP_409_CONFLICT,
    )


async def ensure_current_activation_snapshot(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    lock: bool = False,
) -> dict[str, object]:
    query = (
        select(CampaignActivationEvent)
        .where(
            CampaignActivationEvent.assignment_id == assignment.id,
            CampaignActivationEvent.event_type == CampaignActivationEventType.ACTIVATED.value,
        )
        .order_by(
            CampaignActivationEvent.occurred_at.desc(),
            CampaignActivationEvent.id.desc(),
        )
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    event = await session.scalar(query)
    if event is None or assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        raise _activation_snapshot_error()
    snapshot = event.event_metadata.get("activation_snapshot")
    digest = event.event_metadata.get("activation_snapshot_sha256")
    if not isinstance(snapshot, dict) or not isinstance(digest, str):
        raise _activation_snapshot_error()
    if activation_snapshot_digest(snapshot) != digest:
        raise _activation_snapshot_error()
    activated_at = assignment.activated_at
    expected = {
        "version": ACTIVATION_SNAPSHOT_VERSION,
        "assignment_id": str(assignment.id),
        "campaign_id": str(assignment.campaign_id),
        "driver_profile_id": str(assignment.driver_profile_id),
        "vehicle_id": str(assignment.vehicle_id),
        "offer_terms_sha256": assignment.offer_terms_sha256,
        "activated_at": (
            as_aware_utc(activated_at).isoformat() if activated_at is not None else None
        ),
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise _activation_snapshot_error()
    if event.offer_terms_sha256 != assignment.offer_terms_sha256:
        raise _activation_snapshot_error()
    return snapshot


async def activation_production_start(
    session: AsyncSession,
    *,
    campaign_id: UUID,
) -> ProductionStart:
    production_start = await session.scalar(
        select(ProductionStart)
        .where(ProductionStart.campaign_id == campaign_id)
        .with_for_update()
    )
    if production_start is None:
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "Campaign activation requires a recorded production start",
            status_code=status.HTTP_409_CONFLICT,
        )
    return production_start


def ensure_campaign_activatable(campaign: Campaign, now: datetime) -> None:
    if campaign.status not in {CampaignStatus.SCHEDULED.value, CampaignStatus.ACTIVE.value}:
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
    event_metadata = dict(metadata or {})
    evidence_sha256 = None
    if event_type in {
        CampaignActivationEventType.ASSIGNED,
        CampaignActivationEventType.ACCEPTED,
        CampaignActivationEventType.DECLINED,
        CampaignActivationEventType.EXPIRED,
        CampaignActivationEventType.ACTIVATED,
    }:
        evidence_sha256 = assignment.offer_terms_sha256
        if evidence_sha256 is not None:
            event_metadata.setdefault("offer_terms_sha256", evidence_sha256)
    event = CampaignActivationEvent(
        assignment_id=assignment.id,
        actor_user_id=actor_user_id,
        event_type=event_type.value,
        previous_status=previous_status,
        new_status=assignment.status,
        occurred_at=occurred_at,
        event_metadata=event_metadata,
        offer_terms_sha256=evidence_sha256,
    )
    session.add(event)
    await session.flush()
    return event


async def create_campaign_assignment(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    payload: CampaignAssignmentCreate,
    settings: Settings | None = None,
) -> CampaignAssignment:
    settings = settings or get_settings()
    campaign_id = getattr(payload, "campaign_id", None)
    if isinstance(campaign_id, UUID):
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, admin_user_id)
    await acquire_work_eligibility_lock(
        session,
        driver_profile_id=payload.driver_profile_id,
        vehicle_id=payload.vehicle_id,
    )
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == payload.campaign_id)
        .with_for_update()
    )
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    now = await database_clock(session)
    if payload.recommendation_context is not None:
        await ensure_recommendation_context_current(session, payload=payload, now=now)
    driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == payload.driver_profile_id)
        .with_for_update()
    )
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == payload.vehicle_id).with_for_update()
    )
    if vehicle is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    schedule_campaign = campaign.status == CampaignStatus.APPROVED.value
    if not schedule_campaign:
        ensure_campaign_assignable(campaign, now)
    if campaign.start_at is None or campaign.end_at is None:
        raise AppError(
            "COMPLETE_CAMPAIGN_WINDOW_REQUIRED",
            "A campaign start and end are required before offering an assignment",
            status_code=status.HTTP_409_CONFLICT,
        )
    expires_at = as_aware_utc(payload.expires_at)
    if expires_at <= now or expires_at > as_aware_utc(campaign.end_at):
        raise AppError(
            "INVALID_OFFER_EXPIRY",
            "Offer expiry must be after the current database time and within the campaign window",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
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
    await ensure_no_duplicate_non_terminal_assignment(
        session,
        campaign_id=campaign.id,
        vehicle_id=vehicle.id,
    )
    terms, terms_sha256 = await build_offer_terms(
        session,
        campaign=campaign,
        driver_profile=driver_profile,
        now=now,
        creative_id=payload.creative_id,
        settings=settings,
    )

    assignment = CampaignAssignment(
        campaign_id=campaign.id,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin_user_id,
        status=CampaignAssignmentStatus.OFFERED.value,
        offered_at=now,
        expires_at=expires_at,
        notes=payload.notes,
        assignment_metadata=payload.metadata,
        offer_terms=terms,
        offer_terms_sha256=terms_sha256,
    )
    session.add(assignment)
    await flush_translating_exclusivity_conflict(session)
    if schedule_campaign:
        campaign.status = CampaignStatus.SCHEDULED.value
        await create_audit_event(
            session,
            actor_user_id=admin_user_id,
            action="admin.campaign.scheduled",
            entity_type="campaign",
            entity_id=str(campaign.id),
            metadata={
                "status_before": CampaignStatus.APPROVED.value,
                "status_after": campaign.status,
                "assignment_id": str(assignment.id),
            },
        )
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=admin_user_id,
        event_type=CampaignActivationEventType.ASSIGNED,
        previous_status=None,
        metadata=payload.metadata,
        occurred_at=now,
    )
    from app.models.notification import NotificationType
    from app.services.notifications import create_driver_business_notification

    await create_driver_business_notification(
        session,
        driver_profile_id=assignment.driver_profile_id,
        type_key=NotificationType.ASSIGNMENT_OFFERED,
        event_key=f"assignment:offered:v1:{assignment.id}",
        payload={
            "assignment_id": str(assignment.id),
            "campaign_id": str(assignment.campaign_id),
        },
        manual_contact_purpose="campaign_assignment_offer",
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
    total = int(await session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
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
        locked = await session.scalar(select(model).where(model.id == identifier).with_for_update())
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
    query_now = await database_clock(session)
    due_offer = (
        (CampaignAssignment.status == CampaignAssignmentStatus.OFFERED.value)
        & CampaignAssignment.expires_at.is_not(None)
        & (CampaignAssignment.expires_at <= query_now)
    )
    filters = [~due_offer]
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
    query_now = await database_clock(session)
    due_offer = (
        (CampaignAssignment.status == CampaignAssignmentStatus.OFFERED.value)
        & CampaignAssignment.expires_at.is_not(None)
        & (CampaignAssignment.expires_at <= query_now)
    )
    filters = [CampaignAssignment.driver_profile_id == driver_profile.id, ~due_offer]
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


async def expire_assignment_if_due(
    session: AsyncSession,
    assignment: CampaignAssignment,
    *,
    now: datetime,
) -> bool:
    """Materialize one offer expiry after its campaign/row locks are held."""
    if (
        assignment.status != CampaignAssignmentStatus.OFFERED.value
        or assignment.expires_at is None
        or as_aware_utc(assignment.expires_at) > now
    ):
        return False
    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.EXPIRED.value
    assignment.expired_at = now
    await session.flush()
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=None,
        event_type=CampaignActivationEventType.EXPIRED,
        previous_status=previous_status,
        metadata={"reason": "offer_expired"},
        occurred_at=now,
    )
    return True


async def expire_assignment_offer(
    session: AsyncSession,
    assignment_id: UUID,
) -> bool:
    """Lock and lazily expire one offer using the shared campaign authority."""
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is None:
        return False
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        return False
    assignment = await session.scalar(
        select(CampaignAssignment)
        .where(CampaignAssignment.id == assignment_id)
        .with_for_update()
    )
    if assignment is None:
        return False
    now = await database_clock(session)
    return await expire_assignment_if_due(session, assignment, now=now)


async def expire_due_assignment_offers(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> int:
    """Idempotently sweep due offers in deterministic campaign/assignment order."""
    now = await database_clock(session)
    ids = (
        await session.execute(
            select(CampaignAssignment.id)
            .where(
                CampaignAssignment.status == CampaignAssignmentStatus.OFFERED.value,
                CampaignAssignment.expires_at.is_not(None),
                CampaignAssignment.expires_at <= now,
            )
            .order_by(CampaignAssignment.campaign_id, CampaignAssignment.id)
            .limit(limit)
        )
    ).scalars().all()
    expired = 0
    for assignment_id in ids:
        if await expire_assignment_offer(session, assignment_id):
            expired += 1
    return expired


def frozen_zone_geometry_hash(rows: list[tuple]) -> str:
    """Deterministic hash of a frozen zone set's sorted (id, geometry) pairs."""
    canonical_rows = sorted((str(row[0]), str(row[1])) for row in rows)
    return hashlib.sha256(
        json.dumps(canonical_rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def canonical_offer_terms_sha256(terms: dict) -> str:
    encoded = json.dumps(
        terms,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _creative_content_identity(creative: CampaignCreative) -> dict[str, object]:
    if not creative.checksum or not creative.checksum.strip():
        raise AppError(
            "CREATIVE_CONTENT_IDENTITY_REQUIRED",
            "A ready creative must include a content checksum before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    if creative.updated_at is None:
        raise AppError(
            "CREATIVE_VERSION_REQUIRED",
            "A ready creative must include a persisted version before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    content = {
        "checksum": creative.checksum.strip(),
        "stored_file_id": str(creative.stored_file_id),
        "mime_type": creative.mime_type,
        "width_px": creative.width_px,
        "height_px": creative.height_px,
        "duration_seconds": creative.duration_seconds,
    }
    content["content_sha256"] = canonical_offer_terms_sha256(content)
    return content


def _creative_snapshot(creative: CampaignCreative) -> dict[str, object]:
    content = _creative_content_identity(creative)
    return {
        "id": str(creative.id),
        "name": creative.name,
        "creative_type": creative.creative_type,
        "placement": creative.placement,
        "checksum": creative.checksum.strip() if creative.checksum else None,
        "version": as_aware_utc(creative.updated_at).isoformat()
        if creative.updated_at is not None
        else None,
        "content_identity": content,
        "metadata": creative.creative_metadata or {},
    }


def _valid_frozen_currency(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 3
        and value.isascii()
        and value.isalpha()
        and value == value.upper()
    )


def _offer_terms_complete(terms: dict | None, terms_sha256: str | None) -> bool:
    if terms is None or terms_sha256 is None:
        return False
    required = {
        "offer_terms_version",
        "currency",
        "campaign_window_start_at",
        "campaign_window_end_at",
        "service_area",
        "branding",
        "creative",
        "payout",
        "zones",
        "eligibility",
    }
    if not isinstance(terms, dict) or not required.issubset(terms):
        return False
    if canonical_offer_terms_sha256(terms) != terms_sha256:
        return False
    if terms.get("offer_terms_version") != OFFER_TERMS_VERSION:
        return False
    currency = terms.get("currency")
    if not _valid_frozen_currency(currency):
        return False
    service_area = terms.get("service_area")
    branding = terms.get("branding")
    if (
        not isinstance(service_area, dict)
        or not str(service_area.get("city", "")).strip()
        or not isinstance(branding, dict)
        or not branding.get("campaign_id")
        or not branding.get("organization_id")
        or not branding.get("version")
    ):
        return False
    try:
        window_start = datetime.fromisoformat(str(terms["campaign_window_start_at"]))
        window_end = datetime.fromisoformat(str(terms["campaign_window_end_at"]))
        if as_aware_utc(window_start) >= as_aware_utc(window_end):
            return False
    except (TypeError, ValueError):
        return False
    payout = terms.get("payout")
    if not isinstance(payout, dict):
        return False
    payout_currency = payout.get("currency")
    if (
        payout.get("formula_version") != PAYOUT_V3
        or not payout.get("revision_id")
        or not payout.get("payout_rule_id")
        or not payout.get("effective_from")
        or not isinstance(payout.get("eligibility_params"), dict)
        or (
            "currency" in payout
            and (
                not _valid_frozen_currency(payout_currency)
                or payout_currency != currency
            )
        )
    ):
        return False
    try:
        UUID(str(payout["revision_id"]))
        UUID(str(payout["payout_rule_id"]))
        rates = [
            Decimal(str(payout["hourly_rate_naira"])),
            Decimal(str(payout["premium_hourly_rate_naira"])),
            Decimal(str(payout["daily_payable_hours_cap"])),
        ]
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return False
    if (
        not all(rate.is_finite() and rate >= 0 for rate in rates[:2])
        or not rates[2].is_finite()
        or rates[2] <= 0
    ):
        return False
    zones = terms.get("zones")
    if not isinstance(zones, dict) or zones.get("semantics") != (
        "target_zones_are_premium; exclusions_are_unpaid"
    ):
        return False

    def valid_zone_rows(value: object, *, required_rows: bool) -> bool:
        if not isinstance(value, list) or (required_rows and not value):
            return False
        return all(
            isinstance(row, dict)
            and str(row.get("id", "")).strip()
            and str(row.get("wkt", "")).strip()
            and str(row.get("wkt")) != "None"
            for row in value
        )

    if not valid_zone_rows(zones.get("target"), required_rows=True):
        return False
    if not valid_zone_rows(zones.get("premium"), required_rows=True):
        return False
    if not valid_zone_rows(zones.get("exclusion"), required_rows=False):
        return False
    creative = terms.get("creative")
    if not isinstance(creative, dict):
        return False
    content_identity = creative.get("content_identity")
    if (
        not creative.get("id")
        or not creative.get("checksum")
        or not creative.get("version")
        or not isinstance(content_identity, dict)
        or content_identity.get("checksum") != creative.get("checksum")
        or not content_identity.get("content_sha256")
    ):
        return False
    eligibility = terms.get("eligibility")
    return bool(
        isinstance(eligibility, dict)
        and eligibility.get("stationary_policy_marker") == STATIONARY_POLICY_V1
    )


async def build_offer_terms(
    session: AsyncSession,
    *,
    campaign: Campaign,
    driver_profile: DriverProfile,
    now: datetime,
    creative_id: UUID,
    settings: Settings,
) -> tuple[dict, str]:
    """Freeze the exact terms displayed to the driver before an offer exists."""
    creative = await session.scalar(
        select(CampaignCreative)
        .where(CampaignCreative.id == creative_id, CampaignCreative.campaign_id == campaign.id)
        .with_for_update()
    )
    if creative is None or creative.status != CreativeStatus.APPROVED.value:
        raise AppError(
            "APPROVED_CAMPAIGN_CREATIVE_REQUIRED",
            "A currently approved campaign creative must be selected for an offer",
            status_code=status.HTTP_409_CONFLICT,
        )
    stored_file = creative.stored_file
    if (
        creative.stored_file_id is None
        or stored_file is None
        or stored_file.organization_id != campaign.organization_id
        or stored_file.purpose != FilePurpose.CREATIVE.value
        or stored_file.scan_status != FileScanStatus.CLEAN.value
        or stored_file.checksum_sha256 != creative.checksum
        or stored_file.content_type != creative.mime_type
        or stored_file.actual_content_type != creative.mime_type
    ):
        raise AppError(
            "MANAGED_CLEAN_CREATIVE_REQUIRED",
            "An approved creative must remain bound to its clean managed file before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    if campaign.start_at is None or campaign.end_at is None:
        raise AppError(
            "COMPLETE_CAMPAIGN_WINDOW_REQUIRED",
            "A complete campaign window is required before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        normalized_city = normalized_service_city(driver_profile.service_city or "")
    except ValueError as exc:
        raise AppError(
            "SERVICE_AREA_REQUIRED",
            "A normalized driver service area is required before offering",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    creative_snapshot = _creative_snapshot(creative)
    revision = await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(
            CampaignPayoutRuleRevision.campaign_id == campaign.id,
            CampaignPayoutRuleRevision.effective_from <= now,
        )
        .order_by(CampaignPayoutRuleRevision.effective_from.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        revision is None
        or revision.formula_version != PAYOUT_V3
        or not _valid_frozen_currency(revision.currency)
        or revision.currency != campaign.currency
        or revision.hourly_rate_naira is None
        or revision.premium_hourly_rate_naira is None
        or revision.daily_payable_hours_cap is None
    ):
        raise AppError(
            "FROZEN_PAYOUT_TERMS_REQUIRED",
            "An effective payout-v3 base/premium rate and daily cap are required before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    bind = session.get_bind()
    geom = CampaignZone.geom if bind.dialect.name == "sqlite" else func.ST_AsText(CampaignZone.geom)
    rows = (
        await session.execute(
            select(CampaignZone.id, CampaignZone.zone_type, CampaignZone.name, geom)
            .where(CampaignZone.campaign_id == campaign.id)
            .order_by(CampaignZone.zone_type, CampaignZone.id)
            .with_for_update()
        )
    ).all()
    targets = [row for row in rows if row[1] == CampaignZoneType.TARGET.value]
    exclusions = [row for row in rows if row[1] == CampaignZoneType.EXCLUSION.value]
    if not targets:
        raise AppError(
            "TARGET_AREA_REQUIRED",
            "A target service area is required before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    target_rows = [
        {"id": str(row[0]), "name": row[2], "wkt": str(row[3])} for row in targets
    ]
    exclusion_rows = [
        {"id": str(row[0]), "name": row[2], "wkt": str(row[3])} for row in exclusions
    ]
    if any(not row["wkt"] or row["wkt"] == "None" for row in target_rows + exclusion_rows):
        raise AppError(
            "CAMPAIGN_ZONE_GEOMETRY_REQUIRED",
            "All offered service-area zones must have geometry",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = {
        "offer_terms_version": OFFER_TERMS_VERSION,
        "currency": revision.currency,
        "campaign_window_start_at": as_aware_utc(campaign.start_at).isoformat(),
        "campaign_window_end_at": as_aware_utc(campaign.end_at).isoformat(),
        "service_area": {
            "city": normalized_city,
            "country_code": driver_profile.country_code.upper()
            if driver_profile.country_code
            else None,
        },
        "branding": {
            "campaign_id": str(campaign.id),
            "organization_id": str(campaign.organization_id),
            "campaign_name": campaign.name,
            "brand_name": (campaign.campaign_metadata or {}).get("brand_name")
            or (campaign.campaign_metadata or {}).get("brand"),
            "version": as_aware_utc(campaign.updated_at).isoformat()
            if campaign.updated_at is not None
            else None,
        },
        "creative": creative_snapshot,
        "payout": {
            "currency": revision.currency,
            "revision_id": str(revision.id),
            "payout_rule_id": str(revision.payout_rule_id),
            "revision_number": revision.revision_number,
            "effective_from": as_aware_utc(revision.effective_from).isoformat(),
            "formula_version": revision.formula_version,
            "hourly_rate_naira": str(revision.hourly_rate_naira),
            "premium_hourly_rate_naira": str(revision.premium_hourly_rate_naira),
            "daily_payable_hours_cap": str(revision.daily_payable_hours_cap),
            "eligibility_params": revision.eligibility_params or {},
        },
        "zones": {
            "semantics": "target_zones_are_premium; exclusions_are_unpaid",
            "target": target_rows,
            "premium": target_rows,
            "exclusion": exclusion_rows,
            "bonus": [
                {"id": str(row[0]), "name": row[2], "wkt": str(row[3])}
                for row in rows
                if row[1] == CampaignZoneType.BONUS.value
            ],
        },
        # The detector policy marker is part of the offer evidence, while the
        # numeric classifier snapshot remains exactly the payout_v3 binding
        # shape.  The binding carries the same marker in its dedicated column.
        "eligibility": {
            **resolved_eligibility_snapshot(settings, revision.eligibility_params),
            "stationary_policy_marker": STATIONARY_POLICY_V1,
        },
    }
    if not terms["branding"]["version"]:
        raise AppError(
            "CAMPAIGN_VERSION_REQUIRED",
            "A campaign version is required before offering",
            status_code=status.HTTP_409_CONFLICT,
        )
    return terms, canonical_offer_terms_sha256(terms)


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
    campaign: Campaign | None = None,
    settings: Settings | None = None,
) -> AssignmentRuleBinding | None:
    """Materialize a binding solely from the accepted offer snapshot.

    ``campaign`` and ``settings`` are retained in the signature for callers
    from the prior MNY-06 seam, but mutable campaign/rule/zone rows are never
    consulted here. The offer is the only authority after the driver decides.
    """
    terms = assignment.offer_terms
    if not _offer_terms_complete(terms, assignment.offer_terms_sha256):
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "A complete frozen offer is required before acceptance",
            status_code=status.HTTP_409_CONFLICT,
        )
    payout = terms["payout"]
    zones = terms["zones"]
    premium_zone_rows = [(row["id"], row["wkt"]) for row in zones["premium"]]
    exclusion_zone_rows = [(row["id"], row["wkt"]) for row in zones["exclusion"]]
    try:
        window_start = datetime.fromisoformat(terms["campaign_window_start_at"])
        window_end = datetime.fromisoformat(terms["campaign_window_end_at"])
        revision_id = UUID(payout["revision_id"])
        hourly_rate = Decimal(payout["hourly_rate_naira"])
        premium_rate = Decimal(payout["premium_hourly_rate_naira"])
        daily_cap = Decimal(payout["daily_payable_hours_cap"])
        currency = payout["currency"] if "currency" in payout else terms["currency"]
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "The accepted offer snapshot is malformed",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    if as_aware_utc(window_start) >= as_aware_utc(window_end):
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "The accepted offer has an invalid campaign window",
            status_code=status.HTTP_409_CONFLICT,
        )
    if not premium_zone_rows:
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "The accepted offer has no premium service area",
            status_code=status.HTTP_409_CONFLICT,
        )
    revision = await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(
            CampaignPayoutRuleRevision.id == revision_id,
            CampaignPayoutRuleRevision.campaign_id == assignment.campaign_id,
        )
        .with_for_update()
    )
    if (
        revision is None
        or revision.currency != currency
        or str(revision.payout_rule_id) != payout["payout_rule_id"]
    ):
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "The accepted offer currency disagrees with its frozen payout revision",
            status_code=status.HTTP_409_CONFLICT,
        )
    resolved_eligibility = dict(terms["eligibility"])
    resolved_eligibility.pop("stationary_policy_marker", None)
    binding = AssignmentRuleBinding(
        assignment_id=assignment.id,
        revision_id=revision_id,
        currency=currency,
        hourly_rate_naira=hourly_rate,
        premium_hourly_rate_naira=premium_rate,
        daily_payable_hours_cap=daily_cap,
        eligibility_params=payout["eligibility_params"],
        resolved_eligibility_params=resolved_eligibility,
        formula_version=payout["formula_version"],
        premium_zone_ids=[str(row[0]) for row in premium_zone_rows],
        premium_zone_geometry_hash=frozen_zone_geometry_hash(premium_zone_rows),
        premium_zone_geometry_wkts=[str(row[1]) for row in premium_zone_rows],
        exclusion_zone_ids=[str(row[0]) for row in exclusion_zone_rows],
        exclusion_zone_geometry_hash=frozen_zone_geometry_hash(exclusion_zone_rows),
        exclusion_zone_geometry_wkts=[str(row[1]) for row in exclusion_zone_rows],
        stationary_policy_marker=STATIONARY_POLICY_V1,
        campaign_window_start_at=window_start,
        campaign_window_end_at=window_end,
        campaign_window_frozen=True,
        offer_terms_sha256=assignment.offer_terms_sha256,
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
    vehicle_id = await session.scalar(
        select(CampaignAssignment.vehicle_id).where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    if vehicle_id is None:
        raise assignment_not_found()
    await acquire_work_eligibility_lock(
        session,
        driver_profile_id=driver_profile.id,
        vehicle_id=vehicle_id,
    )
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise assignment_not_found()
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
    driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == assignment.driver_profile_id)
        .with_for_update()
    )
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == assignment.vehicle_id).with_for_update()
    )
    if driver_profile is None or vehicle is None:
        raise assignment_not_found()
    now = await database_clock(session)
    if assignment.status == CampaignAssignmentStatus.ACCEPTED.value:
        return assignment
    if assignment.status in {
        CampaignAssignmentStatus.DECLINED.value,
        CampaignAssignmentStatus.EXPIRED.value,
    }:
        raise AppError(
            "ASSIGNMENT_DECISION_CONFLICT",
            "This assignment already has a different terminal decision",
            status_code=status.HTTP_409_CONFLICT,
        )
    if await expire_assignment_if_due(session, assignment, now=now):
        raise OfferExpiredError("The assignment offer expired before it could be accepted")
    if assignment.status == CampaignAssignmentStatus.OFFERED.value:
        ensure_campaign_acceptable(campaign, now)
    if assignment.status != CampaignAssignmentStatus.OFFERED.value:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only offered assignments can be accepted",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
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
    previous_status = assignment.status
    assignment.status = CampaignAssignmentStatus.ACCEPTED.value
    assignment.accepted_at = now
    await session.flush()
    binding = await create_rule_binding_for_accept(
        session,
        assignment=assignment,
        now=now,
        campaign=campaign,
    )
    if binding is None:
        raise AppError(
            "FROZEN_PAYOUT_BINDING_REQUIRED",
            "Accepted frozen payout terms are required before acceptance",
            status_code=status.HTTP_409_CONFLICT,
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
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.campaign_assignment.accepted",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={"campaign_id": str(assignment.campaign_id)},
    )
    from app.models.notification import NotificationType
    from app.services.notifications import create_driver_business_notification

    await create_driver_business_notification(
        session,
        driver_profile_id=assignment.driver_profile_id,
        type_key=NotificationType.ASSIGNMENT_ACCEPTED,
        event_key=f"assignment:accepted:v1:{assignment.id}",
        payload={
            "assignment_id": str(assignment.id),
            "campaign_id": str(assignment.campaign_id),
        },
    )
    await session.refresh(assignment)
    return assignment


async def decline_driver_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
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
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise assignment_not_found()
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
    now = await database_clock(session)
    if assignment.status == CampaignAssignmentStatus.DECLINED.value:
        return assignment
    if assignment.status in {
        CampaignAssignmentStatus.ACCEPTED.value,
        CampaignAssignmentStatus.EXPIRED.value,
    }:
        raise AppError(
            "ASSIGNMENT_DECISION_CONFLICT",
            "This assignment already has a different terminal decision",
            status_code=status.HTTP_409_CONFLICT,
        )
    if await expire_assignment_if_due(session, assignment, now=now):
        raise OfferExpiredError("The assignment offer expired before it could be declined")
    if assignment.status != CampaignAssignmentStatus.OFFERED.value:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only offered assignments can be declined",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    ensure_campaign_acceptable(campaign, now)
    assignment.status = CampaignAssignmentStatus.DECLINED.value
    assignment.declined_at = now
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=user_id,
        event_type=CampaignActivationEventType.DECLINED,
        previous_status=CampaignAssignmentStatus.OFFERED.value,
        metadata=payload.metadata,
        occurred_at=now,
    )
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.campaign_assignment.declined",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={"campaign_id": str(assignment.campaign_id)},
    )
    await session.refresh(assignment)
    return assignment


async def activate_admin_assignment(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    settings: Settings | None = None,
) -> CampaignAssignment:
    settings = settings or get_settings()
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, admin_user_id)
    if campaign_id is None:
        raise assignment_not_found()
    eligibility_row = (
        await session.execute(
            select(
                CampaignAssignment.driver_profile_id,
                CampaignAssignment.vehicle_id,
            ).where(CampaignAssignment.id == assignment_id)
        )
    ).one_or_none()
    if eligibility_row is None:
        raise assignment_not_found()
    await acquire_work_eligibility_lock(
        session,
        driver_profile_id=eligibility_row[0],
        vehicle_id=eligibility_row[1],
    )
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise assignment_not_found()
    assignment = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )
    assert assignment is not None
    if assignment.status not in {
        CampaignAssignmentStatus.ACCEPTED.value,
        CampaignAssignmentStatus.ACTIVE.value,
        CampaignAssignmentStatus.DEACTIVATED.value,
    }:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Only accepted, active or deactivated assignments can be activated",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == assignment.driver_profile_id)
        .with_for_update()
    )
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == assignment.vehicle_id).with_for_update()
    )
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if vehicle is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    now = await database_clock(session)
    ensure_campaign_activatable(campaign, now)
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
    campaign_review = await ensure_campaign_review_approved(session, campaign.id)
    if not _offer_terms_complete(assignment.offer_terms, assignment.offer_terms_sha256):
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "A complete frozen offer is required before activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    assert assignment.offer_terms is not None
    creative_data = assignment.offer_terms["creative"]
    try:
        creative_id = UUID(str(creative_data["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            "FROZEN_OFFER_TERMS_REQUIRED",
            "The accepted offer does not identify a creative",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    creative = await session.scalar(
        select(CampaignCreative)
        .where(CampaignCreative.id == creative_id, CampaignCreative.campaign_id == campaign.id)
        .with_for_update()
    )
    if creative is None or creative.status != CreativeStatus.APPROVED.value:
        raise AppError(
            "APPROVED_CAMPAIGN_CREATIVE_REQUIRED",
            "The selected campaign creative is no longer approved",
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        current_creative = _creative_snapshot(creative)
    except AppError as exc:
        raise AppError(
            "APPROVED_CAMPAIGN_CREATIVE_REQUIRED",
            "The selected campaign creative has incomplete content identity",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    if current_creative != creative_data:
        raise AppError(
            "OFFER_CREATIVE_CHANGED",
            "The selected campaign creative changed after the offer was accepted",
            status_code=status.HTTP_409_CONFLICT,
        )
    creative_review = await session.scalar(
        select(CreativeReviewEvent)
        .where(
            CreativeReviewEvent.creative_id == creative.id,
            CreativeReviewEvent.new_status == CreativeStatus.APPROVED.value,
        )
        .order_by(CreativeReviewEvent.created_at.desc(), CreativeReviewEvent.id.desc())
        .limit(1)
        .with_for_update()
    )
    binding = await session.scalar(
        select(AssignmentRuleBinding)
        .where(AssignmentRuleBinding.assignment_id == assignment.id)
        .with_for_update()
    )
    if binding is None:
        raise AppError(
            "FROZEN_PAYOUT_BINDING_REQUIRED",
            "Accepted frozen payout terms are required before activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        binding.offer_terms_sha256 != assignment.offer_terms_sha256
        or not binding.campaign_window_frozen
        or binding.campaign_window_start_at is None
        or binding.campaign_window_end_at is None
    ):
        raise AppError(
            "FROZEN_PAYOUT_BINDING_REQUIRED",
            "The payout binding is not linked to the accepted offer evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    if assignment.status == CampaignAssignmentStatus.ACTIVE.value:
        reservation = await session.scalar(
            select(CampaignLiabilityReservation)
            .where(CampaignLiabilityReservation.assignment_id == assignment.id)
            .with_for_update()
        )
        if reservation is None:
            reservation = await reserve_assignment_liability(
                session, assignment_id=assignment.id, actor_user_id=admin_user_id
            )
    else:
        reservation = await reserve_assignment_liability(
            session, assignment_id=assignment.id, actor_user_id=admin_user_id
        )
    if reservation is None:
        raise AppError(
            "ASSIGNMENT_FUNDING_REQUIRED",
            "Campaign funding must reserve this assignment before activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    if reservation.status != "reserved":
        raise AppError(
            "ASSIGNMENT_FUNDING_REQUIRED",
            "Campaign funding must reserve this assignment before activation",
            status_code=status.HTTP_409_CONFLICT,
        )
    authorization = await assert_campaign_production_authorized(
        session, campaign_id=campaign.id
    )
    await assert_new_work_authorized(
        session, campaign_id=campaign.id, assignment_id=assignment.id
    )
    evidence = await ensure_current_approved_installation_evidence(
        session,
        assignment=assignment,
        settings=settings,
        now=now,
        lock=True,
    )
    if assignment.status == CampaignAssignmentStatus.ACTIVE.value:
        await ensure_current_activation_snapshot(session, assignment=assignment, lock=True)
        return assignment

    await ensure_no_other_active_assignment_for_vehicle(
        session,
        vehicle_id=assignment.vehicle_id,
        assignment_id=assignment.id,
    )
    await ensure_no_other_active_assignment_for_driver(
        session,
        driver_profile_id=assignment.driver_profile_id,
        assignment_id=assignment.id,
    )
    production_start = await activation_production_start(
        session,
        campaign_id=campaign.id,
    )
    previous_status = assignment.status
    activate_campaign = campaign.status == CampaignStatus.SCHEDULED.value
    assignment.status = CampaignAssignmentStatus.ACTIVE.value
    assignment.activated_at = now
    if activate_campaign:
        campaign.status = CampaignStatus.ACTIVE.value
    snapshot: dict[str, object] = {
        "version": ACTIVATION_SNAPSHOT_VERSION,
        "assignment_id": str(assignment.id),
        "campaign_id": str(campaign.id),
        "driver_profile_id": str(driver_profile.id),
        "vehicle_id": str(vehicle.id),
        "offer_terms_sha256": assignment.offer_terms_sha256,
        "campaign_review_event_id": str(campaign_review.id),
        "creative_id": str(creative.id),
        "creative_review_event_id": (
            str(creative_review.id) if creative_review is not None else None
        ),
        "assignment_rule_binding_id": str(binding.id),
        "liability_reservation_id": str(reservation.id),
        "financial_authorization_id": str(authorization.id),
        "production_start_id": str(production_start.id),
        "production_authority_basis": production_start.authority_basis,
        "production_waiver_id": (
            str(production_start.waiver_id)
            if production_start.waiver_id is not None
            else None
        ),
        "installation_evidence_submission_id": str(evidence.id),
        "installation_evidence_revision": evidence.revision,
        "activated_at": as_aware_utc(now).isoformat(),
    }
    event_metadata = dict(payload.metadata)
    event_metadata["activation_snapshot"] = snapshot
    event_metadata["activation_snapshot_sha256"] = activation_snapshot_digest(snapshot)
    await flush_translating_exclusivity_conflict(session)
    await create_activation_event(
        session,
        assignment=assignment,
        actor_user_id=admin_user_id,
        event_type=CampaignActivationEventType.ACTIVATED,
        previous_status=previous_status,
        metadata=event_metadata,
        occurred_at=now,
    )
    await create_audit_event(
        session,
        actor_user_id=admin_user_id,
        action="admin.campaign_assignment.activated",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={
            "campaign_id": str(campaign.id),
            "activation_snapshot_sha256": event_metadata["activation_snapshot_sha256"],
        },
    )
    if activate_campaign:
        await create_audit_event(
            session,
            actor_user_id=admin_user_id,
            action="admin.campaign.activated",
            entity_type="campaign",
            entity_id=str(campaign.id),
            metadata={
                "status_before": CampaignStatus.SCHEDULED.value,
                "status_after": campaign.status,
                "assignment_id": str(assignment.id),
                "activation_snapshot_sha256": event_metadata["activation_snapshot_sha256"],
            },
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
    driver_profile = await get_driver_profile_for_user(session, user_id)
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(
            CampaignAssignment.id == assignment_id,
            CampaignAssignment.driver_profile_id == driver_profile.id,
        )
    )
    if campaign_id is None:
        raise assignment_not_found()
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise assignment_not_found()
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
    driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == assignment.driver_profile_id)
        .with_for_update()
    )
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == assignment.vehicle_id).with_for_update()
    )
    if driver_profile is None or vehicle is None:
        raise assignment_not_found()
    now = await database_clock(session)
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
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.campaign_assignment.deactivated",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={"campaign_id": str(assignment.campaign_id)},
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
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, admin_user_id)
    if campaign_id is None:
        raise assignment_not_found()
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise assignment_not_found()
    assignment = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )
    if assignment is None:
        raise assignment_not_found()
    # Keep the producer rows behind the assignment lock in the same order as
    # activation and trip start.  This closes the terminal-transition race
    # without taking a reverse profile/vehicle -> assignment path.
    locked_driver_profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == assignment.driver_profile_id)
        .with_for_update()
    )
    locked_vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == assignment.vehicle_id).with_for_update()
    )
    if locked_driver_profile is None or locked_vehicle is None:
        raise assignment_not_found()
    now = await database_clock(session)
    if await expire_assignment_if_due(session, assignment, now=now):
        raise OfferExpiredError("The assignment offer expired before it could be cancelled")
    if (
        assignment.status == CampaignAssignmentStatus.OFFERED.value
        and _offer_terms_complete(assignment.offer_terms, assignment.offer_terms_sha256)
    ):
        raise AppError(
            "OFFER_DECISION_REQUIRED",
            "A complete offer may only be accepted, declined, or expired",
            status_code=status.HTTP_409_CONFLICT,
        )
    if assignment.status in {
        CampaignAssignmentStatus.CANCELLED.value,
        CampaignAssignmentStatus.COMPLETED.value,
        CampaignAssignmentStatus.DECLINED.value,
        CampaignAssignmentStatus.EXPIRED.value,
    }:
        raise AppError(
            "INVALID_ASSIGNMENT_TRANSITION",
            "Terminal decision assignments cannot be cancelled",
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
