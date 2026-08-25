import hashlib
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
from app.models.user import User, UserRole, UserStatus
from app.schemas.heatmaps import (
    HeatmapFeature,
    HeatmapFeatureCollection,
    HeatmapFeatureProperties,
    HeatmapMetadata,
    HeatmapMetric,
)
from app.services.campaigns import get_advertiser_campaign
from app.services.disclosure import (
    DisclosureQuery,
    ensure_disclosure_live_gate,
    record_heatmap_disclosure,
    require_governed_advertiser_output,
)

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
    minimum_resolution = max(
        settings.heatmap_min_resolution_m,
        settings.privacy_min_resolution_m,
    )
    if (
        resolution < minimum_resolution
        or resolution > settings.heatmap_max_resolution_m
    ):
        raise AppError(
            "INVALID_HEATMAP_RESOLUTION",
            "resolution_m is outside the configured heatmap bounds",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "min_resolution_m": minimum_resolution,
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
) -> UUID | None:
    if campaign_id is None:
        return organization_id
    campaign_org_id = await session.scalar(
        select(Campaign.organization_id).where(Campaign.id == campaign_id)
    )
    if campaign_org_id is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if organization_id is not None and campaign_org_id != organization_id:
        raise AppError(
            "INVALID_HEATMAP_FILTERS",
            "campaign_id does not belong to organization_id",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return campaign_org_id


async def _active_admin(session: AsyncSession, actor_user_id: UUID) -> None:
    admin_id = await session.scalar(
        select(User.id).where(
            User.id == actor_user_id,
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
        )
    )
    if admin_id is None:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Admin role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )


async def advertiser_campaign_heatmap(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    query: HeatmapQuery,
    settings: Settings,
) -> HeatmapFeatureCollection:
    await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.heatmap",
        user_id=user_id,
        requires_measurement_run=False,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    result = await build_heatmap(
        session,
        query=query,
        settings=settings,
        campaign_id=campaign.id,
        organization_id=None,
        vehicle_type=None,
        metadata_campaign_id=campaign.id,
        metadata_organization_id=None,
    )
    await record_heatmap_disclosure(
        session,
        query=DisclosureQuery(
            route_id="advertiser.campaign.heatmap",
            principal_id=user_id,
            tenant_id=campaign.organization_id,
            campaign_id=campaign.id,
            start_at=query.start_at,
            end_at=query.end_at,
            filters={
                "bbox": query.bbox,
                "resolution_m": query.resolution_m,
                "metric": query.metric.value,
            },
        ),
        settings=settings,
        has_releasable_cells=bool(result.features),
        result_hash=heatmap_result_hash(result),
    )
    return result


async def admin_heatmap(
    session: AsyncSession,
    *,
    user_id: UUID,
    query: HeatmapQuery,
    settings: Settings,
    campaign_id: UUID | None,
    organization_id: UUID | None,
    vehicle_type: str | None,
) -> HeatmapFeatureCollection:
    ensure_disclosure_live_gate(settings, requires_measurement_run=False)
    await _active_admin(session, user_id)
    disclosure_tenant_id = await ensure_admin_filter_consistency(
        session,
        campaign_id=campaign_id,
        organization_id=organization_id,
    )
    result = await build_heatmap(
        session,
        query=query,
        settings=settings,
        campaign_id=campaign_id,
        organization_id=organization_id,
        vehicle_type=vehicle_type,
        metadata_campaign_id=campaign_id,
        metadata_organization_id=organization_id,
    )
    await record_heatmap_disclosure(
        session,
        query=DisclosureQuery(
            route_id="admin.heatmap",
            principal_id=user_id,
            tenant_id=disclosure_tenant_id,
            campaign_id=campaign_id,
            start_at=query.start_at,
            end_at=query.end_at,
            filters={
                "bbox": query.bbox,
                "resolution_m": query.resolution_m,
                "metric": query.metric.value,
                "vehicle_type": vehicle_type,
            },
        ),
        settings=settings,
        has_releasable_cells=bool(result.features),
        result_hash=heatmap_result_hash(result),
    )
    return result


def heatmap_result_hash(result: HeatmapFeatureCollection) -> str:
    payload = [feature.model_dump(mode="json") for feature in result.features]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
        "privacy_min_vehicles_per_cell": settings.privacy_min_vehicles_per_cell,
        "privacy_min_trips_per_cell": settings.privacy_min_trips_per_cell,
        "privacy_min_days_per_cell": settings.privacy_min_days_per_cell,
        "privacy_max_contributor_share": settings.privacy_max_contributor_share,
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
                ts.vehicle_id,
                date_trunc('day', lp.recorded_at) AS recorded_day,
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
                vehicle_id,
                grid_x,
                grid_y,
                count(*)::integer AS cell_ping_count
            FROM eligible_pings
            GROUP BY trip_session_id, vehicle_id, grid_x, grid_y
        ),
        cell_privacy_counts AS (
            SELECT
                grid_x,
                grid_y,
                count(DISTINCT vehicle_id)::integer AS vehicle_count,
                count(DISTINCT trip_session_id)::integer AS privacy_trip_count,
                count(DISTINCT recorded_day)::integer AS day_count,
                count(*)::numeric AS total_ping_count
            FROM eligible_pings
            GROUP BY grid_x, grid_y
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
        vehicle_cell_metrics AS (
            SELECT
                tcc.grid_x,
                tcc.grid_y,
                tcc.vehicle_id,
                sum(tcc.cell_ping_count)::numeric AS ping_count,
                count(DISTINCT tcc.trip_session_id)::numeric AS trip_count,
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
                ) AS estimated_impressions
            FROM trip_cell_counts tcc
            JOIN trip_window_counts twc ON twc.trip_session_id = tcc.trip_session_id
            LEFT JOIN trip_analytics ta
                ON ta.trip_session_id = tcc.trip_session_id
                AND ta.formula_version = :route_analytics_formula_version
            LEFT JOIN latest_estimates le ON le.trip_session_id = tcc.trip_session_id
            GROUP BY tcc.grid_x, tcc.grid_y, tcc.vehicle_id
        ),
        cell_contributor_caps AS (
            SELECT
                grid_x,
                grid_y,
                greatest(
                    coalesce(max(ping_count) / nullif(sum(ping_count), 0), 0),
                    coalesce(max(trip_count) / nullif(sum(trip_count), 0), 0),
                    coalesce(max(distance_m) / nullif(sum(distance_m), 0), 0),
                    coalesce(
                        max(estimated_impressions)
                        / nullif(sum(estimated_impressions), 0),
                        0
                    )
                ) AS max_share
            FROM vehicle_cell_metrics
            GROUP BY grid_x, grid_y
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
        FROM cell_metrics cm
        JOIN cell_privacy_counts pc USING (grid_x, grid_y)
        JOIN cell_contributor_caps cc USING (grid_x, grid_y)
        WHERE pc.vehicle_count >= :privacy_min_vehicles_per_cell
          AND pc.privacy_trip_count >= :privacy_min_trips_per_cell
          AND pc.day_count >= :privacy_min_days_per_cell
          AND cc.max_share <= :privacy_max_contributor_share
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
