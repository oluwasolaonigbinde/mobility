import json
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
        raise ValueError("BACKEND_CORS_ORIGINS JSON value must be a list")
    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


CorsOrigins = Annotated[list[str], BeforeValidator(_parse_cors_origins)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "mobility-adtech-api"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str | None = None
    redis_url: str | None = None
    backend_cors_origins: CorsOrigins = Field(default_factory=list)
    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"
    jwt_secret_key: str = "change-me-local-development-secret-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_min_length: int = 12
    default_currency: str = "NGN"
    max_campaign_zone_area_sq_km: int = 5000
    max_location_pings_per_batch: int = 500
    location_ping_future_skew_seconds: int = 300
    location_ping_start_skew_seconds: int = 900
    max_location_accuracy_m: int = 10000
    max_location_speed_mps: int = 120

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with /")
        return value.rstrip("/") or "/"

    @field_validator("backend_cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str], info) -> list[str]:
        environment = str(info.data.get("environment", "local")).lower()
        local_environments = {"local", "dev", "development", "test", "testing"}
        if environment not in local_environments and "*" in value:
            raise ValueError("Wildcard CORS origins are not allowed outside local/test")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_token_expire_minutes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        return value

    @field_validator("password_min_length")
    @classmethod
    def validate_password_min_length(cls, value: int) -> int:
        if value < 12:
            raise ValueError("PASSWORD_MIN_LENGTH must be at least 12")
        return value

    @field_validator("max_campaign_zone_area_sq_km")
    @classmethod
    def validate_max_campaign_zone_area_sq_km(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_CAMPAIGN_ZONE_AREA_SQ_KM must be positive")
        return value

    @field_validator(
        "max_location_pings_per_batch",
        "location_ping_future_skew_seconds",
        "location_ping_start_skew_seconds",
        "max_location_accuracy_m",
        "max_location_speed_mps",
    )
    @classmethod
    def validate_positive_tracking_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Location tracking settings must be positive")
        return value

    @field_validator("default_currency")
    @classmethod
    def normalize_default_currency(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
