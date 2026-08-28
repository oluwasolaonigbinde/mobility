from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.measurement import canonical_sha256

SCHEMA_VERSION = "synthetic-target-area-coverage-v1"
HEATMAP_AGGREGATION_VERSION = "heatmap_v1"
HEATMAP_AGGREGATION_METHOD = "postgis_grid_ping_weighted"
SYNTHETIC_DISCLOSURE_REFERENCE = "SYNTHETIC_TEST_ONLY"
SYNTHETIC_QUALIFYING_EVIDENCE_REFERENCE = "SYNTHETIC_TEST_ONLY"
TARGET_PERCENT = Decimal("60")
AREA_QUANTUM = Decimal("0.000001")
PERCENT_QUANTUM = Decimal("0.000001")


def _omitted(reason: str, provenance_sha256: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "SYNTHETIC_VALIDATION_ONLY",
        "test_only": True,
        "provenance_sha256": provenance_sha256,
        "percentage": None,
        "numerator_area_sq_m": None,
        "denominator_area_sq_m": None,
        "meets_synthetic_target": None,
        "synthetic_target_percent": str(TARGET_PERCENT),
        "omission_reason": reason,
        "live_method_approval": "MISSING",
        "live_qualifying_evidence_rule": "MISSING",
    }


def _aware_utc(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).isoformat()


