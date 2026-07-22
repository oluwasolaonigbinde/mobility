import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.campaign_zone import CampaignZoneType
from app.models.driver import DriverProfile
from app.models.trip import LocationPing, TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    FraudFlagType,
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.services.campaign_assignments import get_driver_profile_for_user
from app.services.campaigns import comparable_campaign_datetime
from app.services.provenance import stable_source_fingerprint
from app.services.trips import trip_not_found

DECIMAL_2 = Decimal("0.01")
DECIMAL_4 = Decimal("0.0001")
ANALYTICS_ROW_CONSTRAINTS = frozenset({"uq_trip_analytics_trip_session_id"})
OPEN_FLAG_CONSTRAINTS = frozenset({"uq_fraud_flags_trip_open_flag_type"})
ANALYTICS_FINGERPRINT_FIELDS = (
    "assignment_id",
    "campaign_id",
    "driver_profile_id",
    "vehicle_id",
    "formula_version",
    "status",
    "ping_count",
    "valid_ping_count",
    "invalid_ping_count",
    "started_at",
    "ended_at",
    "first_ping_at",
    "last_ping_at",
    "duration_seconds",
    "active_tracking_seconds",
    "moving_seconds",
    "stationary_seconds",
    "distance_m",
    "avg_speed_mps",
    "max_observed_speed_mps",
    "avg_accuracy_m",
    "poor_accuracy_ping_count",
    "target_zone_distance_m",
    "bonus_zone_distance_m",
    "exclusion_zone_distance_m",
    "target_zone_seconds",
    "bonus_zone_seconds",
    "exclusion_zone_seconds",
    "quality_score",
)


@dataclass(frozen=True)
class SegmentMeasurement:
    distance_m: Decimal
    target_intersects: bool
    bonus_intersects: bool
    exclusion_intersects: bool


@dataclass(frozen=True)
class AnalyticsMetrics:
    poor_accuracy_ratio: float
    stationary_ratio: float
    excessive_gap_count: int
    max_ping_gap_seconds: int
    impossible_speed_count: int
    ignored_segment_count: int
    segment_count: int
    future_ping_count: int
    start_end_distance_m: Decimal | None


@dataclass(frozen=True)
class AnalyticsComputation:
    analytics: TripAnalytics
    fraud_flags: list[FraudFlag]


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(value: datetime) -> datetime:
    return comparable_campaign_datetime(value).astimezone(UTC)


def elapsed_seconds(start: datetime | None, end: datetime | None) -> int:
    if start is None or end is None:
        return 0
    return max(0, int((as_aware_utc(end) - as_aware_utc(start)).total_seconds()))


