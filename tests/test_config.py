import base64
import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings

PRODUCTION_DATABASE_URL = (
    "postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require"
)
PRODUCTION_REDIS_URL = "rediss://:synthetic-redis-secret@redis:6379/0"


def production_settings(**overrides):
    values = {
        "environment": "production",
        "jwt_secret_key": "production-secret-with-at-least-32-characters",
        "database_url": PRODUCTION_DATABASE_URL,
        "redis_url": PRODUCTION_REDIS_URL,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_settings_defaults_load() -> None:
    settings = Settings()

    assert settings.app_name == "mobility-adtech-api"
    assert settings.environment == "local"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.request_id_header == "X-Request-ID"
    assert settings.max_location_pings_per_batch == 500
    assert settings.location_ping_future_skew_seconds == 300
    assert settings.location_ping_start_skew_seconds == 900
    assert settings.max_location_accuracy_m == 10000
    assert settings.max_location_speed_mps == 120
    assert settings.route_analytics_formula_version == "route_analytics_v1"
    assert settings.route_analytics_min_valid_pings == 2
    assert settings.route_analytics_moving_speed_mps == 1.0
    assert settings.route_analytics_stationary_speed_mps == 0.5
    assert settings.route_analytics_impossible_speed_mps == 55.0
    assert settings.route_analytics_max_ping_gap_seconds == 900
    assert settings.route_analytics_poor_accuracy_threshold_m == 100.0
    assert settings.route_analytics_poor_accuracy_ratio_threshold == 0.5
    assert settings.route_analytics_stationary_ratio_threshold == 0.8
    assert settings.route_analytics_looping_radius_m == 50.0
    assert settings.route_analytics_looping_min_distance_m == 1000.0
    assert settings.route_replay_detector_version == "route_replay_v1"
    assert settings.route_replay_coordinate_precision == 5
    assert settings.route_replay_time_tolerance_seconds == 5
    assert settings.route_replay_min_valid_pings == 10
    assert settings.route_replay_min_distance_m == 250.0
    assert settings.route_replay_max_evidence_matches == 10
    assert settings.impression_formula_version == "impressions_v1"
    assert settings.impression_default_traffic_density_per_km == 120.0
    assert settings.impression_default_dwell_impressions_per_minute == 3.0
    assert settings.impression_high_fraud_multiplier == 0.25
    assert settings.impression_medium_fraud_multiplier == 0.70
    assert settings.impression_low_fraud_multiplier == 0.90
    assert settings.impression_insufficient_data_confidence == 0.10
    assert settings.impression_min_confidence == 0.0
    assert settings.impression_max_confidence == 1.0
    assert settings.payout_formula_version == "payout_v1"
    assert settings.payout_default_base_rate_per_km == 0.0
    assert settings.payout_default_base_rate_per_active_hour == 0.0
    assert settings.payout_default_target_zone_bonus_rate_per_km == 0.0
    assert settings.payout_default_bonus_zone_bonus_rate_per_km == 0.0
    assert settings.payout_default_estimated_impression_rate_per_1000 == 0.0
    assert settings.payout_default_low_fraud_multiplier == 0.90
    assert settings.payout_default_medium_fraud_multiplier == 0.70
    assert settings.payout_default_high_fraud_multiplier == 0.25
    assert settings.payout_default_min_payout_per_trip == 0.0
    assert settings.payout_default_max_payout_per_trip is None
    assert settings.payout_crypto_key_version == 1
    assert len(settings.payout_crypto_keys[1]) == 32
    assert "AAECAw" not in repr(settings)


def test_payout_crypto_kek_is_required(monkeypatch) -> None:
    monkeypatch.delenv("PAYOUT_CRYPTO_KEYRING_B64")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        "{}",
        '{"1":"c2hvcnQ="}',
        '{"zero":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}',
    ],
)
def test_payout_crypto_keyring_must_contain_versioned_aes256_keys(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(payout_crypto_keyring_b64=value)


def test_payout_crypto_key_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(payout_crypto_key_version=0)


def test_payout_crypto_active_key_version_must_exist() -> None:
    with pytest.raises(ValidationError):
        Settings(payout_crypto_key_version=2)


@pytest.mark.parametrize(
    "value",
    ["not-json", "{}", '{"1":"c2hvcnQ="}', '{"zero":"c2hvcnQ="}'],
)
def test_trip_evidence_signing_keyring_requires_versioned_hmac_keys(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(trip_evidence_signing_keyring_b64=value)


def test_trip_evidence_signing_key_rotation_retains_verification_keys() -> None:
    encoded = {
        "1": base64.b64encode(b"a" * 32).decode(),
        "2": base64.b64encode(b"b" * 32).decode(),
    }
    settings = Settings(
        trip_evidence_signing_keyring_b64=json.dumps(encoded),
        trip_evidence_signing_key_version=2,
    )

    assert settings.trip_evidence_signing_keys == {1: b"a" * 32, 2: b"b" * 32}


@pytest.mark.parametrize("versions", [("1", "01"), ("01", "1")])
def test_trip_evidence_signing_key_versions_reject_decimal_aliases(
    versions: tuple[str, str],
) -> None:
    encoded = {
        versions[0]: base64.b64encode(b"a" * 32).decode(),
        versions[1]: base64.b64encode(b"b" * 32).decode(),
    }

    with pytest.raises(ValidationError):
        Settings(trip_evidence_signing_keyring_b64=json.dumps(encoded))


def test_trip_evidence_active_signing_key_version_must_exist() -> None:
    encoded = base64.b64encode(b"a" * 32).decode()
    with pytest.raises(ValidationError, match="must exist"):
        Settings(
            trip_evidence_signing_keyring_b64=json.dumps({"1": encoded}),
            trip_evidence_signing_key_version=2,
        )


def test_cors_origin_string_parses_as_list() -> None:
    settings = Settings(backend_cors_origins="http://localhost:3000,http://localhost:5173")

    assert settings.backend_cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_cors_origin_json_string_parses_as_list() -> None:
    settings = Settings(backend_cors_origins='["http://localhost:3000","http://localhost:5173"]')

    assert settings.backend_cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_wildcard_cors_rejected_outside_local_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", backend_cors_origins=["*"])


def test_default_jwt_secret_rejected_outside_local_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_custom_jwt_secret_allowed_outside_local_environment() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.jwt_secret_key == "production-secret-with-at-least-32-characters"


def test_nonlocal_runtime_dependencies_require_authenticated_tls_urls() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        production_settings(database_url=None)
    with pytest.raises(ValidationError, match="REDIS_URL"):
        production_settings(redis_url=None)
    settings = production_settings()
    assert settings.database_url == PRODUCTION_DATABASE_URL
    assert settings.redis_url == PRODUCTION_REDIS_URL


@pytest.mark.parametrize(
    "host",
    [
        "db.local",
        "db.example",
        "example.com",
        "cache.example.net",
        "db.example.org",
        "change-me",
        "replace_me.internal",
        "todo-db.internal",
    ],
)
def test_nonlocal_runtime_urls_reject_special_use_and_placeholder_hosts(host: str) -> None:
    with pytest.raises(ValidationError):
        production_settings(
            database_url=(
                f"postgresql+asyncpg://mobility:synthetic-db-secret@{host}:5432/"
                "mobility?ssl=require"
            )
        )
    with pytest.raises(ValidationError):
        production_settings(
            redis_url=f"rediss://:synthetic-redis-secret@{host}:6379/0"
        )


@pytest.mark.parametrize("host", ["db", "postgres.internal", "10.42.0.8"])
def test_nonlocal_runtime_urls_allow_explicit_bundled_or_managed_hosts(host: str) -> None:
    settings = production_settings(
        database_url=(
            f"postgresql+asyncpg://mobility:synthetic-db-secret@{host}:5432/"
            "mobility?ssl=require"
        ),
        redis_url=f"rediss://:synthetic-redis-secret@{host}:6379/0",
    )
    assert settings.database_url
    assert settings.redis_url


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql+asyncpg://user:do-not-echo@db/mobility"),
        (
            "database_url",
            "postgresql+asyncpg://user:do-not-echo@db/mobility?ssl=require&host=elsewhere",
        ),
        ("redis_url", "redis://:do-not-echo@redis:6379/0"),
        ("redis_url", "rediss://:do-not-echo@redis:6379/0?ssl_cert_reqs=none"),
    ],
)
def test_nonlocal_runtime_url_rejections_redact_credentials(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as captured:
        production_settings(**{field: value})
    assert "do-not-echo" not in str(captured.value)


def test_dsr_exception_references_require_legal_approval_outside_test() -> None:
    with pytest.raises(ValidationError, match="approved privacy legal reference"):
        production_settings(dsr_approved_exception_references="LEGAL-EXCEPTION-1")

    settings = production_settings(
        privacy_legal_approval_reference="COUNSEL-APPROVAL-1",
        dsr_approved_exception_references="LEGAL-EXCEPTION-1",
    )
    assert settings.dsr_approved_exception_references == "LEGAL-EXCEPTION-1"


def test_short_jwt_secret_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret_key="too-short")


