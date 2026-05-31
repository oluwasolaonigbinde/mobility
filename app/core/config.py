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


@lru_cache
def get_settings() -> Settings:
    return Settings()
