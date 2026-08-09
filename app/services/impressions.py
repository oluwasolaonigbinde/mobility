from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.impression import (
    ImpressionEstimate,
    ImpressionEstimateStatus,
    TrafficDensityProfile,
    TrafficDensityProfileStatus,
    TrafficDensityProfileType,
)
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.schemas.impressions import TrafficDensityProfileCreate, TrafficDensityProfileUpdate
from app.services.campaigns import get_advertiser_campaign
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import (
    analytics_not_found,
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
)
from app.services.trips import trip_not_found

DECIMAL_2 = Decimal("0.01")
DECIMAL_4 = Decimal("0.0001")
DEFAULT_PROFILE_CONSTRAINTS = frozenset({"uq_traffic_density_profiles_active_default"})
IMPRESSION_ESTIMATE_CONSTRAINTS = frozenset(
    {"uq_impression_estimates_trip_formula_profile"}
)
IMPRESSION_FINGERPRINT_FIELDS = (
    "trip_analytics_id",
    "assignment_id",
    "campaign_id",
    "driver_profile_id",
    "vehicle_id",
    "status",
    "estimated_impressions",
    "base_distance_impressions",
    "dwell_impressions",
    "target_zone_impressions",
    "bonus_zone_impressions",
    "exclusion_zone_adjustment",
    "quality_multiplier",
    "fraud_adjustment_multiplier",
    "confidence_score",
    "started_at",
    "ended_at",
)


@dataclass(frozen=True)
class ImpressionSummary:
    campaign_id: UUID
    formula_version: str
    estimated_impressions: Decimal
    trip_count: int
    estimated_trip_count: int
    insufficient_data_trip_count: int
    excluded_trip_count: int
    average_confidence_score: Decimal
    start_at: datetime | None
    end_at: datetime | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(maximum, value))


def quantize_2(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_2)


def quantize_4(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_4)


def decimal_km(meters: Decimal) -> Decimal:
    return Decimal(meters or 0) / Decimal("1000")


def time_bucket_and_weight(
    analytics: TripAnalytics,
    profile: TrafficDensityProfile,
) -> tuple[str, Decimal]:
    source_time = analytics.started_at or analytics.first_ping_at
    if source_time is None:
        return "night", profile.night_weight
    hour = source_time.astimezone(UTC).hour if source_time.tzinfo is not None else source_time.hour
    if 5 <= hour <= 10:
        return "morning", profile.morning_weight
    if 11 <= hour <= 15:
        return "midday", profile.midday_weight
    if 16 <= hour <= 20:
        return "evening", profile.evening_weight
    return "night", profile.night_weight


