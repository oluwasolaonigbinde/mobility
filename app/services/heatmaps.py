import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.schemas.heatmaps import (
    HeatmapFeature,
    HeatmapFeatureCollection,
    HeatmapFeatureProperties,
    HeatmapMetadata,
    HeatmapMetric,
)
from app.services.campaigns import get_advertiser_campaign

DECIMAL_2 = Decimal("0.01")
DECIMAL_4 = Decimal("0.0001")


@dataclass(frozen=True)
class HeatmapQuery:
    bbox: list[float]
    resolution_m: int
    metric: HeatmapMetric
    start_at: datetime | None
    end_at: datetime | None


def decimal_2(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(DECIMAL_2)


def decimal_4(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(DECIMAL_4)


def ensure_aware_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise AppError(
            "VALIDATION_ERROR",
            "Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={
                "errors": [
                    {
                        "loc": ["query", field_name],
                        "msg": "Datetime must include timezone information",
                    }
                ]
            },
        )
    return value


def parse_bbox(value: str | None) -> list[float]:
    if value is None or not value.strip():
        raise AppError(
            "MISSING_BBOX",
            "bbox query parameter is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise invalid_bbox("bbox must contain exactly four comma-separated numbers")
    try:
        bbox = [float(part) for part in parts]
    except ValueError as exc:
        raise invalid_bbox("bbox values must be numeric") from exc
    if not all(math.isfinite(coordinate) for coordinate in bbox):
        raise invalid_bbox("bbox values must be finite")
    min_lon, min_lat, max_lon, max_lat = bbox
    if min_lon < -180 or max_lon > 180:
        raise invalid_bbox("bbox longitude values must be between -180 and 180")
    if min_lat < -90 or max_lat > 90:
        raise invalid_bbox("bbox latitude values must be between -90 and 90")
    if min_lon >= max_lon:
        raise invalid_bbox("bbox min_lon must be less than max_lon")
    if min_lat >= max_lat:
        raise invalid_bbox("bbox min_lat must be less than max_lat")
    return bbox


def invalid_bbox(message: str) -> AppError:
    return AppError("INVALID_BBOX", message, status_code=status.HTTP_400_BAD_REQUEST)


def bbox_area_sq_km(bbox: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    earth_radius_km = 6371.0088
    lon_delta = abs(math.radians(max_lon - min_lon))
    lat_factor = abs(math.sin(math.radians(max_lat)) - math.sin(math.radians(min_lat)))
    return earth_radius_km * earth_radius_km * lon_delta * lat_factor


def parse_heatmap_query(
    *,
    bbox: str | None,
    resolution_m: int | None,
    metric: str,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> HeatmapQuery:
    parsed_bbox = parse_bbox(bbox)
    resolution = (
        settings.heatmap_default_resolution_m if resolution_m is None else resolution_m
    )
    if (
        resolution < settings.heatmap_min_resolution_m
        or resolution > settings.heatmap_max_resolution_m
    ):
        raise AppError(
            "INVALID_HEATMAP_RESOLUTION",
            "resolution_m is outside the configured heatmap bounds",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "min_resolution_m": settings.heatmap_min_resolution_m,
                "max_resolution_m": settings.heatmap_max_resolution_m,
            },
        )
    try:
        parsed_metric = HeatmapMetric(metric)
    except ValueError as exc:
        raise AppError(
            "INVALID_HEATMAP_METRIC",
            "Unsupported heatmap metric",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"supported_metrics": [item.value for item in HeatmapMetric]},
        ) from exc

    start_at = ensure_aware_datetime(start_at, "start_at")
    end_at = ensure_aware_datetime(end_at, "end_at")
    if start_at is not None and end_at is not None:
        if start_at > end_at:
            raise AppError(
                "INVALID_DATE_RANGE",
                "start_at must be before or equal to end_at",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        max_date_range_seconds = settings.heatmap_max_date_range_days * 24 * 60 * 60
        if (end_at - start_at).total_seconds() > max_date_range_seconds:
            raise AppError(
                "HEATMAP_DATE_RANGE_TOO_LARGE",
                "Heatmap date range exceeds the configured maximum",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"max_date_range_days": settings.heatmap_max_date_range_days},
            )

    area_sq_km = bbox_area_sq_km(parsed_bbox)
    if area_sq_km > settings.heatmap_max_bbox_area_sq_km:
        raise AppError(
            "HEATMAP_BBOX_TOO_LARGE",
            "bbox area exceeds the configured heatmap maximum",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "max_bbox_area_sq_km": settings.heatmap_max_bbox_area_sq_km,
                "estimated_bbox_area_sq_km": round(area_sq_km, 4),
            },
        )
    estimated_cells = math.ceil((area_sq_km * 1_000_000) / (resolution * resolution))
    if estimated_cells > settings.heatmap_max_cells:
        raise AppError(
            "HEATMAP_TOO_MANY_CELLS",
            "Requested bbox and resolution would produce too many heatmap cells",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_cells": settings.heatmap_max_cells, "estimated_cells": estimated_cells},
        )
    return HeatmapQuery(
        bbox=parsed_bbox,
        resolution_m=resolution,
        metric=parsed_metric,
        start_at=start_at,
        end_at=end_at,
    )


def ensure_postgis(session: AsyncSession) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise AppError(
            "POSTGIS_REQUIRED",
            "Heatmap aggregation requires PostgreSQL/PostGIS",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def ensure_admin_filter_consistency(
    session: AsyncSession,
    *,
    campaign_id: UUID | None,
    organization_id: UUID | None,
) -> None:
    if campaign_id is None or organization_id is None:
        return
    campaign_org_id = await session.scalar(
        select(Campaign.organization_id).where(Campaign.id == campaign_id)
    )
    if campaign_org_id is not None and campaign_org_id != organization_id:
        raise AppError(
            "INVALID_HEATMAP_FILTERS",
            "campaign_id does not belong to organization_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def advertiser_campaign_heatmap(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    query: HeatmapQuery,
    settings: Settings,
) -> HeatmapFeatureCollection:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    return await build_heatmap(
        session,
        query=query,
        settings=settings,
        campaign_id=campaign.id,
        organization_id=None,
        vehicle_type=None,
        metadata_campaign_id=campaign.id,
        metadata_organization_id=None,
    )


async def admin_heatmap(
    session: AsyncSession,
    *,
    query: HeatmapQuery,
    settings: Settings,
    campaign_id: UUID | None,
    organization_id: UUID | None,
    vehicle_type: str | None,
) -> HeatmapFeatureCollection:
    await ensure_admin_filter_consistency(
        session,
        campaign_id=campaign_id,
        organization_id=organization_id,
    )
    return await build_heatmap(
        session,
        query=query,
        settings=settings,
        campaign_id=campaign_id,
        organization_id=organization_id,
        vehicle_type=vehicle_type,
        metadata_campaign_id=campaign_id,
        metadata_organization_id=organization_id,
    )


async def build_heatmap(
    session: AsyncSession,
    *,
    query: HeatmapQuery,
    settings: Settings,
    campaign_id: UUID | None,
    organization_id: UUID | None,
    vehicle_type: str | None,
    metadata_campaign_id: UUID | None,
    metadata_organization_id: UUID | None,
) -> HeatmapFeatureCollection:
    ensure_postgis(session)
    params: dict[str, object] = {
        "min_lon": query.bbox[0],
        "min_lat": query.bbox[1],
        "max_lon": query.bbox[2],
        "max_lat": query.bbox[3],
        "resolution_m": query.resolution_m,
        "route_analytics_formula_version": settings.route_analytics_formula_version,
        "impression_formula_version": settings.impression_formula_version,
        "min_trips_per_cell": settings.heatmap_min_trips_per_cell,
        "max_cells": settings.heatmap_max_cells,
    }
    filters = [
        "lp.geom && bbox.geom",
        "ST_Intersects(lp.geom, bbox.geom)",
    ]
    if query.start_at is not None:
        filters.append("lp.recorded_at >= :start_at")
        params["start_at"] = query.start_at
    if query.end_at is not None:
        filters.append("lp.recorded_at <= :end_at")
        params["end_at"] = query.end_at
    if campaign_id is not None:
        filters.append("ts.campaign_id = :campaign_id")
        params["campaign_id"] = campaign_id
    if organization_id is not None:
        filters.append("c.organization_id = :organization_id")
        params["organization_id"] = organization_id
    if vehicle_type is not None:
        filters.append("v.vehicle_type = :vehicle_type")
        params["vehicle_type"] = vehicle_type

    result = await session.execute(text(aggregation_sql(filters)), params)
    features = [
        heatmap_feature(
            row=row,
            metric=query.metric,
        )
        for row in result.mappings().all()
    ]
    return HeatmapFeatureCollection(
        metadata=HeatmapMetadata(
            metric=query.metric,
            bbox=query.bbox,
            resolution_m=query.resolution_m,
            start_at=query.start_at,
            end_at=query.end_at,
            generated_at=datetime.now(UTC),
            campaign_id=metadata_campaign_id,
            organization_id=metadata_organization_id,
            vehicle_type=vehicle_type,
        ),
        features=features,
    )


def aggregation_sql(filters: list[str]) -> str:
    where_clause = " AND ".join(filters)
    return f"""
        WITH bbox AS (
            SELECT ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326) AS geom
        ),
        eligible_pings AS (
            SELECT
                lp.trip_session_id,
                floor(ST_X(ST_Transform(lp.geom, 3857)) / :resolution_m) * :resolution_m AS grid_x,
                floor(ST_Y(ST_Transform(lp.geom, 3857)) / :resolution_m) * :resolution_m AS grid_y
            FROM location_pings lp
            JOIN trip_sessions ts ON ts.id = lp.trip_session_id
            JOIN campaigns c ON c.id = ts.campaign_id
            JOIN vehicles v ON v.id = ts.vehicle_id
            CROSS JOIN bbox
            WHERE {where_clause}
        ),
        trip_cell_counts AS (
            SELECT
                trip_session_id,
                grid_x,
                grid_y,
                count(*)::integer AS cell_ping_count
            FROM eligible_pings
            GROUP BY trip_session_id, grid_x, grid_y
        ),
        trip_window_counts AS (
            SELECT trip_session_id, count(*)::integer AS total_ping_count
            FROM eligible_pings
            GROUP BY trip_session_id
        ),
        latest_estimates AS (
            SELECT DISTINCT ON (trip_session_id)
                trip_session_id,
                estimated_impressions
            FROM impression_estimates
            WHERE formula_version = :impression_formula_version
            ORDER BY trip_session_id, estimated_at DESC, id DESC
        ),
        cell_metrics AS (
            SELECT
                tcc.grid_x,
                tcc.grid_y,
                sum(tcc.cell_ping_count)::integer AS ping_count,
                count(DISTINCT tcc.trip_session_id)::integer AS trip_count,
                coalesce(
                    sum(
                        coalesce(ta.distance_m, 0)
                        * (tcc.cell_ping_count::numeric / nullif(twc.total_ping_count, 0))
                    ),
                    0
                ) AS distance_m,
                coalesce(
                    sum(
                        coalesce(le.estimated_impressions, 0)
                        * (tcc.cell_ping_count::numeric / nullif(twc.total_ping_count, 0))
                    ),
                    0
                ) AS estimated_impressions,
                coalesce(avg(ta.quality_score), 0) AS average_quality_score
            FROM trip_cell_counts tcc
            JOIN trip_window_counts twc ON twc.trip_session_id = tcc.trip_session_id
            LEFT JOIN trip_analytics ta
                ON ta.trip_session_id = tcc.trip_session_id
                AND ta.formula_version = :route_analytics_formula_version
            LEFT JOIN latest_estimates le ON le.trip_session_id = tcc.trip_session_id
            GROUP BY tcc.grid_x, tcc.grid_y
            HAVING count(DISTINCT tcc.trip_session_id) >= :min_trips_per_cell
        )
        SELECT
            concat(grid_x::bigint, ':', grid_y::bigint) AS cell_id,
            ST_AsGeoJSON(
                ST_Transform(
                    ST_MakeEnvelope(
                        grid_x,
                        grid_y,
                        grid_x + :resolution_m,
                        grid_y + :resolution_m,
                        3857
                    ),
                    4326
                )
            ) AS geometry_json,
            ping_count,
            trip_count,
            distance_m,
            estimated_impressions,
            average_quality_score
        FROM cell_metrics
        ORDER BY grid_y, grid_x
        LIMIT :max_cells
    """


def heatmap_feature(row, *, metric: HeatmapMetric) -> HeatmapFeature:
    ping_count = int(row["ping_count"] or 0)
    trip_count = int(row["trip_count"] or 0)
    distance_m = decimal_2(row["distance_m"])
    estimated_impressions = decimal_2(row["estimated_impressions"])
    values = {
        HeatmapMetric.PING_COUNT: Decimal(ping_count),
        HeatmapMetric.TRIP_COUNT: Decimal(trip_count),
        HeatmapMetric.DISTANCE_M: distance_m,
        HeatmapMetric.ESTIMATED_IMPRESSIONS: estimated_impressions,
    }
    return HeatmapFeature(
        geometry=json.loads(row["geometry_json"]),
        properties=HeatmapFeatureProperties(
            cell_id=row["cell_id"],
            metric=metric,
            weight=values[metric],
            ping_count=ping_count,
            trip_count=trip_count,
            distance_m=distance_m,
            estimated_impressions=estimated_impressions,
            average_quality_score=decimal_4(row["average_quality_score"]),
        ),
    )
