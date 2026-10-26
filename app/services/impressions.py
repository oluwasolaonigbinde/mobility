from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlagSeverity,
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.services.campaigns import get_advertiser_campaign
from app.services.disclosure import (
    lock_trip_disclosure_snapshot,
    record_governed_trip_output,
    require_governed_advertiser_output,
)
from app.services.fraud_holds import fraud_hold_counts
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import (
    analytics_not_found,
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
)
from app.services.trips import trip_not_found

DECIMAL_2 = Decimal("0.01")
DECIMAL_4 = Decimal("0.0001")
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
class FixedEstimateFactors:
    traffic_density_per_km: Decimal = Decimal(
        str(Settings.impression_default_traffic_density_per_km)
    )
    dwell_impressions_per_minute: Decimal = Decimal(
        str(Settings.impression_default_dwell_impressions_per_minute)
    )
    road_category_weight: Decimal = Decimal("1.0")
    morning_weight: Decimal = Decimal("1.0")
    midday_weight: Decimal = Decimal("1.0")
    evening_weight: Decimal = Decimal("1.0")
    night_weight: Decimal = Decimal("0.7")
    target_zone_weight: Decimal = Decimal("1.0")
    bonus_zone_weight: Decimal = Decimal("1.25")
    exclusion_zone_weight: Decimal = Decimal("0.0")


FIXED_ESTIMATE_FACTORS = FixedEstimateFactors()


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
    profile: FixedEstimateFactors,
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
    source_formula_version = metadata.get("source_analytics_formula_version")
    if source_formula_version is not None:
        return source_formula_version == analytics.formula_version and _normalized_utc(
            estimate.estimated_at
        ) >= _normalized_utc(analytics.computed_at)
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
        values["traffic_density_profile_fingerprint"] = metadata.get(
            "traffic_density_profile_fingerprint"
        )
    else:
        metadata = estimate.estimate_metadata or {}
        values["formula_version"] = estimate.formula_version
        values["traffic_density_profile_id"] = estimate.traffic_density_profile_id
        values["source_analytics_fingerprint"] = metadata.get("source_analytics_fingerprint")
        values["fraud_flag_counts"] = metadata.get("fraud_flag_counts")
        values["traffic_density_profile_fingerprint"] = metadata.get(
            "traffic_density_profile_fingerprint"
        )
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


async def get_authoritative_estimate_for_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
    fraud_counts: dict[str, int] | None = None,
    validate_source: bool = True,
) -> ImpressionEstimate | None:
    estimate = await session.scalar(
        select(ImpressionEstimate)
        .where(
            ImpressionEstimate.trip_session_id == trip_id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
            ImpressionEstimate.is_authoritative.is_(True),
        )
        .order_by(ImpressionEstimate.id)
        .limit(1)
    )
    if estimate is None or not validate_source:
        return estimate
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None or analytics.formula_version != settings.route_analytics_formula_version:
        return None
    active_fraud_counts = (
        fraud_counts if fraud_counts is not None else await fraud_hold_counts(session, trip_id)
    )
    return (
        estimate
        if is_current_estimate_for_analytics(
            estimate,
            analytics,
            settings,
            fraud_counts=active_fraud_counts,
        )
        else None
    )


async def current_authoritative_estimates(session, estimates, *, settings):
    """Preserve pinned facts while rejecting stale analytics or active holds."""
    if not estimates:
        return []
    analytics = {
        row.trip_session_id: row
        for row in await session.scalars(
            select(TripAnalytics).where(
                TripAnalytics.trip_session_id.in_({row.trip_session_id for row in estimates})
            )
        )
    }
    valid = []
    for estimate in estimates:
        source = analytics.get(estimate.trip_session_id)
        if source is None or source.formula_version != settings.route_analytics_formula_version:
            continue
        if is_current_estimate_for_analytics(
            estimate,
            source,
            settings,
            fraud_counts=await fraud_hold_counts(session, source.trip_session_id),
        ):
            valid.append(estimate)
    return valid


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


def fraud_multiplier(counts: dict[str, int], settings: Settings) -> Decimal:
    if counts[FraudFlagSeverity.HIGH.value] > 0:
        return Decimal(str(settings.impression_high_fraud_multiplier))
    if counts[FraudFlagSeverity.MEDIUM.value] > 0:
        return Decimal(str(settings.impression_medium_fraud_multiplier))
    if counts[FraudFlagSeverity.LOW.value] > 0:
        return Decimal(str(settings.impression_low_fraud_multiplier))
    return Decimal("1.0")


def profile_metadata(profile: FixedEstimateFactors) -> dict[str, str]:
    return {key: str(value) for key, value in vars(profile).items()}


