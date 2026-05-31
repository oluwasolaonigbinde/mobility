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
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_route_analytics_settings_must_be_positive(
    setting_name: str,
    invalid_value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: invalid_value})


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
