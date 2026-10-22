"""Pilot audience removal and immutable issued-file authority."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas.measurement import MeasurementRunCreate
from app.services.disclosure import DISCLOSURE_ROUTE_INVENTORY
from app.services.measurement import canonical_sha256
from app.services.report_issuances import _issuance_authority_matches


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
        MeasurementRunCreate(
            campaign_id=uuid4(),
            client_request_id=uuid4(),
            period_start_at="2026-10-01T00:00:00Z",
            period_end_at="2026-10-08T00:00:00Z",
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
    assert _issuance_authority_matches(issuance, run, Settings(environment="test")) is (not tamper)
