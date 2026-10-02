from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

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
    AdminFraudFlagListItemRead,
    AdminFraudFlagListMoneyEffectRead,
    AdminFraudFlagRead,
    AdminTripRouteRead,
    AnalyticsRecomputeRequest,
    DriverTripAnalyticsSummary,
    FraudFlagListResponse,
    FraudFlagMoneyEffectRead,
    FraudFlagRead,
    FraudFlagResolveRequest,
    TripAnalyticsRead,
)
from app.services.admin_trip_review import read_flag_route
from app.services.audit import create_audit_event
from app.services.earnings_release import fraud_flag_money_effect
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
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
        reviewed_by_user_id=flag.reviewed_by_user_id,
        reviewed_at=flag.reviewed_at,
        resolution_note=flag.resolution_note,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
    )


async def admin_fraud_flag_response(
    session: AsyncSession,
    *,
    flag: FraudFlag,
    review_sla_days: int,
) -> AdminFraudFlagRead:
    base = fraud_flag_response(flag)
    effect = await fraud_flag_money_effect(session, flag=flag)
    return AdminFraudFlagRead(
        **base.model_dump(),
        review_due_at=flag.detected_at + timedelta(days=review_sla_days),
        escalated_at=flag.escalated_at,
        money_effect=FraudFlagMoneyEffectRead(
            available_net=effect.available_net,
            currency=effect.currency,
            reversal_entry_id=effect.reversal_entry_id,
            reversal_recommended=effect.reversal_recommended,
        ),
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
    computation = await recompute_trip_analytics(
        session,
        trip_id=trip_id,
        metadata=payload.metadata if payload is not None else {},
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.trip_analytics.recomputed",
        entity_type="trip_analytics",
        entity_id=str(computation.analytics.id),
        metadata={
            "trip_session_id": str(trip_id),
            "formula_version": computation.analytics.formula_version,
        },
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
    settings: SettingsDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: FraudFlagStatus | None = None,
    severity: FraudFlagSeverity | None = None,
    flag_type: FraudFlagType | None = None,
    campaign_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    trip_session_id: UUID | None = None,
    oldest_first: bool = False,
    flag_id: UUID | None = None,
    unresolved_only: bool = False,
    group_by_trip: bool = False,
) -> FraudFlagListResponse:
    del current_user
    flags, total = await list_fraud_flags(
        session,
        oldest_first=oldest_first,
        flag_id=flag_id,
        unresolved_only=unresolved_only,
        group_by_trip=group_by_trip,
        limit=limit,
        offset=offset,
        flag_status=status,
        severity=severity,
        flag_type=flag_type,
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        trip_session_id=trip_session_id,
    )
    from app.services.admin_worklist_reads import flag_list_money, trip_contexts

    money = await flag_list_money(session, flags)
    context = await trip_contexts(session, {flag.trip_session_id for flag in flags})
    from sqlalchemy import func, select

    counts = (
        {
            trip_id: count
            for trip_id, count in (
                await session.execute(
                    select(FraudFlag.trip_session_id, func.count())
                    .where(
                        FraudFlag.trip_session_id.in_({flag.trip_session_id for flag in flags}),
                        FraudFlag.status.in_(("open", "acknowledged")),
                    )
                    .group_by(FraudFlag.trip_session_id)
                )
            ).all()
        }
        if flags
        else {}
    )
    return FraudFlagListResponse(
        items=[
            AdminFraudFlagListItemRead(
                **fraud_flag_response(flag).model_dump(),
                review_due_at=flag.detected_at + timedelta(days=settings.fraud_review_sla_days),
                escalated_at=flag.escalated_at,
                money_effect=AdminFraudFlagListMoneyEffectRead(**money[flag.id]),
                **{
                    key: value
                    for key, value in context.get(flag.trip_session_id, {}).items()
                    if key in {"driver_name", "campaign_name", "vehicle_plate", "trip_started_at"}
                },
                problem_count=counts.get(flag.trip_session_id, 0),
            )
            for flag in flags
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/fraud-flags/{flag_id}/route",
    response_model=AdminTripRouteRead,
    summary="Read recorded trip locations for a staff trip review",
)
async def admin_read_flag_route(
    flag_id: UUID,
    response: Response,
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminTripRouteRead:
    response.headers["Cache-Control"] = "private, no-store"
    flag, points, total = await read_flag_route(
        session, flag_id=flag_id, limit=limit, offset=offset
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.fraud_review.route_read",
        entity_type="fraud_flag",
        entity_id=str(flag.id),
        metadata={
            "trip_session_id": str(flag.trip_session_id),
            "limit": limit,
            "offset": offset,
            "point_count": len(points),
        },
    )
    await session.commit()
    return AdminTripRouteRead(
        flag_id=flag.id,
        trip_session_id=flag.trip_session_id,
        items=points,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/fraud-flags/{flag_id}/review/acknowledge",
    response_model=AdminFraudFlagRead,
    summary="Acknowledge a fraud flag for staff review",
)
async def admin_acknowledge_fraud_flag(
    flag_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminFraudFlagRead:
    result = await acknowledge_fraud_flag(
        session,
        flag_id=flag_id,
        actor_user_id=current_user.id,
    )
    response = await admin_fraud_flag_response(
        session,
        flag=result.flag,
        review_sla_days=settings.fraud_review_sla_days,
    )
    await session.commit()
    return response


@router.post(
    "/admin/fraud-flags/{flag_id}/review/resolve",
    response_model=AdminFraudFlagRead,
    summary="Resolve a fraud flag review",
)
async def admin_resolve_fraud_flag(
    flag_id: UUID,
    payload: FraudFlagResolveRequest,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminFraudFlagRead:
    result = await resolve_fraud_flag(
        session,
        flag_id=flag_id,
        actor_user_id=current_user.id,
        outcome=payload.outcome,
        resolution_note=payload.note,
    )
    response = await admin_fraud_flag_response(
        session,
        flag=result.flag,
        review_sla_days=settings.fraud_review_sla_days,
    )
    await session.commit()
    return response


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