@pytest.mark.parametrize(
    "setting_name",
    [
        "max_location_pings_per_batch",
        "location_ping_future_skew_seconds",
        "location_ping_start_skew_seconds",
        "max_location_accuracy_m",
        "max_location_speed_mps",
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_location_tracking_settings_must_be_positive(
    setting_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


@pytest.mark.parametrize(
    "setting_name",
    [
        "route_analytics_min_valid_pings",
        "route_analytics_max_ping_gap_seconds",
        "route_analytics_moving_speed_mps",
        "route_analytics_stationary_speed_mps",
        "route_analytics_impossible_speed_mps",
        "route_analytics_poor_accuracy_threshold_m",
        "route_analytics_looping_radius_m",
        "route_analytics_looping_min_distance_m",
        "route_replay_time_tolerance_seconds",
        "route_replay_min_valid_pings",
        "route_replay_min_distance_m",
        "route_replay_max_evidence_matches",
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_route_analytics_settings_must_be_positive(
    setting_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


@pytest.mark.parametrize("invalid_value", [2, 8])
def test_route_replay_coordinate_precision_is_bounded(invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(route_replay_coordinate_precision=invalid_value)


@pytest.mark.parametrize(
    "setting_name",
    [
        "route_analytics_poor_accuracy_ratio_threshold",
        "route_analytics_stationary_ratio_threshold",
    ],
)
@pytest.mark.parametrize("invalid_value", [-0.1, 1.1])
def test_route_analytics_ratio_settings_must_be_between_zero_and_one(
    setting_name: str,
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


@pytest.mark.parametrize(
    "setting_name",
    [
        "impression_default_traffic_density_per_km",
        "impression_default_dwell_impressions_per_minute",
    ],
)
def test_impression_default_settings_must_be_nonnegative(setting_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: -1})


@pytest.mark.parametrize(
    "setting_name",
    [
        "impression_high_fraud_multiplier",
        "impression_medium_fraud_multiplier",
        "impression_low_fraud_multiplier",
        "impression_insufficient_data_confidence",
        "impression_min_confidence",
        "impression_max_confidence",
    ],
)
@pytest.mark.parametrize("invalid_value", [-0.1, 1.1])
def test_impression_ratio_settings_must_be_between_zero_and_one(
    setting_name: str,
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


def test_impression_min_confidence_must_not_exceed_max() -> None:
    with pytest.raises(ValidationError):
        Settings(impression_min_confidence=0.9, impression_max_confidence=0.5)


@pytest.mark.parametrize(
    "setting_name",
    [
        "payout_default_base_rate_per_km",
        "payout_default_base_rate_per_active_hour",
        "payout_default_target_zone_bonus_rate_per_km",
        "payout_default_bonus_zone_bonus_rate_per_km",
        "payout_default_estimated_impression_rate_per_1000",
        "payout_default_min_payout_per_trip",
        "payout_default_max_payout_per_trip",
    ],
)
def test_payout_default_settings_must_be_nonnegative(setting_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: -1})


@pytest.mark.parametrize(
    "setting_name",
    [
        "payout_default_low_fraud_multiplier",
        "payout_default_medium_fraud_multiplier",
        "payout_default_high_fraud_multiplier",
    ],
)
@pytest.mark.parametrize("invalid_value", [-0.1, 1.1])
def test_payout_ratio_settings_must_be_between_zero_and_one(
    setting_name: str,
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


def test_payout_max_default_must_not_be_below_min() -> None:
    with pytest.raises(ValidationError):
        Settings(payout_default_min_payout_per_trip=10, payout_default_max_payout_per_trip=9)


def test_blank_payout_max_default_parses_as_unset() -> None:
    settings = Settings(payout_default_max_payout_per_trip="")

    assert settings.payout_default_max_payout_per_trip is None


def test_file_kyc_retention_has_no_default_and_blank_parses_as_unset() -> None:
    assert Settings().file_kyc_retention_days is None
    assert Settings(file_kyc_retention_days="").file_kyc_retention_days is None


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_file_kyc_retention_must_be_positive_when_configured(invalid_value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(file_kyc_retention_days=invalid_value)


def test_recurring_evidence_policy_has_no_production_defaults() -> None:
    settings = Settings(
        evidence_high_earner_threshold_ngn="",
        evidence_renewal_lookback_days="",
        evidence_challenge_response_hours="",
    )

    assert settings.evidence_high_earner_threshold_ngn == ""
    assert settings.evidence_renewal_lookback_days is None
    assert settings.evidence_challenge_response_hours is None


def test_email_provider_and_receipt_authority_have_no_production_defaults() -> None:
    settings = Settings(
        email_provider="",
        email_sender_address="",
        email_smtp_host="",
        email_receipt_signing_secret=None,
        email_receipt_key_id="",
    )

    assert settings.email_provider == ""
    assert settings.email_sender_address == ""
    assert settings.email_smtp_host == ""
    assert settings.email_receipt_signing_secret is None
    assert settings.email_receipt_key_id == ""


@pytest.mark.parametrize("invalid_provider", ["ses", "sendgrid", "unknown"])
def test_email_provider_rejects_unimplemented_live_choices(invalid_provider: str) -> None:
    with pytest.raises(ValidationError):
        Settings(email_provider=invalid_provider)


def test_email_receipt_secret_rejects_short_values() -> None:
    with pytest.raises(ValidationError):
        Settings(email_receipt_signing_secret="too-short")

    assert Settings(email_receipt_signing_secret="").email_receipt_signing_secret is None


@pytest.mark.parametrize(
    "setting_name",
    [
        "email_smtp_port",
        "email_delivery_max_attempts",
        "email_delivery_retry_base_seconds",
        "email_delivery_claim_seconds",
    ],
)
def test_email_delivery_numeric_settings_must_be_positive(setting_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: 0})


@pytest.mark.parametrize(
    "setting_name",
    ["evidence_renewal_lookback_days", "evidence_challenge_response_hours"],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_recurring_evidence_windows_must_be_positive(
    setting_name: str, invalid_value: int
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


def test_payout_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PAYOUT_FORMULA_VERSION", "payout_v1")
    monkeypatch.setenv("PAYOUT_DEFAULT_BASE_RATE_PER_KM", "11.5")
    monkeypatch.setenv("PAYOUT_DEFAULT_BASE_RATE_PER_ACTIVE_HOUR", "22.5")
    monkeypatch.setenv("PAYOUT_DEFAULT_TARGET_ZONE_BONUS_RATE_PER_KM", "3.5")
    monkeypatch.setenv("PAYOUT_DEFAULT_BONUS_ZONE_BONUS_RATE_PER_KM", "4.5")
    monkeypatch.setenv("PAYOUT_DEFAULT_ESTIMATED_IMPRESSION_RATE_PER_1000", "5.5")
    monkeypatch.setenv("PAYOUT_DEFAULT_LOW_FRAUD_MULTIPLIER", "0.91")
    monkeypatch.setenv("PAYOUT_DEFAULT_MEDIUM_FRAUD_MULTIPLIER", "0.61")
    monkeypatch.setenv("PAYOUT_DEFAULT_HIGH_FRAUD_MULTIPLIER", "0.21")
    monkeypatch.setenv("PAYOUT_DEFAULT_MIN_PAYOUT_PER_TRIP", "10")
    monkeypatch.setenv("PAYOUT_DEFAULT_MAX_PAYOUT_PER_TRIP", "")

    settings = Settings()

    assert settings.payout_formula_version == "payout_v1"
    assert settings.payout_default_base_rate_per_km == 11.5
    assert settings.payout_default_base_rate_per_active_hour == 22.5
    assert settings.payout_default_target_zone_bonus_rate_per_km == 3.5
    assert settings.payout_default_bonus_zone_bonus_rate_per_km == 4.5
    assert settings.payout_default_estimated_impression_rate_per_1000 == 5.5
    assert settings.payout_default_low_fraud_multiplier == 0.91
    assert settings.payout_default_medium_fraud_multiplier == 0.61
    assert settings.payout_default_high_fraud_multiplier == 0.21
    assert settings.payout_default_min_payout_per_trip == 10
    assert settings.payout_default_max_payout_per_trip is None


def test_default_currency_must_be_three_letters() -> None:
    with pytest.raises(ValidationError):
        Settings(default_currency="NGNA")
