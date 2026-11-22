from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.errors import AppError
from app.models.driver_application import DriverApplicationStatus
from app.schemas.driver_onboarding import (
    AdminPersonPayeeStageRead,
    AdminVehicleStageRead,
)
from app.services.contacts import normalize_phone_input
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
    service_city: str = Field(min_length=1, max_length=128)
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

    @field_validator("service_city")
    @classmethod
    def require_city(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Choose the city you drive in")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_optional_phone(cls, value: str | None) -> str | None:
        value = _trim(value)
        if value is None:
            return None
        try:
            return normalize_phone_input(value)
        except AppError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        normalized = _trim(value)
        return normalized.upper() if normalized is not None else None


class DriverApplicationSubmitResponse(BaseModel):
    status: Literal[DriverApplicationStatus.PENDING.value] = DriverApplicationStatus.PENDING.value
    message: str
    application_reference: str


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
    vehicle: AdminVehicleStageRead = Field(default_factory=AdminVehicleStageRead)


AdminApplicantStage = Literal[
    "Waiting for ID and bank details",
    "ID and bank to review",
    "ID or bank sent back for changes",
    "Waiting for car details",
    "Car to review",
    "Car sent back for changes",
    "Ready for account setup",
    "Added by staff",
]


class AdminApplicantRead(BaseModel):
    stage: AdminApplicantStage
    kind: Literal["application", "staff_added"]
    id: UUID
    application_id: UUID | None
    driver_profile_id: UUID
    user_id: UUID
    full_name: str
    email: str
    phone: str | None
    service_city: str | None
    created_at: datetime


class DriverApplicationAdminListResponse(BaseModel):
    items: list[DriverApplicationAdminRead]
    applicants: list[AdminApplicantRead] | None = None
    total: int
    limit: int
    offset: int


class DriverOnboardingAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email_identity(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized


class DriverAccountSetupInitiate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID


class DriverAccountSetupRead(BaseModel):
    id: UUID
    application_id: UUID
    expires_at: datetime
    state: Literal["pending", "used", "superseded"]


class DriverAccountSetupComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1)


class DriverPublicCommandResponse(BaseModel):
    message: str