def profile_not_found() -> AppError:
    return AppError(
        "TRAFFIC_DENSITY_PROFILE_NOT_FOUND",
        "Traffic density profile was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def profile_inactive() -> AppError:
    return AppError(
        "TRAFFIC_DENSITY_PROFILE_INACTIVE",
        "Traffic density profile is not active",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def impression_estimate_stale() -> AppError:
    return AppError(
        "IMPRESSION_ESTIMATE_STALE",
        "The impression estimate must be recomputed from current trip analytics",
        status_code=status.HTTP_409_CONFLICT,
    )


def _normalized_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_current_estimate_for_analytics(
    estimate: ImpressionEstimate,
    analytics: TripAnalytics,
    settings: Settings,
    *,
    fraud_counts: dict[str, int] | None = None,
) -> bool:
    if (
        estimate.formula_version != settings.impression_formula_version
        or estimate.trip_analytics_id != analytics.id
    ):
        return False
    metadata = estimate.estimate_metadata or {}
    if fraud_counts is not None and metadata.get("fraud_flag_counts") != fraud_counts:
        return False
    source_fingerprint = metadata.get("source_analytics_fingerprint")
    if source_fingerprint is not None:
        return source_fingerprint == analytics_output_fingerprint(analytics)
    source_formula_version = metadata.get(
        "source_analytics_formula_version"
    )
    if source_formula_version is not None:
        return (
            source_formula_version == analytics.formula_version
            and _normalized_utc(estimate.estimated_at)
            >= _normalized_utc(analytics.computed_at)
        )
    return _normalized_utc(estimate.estimated_at) >= _normalized_utc(analytics.computed_at)


def impression_output_fingerprint(
    estimate: ImpressionEstimate | dict,
    *,
    formula_version: str | None = None,
    traffic_density_profile_id: UUID | None = None,
    source_analytics_fingerprint: str | None = None,
) -> str:
    values = {
        field: estimate[field] if isinstance(estimate, dict) else getattr(estimate, field)
        for field in IMPRESSION_FINGERPRINT_FIELDS
    }
    if isinstance(estimate, dict):
        metadata = estimate.get("estimate_metadata") or {}
        values["formula_version"] = formula_version
        values["traffic_density_profile_id"] = traffic_density_profile_id
        values["source_analytics_fingerprint"] = source_analytics_fingerprint
        values["fraud_flag_counts"] = metadata.get("fraud_flag_counts")
    else:
        metadata = estimate.estimate_metadata or {}
        values["formula_version"] = estimate.formula_version
        values["traffic_density_profile_id"] = estimate.traffic_density_profile_id
        values["source_analytics_fingerprint"] = metadata.get(
            "source_analytics_fingerprint"
        )
        values["fraud_flag_counts"] = metadata.get("fraud_flag_counts")
    return stable_source_fingerprint(values)


def ensure_current_estimate_source(
    estimate: ImpressionEstimate,
    analytics: TripAnalytics,
    settings: Settings,
    *,
    fraud_counts: dict[str, int] | None = None,
) -> None:
    if not is_current_estimate_for_analytics(
        estimate,
        analytics,
        settings,
        fraud_counts=fraud_counts,
    ):
        raise impression_estimate_stale()


async def clear_other_active_defaults(
    session: AsyncSession,
    *,
    profile_id: UUID | None = None,
) -> None:
    statement = (
        update(TrafficDensityProfile)
        .where(
            TrafficDensityProfile.status == TrafficDensityProfileStatus.ACTIVE.value,
            TrafficDensityProfile.is_default.is_(True),
        )
        .values(is_default=False, updated_at=utc_now())
    )
    if profile_id is not None:
        statement = statement.where(TrafficDensityProfile.id != profile_id)
    await session.execute(statement)


async def create_traffic_density_profile(
    session: AsyncSession,
    payload: TrafficDensityProfileCreate,
) -> TrafficDensityProfile:
    if payload.is_default and payload.status == TrafficDensityProfileStatus.ACTIVE:
        await clear_other_active_defaults(session)
    profile = TrafficDensityProfile(
        name=payload.name,
        description=payload.description,
        profile_type=payload.profile_type,
        traffic_density_per_km=payload.traffic_density_per_km,
        dwell_impressions_per_minute=payload.dwell_impressions_per_minute,
        road_category_weight=payload.road_category_weight,
        morning_weight=payload.morning_weight,
        midday_weight=payload.midday_weight,
        evening_weight=payload.evening_weight,
        night_weight=payload.night_weight,
        target_zone_weight=payload.target_zone_weight,
        bonus_zone_weight=payload.bonus_zone_weight,
        exclusion_zone_weight=payload.exclusion_zone_weight,
        is_default=payload.is_default,
        status=payload.status,
        profile_metadata=payload.metadata,
    )
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    return profile


async def list_traffic_density_profiles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    profile_status: str | None,
    profile_type: str | None,
    is_default: bool | None,
) -> tuple[list[TrafficDensityProfile], int]:
    filters = []
    if profile_status is not None:
        filters.append(TrafficDensityProfile.status == profile_status)
    if profile_type is not None:
        filters.append(TrafficDensityProfile.profile_type == profile_type)
    if is_default is not None:
        filters.append(TrafficDensityProfile.is_default == is_default)

    statement = select(TrafficDensityProfile)
    count_statement = select(func.count()).select_from(TrafficDensityProfile)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(TrafficDensityProfile.created_at.desc(), TrafficDensityProfile.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_traffic_density_profile(
    session: AsyncSession,
    profile_id: UUID,
) -> TrafficDensityProfile:
    profile = await session.get(TrafficDensityProfile, profile_id)
    if profile is None:
        raise profile_not_found()
    return profile


async def update_traffic_density_profile(
    session: AsyncSession,
    *,
    profile_id: UUID,
    payload: TrafficDensityProfileUpdate,
) -> TrafficDensityProfile:
    profile = await get_traffic_density_profile(session, profile_id)
    update_values = payload.model_dump(exclude_unset=True)
    if "metadata" in update_values:
        profile.profile_metadata = update_values.pop("metadata")
    for field, value in update_values.items():
        setattr(profile, field, value)
    if (
        profile.is_default
        and profile.status == TrafficDensityProfileStatus.ACTIVE.value
    ):
        await clear_other_active_defaults(session, profile_id=profile.id)
    await session.flush()
    await session.refresh(profile)
    return profile


async def get_or_create_default_profile(
    session: AsyncSession,
    settings: Settings,
) -> TrafficDensityProfile:
    profile = await active_default_profile(session)
    if profile is not None:
        return profile

    profile = TrafficDensityProfile(
        name="Settings Default Profile",
        description="Settings-backed default v1 profile.",
        profile_type=TrafficDensityProfileType.DEFAULT.value,
        traffic_density_per_km=Decimal(str(settings.impression_default_traffic_density_per_km)),
        dwell_impressions_per_minute=Decimal(
            str(settings.impression_default_dwell_impressions_per_minute)
        ),
        road_category_weight=Decimal("1.0"),
        morning_weight=Decimal("1.0"),
        midday_weight=Decimal("1.0"),
        evening_weight=Decimal("1.0"),
        night_weight=Decimal("0.7"),
        target_zone_weight=Decimal("1.0"),
        bonus_zone_weight=Decimal("1.25"),
        exclusion_zone_weight=Decimal("0.0"),
        is_default=True,
        status=TrafficDensityProfileStatus.ACTIVE.value,
        profile_metadata={"source": "settings"},
    )
    try:
        async with session.begin_nested():
            session.add(profile)
            await session.flush()
            await session.refresh(profile)
            return profile
    except IntegrityError as exc:
        if not is_expected_uniqueness_conflict(
            exc,
            constraints=DEFAULT_PROFILE_CONSTRAINTS,
        ):
            raise
        existing_profile = await active_default_profile(session)
        if existing_profile is not None:
            return existing_profile
        raise


async def active_default_profile(session: AsyncSession) -> TrafficDensityProfile | None:
    return await session.scalar(
        select(TrafficDensityProfile)
        .where(
            TrafficDensityProfile.status == TrafficDensityProfileStatus.ACTIVE.value,
            TrafficDensityProfile.is_default.is_(True),
        )
        .order_by(TrafficDensityProfile.created_at.desc(), TrafficDensityProfile.id)
        .limit(1)
    )


async def resolve_active_profile(
    session: AsyncSession,
    *,
    profile_id: UUID | None,
    settings: Settings,
) -> TrafficDensityProfile:
    if profile_id is None:
        return await get_or_create_default_profile(session, settings)
    profile = await get_traffic_density_profile(session, profile_id)
    if profile.status != TrafficDensityProfileStatus.ACTIVE.value:
        raise profile_inactive()
    return profile


async def get_trip_for_estimation(session: AsyncSession, trip_id: UUID) -> TripSession:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    # Estimates are diagnostics, not money: `ended` and `sealed` both qualify.
    finalized = (TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value)
    if trip.status not in finalized or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_ENDED",
            "Impressions can only be estimated for ended trips",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return trip


async def get_analytics_for_trip(session: AsyncSession, trip_id: UUID) -> TripAnalytics:
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None:
        raise analytics_not_found()
    return analytics


async def open_fraud_counts(session: AsyncSession, trip_id: UUID) -> dict[str, int]:
    result = await session.execute(
        select(FraudFlag.severity, func.count(FraudFlag.id))
        .where(
            FraudFlag.trip_session_id == trip_id,
            FraudFlag.status == FraudFlagStatus.OPEN.value,
        )
        .group_by(FraudFlag.severity)
    )
    counts = {severity.value: 0 for severity in FraudFlagSeverity}
    for severity, count in result.all():
        counts[str(severity)] = int(count)
    return counts


def fraud_multiplier(counts: dict[str, int], settings: Settings) -> Decimal:
    if counts[FraudFlagSeverity.HIGH.value] > 0:
        return Decimal(str(settings.impression_high_fraud_multiplier))
    if counts[FraudFlagSeverity.MEDIUM.value] > 0:
        return Decimal(str(settings.impression_medium_fraud_multiplier))
    if counts[FraudFlagSeverity.LOW.value] > 0:
        return Decimal(str(settings.impression_low_fraud_multiplier))
    return Decimal("1.0")


def profile_metadata(profile: TrafficDensityProfile) -> dict[str, str]:
    return {
        "traffic_density_per_km": str(profile.traffic_density_per_km),
        "dwell_impressions_per_minute": str(profile.dwell_impressions_per_minute),
        "road_category_weight": str(profile.road_category_weight),
        "morning_weight": str(profile.morning_weight),
        "midday_weight": str(profile.midday_weight),
        "evening_weight": str(profile.evening_weight),
        "night_weight": str(profile.night_weight),
        "target_zone_weight": str(profile.target_zone_weight),
        "bonus_zone_weight": str(profile.bonus_zone_weight),
        "exclusion_zone_weight": str(profile.exclusion_zone_weight),
    }


def estimate_values(
    *,
    analytics: TripAnalytics,
    profile: TrafficDensityProfile,
    counts: dict[str, int],
    request_metadata: dict,
    settings: Settings,
    estimated_at: datetime,
) -> dict:
    quality_multiplier = quantize_4(
        clamp_decimal(Decimal(analytics.quality_score or 0), Decimal("0"), Decimal("1"))
    )
    fraud_adjustment_multiplier = quantize_4(fraud_multiplier(counts, settings))
    time_bucket, time_weight = time_bucket_and_weight(analytics, profile)
    time_weight = Decimal(time_weight)

    if analytics.status == TripAnalyticsStatus.INSUFFICIENT_DATA.value:
        confidence_score = quantize_4(
            Decimal(str(settings.impression_insufficient_data_confidence))
        )
        zero = Decimal("0.00")
        return {
            "status": ImpressionEstimateStatus.INSUFFICIENT_DATA.value,
            "estimated_impressions": zero,
            "base_distance_impressions": zero,
            "dwell_impressions": zero,
            "target_zone_impressions": zero,
            "bonus_zone_impressions": zero,
            "exclusion_zone_adjustment": zero,
            "quality_multiplier": quality_multiplier,
            "fraud_adjustment_multiplier": fraud_adjustment_multiplier,
            "confidence_score": confidence_score,
            "estimated_at": estimated_at,
            "estimate_metadata": {
                "formula_version": settings.impression_formula_version,
                "source_analytics_id": str(analytics.id),
                "traffic_density_profile": profile_metadata(profile),
                "time_bucket": time_bucket,
                "time_zone": "UTC",
                "time_of_day_weight": str(time_weight),
                "road_category_method": "profile_default_weight_no_road_classification_v1",
                "fraud_flag_counts": counts,
                "request_metadata": request_metadata,
                "components": {
                    "reason": "insufficient_data",
                    "estimated_impressions": "0.00",
                },
            },
        }

    if analytics.status == TripAnalyticsStatus.BLOCKED.value:
        confidence_score = quantize_4(
            clamp_decimal(
                Decimal(str(settings.impression_min_confidence)),
                Decimal("0"),
                Decimal(str(settings.impression_max_confidence)),
            )
        )
        zero = Decimal("0.00")
        return {
            "status": ImpressionEstimateStatus.EXCLUDED.value,
            "estimated_impressions": zero,
            "base_distance_impressions": zero,
            "dwell_impressions": zero,
            "target_zone_impressions": zero,
            "bonus_zone_impressions": zero,
            "exclusion_zone_adjustment": zero,
            "quality_multiplier": quality_multiplier,
            "fraud_adjustment_multiplier": fraud_adjustment_multiplier,
            "confidence_score": confidence_score,
            "estimated_at": estimated_at,
            "estimate_metadata": {
                "formula_version": settings.impression_formula_version,
                "source_analytics_id": str(analytics.id),
                "traffic_density_profile": profile_metadata(profile),
                "time_bucket": time_bucket,
                "time_zone": "UTC",
                "time_of_day_weight": str(time_weight),
                "road_category_method": "profile_default_weight_no_road_classification_v1",
                "fraud_flag_counts": counts,
                "request_metadata": request_metadata,
                "components": {
                    "reason": "blocked_analytics",
                    "estimated_impressions": "0.00",
                },
            },
        }

    total_distance_km = decimal_km(analytics.distance_m)
    target_zone_distance_km = decimal_km(analytics.target_zone_distance_m)
    bonus_zone_distance_km = decimal_km(analytics.bonus_zone_distance_m)
    exclusion_zone_distance_km = decimal_km(analytics.exclusion_zone_distance_m)
    stationary_minutes = Decimal(analytics.stationary_seconds or 0) / Decimal("60")

    base_distance_impressions = quantize_2(
        total_distance_km
        * profile.traffic_density_per_km
        * profile.road_category_weight
        * time_weight
        * quality_multiplier
    )
    target_zone_impressions = quantize_2(
        target_zone_distance_km
        * profile.traffic_density_per_km
        * profile.target_zone_weight
        * quality_multiplier
    )
    bonus_zone_impressions = quantize_2(
        bonus_zone_distance_km
        * profile.traffic_density_per_km
        * profile.bonus_zone_weight
        * quality_multiplier
    )
    dwell_impressions = quantize_2(
        stationary_minutes
        * profile.dwell_impressions_per_minute
        * time_weight
        * quality_multiplier
    )
    exclusion_zone_adjustment = quantize_2(
        exclusion_zone_distance_km
        * profile.traffic_density_per_km
        * profile.exclusion_zone_weight
    )
    pre_fraud_estimate = (
        base_distance_impressions
        + target_zone_impressions
        + bonus_zone_impressions
        + dwell_impressions
        - exclusion_zone_adjustment
    )
    estimated_impressions = quantize_2(
        max(Decimal("0"), pre_fraud_estimate * fraud_adjustment_multiplier)
    )
    confidence_score = quantize_4(
        clamp_decimal(
            quality_multiplier * fraud_adjustment_multiplier,
            Decimal(str(settings.impression_min_confidence)),
            Decimal(str(settings.impression_max_confidence)),
        )
    )
    return {
        "status": ImpressionEstimateStatus.ESTIMATED.value,
        "estimated_impressions": estimated_impressions,
        "base_distance_impressions": base_distance_impressions,
        "dwell_impressions": dwell_impressions,
        "target_zone_impressions": target_zone_impressions,
        "bonus_zone_impressions": bonus_zone_impressions,
        "exclusion_zone_adjustment": exclusion_zone_adjustment,
        "quality_multiplier": quality_multiplier,
        "fraud_adjustment_multiplier": fraud_adjustment_multiplier,
        "confidence_score": confidence_score,
        "estimated_at": estimated_at,
        "estimate_metadata": {
            "formula_version": settings.impression_formula_version,
            "source_analytics_id": str(analytics.id),
            "traffic_density_profile": profile_metadata(profile),
            "time_bucket": time_bucket,
            "time_zone": "UTC",
            "time_of_day_weight": str(time_weight),
            "road_category_method": "profile_default_weight_no_road_classification_v1",
            "fraud_flag_counts": counts,
            "request_metadata": request_metadata,
            "inputs": {
                "total_distance_km": str(total_distance_km),
                "target_zone_distance_km": str(target_zone_distance_km),
                "bonus_zone_distance_km": str(bonus_zone_distance_km),
                "exclusion_zone_distance_km": str(exclusion_zone_distance_km),
                "stationary_minutes": str(stationary_minutes),
            },
            "components": {
                "base_distance_impressions": str(base_distance_impressions),
                "target_zone_impressions": str(target_zone_impressions),
                "bonus_zone_impressions": str(bonus_zone_impressions),
                "dwell_impressions": str(dwell_impressions),
                "exclusion_zone_adjustment": str(exclusion_zone_adjustment),
                "pre_fraud_estimate": str(pre_fraud_estimate),
                "estimated_impressions": str(estimated_impressions),
            },
        },
    }


async def estimate_trip_impressions(
    session: AsyncSession,
    *,
    trip_id: UUID,
    traffic_density_profile_id: UUID | None,
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
) -> ImpressionEstimate:
    trip = await get_trip_for_estimation(session, trip_id)
    analytics = await get_analytics_for_trip(session, trip.id)
    ensure_current_analytics_formula(analytics, settings)
    profile = await resolve_active_profile(
        session,
        profile_id=traffic_density_profile_id,
        settings=settings,
    )
    counts = await open_fraud_counts(session, trip.id)
    values = estimate_values(
        analytics=analytics,
        profile=profile,
        counts=counts,
        request_metadata=metadata,
        settings=settings,
        estimated_at=now or utc_now(),
    )
    source_analytics_fingerprint = analytics_output_fingerprint(analytics)
    values["estimate_metadata"].update(
        {
            "source_analytics_formula_version": analytics.formula_version,
            "source_analytics_computed_at": analytics.computed_at.isoformat(),
            "source_analytics_fingerprint": source_analytics_fingerprint,
        }
    )
    values.update(
        {
            "trip_analytics_id": analytics.id,
            "assignment_id": analytics.assignment_id,
            "campaign_id": analytics.campaign_id,
            "driver_profile_id": analytics.driver_profile_id,
            "vehicle_id": analytics.vehicle_id,
            "started_at": analytics.started_at,
            "ended_at": analytics.ended_at,
        }
    )
    values["estimate_metadata"]["output_fingerprint"] = impression_output_fingerprint(
        values,
        formula_version=settings.impression_formula_version,
        traffic_density_profile_id=profile.id,
        source_analytics_fingerprint=source_analytics_fingerprint,
    )
    estimate = await session.scalar(
        select(ImpressionEstimate).where(
            ImpressionEstimate.trip_session_id == trip.id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
            ImpressionEstimate.traffic_density_profile_id == profile.id,
        )
    )
    if estimate is None:
        candidate = ImpressionEstimate(
            trip_session_id=trip.id,
            traffic_density_profile_id=profile.id,
            formula_version=settings.impression_formula_version,
            **values,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(
                exc,
                constraints=IMPRESSION_ESTIMATE_CONSTRAINTS,
            ):
                raise
            estimate = await session.scalar(
                select(ImpressionEstimate).where(
                    ImpressionEstimate.trip_session_id == trip.id,
                    ImpressionEstimate.formula_version == settings.impression_formula_version,
                    ImpressionEstimate.traffic_density_profile_id == profile.id,
                )
            )
            if estimate is None:
                raise
        else:
            estimate = candidate
    for field, value in values.items():
        setattr(estimate, field, value)
    await session.flush()
    await session.refresh(estimate)
    return estimate


async def list_impression_estimates(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    campaign_id: UUID | None,
    trip_session_id: UUID | None,
    driver_profile_id: UUID | None,
    vehicle_id: UUID | None,
    estimate_status: str | None,
    traffic_density_profile_id: UUID | None,
) -> tuple[list[ImpressionEstimate], int]:
    filters = []
    if campaign_id is not None:
        filters.append(ImpressionEstimate.campaign_id == campaign_id)
    if trip_session_id is not None:
        filters.append(ImpressionEstimate.trip_session_id == trip_session_id)
    if driver_profile_id is not None:
        filters.append(ImpressionEstimate.driver_profile_id == driver_profile_id)
    if vehicle_id is not None:
        filters.append(ImpressionEstimate.vehicle_id == vehicle_id)
    if estimate_status is not None:
        filters.append(ImpressionEstimate.status == estimate_status)
    if traffic_density_profile_id is not None:
        filters.append(ImpressionEstimate.traffic_density_profile_id == traffic_density_profile_id)

    statement = select(ImpressionEstimate)
    count_statement = select(func.count()).select_from(ImpressionEstimate)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(ImpressionEstimate.estimated_at.desc(), ImpressionEstimate.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def advertiser_campaign_impression_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> ImpressionSummary:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    filters = [
        ImpressionEstimate.campaign_id == campaign.id,
        ImpressionEstimate.formula_version == settings.impression_formula_version,
    ]
    if start_at is not None:
        filters.append(ImpressionEstimate.estimated_at >= start_at)
    if end_at is not None:
        filters.append(ImpressionEstimate.estimated_at <= end_at)

    result = await session.execute(
        select(
            func.coalesce(func.sum(ImpressionEstimate.estimated_impressions), 0),
            func.count(ImpressionEstimate.id),
            func.coalesce(
                func.sum(
                    case(
                        (ImpressionEstimate.status == ImpressionEstimateStatus.ESTIMATED.value, 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            ImpressionEstimate.status
                            == ImpressionEstimateStatus.INSUFFICIENT_DATA.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (ImpressionEstimate.status == ImpressionEstimateStatus.EXCLUDED.value, 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.avg(ImpressionEstimate.confidence_score), 0),
        ).where(*filters)
    )
    row = result.one()
    return ImpressionSummary(
        campaign_id=campaign.id,
        formula_version=settings.impression_formula_version,
        estimated_impressions=quantize_2(Decimal(str(row[0] or 0))),
        trip_count=int(row[1] or 0),
        estimated_trip_count=int(row[2] or 0),
        insufficient_data_trip_count=int(row[3] or 0),
        excluded_trip_count=int(row[4] or 0),
        average_confidence_score=quantize_4(Decimal(str(row[5] or 0))),
        start_at=start_at,
        end_at=end_at,
    )
