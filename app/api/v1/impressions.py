from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query
from starlette import status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.core.errors import AppError
from app.models.impression import (
    ImpressionEstimate,
    ImpressionEstimateStatus,
    TrafficDensityProfile,
    TrafficDensityProfileStatus,
    TrafficDensityProfileType,
)
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.impressions import (
    CampaignImpressionSummary,
    EstimateImpressionsRequest,
    ImpressionEstimateListResponse,
    ImpressionEstimateRead,
    TrafficDensityProfileCreate,
    TrafficDensityProfileListResponse,
    TrafficDensityProfileRead,
    TrafficDensityProfileUpdate,
)
from app.services.audit import create_audit_event
from app.services.impressions import (
    advertiser_campaign_impression_summary,
    create_traffic_density_profile,
    estimate_trip_impressions,
    get_traffic_density_profile,
    list_impression_estimates,
    list_traffic_density_profiles,
    update_traffic_density_profile,
)

router = APIRouter(tags=["Impressions"])


def ensure_impression_datetime(value: datetime | None, field_name: str) -> datetime | None:
    try:
        return ensure_timezone_aware(value)
    except ValueError as exc:
        raise AppError(
            "VALIDATION_ERROR",
            "Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"errors": [{"loc": ["query", field_name], "msg": str(exc)}]},
        ) from exc


def ensure_impression_date_range(
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start_at = ensure_impression_datetime(start_at, "start_at")
    end_at = ensure_impression_datetime(end_at, "end_at")
    if start_at is not None and end_at is not None and start_at > end_at:
        raise AppError(
            "INVALID_DATE_RANGE",
            "start_at must be before or equal to end_at",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return start_at, end_at


def profile_response(profile: TrafficDensityProfile) -> TrafficDensityProfileRead:
    return TrafficDensityProfileRead(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        profile_type=profile.profile_type,
        traffic_density_per_km=profile.traffic_density_per_km,
        dwell_impressions_per_minute=profile.dwell_impressions_per_minute,
        road_category_weight=profile.road_category_weight,
        morning_weight=profile.morning_weight,
        midday_weight=profile.midday_weight,
        evening_weight=profile.evening_weight,
        night_weight=profile.night_weight,
        target_zone_weight=profile.target_zone_weight,
        bonus_zone_weight=profile.bonus_zone_weight,
        exclusion_zone_weight=profile.exclusion_zone_weight,
        is_default=profile.is_default,
        status=profile.status,
        metadata=profile.profile_metadata,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def estimate_response(estimate: ImpressionEstimate) -> ImpressionEstimateRead:
    return ImpressionEstimateRead(
        id=estimate.id,
        trip_session_id=estimate.trip_session_id,
        trip_analytics_id=estimate.trip_analytics_id,
        assignment_id=estimate.assignment_id,
        campaign_id=estimate.campaign_id,
        driver_profile_id=estimate.driver_profile_id,
        vehicle_id=estimate.vehicle_id,
        traffic_density_profile_id=estimate.traffic_density_profile_id,
        formula_version=estimate.formula_version,
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
    "/admin/traffic-density-profiles",
    response_model=TrafficDensityProfileRead,
    summary="Create a traffic density profile",
)
async def admin_create_traffic_density_profile(
    payload: TrafficDensityProfileCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> TrafficDensityProfileRead:
    profile = await create_traffic_density_profile(session, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.traffic_density_profile.created",
        entity_type="traffic_density_profile",
        entity_id=str(profile.id),
        metadata={"name": profile.name, "profile_type": profile.profile_type},
    )
    await session.commit()
    return profile_response(profile)


@router.get(
    "/admin/traffic-density-profiles",
    response_model=TrafficDensityProfileListResponse,
    summary="List traffic density profiles",
)
async def admin_list_traffic_density_profiles(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: TrafficDensityProfileStatus | None = None,
    profile_type: TrafficDensityProfileType | None = None,
    is_default: bool | None = None,
) -> TrafficDensityProfileListResponse:
    del current_user
    profiles, total = await list_traffic_density_profiles(
        session,
        limit=limit,
        offset=offset,
        profile_status=status,
        profile_type=profile_type,
        is_default=is_default,
    )
    return TrafficDensityProfileListResponse(
        items=[profile_response(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/traffic-density-profiles/{profile_id}",
    response_model=TrafficDensityProfileRead,
    summary="Read a traffic density profile",
)
async def admin_get_traffic_density_profile(
    profile_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> TrafficDensityProfileRead:
    del current_user
    return profile_response(await get_traffic_density_profile(session, profile_id))


@router.patch(
    "/admin/traffic-density-profiles/{profile_id}",
    response_model=TrafficDensityProfileRead,
    summary="Update a traffic density profile",
)
async def admin_update_traffic_density_profile(
    profile_id: UUID,
    payload: TrafficDensityProfileUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> TrafficDensityProfileRead:
    profile = await update_traffic_density_profile(session, profile_id=profile_id, payload=payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.traffic_density_profile.updated",
        entity_type="traffic_density_profile",
        entity_id=str(profile.id),
        metadata={"changed_fields": sorted(payload.model_dump(exclude_unset=True))},
    )
    await session.commit()
    return profile_response(profile)


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
        traffic_density_profile_id=(
            payload.traffic_density_profile_id if payload is not None else None
        ),
        metadata=payload.metadata if payload is not None else {},
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.impression_estimate.created",
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
    traffic_density_profile_id: UUID | None = None,
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
        traffic_density_profile_id=traffic_density_profile_id,
    )
    return ImpressionEstimateListResponse(
        items=[estimate_response(estimate) for estimate in estimates],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/impressions/summary",
    response_model=CampaignImpressionSummary,
    summary="Read advertiser campaign impression summary",
)
async def advertiser_get_campaign_impression_summary(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> CampaignImpressionSummary:
    start_at, end_at = ensure_impression_date_range(start_at, end_at)
    summary = await advertiser_campaign_impression_summary(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )
    return CampaignImpressionSummary(
        campaign_id=summary.campaign_id,
        formula_version=summary.formula_version,
        estimated_impressions=summary.estimated_impressions,
        trip_count=summary.trip_count,
        estimated_trip_count=summary.estimated_trip_count,
        insufficient_data_trip_count=summary.insufficient_data_trip_count,
        excluded_trip_count=summary.excluded_trip_count,
        average_confidence_score=summary.average_confidence_score,
        start_at=summary.start_at,
        end_at=summary.end_at,
    )
