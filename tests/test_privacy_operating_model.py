from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "docs" / "privacy-register.json"
MODEL_PATH = ROOT / "docs" / "privacy-operating-model.md"
TABLETOP_PATH = ROOT / "docs" / "privacy-tabletop-w3-00a.md"


def load_register() -> dict:
    return json.loads(REGISTER_PATH.read_text())


def test_privacy_register_is_fail_closed_and_complete() -> None:
    register = load_register()

    assert register["schema_version"] == "privacy-register-v1"
    assert register["status"] == "DRAFT_BUILD_ONLY"
    assert register["external_gate"] == "EXT-LEGAL-PRIVACY"
    assert register["live_use_authorized"] is False
    assert set(register["approval"].values()) == {"MISSING"}

    role_keys = set(register["role_allocation"])
    assert {
        "business_controller_role",
        "privacy_approval_role",
        "platform_operator_role",
        "processor_allocation",
        "data_subjects",
    } <= role_keys

    purposes = register["purposes"]
    assert len(purposes) == 9
    assert len({purpose["id"] for purpose in purposes}) == len(purposes)
    required_purpose_fields = {
        "id",
        "purpose",
        "data_classes",
        "owner_role",
        "lawful_basis_candidate",
        "basis_approval",
        "retention_class",
        "recipients",
        "withdrawal_or_objection_effect",
    }
    for purpose in purposes:
        assert required_purpose_fields <= set(purpose)
        assert all(purpose[field] for field in required_purpose_fields)
        assert purpose["basis_approval"] == "MISSING"

    tracking = next(purpose for purpose in purposes if purpose["id"] == "P03_TRIP_TRACKING")
    assert tracking["recipients"] == [
        "existing analytics, fraud and payout services",
        "the grandfathered heatmap service until W3-00C migration",
    ]
    assert all("staff" not in recipient.lower() for recipient in tracking["recipients"])

    retention = {row["id"]: row for row in register["retention_schedule"]}
    assert {purpose["retention_class"] for purpose in purposes} == set(retention)
    registered_classes = {
        data_class
        for purpose in purposes
        for data_class in purpose["data_classes"]
    }
    retained_classes = {
        data_class
        for row in retention.values()
        for data_class in row["data_classes"]
    }
    assert registered_classes == retained_classes
    assert all(row["approval"] == "MISSING" for row in retention.values())


def test_provider_notice_breach_and_dpia_registers_do_not_claim_approval() -> None:
    register = load_register()

    assert register["subprocessors"]
    for processor in register["subprocessors"]:
        assert processor["provider"] == "MISSING"
        assert processor["region"] == "MISSING"
        assert processor["agreement"] == "MISSING"
        assert processor["live_use"] is False

    notice = register["notice_and_consent"]
    assert notice["approved_notice_versions"] == []
    assert notice["live_tracking_notice"] == "MISSING"
    assert len(notice["withdrawal_procedure"]) >= 6

    breach = register["breach_responsibilities"]
    assert breach["notification_deadline"].startswith("MISSING")
    assert len(breach["steps"]) >= 5

    risks = register["dpia_risks"]
    assert len(risks) >= 7
    assert all(risk["residual"].startswith("OPEN") for risk in risks)


def test_operating_model_and_tabletop_preserve_external_gates() -> None:
    model = MODEL_PATH.read_text()
    tabletop = TABLETOP_PATH.read_text()

    for required in (
        "EXT-LEGAL-PRIVACY",
        "live_use_authorized=false",
        "not legal approval",
        "Controller and processor allocation",
        "ROPA and purpose rules",
        "Retention and DSR posture",
        "Notice, consent, and withdrawal",
        "Breach register and escalation",
        "DPIA treatment",
    ):
        assert required in model

    assert "No real person" in tabletop
    assert "DSR-W3A-001" in tabletop
    assert "BREACH-W3A-001" in tabletop
    assert tabletop.count("BLOCKED") >= 4
    assert "W3-00B" in tabletop
    assert "W2-02E" in tabletop
