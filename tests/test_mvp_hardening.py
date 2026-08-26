import json
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
)

from app.main import create_app
from app.models.user import UserRole

SNAPSHOT_PATH = Path("docs/api/openapi.snapshot.json")
EXPECTED_ALEMBIC_HEAD = "0064_budget_notifications_recovery"
EXPECTED_MIGRATIONS = {
    "0001_enable_extensions.py",
    "0002_identity_and_organizations.py",
    "0003_driver_vehicle_foundations.py",
    "0004_campaigns_and_creatives.py",
    "0005_campaign_zones.py",
    "0006_campaign_assignments.py",
    "0007_trip_tracking.py",
    "0008_route_analytics_and_fraud_flags.py",
    "0009_impression_estimation.py",
    "0010_payouts_and_earnings.py",
    "0011_user_password_management.py",
    "0012_audit_event_indexes.py",
    "0013_payout_v2_hourly_caps.py",
    "0014_location_pings_partitioning.py",
    "0015_payout_day_allocation.py",
    "0016_trip_seal_protocol.py",
    "0017_seal_review_hardening.py",
    "0018_payout_rule_revisions.py",
    "0019_assignment_rule_bindings.py",
    "0020_payout_correction_orders.py",
    "0021_frozen_payout_v3_terms.py",
    "0022_current_fraud_assessments.py",
    "0023_route_replay_signatures.py",
    "0024_fraud_review_holds.py",
    "0025_fraud_disputes_notifications.py",
    "0026_frozen_campaign_payment_window.py",
    "0027_earnings_release_sla.py",
    "0028_protected_payee_accounts.py",
    "0029_payout_batch_reservation.py",
    "0030_provider_line_reconciliation.py",
    "0031_carry_forward_payout_debt.py",
    "0032_commercial_quotation_terms.py",
    "0033_advertiser_company_profiles.py",
    "0034_canonical_receipts_allocations.py",
    "0035_vat_itemised_invoices.py",
    "0036_invoice_authority_hardening.py",
    "0037_funded_liability_authority.py",
    "0038_payment_gateway_events.py",
    "0039_billing_corrections_refunds.py",
    "0040_budget_policy_blocked_state.py",
    "0041_invoice_correction_retry_identity.py",
    "0042_invoice_number_prefix_sequence.py",
    "0043_campaign_review_lifecycle.py",
    "0044_notification_outbox.py",
    "0045_disclosure_query_history.py",
    "0046_retargeting_sources.py",
    "0047_retargeting_source_links.py",
    "0048_campaign_assignment_offer_lifecycle.py",
    "0049_assignment_activity_flags.py",
    "0050_driver_applications.py",
    "0051_canonical_impression_authority.py",
    "0052_stored_files.py",
    "0053_file_scanning.py",
    "0054_managed_creatives.py",
    "0055_kyc_key_custody.py",
    "0056_creative_review.py",
    "0057_installation_evidence.py",
    "0058_campaign_changes.py",
    "0059_campaign_cancellations.py",
    "0060_evidence_verifications.py",
    "0061_email_delivery.py",
    "0062_data_subject_requests.py",
    "0063_measurement_runs.py",
    "0064_budget_notifications_recovery.py",
}
MAJOR_CONTRACT_PATHS = {
    "health": "/api/v1/health",
    "auth": "/api/v1/auth/login",
    "me": "/api/v1/me",
    "admin users": "/api/v1/admin/users",
    "admin orgs": "/api/v1/admin/advertiser-organizations",
    "driver profiles": "/api/v1/driver/profile",
    "vehicles": "/api/v1/driver/vehicles",
    "campaigns": "/api/v1/advertiser/campaigns",
    "creatives": "/api/v1/advertiser/campaigns/{campaign_id}/creatives",
    "campaign zones": "/api/v1/advertiser/campaigns/{campaign_id}/zones",
    "assignments": "/api/v1/admin/campaign-assignments",
    "trips": "/api/v1/driver/trips/{trip_id}",
    "pings": "/api/v1/driver/trips/{trip_id}/pings",
    "analytics": "/api/v1/admin/trips/{trip_id}/analytics",
    "fraud": "/api/v1/admin/fraud-flags",
    "impressions": "/api/v1/admin/impression-estimates",
    "payouts": "/api/v1/admin/payout-calculations",
    "earnings": "/api/v1/driver/earnings/ledger",
    "advertiser reports": "/api/v1/advertiser/campaigns/{campaign_id}/report",
    "heatmaps": "/api/v1/advertiser/campaigns/{campaign_id}/heatmap",
    "planning sources": "/api/v1/advertiser/retargeting-sources",
    "planning source links": "/api/v1/advertiser/retargeting-source-links",
    "protected KYC": "/api/v1/driver/kyc/submissions",
}
PROTECTED_GET_PATHS = [
    "/api/v1/me",
    "/api/v1/admin/users",
    "/api/v1/admin/campaigns",
    "/api/v1/advertiser/organization",
    "/api/v1/advertiser/campaigns",
    "/api/v1/driver/profile",
    "/api/v1/driver/vehicles",
    "/api/v1/admin/payout-calculations",
    "/api/v1/driver/earnings/ledger",
]
SENSITIVE_ADVERTISER_TERMS = {
    "password_hash",
    "license_number",
    "plate_number",
    "plate_number_normalized",
    "idempotency_key",
    "location_ping",
    "raw_gps",
    "driver_email",
    "driver_phone",
    "driver_full_name",
    "ledger_entry_id",
}