def decimal_from_number(value: object, quantum: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(quantum)


def ratio(numerator: int | Decimal, denominator: int | Decimal) -> float:
    if denominator == 0:
        return 0.0
    return float(Decimal(numerator) / Decimal(denominator))


def analytics_not_found() -> AppError:
    return AppError(
        "ANALYTICS_NOT_FOUND",
        "Trip analytics were not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def analytics_formula_version_mismatch(
    *,
    expected: str,
    actual: str,
) -> AppError:
    return AppError(
        "ANALYTICS_FORMULA_VERSION_MISMATCH",
        "Trip analytics must be recomputed with the current formula before downstream processing",
        status_code=status.HTTP_409_CONFLICT,
        details={"expected_formula_version": expected, "actual_formula_version": actual},
    )


def ensure_current_analytics_formula(analytics: TripAnalytics, settings: Settings) -> None:
    if analytics.formula_version != settings.route_analytics_formula_version:
        raise analytics_formula_version_mismatch(
            expected=settings.route_analytics_formula_version,
            actual=analytics.formula_version,
        )


def analytics_output_fingerprint(analytics: TripAnalytics | dict) -> str:
    values = {
        field: analytics[field] if isinstance(analytics, dict) else getattr(analytics, field)
        for field in ANALYTICS_FINGERPRINT_FIELDS
    }
    return stable_source_fingerprint(values)


def ensure_postgis(session: AsyncSession) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise AppError(
            "POSTGIS_REQUIRED",
            "Route analytics requires PostgreSQL/PostGIS",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def is_valid_ping(ping: LocationPing) -> bool:
    return (
        not isinstance(ping.latitude, bool)
        and not isinstance(ping.longitude, bool)
        and isinstance(ping.latitude, int | float)
        and isinstance(ping.longitude, int | float)
        and math.isfinite(ping.latitude)
        and math.isfinite(ping.longitude)
        and -90 <= ping.latitude <= 90
        and -180 <= ping.longitude <= 180
    )


async def get_admin_trip(session: AsyncSession, trip_id: UUID) -> TripSession:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    return trip


def ensure_trip_ended(trip: TripSession) -> None:
    if trip.status != TripSessionStatus.ENDED.value or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_ENDED",
            "Trip analytics can only be computed for ended trips",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def load_ordered_pings(session: AsyncSession, trip_id: UUID) -> list[LocationPing]:
    result = await session.execute(
        select(LocationPing)
        .where(LocationPing.trip_session_id == trip_id)
        .order_by(
            LocationPing.recorded_at,
            LocationPing.sequence_number.asc().nullslast(),
            LocationPing.created_at,
            LocationPing.id,
        )
    )
    return list(result.scalars().all())


async def measure_segment(
    session: AsyncSession,
    *,
    start_ping_id: UUID,
    end_ping_id: UUID,
    campaign_id: UUID,
) -> SegmentMeasurement:
    result = await session.execute(
        text(
            """
            SELECT
                ST_Distance(start_ping.geom::geography, end_ping.geom::geography) AS distance_m,
                EXISTS (
                    SELECT 1
                    FROM campaign_zones
                    WHERE campaign_id = :campaign_id
                      AND zone_type = :target_zone_type
                      AND ST_Intersects(ST_MakeLine(start_ping.geom, end_ping.geom), geom)
                ) AS target_intersects,
                EXISTS (
                    SELECT 1
                    FROM campaign_zones
                    WHERE campaign_id = :campaign_id
                      AND zone_type = :bonus_zone_type
                      AND ST_Intersects(ST_MakeLine(start_ping.geom, end_ping.geom), geom)
                ) AS bonus_intersects,
                EXISTS (
                    SELECT 1
                    FROM campaign_zones
                    WHERE campaign_id = :campaign_id
                      AND zone_type = :exclusion_zone_type
                      AND ST_Intersects(ST_MakeLine(start_ping.geom, end_ping.geom), geom)
                ) AS exclusion_intersects
            FROM location_pings AS start_ping
            JOIN location_pings AS end_ping ON end_ping.id = :end_ping_id
            WHERE start_ping.id = :start_ping_id
            """
        ),
        {
            "start_ping_id": start_ping_id,
            "end_ping_id": end_ping_id,
            "campaign_id": campaign_id,
            "target_zone_type": CampaignZoneType.TARGET.value,
            "bonus_zone_type": CampaignZoneType.BONUS.value,
            "exclusion_zone_type": CampaignZoneType.EXCLUSION.value,
        },
    )
    row = result.mappings().one()
    return SegmentMeasurement(
        distance_m=decimal_from_number(row["distance_m"], DECIMAL_4),
        target_intersects=bool(row["target_intersects"]),
        bonus_intersects=bool(row["bonus_intersects"]),
        exclusion_intersects=bool(row["exclusion_intersects"]),
    )


async def measure_ping_distance(
    session: AsyncSession,
    *,
    start_ping_id: UUID,
    end_ping_id: UUID,
) -> Decimal:
    result = await session.execute(
        text(
            """
            SELECT ST_Distance(start_ping.geom::geography, end_ping.geom::geography) AS distance_m
            FROM location_pings AS start_ping
            JOIN location_pings AS end_ping ON end_ping.id = :end_ping_id
            WHERE start_ping.id = :start_ping_id
            """
        ),
        {"start_ping_id": start_ping_id, "end_ping_id": end_ping_id},
    )
    return decimal_from_number(result.mappings().one()["distance_m"], DECIMAL_4)


def compute_quality_score(
    *,
    poor_accuracy_ratio: float,
    excessive_gap_count: int,
    segment_count: int,
    impossible_speed_count: int,
    stationary_ratio: float,
    settings: Settings,
) -> Decimal:
    score = Decimal("1.0")
    score -= Decimal("0.30") * Decimal(str(poor_accuracy_ratio))
    gap_ratio = Decimal(excessive_gap_count) / Decimal(max(segment_count, 1))
    score -= min(Decimal("0.25"), Decimal("0.25") * gap_ratio)
    if impossible_speed_count > 0:
        score -= Decimal("0.25")
    if stationary_ratio > settings.route_analytics_stationary_ratio_threshold:
        score -= Decimal("0.20") * Decimal(str(stationary_ratio))
    return max(Decimal("0"), min(Decimal("1"), score)).quantize(DECIMAL_4)


def fraud_flag(
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    flag_type: FraudFlagType,
    severity: FraudFlagSeverity,
    description: str,
    evidence: dict,
    detected_at: datetime,
) -> FraudFlag:
    return FraudFlag(
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=trip.assignment_id,
        campaign_id=trip.campaign_id,
        driver_profile_id=trip.driver_profile_id,
        vehicle_id=trip.vehicle_id,
        flag_type=flag_type.value,
        severity=severity.value,
        status=FraudFlagStatus.OPEN.value,
        description=description,
        evidence=evidence,
        detected_at=detected_at,
    )


def build_fraud_flags(
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    metrics: AnalyticsMetrics,
    settings: Settings,
    detected_at: datetime,
) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    if analytics.valid_ping_count < settings.route_analytics_min_valid_pings:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.INSUFFICIENT_PINGS,
                severity=FraudFlagSeverity.MEDIUM,
                description="Trip has fewer valid pings than required for analytics.",
                evidence={
                    "valid_ping_count": analytics.valid_ping_count,
                    "min_valid_pings": settings.route_analytics_min_valid_pings,
                },
                detected_at=detected_at,
            )
        )
    if metrics.impossible_speed_count > 0:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.IMPOSSIBLE_SPEED,
                severity=FraudFlagSeverity.HIGH,
                description="Observed speed exceeded configured threshold.",
                evidence={
                    "max_observed_speed_mps": float(analytics.max_observed_speed_mps or 0),
                    "offending_segment_count": metrics.impossible_speed_count,
                    "threshold_mps": settings.route_analytics_impossible_speed_mps,
                },
                detected_at=detected_at,
            )
        )
    if metrics.poor_accuracy_ratio > settings.route_analytics_poor_accuracy_ratio_threshold:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.POOR_ACCURACY,
                severity=FraudFlagSeverity.MEDIUM,
                description="Poor GPS accuracy ratio exceeded configured threshold.",
                evidence={
                    "poor_accuracy_ratio": metrics.poor_accuracy_ratio,
                    "poor_accuracy_ping_count": analytics.poor_accuracy_ping_count,
                    "threshold_ratio": settings.route_analytics_poor_accuracy_ratio_threshold,
                },
                detected_at=detected_at,
            )
        )
    if metrics.stationary_ratio > settings.route_analytics_stationary_ratio_threshold:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.STATIONARY_TRIP,
                severity=FraudFlagSeverity.MEDIUM,
                description="Stationary time ratio exceeded configured threshold.",
                evidence={
                    "stationary_seconds": analytics.stationary_seconds,
                    "stationary_ratio": metrics.stationary_ratio,
                    "threshold_ratio": settings.route_analytics_stationary_ratio_threshold,
                },
                detected_at=detected_at,
            )
        )
    if metrics.excessive_gap_count > 0:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.EXCESSIVE_PING_GAP,
                severity=FraudFlagSeverity.MEDIUM,
                description="Consecutive location pings had an excessive time gap.",
                evidence={
                    "max_gap_seconds": metrics.max_ping_gap_seconds,
                    "gap_count": metrics.excessive_gap_count,
                    "threshold_seconds": settings.route_analytics_max_ping_gap_seconds,
                },
                detected_at=detected_at,
            )
        )
    if metrics.future_ping_count > 0:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.FUTURE_TIMESTAMP,
                severity=FraudFlagSeverity.MEDIUM,
                description="Stored location pings include future timestamps.",
                evidence={
                    "future_ping_count": metrics.future_ping_count,
                    "future_skew_seconds": settings.location_ping_future_skew_seconds,
                },
                detected_at=detected_at,
            )
        )
    if (
        metrics.start_end_distance_m is not None
        and analytics.distance_m > Decimal(str(settings.route_analytics_looping_min_distance_m))
        and metrics.start_end_distance_m <= Decimal(str(settings.route_analytics_looping_radius_m))
        and metrics.start_end_distance_m / max(analytics.distance_m, Decimal("1")) <= Decimal("0.1")
    ):
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.ROUTE_LOOPING,
                severity=FraudFlagSeverity.LOW,
                description="Trip route ended close to its start after significant distance.",
                evidence={
                    "start_end_distance_m": float(metrics.start_end_distance_m),
                    "total_distance_m": float(analytics.distance_m),
                    "looping_radius_m": settings.route_analytics_looping_radius_m,
                    "looping_min_distance_m": settings.route_analytics_looping_min_distance_m,
                },
                detected_at=detected_at,
            )
        )
    if analytics.exclusion_zone_distance_m > 0 or analytics.exclusion_zone_seconds > 0:
        flags.append(
            fraud_flag(
                trip=trip,
                analytics=analytics,
                flag_type=FraudFlagType.EXCLUSION_ZONE_PRESENCE,
                severity=FraudFlagSeverity.MEDIUM,
                description="Trip route intersected an exclusion zone.",
                evidence={
                    "exclusion_zone_distance_m": float(analytics.exclusion_zone_distance_m),
                    "exclusion_zone_seconds": analytics.exclusion_zone_seconds,
                },
                detected_at=detected_at,
            )
        )
    return flags


