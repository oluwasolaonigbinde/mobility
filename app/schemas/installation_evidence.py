from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.installation_evidence import InstallationEvidenceStatus
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


class InstallationEvidencePolicyRead(BaseModel):
    configured: bool
    can_upload: bool
    required_views: list[str]
    evidence_validity_hours: int | None
    display_proof_challenge_ttl_seconds: int | None
    display_proof_validity_seconds: int | None


class DisplayProofChallengeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID


class DisplayProofChallengeRead(BaseModel):
    challenge_id: UUID
    nonce: str
    evidence_submission_id: UUID
    expires_at: datetime


class DisplayProofCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    nonce: str = Field(min_length=32, max_length=256)
    device_id: UUID
    stored_file_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisplayProofRead(BaseModel):
    id: UUID
    challenge_id: UUID
    assignment_id: UUID
    evidence_submission_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    device_id: UUID
    stored_file_id: UUID
    verified_at: datetime
    valid_until: datetime
    metadata: dict[str, Any]
