from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.installation_evidence import InstallationEvidenceStatus
from app.schemas.campaign_assignments import AssignmentReadinessRead
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.drivers import normalize_optional_text


class InstallationPhotoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: str = Field(min_length=1, max_length=64)
    stored_file_id: UUID

    @field_validator("view")
    @classmethod
    def normalize_view(cls, value: str) -> str:
        return value.strip().lower()


class InstallationEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    device_id: UUID
    captured_at: datetime
    photos: list[InstallationPhotoCreate] = Field(min_length=1, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_aware(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


class InstallationEvidenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class InstallationEvidencePhotoRead(BaseModel):
    view: str
    stored_file_id: UUID


class InstallationEvidenceRead(BaseModel):
    activation: AssignmentReadinessRead | None = None
    driver_name: str | None = None
    campaign_name: str | None = None
    id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    submitted_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    revision: int
    device_id: UUID
    captured_at: datetime
    status: InstallationEvidenceStatus
    rejection_reason: str | None
    reviewed_at: datetime | None
    approved_until: datetime | None
    photos: list[InstallationEvidencePhotoRead]
    metadata: dict[str, Any]
    submitted_at: datetime


class InstallationEvidenceList(BaseModel):
    items: list[InstallationEvidenceRead]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class InstallationEvidencePolicyRead(BaseModel):
    required_views: list[str]
    evidence_validity_hours: int
