from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.services.target_area_coverage import (
    _coverage_areas,
    calculate_synthetic_target_area_coverage,
    seal_synthetic_target_area_provenance,
)

FIXTURE = Path("tests/fixtures/measurement/target_area_coverage_abuja.json")


def raw_provenance() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def sealed(value: dict | None = None) -> dict:
    return seal_synthetic_target_area_provenance(value or raw_provenance())


def calculate(postgis_db_sessionmaker, value: dict) -> dict:
    async def run() -> dict:
        async with postgis_db_sessionmaker() as session:
            return await calculate_synthetic_target_area_coverage(session, value)

    return asyncio.run(run())


def test_abuja_golden_is_clipped_above_target_and_reproducible(
    postgis_db_sessionmaker,
) -> None:
    provenance = sealed()

    first = calculate(postgis_db_sessionmaker, provenance)
    replay = calculate(postgis_db_sessionmaker, copy.deepcopy(provenance))

    assert first == replay
    assert first["status"] == "SYNTHETIC_VALIDATION_ONLY"
    assert first["test_only"] is True
    assert first["percentage"] == "62.500000"
    assert first["numerator_area_sq_m"] == "1211174.312837"
    assert first["denominator_area_sq_m"] == "1937878.914551"
    assert first["meets_synthetic_target"] is True
    assert first["synthetic_target_percent"] == "60"
    assert first["provenance_sha256"] == provenance["provenance_sha256"]
    assert first["provenance_sha256"] == (
        "12247dcbd865ec990d8f5f0e66532579fd5d402c8183c13220e3012fc89839e5"
    )
    assert first["omission_reason"] is None
    assert "people, views, reach, attribution" in first["uncertainty"]


def test_cell_union_prevents_overlap_double_count(postgis_db_sessionmaker) -> None:
    provenance = raw_provenance()
    qualifying = set(provenance["qualifying_synthetic_cell_ids"])
    geometries = [
        cell["geometry"] for cell in provenance["fixed_cells"] if cell["cell_id"] in qualifying
    ]

    async def areas(cells: list[dict]) -> dict:
        async with postgis_db_sessionmaker() as session:
            return await _coverage_areas(
                session,
                zone_json=json.dumps(provenance["target_zone"]["geometry"]),
                cells_json=json.dumps(cells),
            )

    baseline = asyncio.run(areas(geometries))
    overlapping = asyncio.run(areas([*geometries, copy.deepcopy(geometries[1])]))

    assert overlapping["numerator_area_sq_m"] == baseline["numerator_area_sq_m"]


def test_partial_boundary_clipping_and_below_target(postgis_db_sessionmaker) -> None:
    provenance = raw_provenance()
    provenance["qualifying_synthetic_cell_ids"] = [
        "823500:1013500",
        "824000:1013500",
        "823500:1014000",
        "824000:1014000",
    ]

    result = calculate(postgis_db_sessionmaker, sealed(provenance))

    assert result["percentage"] == "37.500000"
    assert result["meets_synthetic_target"] is False


def test_exact_sixty_percent_meets_synthetic_target(postgis_db_sessionmaker) -> None:
    provenance = raw_provenance()
    provenance["target_zone"]["geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [
                [7.397626364724259, 9.066351183931564],
                [7.397626364724259, 9.070786617531839],
                [7.42008424665, 9.070786617531839],
                [7.42008424665, 9.066351183931564],
                [7.397626364724259, 9.066351183931564],
            ]
        ],
    }
    provenance["qualifying_synthetic_cell_ids"] = [
        "823500:1013500",
        "824000:1013500",
        "824500:1013500",
    ]

    result = calculate(postgis_db_sessionmaker, sealed(provenance))

    assert result["percentage"] == "60.000000"
    assert result["meets_synthetic_target"] is True