def _uuid_text(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _valid_position(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 2:
        return False
    lon, lat = value[0], value[1]
    return (
        isinstance(lon, (int, float))
        and not isinstance(lon, bool)
        and math.isfinite(lon)
        and -180 <= lon <= 180
        and isinstance(lat, (int, float))
        and not isinstance(lat, bool)
        and math.isfinite(lat)
        and -90 <= lat <= 90
    )


def _valid_ring(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 4
        and all(_valid_position(position) for position in value)
        and value[0][:2] == value[-1][:2]
    )


def _normalized_geometry(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != {"type", "coordinates"}:
        return None
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "Polygon":
        valid = (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(_valid_ring(ring) for ring in coordinates)
        )
    elif geometry_type == "MultiPolygon":
        valid = (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(
                isinstance(polygon, list)
                and bool(polygon)
                and all(_valid_ring(ring) for ring in polygon)
                for polygon in coordinates
            )
        )
    else:
        valid = False
    if not valid:
        return None
    return {"type": geometry_type, "coordinates": coordinates}


def _normalized_period(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    start_at = _aware_utc(value.get("start_at"))
    end_at = _aware_utc(value.get("end_at"))
    if start_at is None or end_at is None or start_at >= end_at:
        return None
    return {
        "start_at": start_at,
        "end_at": end_at,
        "complete": value.get("complete") is True,
        "boundary": value.get("boundary"),
    }


def _normalize_provenance(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, dict):
        return None, "provenance_missing"
    if value.get("test_only") is not True:
        return None, "synthetic_test_only_required"
    if value.get("schema_version") != SCHEMA_VERSION:
        return None, "provenance_schema_mismatch"

    calculated_at = _aware_utc(value.get("calculated_at"))
    scope = value.get("scope")
    if calculated_at is None or not isinstance(scope, dict):
        return None, "provenance_missing"
    organization_id = _uuid_text(scope.get("organization_id"))
    campaign_id = _uuid_text(scope.get("campaign_id"))
    period = _normalized_period(scope.get("period"))
    if organization_id is None or campaign_id is None or period is None:
        return None, "scope_or_period_invalid"
    if period["boundary"] != "[start_at,end_at)":
        return None, "scope_or_period_invalid"
    if not period["complete"]:
        return None, "measurement_period_incomplete"

    zone = value.get("target_zone")
    if not isinstance(zone, dict) or zone.get("geometry") is None:
        return None, "target_zone_geometry_absent"
    zone_geometry = _normalized_geometry(zone.get("geometry"))
    if zone_geometry is None:
        return None, "target_zone_geometry_invalid"
    zone_id = _uuid_text(zone.get("id"))
    revision = zone.get("revision")
    if zone_id is None or not isinstance(revision, str) or not revision.strip():
        return None, "target_zone_revision_absent"
    if (
        _uuid_text(zone.get("organization_id")) != organization_id
        or _uuid_text(zone.get("campaign_id")) != campaign_id
        or _normalized_period(zone.get("period")) != period
    ):
        return None, "scope_or_period_mismatch"

    authority = value.get("fixed_cell_authority")
    if not isinstance(authority, dict):
        return None, "fixed_cell_authority_absent"
    resolution_m = authority.get("resolution_m")
    if (
        authority.get("aggregation_version") != HEATMAP_AGGREGATION_VERSION
        or authority.get("aggregation_method") != HEATMAP_AGGREGATION_METHOD
        or not isinstance(resolution_m, int)
        or isinstance(resolution_m, bool)
        or resolution_m <= 0
    ):
        return None, "fixed_cell_authority_mismatch"
    if authority.get("disclosure_reference") != SYNTHETIC_DISCLOSURE_REFERENCE:
        return None, "disclosure_clearance_absent"
    if (
        _uuid_text(authority.get("organization_id")) != organization_id
        or _uuid_text(authority.get("campaign_id")) != campaign_id
        or _normalized_period(authority.get("period")) != period
    ):
        return None, "scope_or_period_mismatch"

    cells = value.get("fixed_cells")
    if not isinstance(cells, list):
        return None, "fixed_cell_provenance_absent"
    normalized_cells: list[dict[str, Any]] = []
    seen_cell_ids: set[str] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            return None, "fixed_cell_provenance_invalid"
        cell_id = cell.get("cell_id")
        geometry = _normalized_geometry(cell.get("geometry"))
        if not isinstance(cell_id, str) or not cell_id or geometry is None:
            return None, "fixed_cell_provenance_invalid"
        if cell_id in seen_cell_ids:
            return None, "duplicate_fixed_cell_id"
        seen_cell_ids.add(cell_id)
        if (
            _uuid_text(cell.get("organization_id")) != organization_id
            or _uuid_text(cell.get("campaign_id")) != campaign_id
            or _normalized_period(cell.get("period")) != period
        ):
            return None, "scope_or_period_mismatch"
        normalized_cells.append(
            {
                "cell_id": cell_id,
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "period": period,
                "geometry": geometry,
            }
        )
    normalized_cells.sort(key=lambda cell: cell["cell_id"])

    cleared = value.get("disclosure_cleared_cell_ids")
    qualifying = value.get("qualifying_synthetic_cell_ids")
    if not isinstance(cleared, list) or not all(isinstance(item, str) for item in cleared):
        return None, "disclosure_clearance_absent"
    if not isinstance(qualifying, list) or not all(isinstance(item, str) for item in qualifying):
        return None, "qualifying_evidence_absent"
    cleared_ids = sorted(set(cleared))
    qualifying_ids = sorted(set(qualifying))
    if not set(cleared_ids).issubset(seen_cell_ids):
        return None, "unknown_disclosure_cell_id"
    if not set(qualifying_ids).issubset(seen_cell_ids):
        return None, "unknown_qualifying_cell_id"
    if not set(qualifying_ids).issubset(cleared_ids):
        return None, "disclosure_clearance_absent"
    if value.get("qualifying_evidence_reference") != SYNTHETIC_QUALIFYING_EVIDENCE_REFERENCE:
        return None, "qualifying_evidence_reference_absent"

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "test_only": True,
        "calculated_at": calculated_at,
        "scope": {
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "period": period,
        },
        "target_zone": {
            "id": zone_id,
            "revision": revision.strip(),
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "period": period,
            "geometry": zone_geometry,
        },
        "fixed_cell_authority": {
            "aggregation_version": HEATMAP_AGGREGATION_VERSION,
            "aggregation_method": HEATMAP_AGGREGATION_METHOD,
            "resolution_m": resolution_m,
            "disclosure_reference": SYNTHETIC_DISCLOSURE_REFERENCE,
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "period": period,
        },
        "fixed_cells": normalized_cells,
        "disclosure_cleared_cell_ids": cleared_ids,
        "qualifying_synthetic_cell_ids": qualifying_ids,
        "qualifying_evidence_reference": SYNTHETIC_QUALIFYING_EVIDENCE_REFERENCE,
    }
    return normalized, None


def seal_synthetic_target_area_provenance(value: dict[str, Any]) -> dict[str, Any]:
    normalized, reason = _normalize_provenance(value)
    if normalized is None:
        raise ValueError(reason)
    return {**normalized, "provenance_sha256": canonical_sha256(normalized)}


async def calculate_synthetic_target_area_coverage(
    session: AsyncSession, provenance: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(provenance, dict) or provenance.get("test_only") is not True:
        return _omitted("synthetic_test_only_required")
    normalized, reason = _normalize_provenance(provenance)
    if normalized is None:
        return _omitted(reason or "provenance_invalid")
    provenance_sha256 = canonical_sha256(normalized)
    if provenance.get("provenance_sha256") != provenance_sha256:
        return _omitted("provenance_hash_mismatch", provenance_sha256)

    qualifying_ids = set(normalized["qualifying_synthetic_cell_ids"])
    if not qualifying_ids:
        return _omitted("qualifying_evidence_absent", provenance_sha256)
    cleared_ids = set(normalized["disclosure_cleared_cell_ids"])
    included_ids = qualifying_ids & cleared_ids
    if not included_ids:
        return _omitted("disclosure_clearance_absent", provenance_sha256)
    included_cells = [cell for cell in normalized["fixed_cells"] if cell["cell_id"] in included_ids]

    if session.get_bind().dialect.name != "postgresql":
        return _omitted("postgis_unavailable", provenance_sha256)

    zone_json = json.dumps(
        normalized["target_zone"]["geometry"], separators=(",", ":"), sort_keys=True
    )
    cells_json = json.dumps(
        [cell["geometry"] for cell in included_cells],
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        async with session.begin_nested():
            validation = (
                (
                    await session.execute(
                        text(
                            """
                        WITH zone AS (
                            SELECT ST_SetSRID(ST_GeomFromGeoJSON(:zone_json), 4326) AS geom
                        ),
                        cells AS (
                            SELECT ST_SetSRID(
                                ST_GeomFromGeoJSON(item.value::text), 4326
                            ) AS geom
                            FROM jsonb_array_elements(CAST(:cells_json AS jsonb)) AS item(value)
                        )
                        SELECT
                            ST_IsValid(zone.geom) AS zone_valid,
                            ST_IsEmpty(zone.geom) AS zone_empty,
                            ST_GeometryType(zone.geom) IN (
                                'ST_Polygon', 'ST_MultiPolygon'
                            ) AS zone_polygonal,
                            COALESCE(bool_and(ST_IsValid(cells.geom)), false) AS cells_valid,
                            COALESCE(bool_and(NOT ST_IsEmpty(cells.geom)), false) AS cells_nonempty,
                            COALESCE(bool_and(ST_GeometryType(cells.geom) IN (
                                'ST_Polygon', 'ST_MultiPolygon'
                            )), false) AS cells_polygonal
                        FROM zone
                        CROSS JOIN cells
                        GROUP BY zone.geom
                        """
                        ),
                        {"zone_json": zone_json, "cells_json": cells_json},
                    )
                )
                .mappings()
                .one()
            )
            if not (
                validation["zone_valid"]
                and not validation["zone_empty"]
                and validation["zone_polygonal"]
            ):
                return _omitted("target_zone_geometry_invalid", provenance_sha256)
            if not (
                validation["cells_valid"]
                and validation["cells_nonempty"]
                and validation["cells_polygonal"]
            ):
                return _omitted("fixed_cell_geometry_invalid", provenance_sha256)

            areas = (
                (
                    await session.execute(
                        text(
                            """
                        WITH zone AS (
                            SELECT ST_SetSRID(ST_GeomFromGeoJSON(:zone_json), 4326) AS geom
                        ),
                        cells AS (
                            SELECT ST_SetSRID(
                                ST_GeomFromGeoJSON(item.value::text), 4326
                            ) AS geom
                            FROM jsonb_array_elements(CAST(:cells_json AS jsonb)) AS item(value)
                        ),
                        clipped AS (
                            SELECT ST_CollectionExtract(
                                ST_Intersection(cells.geom, zone.geom), 3
                            ) AS geom
                            FROM cells
                            CROSS JOIN zone
                        ),
                        covered AS (
                            SELECT ST_Union(geom) AS geom
                            FROM clipped
                            WHERE NOT ST_IsEmpty(geom)
                        )
                        SELECT
                            CAST(ST_Area(zone.geom::geography) AS numeric(30, 12))
                                AS denominator_area_sq_m,
                            CAST(COALESCE(ST_Area(covered.geom::geography), 0)
                                AS numeric(30, 12)) AS numerator_area_sq_m
                        FROM zone
                        CROSS JOIN covered
                        """
                        ),
                        {"zone_json": zone_json, "cells_json": cells_json},
                    )
                )
                .mappings()
                .one()
            )
    except (SQLAlchemyError, ValueError):
        return _omitted("spatial_calculation_failed", provenance_sha256)

    denominator_raw = Decimal(str(areas["denominator_area_sq_m"] or 0))
    if denominator_raw <= 0:
        return _omitted("target_zone_area_not_positive", provenance_sha256)
    numerator_raw = Decimal(str(areas["numerator_area_sq_m"] or 0))
    denominator = denominator_raw.quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)
    numerator = numerator_raw.quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)
    percentage = ((numerator_raw * Decimal(100)) / denominator_raw).quantize(
        PERCENT_QUANTUM, rounding=ROUND_HALF_UP
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "SYNTHETIC_VALIDATION_ONLY",
        "test_only": True,
        "provenance_sha256": provenance_sha256,
        "percentage": str(percentage),
        "numerator_area_sq_m": str(numerator),
        "denominator_area_sq_m": str(denominator),
        "meets_synthetic_target": percentage >= TARGET_PERCENT,
        "synthetic_target_percent": str(TARGET_PERCENT),
        "omission_reason": None,
        "live_method_approval": "MISSING",
        "live_qualifying_evidence_rule": "MISSING",
        "uncertainty": (
            "Synthetic geographic evidence only; not people, views, reach, attribution, "
            "causal effect, or live method approval."
        ),
    }
