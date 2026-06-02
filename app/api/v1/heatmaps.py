from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.vehicle import VehicleType
from app.schemas.heatmaps import HeatmapFeatureCollection
from app.services.heatmaps import (
    admin_heatmap,
    advertiser_campaign_heatmap,
    parse_heatmap_query,
)

router = APIRouter(tags=["heatmaps"])


@router.get(
    "/advertiser/campaigns/{campaign_id}/heatmap",
    response_model=HeatmapFeatureCollection,
    summary="Read advertiser campaign heatmap",
)
async def advertiser_get_campaign_heatmap(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    bbox: str | None = None,
    resolution_m: Annotated[int | None, Query(ge=1)] = None,
    metric: str = "ping_count",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> HeatmapFeatureCollection:
    query = parse_heatmap_query(
        bbox=bbox,
        resolution_m=resolution_m,
        metric=metric,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )
    return await advertiser_campaign_heatmap(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        query=query,
        settings=settings,
    )


@router.get(
    "/admin/heatmap",
    response_model=HeatmapFeatureCollection,
    summary="Read admin heatmap",
)
async def admin_get_heatmap(
    _: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    bbox: str | None = None,
    resolution_m: Annotated[int | None, Query(ge=1)] = None,
    metric: str = "ping_count",
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    campaign_id: UUID | None = None,
    organization_id: UUID | None = None,
    vehicle_type: VehicleType | None = None,
) -> HeatmapFeatureCollection:
    query = parse_heatmap_query(
        bbox=bbox,
        resolution_m=resolution_m,
        metric=metric,
        start_at=start_at,
        end_at=end_at,
        settings=settings,
    )
    return await admin_heatmap(
        session,
        query=query,
        settings=settings,
        campaign_id=campaign_id,
        organization_id=organization_id,
        vehicle_type=vehicle_type.value if vehicle_type is not None else None,
    )
