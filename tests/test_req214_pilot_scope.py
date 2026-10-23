"""Pilot audience removal and immutable issued-file authority."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.schemas.campaign_reports import CampaignReportCreate
from app.services.disclosure import DISCLOSURE_ROUTE_INVENTORY
from app.services.report_integrity import canonical_sha256
from app.services.report_issuances import _issued_snapshot_is_intact


def test_pilot_has_no_audience_routes_and_keeps_report_disclosure_registration():
    paths = create_app().openapi()["paths"]
    assert not any(
        word in path
        for path in paths
        for word in ("retargeting", "audience", "exposure-segments", "zone-insights")
    )
    assert "advertiser.campaign.report" in DISCLOSURE_ROUTE_INVENTORY
    assert not any("audience" in route for route in DISCLOSURE_ROUTE_INVENTORY)


@pytest.mark.parametrize("retired", [{"mode": "roi_enabled"}, {"roi": {}}])
def test_removed_financial_inputs_are_rejected(retired):
    with pytest.raises(ValidationError) as exc:
        CampaignReportCreate(
            campaign_id=uuid4(),
            client_request_id=uuid4(),
            start_date="2026-10-01",
            end_date="2026-10-08",
            **retired,
        )
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    "tamper", [None, "input_manifest", "result_manifest", "proof_manifest", "report_snapshot"]
)
def test_historical_ready_files_use_bound_hashes_without_reinterpreting_retired_formats(tamper):
    run = SimpleNamespace()
    issuance = SimpleNamespace(status="ready", snapshot={"historical": "issued bytes stay frozen"})
    issuance.snapshot_sha256 = canonical_sha256(issuance.snapshot)
    for field in ("input_manifest", "result_manifest", "proof_manifest", "report_snapshot"):
        value = {"mode": "roi_enabled", "linked_source_recommendations": ["historical"]}
        digest = canonical_sha256(value)
        setattr(run, field, value)
        setattr(run, field + "_sha256", digest)
        setattr(issuance, field + "_sha256", digest)
    if tamper:
        setattr(run, tamper, {"changed": "after issue"})
    assert _issued_snapshot_is_intact(issuance, run) is (not tamper)