@pytest.mark.parametrize("mismatch", ["organization", "campaign", "period"])
def test_scope_and_half_open_period_mismatch_omit(postgis_db_sessionmaker, mismatch: str) -> None:
    provenance = raw_provenance()
    if mismatch == "organization":
        provenance["fixed_cells"][0]["organization_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    elif mismatch == "campaign":
        provenance["target_zone"]["campaign_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    else:
        provenance["fixed_cell_authority"]["period"]["boundary"] = "[start_at,end_at]"

    result = calculate(postgis_db_sessionmaker, provenance)

    assert result["percentage"] is None
    assert result["omission_reason"] in {"scope_or_period_mismatch", "scope_or_period_invalid"}


def test_qualification_disclosure_and_complete_period_fail_closed(
    postgis_db_sessionmaker,
) -> None:
    no_qualification = raw_provenance()
    no_qualification["qualifying_synthetic_cell_ids"] = []
    no_clearance = raw_provenance()
    no_clearance["disclosure_cleared_cell_ids"] = [
        "825000:1013500",
        "825500:1013500",
    ]
    incomplete = raw_provenance()
    period_owners = (
        incomplete["scope"],
        incomplete["target_zone"],
        incomplete["fixed_cell_authority"],
    )
    for owner in period_owners:
        owner["period"]["complete"] = False
    for cell in incomplete["fixed_cells"]:
        cell["period"]["complete"] = False

    no_qualification_result = calculate(postgis_db_sessionmaker, sealed(no_qualification))
    no_clearance_result = calculate(postgis_db_sessionmaker, no_clearance)
    incomplete_result = calculate(postgis_db_sessionmaker, incomplete)

    assert no_qualification_result["omission_reason"] == "qualifying_evidence_absent"
    assert no_clearance_result["omission_reason"] == "disclosure_clearance_absent"
    assert incomplete_result["omission_reason"] == "measurement_period_incomplete"
    assert all(
        result["percentage"] is None
        for result in (no_qualification_result, no_clearance_result, incomplete_result)
    )


def test_missing_zero_invalid_and_outside_zone_geometry_omit_or_zero(
    postgis_db_sessionmaker,
) -> None:
    missing = raw_provenance()
    missing["target_zone"].pop("geometry")
    tiny = raw_provenance()
    tiny["target_zone"]["geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [
                [7.4, 9.08],
                [7.4, 9.080000000001],
                [7.400000000001, 9.080000000001],
                [7.400000000001, 9.08],
                [7.4, 9.08],
            ]
        ],
    }
    outside = raw_provenance()
    outside_cell = copy.deepcopy(outside["fixed_cells"][0])
    outside_cell["cell_id"] = "830000:1013500"
    outside_cell["geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [
                [7.456016858192028, 9.066351183931564],
                [7.456016858192028, 9.070786617531839],
                [7.460508434612625, 9.070786617531839],
                [7.460508434612625, 9.066351183931564],
                [7.456016858192028, 9.066351183931564],
            ]
        ],
    }
    outside["fixed_cells"] = [outside_cell]
    outside["disclosure_cleared_cell_ids"] = [outside_cell["cell_id"]]
    outside["qualifying_synthetic_cell_ids"] = [outside_cell["cell_id"]]

    missing_result = calculate(postgis_db_sessionmaker, missing)
    tiny_result = calculate(postgis_db_sessionmaker, sealed(tiny))
    outside_result = calculate(postgis_db_sessionmaker, sealed(outside))

    assert missing_result["omission_reason"] == "target_zone_geometry_absent"
    assert missing_result["percentage"] is None
    assert tiny_result["percentage"] is None
    assert tiny_result["omission_reason"] == "target_zone_area_not_positive"
    assert outside_result["percentage"] == "0.000000"
    assert outside_result["meets_synthetic_target"] is False


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("duplicate_cell", "duplicate_fixed_cell_id"),
        ("unknown_qualifying", "unknown_qualifying_cell_id"),
        ("non_polygon", "fixed_cell_provenance_invalid"),
        ("out_of_range", "fixed_cell_provenance_invalid"),
    ],
)
def test_malformed_cell_provenance_omits_before_spatial_work(
    postgis_db_sessionmaker, mutation: str, reason: str
) -> None:
    provenance = raw_provenance()
    if mutation == "duplicate_cell":
        provenance["fixed_cells"].append(copy.deepcopy(provenance["fixed_cells"][0]))
    elif mutation == "unknown_qualifying":
        provenance["qualifying_synthetic_cell_ids"].append("unknown:cell")
    elif mutation == "non_polygon":
        provenance["fixed_cells"][0]["geometry"] = {
            "type": "Point",
            "coordinates": [7.4, 9.08],
        }
    else:
        provenance["fixed_cells"][0]["geometry"]["coordinates"][0][0][0] = 181.0

    result = calculate(postgis_db_sessionmaker, provenance)

    assert result["percentage"] is None
    assert result["omission_reason"] == reason


