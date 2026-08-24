import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, literal_column, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_zone import CampaignZone
from app.schemas.campaign_zones import CampaignZoneCreate, CampaignZoneUpdate
from app.services.campaigns import get_advertiser_campaign, get_required_advertiser_context

MUTABLE_CAMPAIGN_STATUSES = {
    CampaignStatus.DRAFT,
    CampaignStatus.REJECTED,
}


@dataclass(frozen=True)
class CampaignZoneGeometry:
    geojson_text: str
    area_sq_m: Decimal


@dataclass(frozen=True)
class CampaignZoneView:
    zone: CampaignZone
    geometry: dict[str, Any]
    area_sq_m: Decimal


def invalid_geojson(message: str) -> AppError:
    return AppError("INVALID_GEOJSON", message, status_code=status.HTTP_400_BAD_REQUEST)


def ensure_mutable_campaign(campaign: Campaign) -> None:
    if campaign.status not in MUTABLE_CAMPAIGN_STATUSES:
        raise AppError(
            "CAMPAIGN_STATUS_FORBIDS_ZONE_MUTATION",
            "Campaign status does not allow campaign zone changes",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def normalize_coordinate(position: Any) -> list[float]:
    if not isinstance(position, list | tuple) or len(position) != 2:
        raise invalid_geojson("GeoJSON positions must be [longitude, latitude] pairs")
    longitude, latitude = position
    if (
        isinstance(longitude, bool)
        or isinstance(latitude, bool)
        or not isinstance(longitude, int | float)
        or not isinstance(latitude, int | float)
        or not math.isfinite(longitude)
        or not math.isfinite(latitude)
    ):
        raise invalid_geojson("GeoJSON coordinates must be finite numbers")
    if longitude < -180 or longitude > 180:
        raise invalid_geojson("Longitude must be between -180 and 180")
    if latitude < -90 or latitude > 90:
        raise invalid_geojson("Latitude must be between -90 and 90")
    return [float(longitude), float(latitude)]


def normalize_linear_ring(ring: Any) -> list[list[float]]:
    if not isinstance(ring, list) or len(ring) < 4:
        raise invalid_geojson("Polygon linear rings must contain at least four positions")
    coordinates = [normalize_coordinate(position) for position in ring]
    if coordinates[0] != coordinates[-1]:
        raise invalid_geojson("Polygon linear rings must be closed")
    return coordinates


def normalize_polygon_coordinates(polygon: Any) -> list[list[list[float]]]:
    if not isinstance(polygon, list) or not polygon:
        raise invalid_geojson("Polygon coordinates must include at least one linear ring")
    return [normalize_linear_ring(ring) for ring in polygon]


def normalize_geojson_geometry(geometry: Any) -> dict[str, Any]:
    if not isinstance(geometry, dict):
        raise invalid_geojson("Geometry must be a GeoJSON object")

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        multipolygon = [normalize_polygon_coordinates(coordinates)]
    elif geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise invalid_geojson("MultiPolygon coordinates must include at least one polygon")
        multipolygon = [normalize_polygon_coordinates(polygon) for polygon in coordinates]
    else:
        raise invalid_geojson("Geometry type must be Polygon or MultiPolygon")

    return {"type": "MultiPolygon", "coordinates": multipolygon}


def geometry_expression(geojson_text: str):
    return func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson_text), 4326))


