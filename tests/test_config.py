import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_load() -> None:
    settings = Settings()

    assert settings.app_name == "mobility-adtech-api"
    assert settings.environment == "local"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.request_id_header == "X-Request-ID"


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