def test_hash_is_order_invariant_and_tampering_is_detected(
    postgis_db_sessionmaker,
) -> None:
    original = sealed()
    reordered = raw_provenance()
    reordered["fixed_cells"].reverse()
    reordered["disclosure_cleared_cell_ids"].reverse()
    reordered["qualifying_synthetic_cell_ids"].reverse()
    reordered_sealed = sealed(reordered)
    tampered = copy.deepcopy(original)
    tampered["target_zone"]["revision"] = "tampered-zone-revision"

    assert reordered_sealed["provenance_sha256"] == original["provenance_sha256"]
    assert calculate(postgis_db_sessionmaker, reordered_sealed)["percentage"] == "62.500000"
    tampered_result = calculate(postgis_db_sessionmaker, tampered)
    assert tampered_result["percentage"] is None
    assert tampered_result["omission_reason"] == "provenance_hash_mismatch"


@pytest.mark.parametrize(
    ("reference_list", "reason"),
    [
        ("disclosure_cleared_cell_ids", "duplicate_disclosure_cell_id"),
        ("qualifying_synthetic_cell_ids", "duplicate_qualifying_cell_id"),
    ],
)
def test_duplicate_evidence_references_are_rejected(
    postgis_db_sessionmaker, reference_list: str, reason: str
) -> None:
    provenance = raw_provenance()
    provenance[reference_list].append(provenance[reference_list][0])

    result = calculate(postgis_db_sessionmaker, provenance)

    assert result["percentage"] is None
    assert result["omission_reason"] == reason


@pytest.mark.parametrize("mutation", ["moved", "oversized", "id", "resolution"])
def test_fixed_cell_identity_geometry_and_resolution_must_agree(
    postgis_db_sessionmaker, mutation: str
) -> None:
    provenance = raw_provenance()
    cell = provenance["fixed_cells"][0]
    if mutation == "moved":
        for position in cell["geometry"]["coordinates"][0]:
            position[0] += 0.0001
    elif mutation == "oversized":
        cell["geometry"]["coordinates"][0][1][1] += 0.0001
        cell["geometry"]["coordinates"][0][2][1] += 0.0001
    elif mutation == "id":
        old_id = cell["cell_id"]
        cell["cell_id"] = "900000:1013500"
        provenance["disclosure_cleared_cell_ids"] = [
            cell["cell_id"] if value == old_id else value
            for value in provenance["disclosure_cleared_cell_ids"]
        ]
        provenance["qualifying_synthetic_cell_ids"] = [
            cell["cell_id"] if value == old_id else value
            for value in provenance["qualifying_synthetic_cell_ids"]
        ]
    else:
        provenance["fixed_cell_authority"]["resolution_m"] = 600

    result = calculate(postgis_db_sessionmaker, sealed(provenance))

    assert result["percentage"] is None
    assert result["omission_reason"] == "fixed_cell_identity_mismatch"


def test_malformed_nonqualifying_cell_fails_closed(postgis_db_sessionmaker) -> None:
    provenance = raw_provenance()
    cell = provenance["fixed_cells"][-1]
    ring = cell["geometry"]["coordinates"][0]
    cell["geometry"]["coordinates"][0] = [ring[0], ring[2], ring[1], ring[3], ring[0]]

    result = calculate(postgis_db_sessionmaker, sealed(provenance))

    assert result["percentage"] is None
    assert result["omission_reason"] == "fixed_cell_geometry_invalid"


def test_live_input_and_unavailable_postgis_never_issue_percentage(db_sessionmaker) -> None:
    class SqlTrap:
        def get_bind(self):
            raise AssertionError("live input reached database authority")

    live = raw_provenance()
    live["test_only"] = False
    live_result = asyncio.run(calculate_synthetic_target_area_coverage(SqlTrap(), live))

    async def unavailable() -> dict:
        async with db_sessionmaker() as session:
            return await calculate_synthetic_target_area_coverage(session, sealed())

    unavailable_result = asyncio.run(unavailable())

    assert live_result["percentage"] is None
    assert live_result["omission_reason"] == "synthetic_test_only_required"
    assert unavailable_result["percentage"] is None
    assert unavailable_result["omission_reason"] == "postgis_unavailable"