def test_openapi_snapshot_exists_and_contains_mvp_contract_paths() -> None:
    assert SNAPSHOT_PATH.exists()

    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snapshot["info"]["title"] == "mobility-adtech-api"
    assert snapshot["paths"]["/api/v1/health"]

    missing = [
        f"{group}: {path}"
        for group, path in MAJOR_CONTRACT_PATHS.items()
        if path not in snapshot["paths"]
    ]
    assert missing == []


def test_generated_openapi_matches_checked_in_snapshot_paths(client) -> None:
    generated = client.get("/openapi.json").json()
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert set(generated["paths"]) == set(snapshot["paths"])


def test_openapi_snapshot_omits_secrets_and_advertiser_sensitive_terms() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot_text = json.dumps(snapshot).lower()

    assert "password_hash" not in snapshot_text
    assert "database_url" not in snapshot_text
    assert "jwt_secret" not in snapshot_text
    assert "postgresql+asyncpg" not in snapshot_text

    advertiser_path_text = json.dumps(
        {
            path: operations
            for path, operations in snapshot["paths"].items()
            if path.startswith("/api/v1/advertiser/") or "heatmap" in path
        }
    ).lower()
    for term in SENSITIVE_ADVERTISER_TERMS:
        assert term not in advertiser_path_text


def test_representative_protected_get_routes_reject_missing_auth(db_client) -> None:
    for path in PROTECTED_GET_PATHS:
        response = db_client.get(path, headers={"X-Request-ID": f"slice13-{path}"})

        assert response.status_code == 401, path
        payload = response.json()
        assert payload["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert payload["error"]["request_id"].startswith("slice13-")


def test_static_routes_precede_dynamic_siblings(settings) -> None:
    routes = list(create_app(settings).openapi()["paths"])

    assert routes.index("/api/v1/driver/campaign-assignments/active") < routes.index(
        "/api/v1/driver/campaign-assignments/{assignment_id}"
    )
    assert routes.index("/api/v1/driver/trips/current") < routes.index(
        "/api/v1/driver/trips/{trip_id}"
    )


def test_no_public_delete_routes_for_payout_ledger_critical_parents(settings) -> None:
    delete_paths = {
        path
        for path, operations in create_app(settings).openapi()["paths"].items()
        if "delete" in operations
    }

    assert delete_paths == {"/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}"}


def test_migration_chain_matches_authorized_head() -> None:
    migration_names = {
        path.name for path in Path("alembic/versions").glob("*.py") if path.name != "__init__.py"
    }

    assert migration_names == EXPECTED_MIGRATIONS

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == [EXPECTED_ALEMBIC_HEAD]


def test_cost_summary_invalid_date_range_uses_standard_error_envelope(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    headers = auth_headers(db_client, "advertiser@example.com")
    headers["X-Request-ID"] = "slice13-cost-range"

    response = db_client.get(
        (
            f"/api/v1/advertiser/campaigns/{campaign.id}/cost-summary"
            "?start_at=2026-01-02T00:00:00%2B00:00"
            "&end_at=2026-01-01T00:00:00%2B00:00"
        ),
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_DATE_RANGE",
            "message": "start_at must be before or equal to end_at",
            "details": {},
            "request_id": "slice13-cost-range",
        }
    }


def test_advertiser_campaign_list_invalid_date_range_uses_standard_error_envelope(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="campaign-list-range-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    headers = auth_headers(db_client, "campaign-list-range-advertiser@example.com")
    headers["X-Request-ID"] = "slice13-campaign-list-range"

    response = db_client.get(
        (
            "/api/v1/advertiser/campaigns"
            "?start_at_from=2026-01-02T00:00:00%2B00:00"
            "&start_at_to=2026-01-01T00:00:00%2B00:00"
        ),
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_DATE_RANGE",
            "message": "start_at_from must be before or equal to start_at_to",
            "details": {},
            "request_id": "slice13-campaign-list-range",
        }
    }


def test_advertiser_campaign_list_naive_datetime_uses_standard_error_envelope(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="campaign-list-naive-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    headers = auth_headers(db_client, "campaign-list-naive-advertiser@example.com")
    headers["X-Request-ID"] = "slice13-campaign-list-naive"

    response = db_client.get(
        "/api/v1/advertiser/campaigns?start_at_from=2026-01-01T00:00:00",
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {
                "errors": [
                    {
                        "loc": ["query", "start_at_from"],
                        "msg": "Datetime must include timezone information",
                    }
                ]
            },
            "request_id": "slice13-campaign-list-naive",
        }
    }


def test_impression_summary_invalid_date_range_uses_standard_error_envelope(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="impression-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    headers = auth_headers(db_client, "impression-advertiser@example.com")
    headers["X-Request-ID"] = "slice13-impression-range"

    response = db_client.get(
        (
            f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary"
            "?start_at=2026-01-02T00:00:00%2B00:00"
            "&end_at=2026-01-01T00:00:00%2B00:00"
        ),
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_DATE_RANGE",
            "message": "start_at must be before or equal to end_at",
            "details": {},
            "request_id": "slice13-impression-range",
        }
    }


def test_impression_summary_naive_datetime_uses_standard_error_envelope(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="impression-naive-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    headers = auth_headers(db_client, "impression-naive-advertiser@example.com")
    headers["X-Request-ID"] = "slice13-impression-naive"

    response = db_client.get(
        (
            f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary"
            "?start_at=2026-01-01T00:00:00"
        ),
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {
                "errors": [
                    {
                        "loc": ["query", "start_at"],
                        "msg": "Datetime must include timezone information",
                    }
                ]
            },
            "request_id": "slice13-impression-naive",
        }
    }
