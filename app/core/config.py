import json
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, field_validator, model_validator
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
    route_analytics_formula_version: str = "route_analytics_v1"
    route_analytics_min_valid_pings: int = 2
    route_analytics_moving_speed_mps: float = 1.0
    route_analytics_stationary_speed_mps: float = 0.5
    route_analytics_impossible_speed_mps: float = 55.0
    route_analytics_max_ping_gap_seconds: int = 900
    route_analytics_poor_accuracy_threshold_m: float = 100.0
    route_analytics_poor_accuracy_ratio_threshold: float = 0.5
    route_analytics_stationary_ratio_threshold: float = 0.8
    route_analytics_looping_radius_m: float = 50.0
    route_analytics_looping_min_distance_m: float = 1000.0
    impression_formula_version: str = "impressions_v1"
    impression_default_traffic_density_per_km: float = 120.0
    impression_default_dwell_impressions_per_minute: float = 3.0
    impression_high_fraud_multiplier: float = 0.25
    impression_medium_fraud_multiplier: float = 0.70
    impression_low_fraud_multiplier: float = 0.90
    impression_insufficient_data_confidence: float = 0.10
    impression_min_confidence: float = 0.0
    impression_max_confidence: float = 1.0

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

    @field_validator(
        "route_analytics_min_valid_pings",
        "route_analytics_max_ping_gap_seconds",
    )
    @classmethod
    def validate_positive_route_analytics_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Route analytics integer settings must be positive")
        return value

    @field_validator(
        "route_analytics_moving_speed_mps",
        "route_analytics_stationary_speed_mps",
        "route_analytics_impossible_speed_mps",
        "route_analytics_poor_accuracy_threshold_m",
        "route_analytics_looping_radius_m",
        "route_analytics_looping_min_distance_m",
    )
    @classmethod
    def validate_positive_route_analytics_floats(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Route analytics numeric settings must be positive")
        return value

    @field_validator(
        "route_analytics_poor_accuracy_ratio_threshold",
        "route_analytics_stationary_ratio_threshold",
    )
    @classmethod
    def validate_route_analytics_ratios(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Route analytics ratio settings must be between 0 and 1")
        return value

    @field_validator(
        "impression_default_traffic_density_per_km",
        "impression_default_dwell_impressions_per_minute",
    )
    @classmethod
    def validate_nonnegative_impression_defaults(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Impression default settings must be nonnegative")
        return value

    @field_validator(
        "impression_high_fraud_multiplier",
        "impression_medium_fraud_multiplier",
        "impression_low_fraud_multiplier",
        "impression_insufficient_data_confidence",
        "impression_min_confidence",
        "impression_max_confidence",
    )
    @classmethod
    def validate_impression_ratios(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Impression ratio settings must be between 0 and 1")
        return value

    @field_validator("default_currency")
    @classmethod
    def normalize_default_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_impression_confidence_bounds(self) -> "Settings":
        if self.impression_min_confidence > self.impression_max_confidence:
            raise ValueError("IMPRESSION_MIN_CONFIDENCE must not exceed IMPRESSION_MAX_CONFIDENCE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
