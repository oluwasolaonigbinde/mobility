from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.vehicle import VehicleType
from app.schemas.heatmaps import HeatmapFeatureCollection
from app.services.heatmaps import (
    admin_heatmap,
    parse_heatmap_query,
)

router = APIRouter(tags=["Heatmaps"])


@router.get(
    "/admin/heatmap",
    response_model=HeatmapFeatureCollection,
    summary="Read admin heatmap",
    description="Return bounded aggregate GeoJSON heatmap cells across campaigns for admins.",
)
async def admin_get_heatmap(
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    bbox: str | None = Query(
        default=None,
        description="Required min_lon,min_lat,max_lon,max_lat bbox.",
    ),
    resolution_m: Annotated[
        int | None,
        Query(ge=1, description="Grid cell size in meters."),
    ] = None,
    metric: str = Query(
        default="ping_count",
        description="One of ping_count, trip_count, distance_m, estimated_impressions.",
    ),
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
        user_id=current_user.id,
        query=query,
        settings=settings,
        campaign_id=campaign_id,
        organization_id=organization_id,
        vehicle_type=vehicle_type.value if vehicle_type is not None else None,
    )
