from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "measurement-methodology.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "measurement"
ADVERTISER_DIR = ROOT / "frontend" / "src" / "app" / "advertiser"
SHARED_COMPONENTS_DIR = ROOT / "frontend" / "src" / "components"
COPY_SOURCE_DIRS = (ADVERTISER_DIR, SHARED_COMPONENTS_DIR)
COPY_SOURCE_SUFFIXES = {".ts", ".tsx"}


def advertiser_reachable_copy() -> str:
    return "\n".join(
        path.read_text()
        for source_dir in COPY_SOURCE_DIRS
        for path in sorted(source_dir.rglob("*"))
        if path.suffix in COPY_SOURCE_SUFFIXES and ".test." not in path.name
    )


def prohibited_claim_pattern(claim: str) -> re.Pattern[str]:
    phrase = re.sub(r"\\\s+", r"\\s+", re.escape(claim.strip()))
    return re.compile(rf"(?<!\w){phrase}(?!\w)", re.IGNORECASE)


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
    required = {
        "display_label",
        "class",
        "unit",
        "source",
        "vintage",
        "uncertainty",
        "missing_data",
    }
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


def test_frozen_disclosure_wording_is_taken_from_the_contract() -> None:
    # R47: the frozen result must reproduce the contract's own clauses verbatim so a
    # run stays reproducible from its manifest without reading this file at runtime.
    from app.schemas.measurement import (
        MeasurementRoiMethodRead,
        MeasurementRoiProvenanceRead,
    )
    from app.services.measurement import (
        DENSITY_PARAMETER_CALIBRATION,
        DENSITY_PARAMETER_SOURCE,
        MODELLED_CONTACTS_UNCERTAINTY,
        ROI_METHOD_LIMITATIONS,
        SUPPRESSED_TOTAL_LABEL,
        VERIFIED_MOVEMENT_CAVEAT,
    )

    contract = read_json(CONTRACT_PATH)
    metrics = {row["id"]: row for row in contract["metric_hierarchy"]}

    assert VERIFIED_MOVEMENT_CAVEAT == metrics["verified_vehicle_movement"]["uncertainty"]
    # Pre-R47 wording is preserved verbatim: app/services/audience.py and
    # app/services/audience_delivery.py both fail closed without this exact statement.
    assert MODELLED_CONTACTS_UNCERTAINTY == (
        "Model confidence is a diagnostic, not a statistical confidence interval."
    )
    contacts_uncertainty = metrics["modelled_potential_contacts"]["uncertainty"]
    assert "not a statistical confidence interval" in contacts_uncertainty
    assert DENSITY_PARAMETER_SOURCE == metrics["modelled_potential_contacts"]["source"]
    assert DENSITY_PARAMETER_CALIBRATION == metrics["modelled_potential_contacts"]["calibration"]
    assert ROI_METHOD_LIMITATIONS == metrics["true_roi"]["limitations"]

    rule = contract["completeness_rule"]
    assert set(rule) == {
        "denominator",
        "in_progress_handling",
        "disclosure",
        "suppression",
        "omitted_label",
        "consistency",
    }
    assert all(value.strip() for value in rule.values())
    # One published omission wording for screen, CSV and PDF.
    assert SUPPRESSED_TOTAL_LABEL == rule["omitted_label"]
    assert SUPPRESSED_TOTAL_LABEL.isascii(), "the bounded PDF renderer is ASCII-only"
    frontend_label = (
        ADVERTISER_DIR / "campaigns" / "[campaignId]" / "report" / "measurement-authority.tsx"
    ).read_text()
    assert f'"{SUPPRESSED_TOTAL_LABEL}"' in frontend_label

    # Every ROI fact the contract demands is a field the read contract actually exposes.
    exposed = (
        set(MeasurementRoiMethodRead.model_fields)
        | set(MeasurementRoiProvenanceRead.model_fields)
        | {"method_revision"}
    )
    assert set(contract["roi_gate"]["required_disclosure"]) <= exposed


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
    calculated = (
        Decimal(inputs["attributed_revenue"]) - Decimal(inputs["approved_cost_basis"])
    ) / Decimal(inputs["approved_cost_basis"])
    assert calculated == Decimal(fixture["roi"]["ratio"])
    assert calculated * 100 == Decimal(fixture["roi"]["percent"])
    assert fixture["roi_gate"]["decision"] == "INCLUDE_FOR_SYNTHETIC_TEST_ONLY"


def test_advertiser_copy_uses_safe_measurement_terms() -> None:
    contract = read_json(CONTRACT_PATH)
    copy = advertiser_reachable_copy()

    assert "Campaign Performance Analysis" in copy
    assert "Modelled potential contacts" in copy
    assert "Model confidence diagnostic" in copy
    assert "not a statistical confidence interval" in copy
    prohibited_claims = contract["prohibited_claims"]
    assert prohibited_claims
    for prohibited in prohibited_claims:
        assert not prohibited_claim_pattern(prohibited).search(copy), prohibited


def test_prohibited_claim_patterns_are_case_insensitive_whole_phrases() -> None:
    pattern = prohibited_claim_pattern("verified exposure")

    assert pattern.search("VERIFIED EXPOSURE")
    assert pattern.search("verified\n exposure")
    assert not pattern.search("unverified exposure")
    assert not pattern.search("verified exposures")
