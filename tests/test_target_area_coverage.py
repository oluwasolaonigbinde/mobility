from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.services.target_area_coverage import (
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
    baseline = calculate(postgis_db_sessionmaker, sealed())
    overlapping = raw_provenance()
    duplicate = copy.deepcopy(overlapping["fixed_cells"][1])
    duplicate["cell_id"] = "overlap:synthetic"
    overlapping["fixed_cells"].append(duplicate)
    overlapping["disclosure_cleared_cell_ids"].append(duplicate["cell_id"])
    overlapping["qualifying_synthetic_cell_ids"].append(duplicate["cell_id"])

    result = calculate(postgis_db_sessionmaker, sealed(overlapping))

    assert result["percentage"] == baseline["percentage"] == "62.500000"
    assert result["numerator_area_sq_m"] == baseline["numerator_area_sq_m"]


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
    outside_cell["cell_id"] = "outside:synthetic"
    outside_cell["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[8.0, 10.0], [8.0, 10.01], [8.01, 10.01], [8.01, 10.0], [8.0, 10.0]]],
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
    reordered["qualifying_synthetic_cell_ids"] = list(
        reversed(reordered["qualifying_synthetic_cell_ids"])
    ) + [reordered["qualifying_synthetic_cell_ids"][0]]
    reordered_sealed = sealed(reordered)
    tampered = copy.deepcopy(original)
    tampered["target_zone"]["revision"] = "tampered-zone-revision"

    assert reordered_sealed["provenance_sha256"] == original["provenance_sha256"]
    assert calculate(postgis_db_sessionmaker, reordered_sealed)["percentage"] == "62.500000"
    tampered_result = calculate(postgis_db_sessionmaker, tampered)
    assert tampered_result["percentage"] is None
    assert tampered_result["omission_reason"] == "provenance_hash_mismatch"


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
