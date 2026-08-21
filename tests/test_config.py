import pytest
from pydantic import ValidationError

from app.core.config import Settings


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


def test_cors_origin_string_parses_as_list() -> None:
    settings = Settings(backend_cors_origins="http://localhost:3000,http://localhost:5173")

    assert settings.backend_cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_cors_origin_json_string_parses_as_list() -> None:
    settings = Settings(
        backend_cors_origins='["http://localhost:3000","http://localhost:5173"]'
    )

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
    settings = Settings(
        environment="production",
        jwt_secret_key="production-secret-with-at-least-32-characters",
    )

    assert settings.environment == "production"
    assert settings.jwt_secret_key == "production-secret-with-at-least-32-characters"


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
