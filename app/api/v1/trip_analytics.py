from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    FraudFlagType,
    TripAnalytics,
)
from app.schemas.trip_analytics import (
    AnalyticsRecomputeRequest,
    DriverTripAnalyticsSummary,
    FraudFlagListResponse,
    FraudFlagRead,
    TripAnalyticsRead,
)
from app.services.trip_analytics import (
    AnalyticsComputation,
    get_driver_trip_analytics,
    get_trip_analytics_with_flags,
    list_fraud_flags,
    recompute_trip_analytics,
)

router = APIRouter(tags=["Analytics"])


def fraud_flag_response(flag: FraudFlag) -> FraudFlagRead:
    return FraudFlagRead(
        id=flag.id,
        trip_session_id=flag.trip_session_id,
        trip_analytics_id=flag.trip_analytics_id,
        assignment_id=flag.assignment_id,
        campaign_id=flag.campaign_id,
        driver_profile_id=flag.driver_profile_id,
        vehicle_id=flag.vehicle_id,
        flag_type=flag.flag_type,
        severity=flag.severity,
        status=flag.status,
        description=flag.description,
        evidence=flag.evidence,
        detected_at=flag.detected_at,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
    )


def analytics_response(computation: AnalyticsComputation) -> TripAnalyticsRead:
    analytics = computation.analytics
    return TripAnalyticsRead(
        id=analytics.id,
        trip_session_id=analytics.trip_session_id,
        assignment_id=analytics.assignment_id,
        campaign_id=analytics.campaign_id,
        driver_profile_id=analytics.driver_profile_id,
        vehicle_id=analytics.vehicle_id,
        formula_version=analytics.formula_version,
        status=analytics.status,
        ping_count=analytics.ping_count,
        valid_ping_count=analytics.valid_ping_count,
        invalid_ping_count=analytics.invalid_ping_count,
        started_at=analytics.started_at,
        ended_at=analytics.ended_at,
        first_ping_at=analytics.first_ping_at,
        last_ping_at=analytics.last_ping_at,
        duration_seconds=analytics.duration_seconds,
        active_tracking_seconds=analytics.active_tracking_seconds,
        moving_seconds=analytics.moving_seconds,
        stationary_seconds=analytics.stationary_seconds,
        distance_m=analytics.distance_m,
        avg_speed_mps=analytics.avg_speed_mps,
        max_observed_speed_mps=analytics.max_observed_speed_mps,
        avg_accuracy_m=analytics.avg_accuracy_m,
        poor_accuracy_ping_count=analytics.poor_accuracy_ping_count,
        target_zone_distance_m=analytics.target_zone_distance_m,
        bonus_zone_distance_m=analytics.bonus_zone_distance_m,
        exclusion_zone_distance_m=analytics.exclusion_zone_distance_m,
        target_zone_seconds=analytics.target_zone_seconds,
        bonus_zone_seconds=analytics.bonus_zone_seconds,
        exclusion_zone_seconds=analytics.exclusion_zone_seconds,
        quality_score=analytics.quality_score,
        computed_at=analytics.computed_at,
        metadata=analytics.analytics_metadata,
        created_at=analytics.created_at,
        updated_at=analytics.updated_at,
        fraud_flags=[fraud_flag_response(flag) for flag in computation.fraud_flags],
    )


def driver_summary_response(analytics: TripAnalytics, flag_counts: dict[str, int]):
    return DriverTripAnalyticsSummary(
        trip_id=analytics.trip_session_id,
        analytics_status=analytics.status,
        distance_m=analytics.distance_m,
        duration_seconds=analytics.duration_seconds,
        moving_seconds=analytics.moving_seconds,
        stationary_seconds=analytics.stationary_seconds,
        quality_score=analytics.quality_score,
        has_flags=sum(flag_counts.values()) > 0,
        flag_counts=flag_counts,
    )


@router.post(
    "/admin/trips/{trip_id}/recompute-analytics",
    response_model=TripAnalyticsRead,
    summary="Recompute analytics for an ended trip",
)
async def admin_recompute_trip_analytics(
    trip_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    payload: Annotated[AnalyticsRecomputeRequest | None, Body()] = None,
) -> TripAnalyticsRead:
    del current_user
    computation = await recompute_trip_analytics(
        session,
        trip_id=trip_id,
        metadata=payload.metadata if payload is not None else {},
        settings=settings,
    )
    await session.commit()
    return analytics_response(computation)


@router.get(
    "/admin/trips/{trip_id}/analytics",
    response_model=TripAnalyticsRead,
    summary="Read analytics for a trip",
)
async def admin_get_trip_analytics(
    trip_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> TripAnalyticsRead:
    del current_user
    return analytics_response(await get_trip_analytics_with_flags(session, trip_id=trip_id))


@router.get(
    "/admin/fraud-flags",
    response_model=FraudFlagListResponse,
    summary="List fraud and anomaly flags",
)
async def admin_list_fraud_flags(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: FraudFlagStatus | None = None,
    severity: FraudFlagSeverity | None = None,
    flag_type: FraudFlagType | None = None,
    campaign_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    trip_session_id: UUID | None = None,
) -> FraudFlagListResponse:
    del current_user
    flags, total = await list_fraud_flags(
        session,
        limit=limit,
        offset=offset,
        flag_status=status,
        severity=severity,
        flag_type=flag_type,
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        trip_session_id=trip_session_id,
    )
    return FraudFlagListResponse(
        items=[fraud_flag_response(flag) for flag in flags],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/driver/trips/{trip_id}/analytics-summary",
    response_model=DriverTripAnalyticsSummary,
    summary="Read current driver's trip analytics summary",
)
async def driver_get_trip_analytics_summary(
    trip_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> DriverTripAnalyticsSummary:
    analytics, flag_counts = await get_driver_trip_analytics(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
    )
    return driver_summary_response(analytics, flag_counts)