def area_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def validate_geometry_with_postgis(
    session: AsyncSession,
    geometry: dict[str, Any],
    settings: Settings,
) -> CampaignZoneGeometry:
    normalized_geometry = normalize_geojson_geometry(geometry)
    geojson_text = json.dumps(normalized_geometry, separators=(",", ":"))
    if session.get_bind().dialect.name != "postgresql":
        raise AppError(
            "POSTGIS_REQUIRED",
            "Campaign zone geometry validation requires PostgreSQL/PostGIS",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        result = await session.execute(
            text(
                """
                WITH parsed AS (
                    SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)) AS geom
                )
                SELECT
                    ST_IsValid(geom) AS is_valid,
                    ST_IsValidReason(geom) AS validity_reason,
                    ST_GeometryType(geom) AS geometry_type,
                    ST_SRID(geom) AS srid,
                    ST_Area(geom::geography) AS area_sq_m
                FROM parsed
                """
            ),
            {"geojson": geojson_text},
        )
    except SQLAlchemyError as exc:
        raise invalid_geojson("Geometry could not be parsed by PostGIS") from exc

    row = result.mappings().one()
    if row["geometry_type"] != "ST_MultiPolygon" or row["srid"] != 4326:
        raise invalid_geojson("Geometry must resolve to a MultiPolygon with SRID 4326")
    if not row["is_valid"]:
        raise AppError(
            "INVALID_POLYGON",
            "Polygon geometry is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"reason": row["validity_reason"]},
        )

    area_sq_m = Decimal(str(row["area_sq_m"]))
    max_area_sq_m = Decimal(settings.max_campaign_zone_area_sq_km) * Decimal("1000000")
    if area_sq_m > max_area_sq_m:
        raise AppError(
            "CAMPAIGN_ZONE_AREA_EXCEEDED",
            "Campaign zone area exceeds the configured maximum",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_area_sq_km": settings.max_campaign_zone_area_sq_km},
        )
    return CampaignZoneGeometry(geojson_text=geojson_text, area_sq_m=area_decimal(area_sq_m))


def zone_view_statement():
    return select(
        CampaignZone,
        func.ST_AsGeoJSON(CampaignZone.geom).label("geometry_json"),
        literal_column("ST_Area(campaign_zones.geom::geography)").label("area_sq_m"),
    )


def row_to_zone_view(row: Any) -> CampaignZoneView:
    return CampaignZoneView(
        zone=row[0],
        geometry=json.loads(row.geometry_json),
        area_sq_m=area_decimal(row.area_sq_m),
    )


async def get_campaign_zone_view(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    zone_id: UUID,
) -> CampaignZoneView:
    result = await session.execute(
        zone_view_statement().where(
            CampaignZone.id == zone_id,
            CampaignZone.campaign_id == campaign_id,
        )
    )
    row = result.first()
    if row is None:
        raise AppError(
            "CAMPAIGN_ZONE_NOT_FOUND",
            "Campaign zone was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row_to_zone_view(row)


async def create_campaign_zone(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    payload: CampaignZoneCreate,
    settings: Settings,
) -> CampaignZoneView:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await get_required_advertiser_context(session, user_id, require_write=True)
    ensure_mutable_campaign(campaign)
    geometry = await validate_geometry_with_postgis(session, payload.geometry, settings)

    zone = CampaignZone(
        campaign_id=campaign.id,
        created_by_user_id=user_id,
        name=payload.name,
        description=payload.description,
        zone_type=payload.zone_type,
        geom=geometry_expression(geometry.geojson_text),
        zone_metadata=payload.metadata,
    )
    session.add(zone)
    await session.flush()
    return await get_campaign_zone_view(session, campaign_id=campaign.id, zone_id=zone.id)


async def list_campaign_zones(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    limit: int,
    offset: int,
    zone_type: str | None,
) -> tuple[list[CampaignZoneView], int]:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    filters = [CampaignZone.campaign_id == campaign.id]
    if zone_type is not None:
        filters.append(CampaignZone.zone_type == zone_type)

    statement = zone_view_statement()
    count_statement = select(func.count()).select_from(CampaignZone)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignZone.created_at.desc(), CampaignZone.id)
        .limit(limit)
        .offset(offset)
    )
    return [row_to_zone_view(row) for row in result.all()], int(total or 0)


async def get_campaign_zone(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    zone_id: UUID,
) -> CampaignZoneView:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    return await get_campaign_zone_view(session, campaign_id=campaign.id, zone_id=zone_id)


async def update_campaign_zone(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    zone_id: UUID,
    payload: CampaignZoneUpdate,
    settings: Settings,
) -> tuple[CampaignZoneView, list[str]]:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await get_required_advertiser_context(session, user_id, require_write=True)
    ensure_mutable_campaign(campaign)
    view = await get_campaign_zone_view(session, campaign_id=campaign.id, zone_id=zone_id)
    update_values = payload.model_dump(exclude_unset=True)
    changed_fields = list(update_values)

    for required_field in ["name", "zone_type", "geometry"]:
        if required_field in update_values and update_values[required_field] is None:
            raise AppError(
                "INVALID_CAMPAIGN_ZONE_UPDATE",
                f"{required_field} cannot be null",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if "metadata" in update_values:
        metadata = update_values.pop("metadata")
        if metadata is None:
            raise AppError(
                "INVALID_METADATA",
                "Metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        view.zone.zone_metadata = metadata

    if "geometry" in update_values:
        geometry = await validate_geometry_with_postgis(
            session,
            update_values.pop("geometry"),
            settings,
        )
        view.zone.geom = geometry_expression(geometry.geojson_text)

    for field, value in update_values.items():
        setattr(view.zone, field, value)

    await session.flush()
    return (
        await get_campaign_zone_view(session, campaign_id=campaign.id, zone_id=zone_id),
        changed_fields,
    )


async def delete_campaign_zone(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    zone_id: UUID,
) -> CampaignZoneView:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await get_required_advertiser_context(session, user_id, require_write=True)
    ensure_mutable_campaign(campaign)
    view = await get_campaign_zone_view(session, campaign_id=campaign.id, zone_id=zone_id)
    await session.execute(delete(CampaignZone).where(CampaignZone.id == view.zone.id))
    await session.flush()
    return view
