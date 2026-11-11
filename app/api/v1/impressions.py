from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.impression import (
    ImpressionEstimate,
    ImpressionEstimateStatus,
)
from app.schemas.impressions import (
    EstimateImpressionsRequest,
    ImpressionEstimateListResponse,
    ImpressionEstimateRead,
)
from app.services.audit import create_audit_event
from app.services.impressions import (
    estimate_trip_impressions,
    list_impression_estimates,
)

router = APIRouter(tags=["Impressions"])


def estimate_response(estimate: ImpressionEstimate) -> ImpressionEstimateRead:
    return ImpressionEstimateRead(
        id=estimate.id,
        trip_session_id=estimate.trip_session_id,
        trip_analytics_id=estimate.trip_analytics_id,
        assignment_id=estimate.assignment_id,
        campaign_id=estimate.campaign_id,
        driver_profile_id=estimate.driver_profile_id,
        vehicle_id=estimate.vehicle_id,
        formula_version=estimate.formula_version,
        is_authoritative=estimate.is_authoritative,
        status=estimate.status,
        estimated_impressions=estimate.estimated_impressions,
        base_distance_impressions=estimate.base_distance_impressions,
        dwell_impressions=estimate.dwell_impressions,
        target_zone_impressions=estimate.target_zone_impressions,
        bonus_zone_impressions=estimate.bonus_zone_impressions,
        exclusion_zone_adjustment=estimate.exclusion_zone_adjustment,
        quality_multiplier=estimate.quality_multiplier,
        fraud_adjustment_multiplier=estimate.fraud_adjustment_multiplier,
        confidence_score=estimate.confidence_score,
        started_at=estimate.started_at,
        ended_at=estimate.ended_at,
        estimated_at=estimate.estimated_at,
        metadata=estimate.estimate_metadata,
        created_at=estimate.created_at,
        updated_at=estimate.updated_at,
    )


@router.post(
    "/admin/trips/{trip_id}/estimate-impressions",
    response_model=ImpressionEstimateRead,
    summary="Estimate impressions for one analyzed trip",
)
async def admin_estimate_trip_impressions(
    trip_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    payload: Annotated[EstimateImpressionsRequest | None, Body()] = None,
) -> ImpressionEstimateRead:
    estimate = await estimate_trip_impressions(
        session,
        trip_id=trip_id,
        metadata=payload.metadata if payload is not None else {},
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.impression_estimate.computed",
        entity_type="impression_estimate",
        entity_id=str(estimate.id),
        metadata={
            "trip_session_id": str(trip_id),
            "formula_version": estimate.formula_version,
        },
    )
    await session.commit()
    return estimate_response(estimate)


@router.get(
    "/admin/impression-estimates",
    response_model=ImpressionEstimateListResponse,
    summary="List impression estimates",
)
async def admin_list_impression_estimates(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    campaign_id: UUID | None = None,
    trip_session_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    status: ImpressionEstimateStatus | None = None,
) -> ImpressionEstimateListResponse:
    del current_user
    estimates, total = await list_impression_estimates(
        session,
        limit=limit,
        offset=offset,
        campaign_id=campaign_id,
        trip_session_id=trip_session_id,
        driver_profile_id=driver_profile_id,
        vehicle_id=vehicle_id,
        estimate_status=status,
    )
    return ImpressionEstimateListResponse(
        items=[estimate_response(estimate) for estimate in estimates],
        total=total,
        limit=limit,
        offset=offset,
    )
