from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "measurement-methodology.json"
ADVERTISER_DIR = ROOT / "frontend" / "src" / "app" / "advertiser"
SHARED_COMPONENTS_DIR = ROOT / "frontend" / "src" / "components"
COPY_SOURCE_DIRS = (ADVERTISER_DIR, SHARED_COMPONENTS_DIR)
COPY_SOURCE_SUFFIXES = {".ts", ".tsx"}


HEADLINE_LABEL = "Estimated ad exposure"
HEADLINE_DISCLAIMER = "not a count of people or measured views"
HEADLINE_STAT_LABEL = f'label="{HEADLINE_LABEL}"'
DIAGNOSTIC_PATTERN = re.compile(
    r"model\s+(confidence|diagnostic)|confidence\s+(score|diagnostic)", re.IGNORECASE
)


def advertiser_reachable_copy_files() -> dict[Path, str]:
    return {
        path: path.read_text()
        for source_dir in COPY_SOURCE_DIRS
        for path in sorted(source_dir.rglob("*"))
        if path.suffix in COPY_SOURCE_SUFFIXES and ".test." not in path.name
    }


def prohibited_claim_pattern(claim: str) -> re.Pattern[str]:
    phrase = re.sub(r"\\\s+", r"\\s+", re.escape(claim.strip()))
    return re.compile(rf"(?<!\w){phrase}(?!\w)", re.IGNORECASE)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_frozen_disclosure_wording_is_taken_from_the_contract() -> None:
    # R47: the frozen result must reproduce the contract's own clauses verbatim so a
    # run stays reproducible from its manifest without reading this file at runtime.
    from app.services.historical_measurement import (
        DENSITY_PARAMETER_CALIBRATION,
        DENSITY_PARAMETER_SOURCE,
        MODELLED_CONTACTS_UNCERTAINTY,
        SUPPRESSED_TOTAL_LABEL,
        VERIFIED_MOVEMENT_CAVEAT,
    )

    contract = read_json(CONTRACT_PATH)
    metrics = {row["id"]: row for row in contract["metric_hierarchy"]}

    assert VERIFIED_MOVEMENT_CAVEAT == metrics["verified_vehicle_movement"]["uncertainty"]
    # Reports retain the exact model uncertainty statement.

    assert MODELLED_CONTACTS_UNCERTAINTY == (
        "Model confidence is a diagnostic, not a statistical confidence interval."
    )
    contacts_uncertainty = metrics["modelled_potential_contacts"]["uncertainty"]
    assert "not a statistical confidence interval" in contacts_uncertainty
    assert DENSITY_PARAMETER_SOURCE == metrics["modelled_potential_contacts"]["source"]
    assert DENSITY_PARAMETER_CALIBRATION == metrics["modelled_potential_contacts"]["calibration"]

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
    # D74 approves plain wording for new v2 runs/exports; the v1 contract is historical.
    assert rule["omitted_label"] == "Omitted - insufficient frozen evidence"
    assert SUPPRESSED_TOTAL_LABEL == "Not enough data"
    assert SUPPRESSED_TOTAL_LABEL.isascii(), "the bounded PDF renderer is ASCII-only"


def test_advertiser_copy_uses_safe_measurement_terms() -> None:
    contract = read_json(CONTRACT_PATH)
    copy_files = advertiser_reachable_copy_files()
    copy = "\n".join(copy_files.values())

    assert "Estimated views" in copy
    # S9/D118 moves issued-report uncertainty into the CSV/PDF renderer.
    from app.services.campaign_report_rendering import UNCERTAINTY

    assert "not measured people or guaranteed views" in UNCERTAINTY
    assert "no independent traffic survey or field calibration" in UNCERTAINTY
    for path, text in copy_files.items():
        if DIAGNOSTIC_PATTERN.search(text):
            assert (
                "not a statistical confidence interval" in text
                or "Model confidence describes the estimate; it is not a statistical interval."
                in text
            ), path
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