async def upsert_analytics(
    session: AsyncSession,
    *,
    trip: TripSession,
    values: dict,
) -> TripAnalytics:
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
    )
    if analytics is None:
        candidate = TripAnalytics(trip_session_id=trip.id, **values)
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(
                exc,
                constraints=ANALYTICS_ROW_CONSTRAINTS,
            ):
                raise
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
            )
            if analytics is None:
                raise
        else:
            analytics = candidate
    for field, value in values.items():
        setattr(analytics, field, value)
    await session.flush()
    await session.refresh(analytics)
    return analytics


async def replace_open_fraud_flags(
    session: AsyncSession,
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    metrics: AnalyticsMetrics,
    settings: Settings,
    detected_at: datetime,
) -> list[FraudFlag]:
    for attempt in range(2):
        flags = build_fraud_flags(
            trip=trip,
            analytics=analytics,
            metrics=metrics,
            settings=settings,
            detected_at=detected_at,
        )
        try:
            async with session.begin_nested():
                await session.execute(
                    delete(FraudFlag).where(
                        FraudFlag.trip_session_id == trip.id,
                        FraudFlag.status == FraudFlagStatus.OPEN.value,
                    )
                )
                session.add_all(flags)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(
                exc,
                constraints=OPEN_FLAG_CONSTRAINTS,
            ):
                raise
            if attempt == 1:
                raise
            continue
        for flag in flags:
            await session.refresh(flag)
        return flags
    raise AssertionError("open fraud flag replacement exhausted retries")


