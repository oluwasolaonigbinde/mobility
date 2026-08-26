from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.evidence_verification import EvidenceVerificationStatus, EvidenceVerificationType


class PhysicalSpotCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    trip_session_id: UUID
    client_request_id: UUID
    note: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must not be blank")
        return normalized


class PhysicalSpotCheckResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["passed", "failed"]
    note: str = Field(min_length=1, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("note must not be blank")
        return normalized


class EvidenceVerificationRead(BaseModel):
    id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    source_trip_session_id: UUID
    verification_type: EvidenceVerificationType
    status: EvidenceVerificationStatus
    issued_by_user_id: UUID | None
    resolved_by_user_id: UUID | None
    due_at: datetime | None
    display_proof_id: UUID | None
    fraud_flag_id: UUID | None
    result_note: str | None
    metadata: dict[str, Any]
    issued_at: datetime
    resolved_at: datetime | None


class EvidenceVerificationList(BaseModel):
    items: list[EvidenceVerificationRead]
