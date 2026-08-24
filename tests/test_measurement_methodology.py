from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "measurement-methodology.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "measurement"
ADVERTISER_DIR = ROOT / "frontend" / "src" / "app" / "advertiser"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_contract_is_complete_and_live_use_fails_closed() -> None:
    contract = read_json(CONTRACT_PATH)

    assert contract["schema_version"] == "measurement-methodology-v1"
    assert contract["status"] == "DRAFT_BUILD_ONLY"
    assert contract["external_gate"] == "EXT-REPORT-METHOD"
    assert contract["live_report_issuance_authorized"] is False
    assert contract["standard_deliverable"] == "Campaign Performance Analysis"
    assert contract["roi_gate"]["default"] == "OMIT"
    assert contract["roi_gate"]["production_enabled"] is False
    assert len(contract["roi_gate"]["all_required"]) >= 7

    metrics = {row["id"]: row for row in contract["metric_hierarchy"]}
    assert set(metrics) == {
        "verified_vehicle_movement",
        "modelled_potential_contacts",
        "target_area_coverage",
        "driver_campaign_cost",
        "true_roi",
    }
    required = {"display_label", "class", "unit", "source", "vintage", "uncertainty", "missing_data"}
    assert all(required <= row.keys() for row in metrics.values())
    contacts = metrics["modelled_potential_contacts"]
    assert contacts["storage_field"] == "estimated_impressions"
    assert {"verified views", "unique reach", "audience", "attribution", "people exposed"} <= set(
        contacts["never_equivalent_to"]
    )

    coverage = metrics["target_area_coverage"]["candidate_formula"]
    assert coverage["status"] == "SYNTHETIC_VALIDATION_ONLY"
    assert coverage["live_method_approval"] == "MISSING"
    assert coverage["target"] == "at least 60 percent"


def test_performance_fixture_omits_roi() -> None:
    fixture = read_json(FIXTURE_DIR / "performance_only.json")

    assert fixture["test_only"] is True
    assert fixture["title"] == "Campaign Performance Analysis"
    assert fixture["mode"] == "performance_only"
    assert fixture["roi"] is None
    assert fixture["roi_gate"]["decision"] == "OMIT"
    assert "true_roi" not in fixture["metrics"]


def test_roi_fixture_is_complete_synthetic_evidence_only() -> None:
    fixture = read_json(FIXTURE_DIR / "roi_enabled_synthetic.json")

    assert fixture["test_only"] is True
    assert fixture["method"]["approval"] == "SYNTHETIC_TEST_ONLY"
    for field in (
        "revision",
        "formula",
        "attribution_rule",
        "attribution_window",
        "cost_basis",
        "exclusions",
        "corrections",
        "late_data",
    ):
        assert fixture["method"][field]
    inputs = fixture["inputs"]
    calculated = (Decimal(inputs["attributed_revenue"]) - Decimal(inputs["approved_cost_basis"])) / Decimal(
        inputs["approved_cost_basis"]
    )
    assert calculated == Decimal(fixture["roi"]["ratio"])
    assert calculated * 100 == Decimal(fixture["roi"]["percent"])
    assert fixture["roi_gate"]["decision"] == "INCLUDE_FOR_SYNTHETIC_TEST_ONLY"


def test_advertiser_copy_uses_safe_measurement_terms() -> None:
    copy = "\n".join(
        path.read_text()
        for path in ADVERTISER_DIR.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    assert "Campaign Performance Analysis" in copy
    assert "Modelled potential contacts" in copy
    assert "Model confidence diagnostic" in copy
    assert "not a statistical confidence interval" in copy
    for prohibited in (
        "Attribution report",
        "GPS-verified exposure",
        "Where was the campaign most likely seen?",
        "Estimated impressions · daily",
        'label="Est. impressions"',
        'label="Avg confidence"',
        "Exposure map",
        "Exposure heatmap",
        "Where your campaign was seen",
        "premium exposure",
        "Pay premium for attention",
    ):
        assert prohibited not in copy
