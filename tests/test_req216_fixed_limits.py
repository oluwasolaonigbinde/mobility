"""D117: defaults are unchanged and deployment input cannot loosen them."""

from pathlib import Path

import pytest

from app.core.config import Settings

# Captured from the pre-B5 configuration, not calculated from current defaults.
EXPECTED_LIMITS = {
    "access_token_expire_minutes": 60,
    "campaign_enquiry_rate_limit_global_max_attempts": 100,
    "campaign_enquiry_rate_limit_ip_max_attempts": 5,
    "campaign_enquiry_rate_limit_window_seconds": 3600,
    "driver_account_setup_ttl_seconds": 86400,
    "driver_onboarding_access_ttl_seconds": 86400,
    "driver_registration_rate_limit_email_max_attempts": 3,
    "driver_registration_rate_limit_email_window_seconds": 3600,
    "driver_registration_rate_limit_ip_max_attempts": 10,
    "driver_registration_rate_limit_ip_window_seconds": 3600,
    "email_delivery_claim_seconds": 120,
    "email_delivery_max_attempts": 5,
    "email_delivery_retry_base_seconds": 60,
    "fraud_review_sla_days": 7,
    "location_ping_end_skew_seconds": 300,
    "location_ping_future_skew_seconds": 300,
    "location_ping_start_skew_seconds": 900,
    "login_rate_limit_account_max_failures": 5,
    "login_rate_limit_account_window_seconds": 900,
    "login_rate_limit_global_max_failures": 250,
    "login_rate_limit_global_window_seconds": 300,
    "login_rate_limit_ip_max_failures": 150,
    "login_rate_limit_ip_window_seconds": 300,
    "malware_scanner_port": 3310,
    "malware_scanner_timeout_seconds": 30,
    "max_campaign_zone_area_sq_km": 5000,
    "max_location_accuracy_m": 10000,
    "max_location_pings_per_batch": 500,
    "max_location_speed_mps": 120,
    "object_storage_download_ttl_seconds": 60,
    "object_storage_orphan_ttl_hours": 24,
    "object_storage_presign_ttl_seconds": 300,
    "password_min_length": 12,
    "password_reset_account_max_attempts": 3,
    "password_reset_ip_max_attempts": 10,
    "password_reset_rate_window_seconds": 3600,
    "password_reset_ttl_seconds": 1800,
    "phone_verification_max_code_attempts": 5,
    "phone_verification_request_max_attempts": 3,
    "phone_verification_request_window_seconds": 3600,
    "phone_verification_ttl_seconds": 600,
    "session_absolute_lifetime_minutes": 720,
    "trip_seal_grace_seconds": 600,
    "worker_sweep_batch_size": 25,
    "worker_sweep_interval_minutes": 5,
}


@pytest.mark.parametrize("name,expected", EXPECTED_LIMITS.items())
def test_fixed_limit_matches_before_value_and_ignores_environment(name, expected, monkeypatch):
    monkeypatch.setenv(name.upper(), "999999")
    settings = Settings(_env_file=None, **{name: 0})
    assert name not in Settings.model_fields
    assert getattr(settings, name) == expected


def test_phone_support_destination_and_retired_authority(settings):
    assert Settings(_env_file=None).phone_verification_terrax_number == "+2347074200080"
    for name in (
        "phone_operator_external_approved",
        "phone_operator_name",
        "phone_whatsapp_notice_approval_reference",
        "email_receipt_signing_secret",
        "email_receipt_key_id",
    ):
        assert name not in Settings.model_fields
        assert not hasattr(settings, name)


def test_all_runtime_templates_default_to_client_support_number():
    root = Path(__file__).resolve().parents[1]
    for name in (".env.example", "production.env.example", "staging.env.example"):
        assert "PHONE_VERIFICATION_TERRAX_NUMBER=+2347074200080\n" in (root / name).read_text()
    for name in ("docker-compose.yml", "docker-compose.production.yml"):
        source = (root / name).read_text()
        assert "${PHONE_VERIFICATION_TERRAX_NUMBER:-+2347074200080}" in source
        assert "PHONE_OPERATOR_EXTERNAL_APPROVED" not in source