async def recompute_trip_analytics(
    session: AsyncSession,
    *,
    trip_id: UUID,
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
) -> AnalyticsComputation:
    ensure_postgis(session)
    now = now or utc_now()
    trip = await get_admin_trip(session, trip_id)
    ensure_trip_ended(trip)

    pings = await load_ordered_pings(session, trip.id)
    valid_pings = [ping for ping in pings if is_valid_ping(ping)]
    ping_count = len(pings)
    valid_ping_count = len(valid_pings)
    poor_accuracy_ping_count = sum(
        1
        for ping in valid_pings
        if ping.accuracy_m is not None
        and ping.accuracy_m > settings.route_analytics_poor_accuracy_threshold_m
    )
    poor_accuracy_ratio = ratio(poor_accuracy_ping_count, valid_ping_count)
    average_accuracy_values = [
        Decimal(str(ping.accuracy_m)) for ping in valid_pings if ping.accuracy_m is not None
    ]
    avg_accuracy_m = (
        (sum(average_accuracy_values) / Decimal(len(average_accuracy_values))).quantize(DECIMAL_2)
        if average_accuracy_values
        else None
    )
    first_ping_at = valid_pings[0].recorded_at if valid_pings else None
    last_ping_at = valid_pings[-1].recorded_at if valid_pings else None
    duration_seconds = elapsed_seconds(trip.started_at, trip.ended_at)
    active_tracking_seconds = elapsed_seconds(first_ping_at, last_ping_at)

    total_distance_m = Decimal("0")
    target_zone_distance_m = Decimal("0")
    bonus_zone_distance_m = Decimal("0")
    exclusion_zone_distance_m = Decimal("0")
    target_zone_seconds = 0
    bonus_zone_seconds = 0
    exclusion_zone_seconds = 0
    moving_seconds = 0
    stationary_seconds = 0
    segment_time_seconds = 0
    ignored_segment_count = 0
    excessive_gap_count = 0
    max_ping_gap_seconds = 0
    impossible_speed_count = 0
    max_observed_speed_mps: Decimal | None = None

    if valid_ping_count >= settings.route_analytics_min_valid_pings:
        for start_ping, end_ping in zip(valid_pings, valid_pings[1:], strict=False):
            delta_seconds = elapsed_seconds(start_ping.recorded_at, end_ping.recorded_at)
            if delta_seconds <= 0:
                ignored_segment_count += 1
                continue
            segment_time_seconds += delta_seconds
            max_ping_gap_seconds = max(max_ping_gap_seconds, delta_seconds)
            if delta_seconds > settings.route_analytics_max_ping_gap_seconds:
                excessive_gap_count += 1

            measurement = await measure_segment(
                session,
                start_ping_id=start_ping.id,
                end_ping_id=end_ping.id,
                campaign_id=trip.campaign_id,
            )
            speed_mps = (measurement.distance_m / Decimal(delta_seconds)).quantize(DECIMAL_4)
            total_distance_m += measurement.distance_m
            max_observed_speed_mps = (
                speed_mps
                if max_observed_speed_mps is None
                else max(max_observed_speed_mps, speed_mps)
            )
            if speed_mps > Decimal(str(settings.route_analytics_impossible_speed_mps)):
                impossible_speed_count += 1
            if speed_mps >= Decimal(str(settings.route_analytics_moving_speed_mps)):
                moving_seconds += delta_seconds
            else:
                stationary_seconds += delta_seconds
            if measurement.target_intersects:
                target_zone_distance_m += measurement.distance_m
                target_zone_seconds += delta_seconds
            if measurement.bonus_intersects:
                bonus_zone_distance_m += measurement.distance_m
                bonus_zone_seconds += delta_seconds
            if measurement.exclusion_intersects:
                exclusion_zone_distance_m += measurement.distance_m
                exclusion_zone_seconds += delta_seconds

    avg_speed_mps = (
        (total_distance_m / Decimal(segment_time_seconds)).quantize(DECIMAL_4)
        if segment_time_seconds
        else None
    )
    stationary_ratio = ratio(stationary_seconds, segment_time_seconds)
    future_limit = now + timedelta(seconds=settings.location_ping_future_skew_seconds)
    future_ping_count = sum(
        1 for ping in valid_pings if as_aware_utc(ping.recorded_at) > future_limit
    )
    start_end_distance_m = (
        await measure_ping_distance(
            session,
            start_ping_id=valid_pings[0].id,
            end_ping_id=valid_pings[-1].id,
        )
        if valid_ping_count >= settings.route_analytics_min_valid_pings
        else None
    )
    status_value = (
        TripAnalyticsStatus.COMPUTED.value
        if valid_ping_count >= settings.route_analytics_min_valid_pings
        else TripAnalyticsStatus.INSUFFICIENT_DATA.value
    )
    quality_score = (
        compute_quality_score(
            poor_accuracy_ratio=poor_accuracy_ratio,
            excessive_gap_count=excessive_gap_count,
            segment_count=max(valid_ping_count - 1 - ignored_segment_count, 0),
            impossible_speed_count=impossible_speed_count,
            stationary_ratio=stationary_ratio,
            settings=settings,
        )
        if status_value == TripAnalyticsStatus.COMPUTED.value
        else Decimal("0.0000")
    )
    metrics = AnalyticsMetrics(
        poor_accuracy_ratio=poor_accuracy_ratio,
        stationary_ratio=stationary_ratio,
        excessive_gap_count=excessive_gap_count,
        max_ping_gap_seconds=max_ping_gap_seconds,
        impossible_speed_count=impossible_speed_count,
        ignored_segment_count=ignored_segment_count,
        segment_count=max(valid_ping_count - 1 - ignored_segment_count, 0),
        future_ping_count=future_ping_count,
        start_end_distance_m=start_end_distance_m,
    )
    analytics_metadata = {
        "formula_version": settings.route_analytics_formula_version,
        "poor_accuracy_ratio": poor_accuracy_ratio,
        "stationary_ratio": stationary_ratio,
        "excessive_gap_count": excessive_gap_count,
        "impossible_speed_count": impossible_speed_count,
        "ignored_segment_count": ignored_segment_count,
        "future_ping_count": future_ping_count,
        "zone_approximation_method": "whole_segment_attribution_on_postgis_intersection",
        "between_threshold_speed_classification": "stationary",
        "request_metadata": metadata,
    }
    analytics_values = {
        "assignment_id": trip.assignment_id,
        "campaign_id": trip.campaign_id,
        "driver_profile_id": trip.driver_profile_id,
        "vehicle_id": trip.vehicle_id,
        "formula_version": settings.route_analytics_formula_version,
        "status": status_value,
        "ping_count": ping_count,
        "valid_ping_count": valid_ping_count,
        "invalid_ping_count": ping_count - valid_ping_count,
        "started_at": trip.started_at,
        "ended_at": trip.ended_at,
        "first_ping_at": first_ping_at,
        "last_ping_at": last_ping_at,
        "duration_seconds": duration_seconds,
        "active_tracking_seconds": active_tracking_seconds,
        "moving_seconds": moving_seconds,
        "stationary_seconds": stationary_seconds,
        "distance_m": total_distance_m.quantize(DECIMAL_2),
        "avg_speed_mps": avg_speed_mps,
        "max_observed_speed_mps": max_observed_speed_mps,
        "avg_accuracy_m": avg_accuracy_m,
        "poor_accuracy_ping_count": poor_accuracy_ping_count,
        "target_zone_distance_m": target_zone_distance_m.quantize(DECIMAL_2),
        "bonus_zone_distance_m": bonus_zone_distance_m.quantize(DECIMAL_2),
        "exclusion_zone_distance_m": exclusion_zone_distance_m.quantize(DECIMAL_2),
        "target_zone_seconds": target_zone_seconds,
        "bonus_zone_seconds": bonus_zone_seconds,
        "exclusion_zone_seconds": exclusion_zone_seconds,
        "quality_score": quality_score,
        "computed_at": now,
        "analytics_metadata": analytics_metadata,
        "updated_at": now,
    }
    analytics_metadata["output_fingerprint"] = analytics_output_fingerprint(analytics_values)
    analytics = await upsert_analytics(
        session,
        trip=trip,
        values=analytics_values,
    )
    flags = await replace_open_fraud_flags(
        session,
        trip=trip,
        analytics=analytics,
        metrics=metrics,
        settings=settings,
        detected_at=now,
    )
    await session.refresh(analytics)
    return AnalyticsComputation(analytics=analytics, fraud_flags=flags)


