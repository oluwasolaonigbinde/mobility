from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.driver import DriverOnboardingStatus


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_optional_country_code(value: str | None) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    normalized = normalized.upper()
    if len(normalized) != 2:
        raise ValueError("Country code must be two characters")
    return normalized


class DriverProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onboarding_status: DriverOnboardingStatus = DriverOnboardingStatus.PENDING
    license_number: str | None = Field(default=None, max_length=128)
    service_city: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("license_number", "service_city")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return normalize_optional_country_code(value)


class DriverProfileAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    onboarding_status: DriverOnboardingStatus | None = None
    license_number: str | None = Field(default=None, max_length=128)
    service_city: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    metadata: dict[str, Any] | None = None

    @field_validator("license_number", "service_city")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return normalize_optional_country_code(value)


class DriverProfileSelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    license_number: str | None = Field(default=None, max_length=128)
    service_city: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("license_number", "service_city")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return normalize_optional_country_code(value)


class DriverProfileRead(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    phone: str | None
    onboarding_status: DriverOnboardingStatus
    license_number: str | None
    service_city: str | None
    country_code: str | None
    created_at: datetime
    updated_at: datetime


class AdminDriverProfileRead(DriverProfileRead):
    metadata: dict[str, Any] = Field(default_factory=dict)


class DriverProfileListResponse(BaseModel):
    items: list[AdminDriverProfileRead]
    total: int
    limit: int
    offset: int
