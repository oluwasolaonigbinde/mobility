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
