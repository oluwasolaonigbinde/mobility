from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.driver_application import DriverApplicationStatus
from app.schemas.driver_onboarding import AdminPersonPayeeStageRead, PersonPayeeStageRead
from app.services.users import normalize_email


def _trim(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class DriverApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    service_city: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("full_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name is required")
        return normalized

    @field_validator("phone", "service_city")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return _trim(value)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        normalized = _trim(value)
        return normalized.upper() if normalized is not None else None


class DriverApplicationSubmitResponse(BaseModel):
    status: Literal[DriverApplicationStatus.PENDING.value] = DriverApplicationStatus.PENDING.value
    message: str
    application_reference: str


class DriverApplicationStatusResponse(BaseModel):
    status: Literal[DriverApplicationStatus.PENDING.value] = DriverApplicationStatus.PENDING.value
    message: str
    person_payee: PersonPayeeStageRead = Field(
        default_factory=lambda: PersonPayeeStageRead(status="not_submitted")
    )


class DriverApplicationAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    driver_profile_id: UUID
    status: DriverApplicationStatus
    email: str
    full_name: str
    phone: str | None
    service_city: str | None
    country_code: str | None
    created_at: datetime
    updated_at: datetime
    person_payee: AdminPersonPayeeStageRead = Field(
        default_factory=lambda: AdminPersonPayeeStageRead(status="not_submitted")
    )


class DriverApplicationAdminListResponse(BaseModel):
    items: list[DriverApplicationAdminRead]
    total: int
    limit: int
    offset: int