def estimate_values(
    *,
    analytics: TripAnalytics,
    profile: FixedEstimateFactors,
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
        stationary_minutes * profile.dwell_impressions_per_minute * time_weight * quality_multiplier
    )
    exclusion_zone_adjustment = quantize_2(
        exclusion_zone_distance_km * profile.traffic_density_per_km * profile.exclusion_zone_weight
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


async def estimate_trip_impressions(session, *, trip_id, metadata, settings, now=None):
    trip = await get_trip_for_estimation(session, trip_id)
    analytics = await get_analytics_for_trip(session, trip.id)
    ensure_current_analytics_formula(analytics, settings)
    counts = await fraud_hold_counts(session, trip.id)
    await session.refresh(analytics)
    ensure_current_analytics_formula(analytics, settings)
    pinned = await get_authoritative_estimate_for_trip(
        session, trip_id=trip.id, settings=settings, fraud_counts=counts
    )
    if pinned is not None:
        pinned.estimate_metadata = {
            **pinned.estimate_metadata,
            "request_metadata": metadata,
        }
        await session.flush()
        await session.refresh(pinned)
        return pinned
    source_fingerprint = analytics_output_fingerprint(analytics)
    values = estimate_values(
        analytics=analytics,
        profile=FIXED_ESTIMATE_FACTORS,
        counts=counts,
        request_metadata=metadata,
        settings=settings,
        estimated_at=now or utc_now(),
    )
    values["estimate_metadata"].update(
        {
            "source_analytics_formula_version": analytics.formula_version,
            "source_analytics_computed_at": analytics.computed_at.isoformat(),
            "source_analytics_fingerprint": source_fingerprint,
            "estimate_method": "fixed-default-factors-v1",
        }
    )
    values.update(
        {
            field: getattr(analytics, field)
            for field in (
                "assignment_id",
                "campaign_id",
                "driver_profile_id",
                "vehicle_id",
                "started_at",
                "ended_at",
            )
        }
    )
    values["trip_analytics_id"] = analytics.id
    values["estimate_metadata"]["output_fingerprint"] = impression_output_fingerprint(
        values,
        formula_version=settings.impression_formula_version,
        traffic_density_profile_id=None,
        source_analytics_fingerprint=source_fingerprint,
    )
    async with session.begin_nested():
        await session.execute(
            update(ImpressionEstimate)
            .where(
                ImpressionEstimate.trip_session_id == trip.id,
                ImpressionEstimate.formula_version == settings.impression_formula_version,
                ImpressionEstimate.is_authoritative.is_(True),
            )
            .values(is_authoritative=False)
        )
        estimate = await session.scalar(
            select(ImpressionEstimate)
            .where(
                ImpressionEstimate.trip_session_id == trip.id,
                ImpressionEstimate.formula_version == settings.impression_formula_version,
                ImpressionEstimate.traffic_density_profile_id.is_(None),
            )
            .with_for_update()
        )
        if estimate is None:
            estimate = ImpressionEstimate(
                trip_session_id=trip.id,
                traffic_density_profile_id=None,
                formula_version=settings.impression_formula_version,
                **values,
            )
            session.add(estimate)
        else:
            for field, value in values.items():
                setattr(estimate, field, value)
        estimate.is_authoritative = True
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
    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.impressions_summary",
        user_id=user_id,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(
        session,
        tenant_id=organization_id,
        campaign_id=campaign.id,
    )
    filters = [
        ImpressionEstimate.campaign_id == campaign.id,
        ImpressionEstimate.formula_version == settings.impression_formula_version,
        ImpressionEstimate.is_authoritative.is_(True),
    ]
    if start_at is not None:
        filters.append(ImpressionEstimate.estimated_at >= start_at)
    if end_at is not None:
        filters.append(ImpressionEstimate.estimated_at <= end_at)

    estimates = list(
        (
            await session.scalars(
                select(ImpressionEstimate).where(*filters).order_by(ImpressionEstimate.id)
            )
        ).all()
    )
    estimates = await current_authoritative_estimates(session, estimates, settings=settings)
    estimated_impressions = sum(
        (Decimal(estimate.estimated_impressions or 0) for estimate in estimates),
        Decimal("0"),
    )
    estimated_count = sum(
        estimate.status == ImpressionEstimateStatus.ESTIMATED.value for estimate in estimates
    )
    insufficient_count = sum(
        estimate.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value
        for estimate in estimates
    )
    excluded_count = sum(
        estimate.status == ImpressionEstimateStatus.EXCLUDED.value for estimate in estimates
    )
    confidence_total = sum(
        (Decimal(estimate.confidence_score or 0) for estimate in estimates),
        Decimal("0"),
    )
    result = ImpressionSummary(
        campaign_id=campaign.id,
        formula_version=settings.impression_formula_version,
        estimated_impressions=quantize_2(estimated_impressions),
        trip_count=len(estimates),
        estimated_trip_count=estimated_count,
        insufficient_data_trip_count=insufficient_count,
        excluded_trip_count=excluded_count,
        average_confidence_score=quantize_4(
            confidence_total / len(estimates) if estimates else Decimal("0")
        ),
        start_at=start_at,
        end_at=end_at,
    )
    await record_governed_trip_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.impressions_summary",
        principal_id=user_id,
        tenant_id=organization_id,
        campaign_id=campaign.id,
        start_at=start_at,
        end_at=end_at,
        filters={},
        result=result,
    )
    return result