async def get_trip_analytics_with_flags(
    session: AsyncSession,
    *,
    trip_id: UUID,
) -> AnalyticsComputation:
    await get_admin_trip(session, trip_id)
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None:
        raise analytics_not_found()
    flags = await list_flags_for_trip(session, trip_id=trip_id)
    return AnalyticsComputation(analytics=analytics, fraud_flags=flags)


async def list_flags_for_trip(session: AsyncSession, *, trip_id: UUID) -> list[FraudFlag]:
    result = await session.execute(
        select(FraudFlag)
        .where(FraudFlag.trip_session_id == trip_id)
        .order_by(FraudFlag.detected_at.desc(), FraudFlag.id)
    )
    return list(result.scalars().all())


async def list_fraud_flags(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    flag_status: str | None,
    severity: str | None,
    flag_type: str | None,
    campaign_id: UUID | None,
    driver_profile_id: UUID | None,
    trip_session_id: UUID | None,
) -> tuple[list[FraudFlag], int]:
    filters = []
    if flag_status is not None:
        filters.append(FraudFlag.status == flag_status)
    if severity is not None:
        filters.append(FraudFlag.severity == severity)
    if flag_type is not None:
        filters.append(FraudFlag.flag_type == flag_type)
    if campaign_id is not None:
        filters.append(FraudFlag.campaign_id == campaign_id)
    if driver_profile_id is not None:
        filters.append(FraudFlag.driver_profile_id == driver_profile_id)
    if trip_session_id is not None:
        filters.append(FraudFlag.trip_session_id == trip_session_id)

    statement = select(FraudFlag)
    count_statement = select(func.count()).select_from(FraudFlag)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(FraudFlag.detected_at.desc(), FraudFlag.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_driver_trip_analytics(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
) -> tuple[TripAnalytics, dict[str, int]]:
    driver_profile: DriverProfile = await get_driver_profile_for_user(session, user_id)
    trip = await session.scalar(
        select(TripSession).where(
            TripSession.id == trip_id,
            TripSession.driver_profile_id == driver_profile.id,
        )
    )
    if trip is None:
        raise trip_not_found()
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
    )
    if analytics is None:
        raise analytics_not_found()

    result = await session.execute(
        select(FraudFlag.severity, func.count(FraudFlag.id))
        .where(
            FraudFlag.trip_session_id == trip.id,
            FraudFlag.status == FraudFlagStatus.OPEN.value,
        )
        .group_by(FraudFlag.severity)
    )
    counts = {severity.value: 0 for severity in FraudFlagSeverity}
    for severity, count in result.all():
        counts[str(severity)] = int(count)
    return analytics, counts
