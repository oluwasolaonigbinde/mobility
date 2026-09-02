from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.trip import TripSessionStatus
from app.schemas.campaigns import ensure_timezone_aware
from app.schemas.drivers import normalize_optional_text
from app.schemas.vehicles import normalize_required_text


class TripStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    evidence_protocol_version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TripEvidenceManifestEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_sequence: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1)
    payload_hash_version: Literal[2] = 2
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    submitted_count: int = Field(ge=0)

    @field_validator("idempotency_key")
    @classmethod
    def trim_manifest_idempotency_key(cls, value: str) -> str:
        return normalize_required_text(value)


class TripEvidenceManifestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    root_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ping_count: int = Field(ge=0)
    complete: bool
    entries: list[TripEvidenceManifestEntryCreate]


class TripEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_reason: str | None = None
    # Client finalization watermark (RM3): how many batches the client has cut
    # for this trip and how many pings it recorded. The trip fast-seals when
    # the server holds >= client_batch_count batches; client_complete is the
    # client's own completeness claim (False = ended with unsynced data).
    client_batch_count: int | None = Field(default=None, ge=0)
    client_ping_count: int | None = Field(default=None, ge=0)
    client_complete: bool | None = None
    evidence_manifest: TripEvidenceManifestCreate | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("end_reason")
    @classmethod
    def trim_end_reason(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class LocationPingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    speed_mps: float | None = Field(default=None, ge=0)
    heading_degrees: float | None = Field(default=None, ge=0, lt=360)
    altitude_m: float | None = Field(default=None, ge=-500, le=10000)
    sequence_number: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_must_be_aware(cls, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


class LocationPingBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1)
    batch_sequence: int | None = Field(default=None, ge=0)
    pings: list[LocationPingCreate] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key")
    @classmethod
    def trim_idempotency_key(cls, value: str) -> str:
        return normalize_required_text(value)


class TripRead(BaseModel):
    id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    display_proof_id: UUID | None
    status: TripSessionStatus
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None = None
    evidence_protocol_version: int
    evidence_manifest_root_sha256: str | None = None
    evidence_manifest_complete: bool = False
    evidence_manifest_verified_at: datetime | None = None
    sealed_at: datetime | None = None
    seal_reason: str | None = None
    ping_count: int
    first_ping_at: datetime | None
    last_ping_at: datetime | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CurrentTripResponse(BaseModel):
    trip: TripRead | None


class LocationPingBatchResponse(BaseModel):
    batch_id: UUID
    trip_id: UUID
    accepted_count: int
    submitted_count: int
    rejected_count: int = 0
    batch_sequence: int | None = None
    payload_hash_version: int
    payload_hash: str
    outcome: str | None = None
    receipt_format_version: int | None = None
    receipt_key_version: int | None = None
    receipt_signature: str | None = None
    duplicate: bool
    # True when the trip was already sealed: the payload is preserved in
    # quarantine (batch_id is the quarantine row) and no pings were inserted.
    # The client must treat this as an ACK and drop the batch from its queue.
    quarantined: bool = False


class TripEvidenceReconcileResponse(BaseModel):
    trip_id: UUID
    status: TripSessionStatus
    manifest_root_sha256: str
    manifest_complete: bool
    manifest_verified_at: datetime
    receipt_format_version: int
    receipt_key_version: int
    receipt_signature: str
    duplicate: bool


class QuarantinedPingBatchRead(BaseModel):
    id: UUID
    trip_session_id: UUID
    idempotency_key: str
    ping_count: int
    received_at: datetime
    status: str
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None
    resolution_note: str | None = None
    applied_batch_id: UUID | None = None
    created_at: datetime


class QuarantinedPingBatchListResponse(BaseModel):
    items: list[QuarantinedPingBatchRead]
    total: int
    limit: int
    offset: int


class QuarantineResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str) -> str:
        return normalize_required_text(value)


class QuarantineApplyResponse(BaseModel):
    quarantine_id: UUID
    trip_id: UUID
    applied_batch_id: UUID
    accepted_count: int
    # Africa/Lagos calendar days the applied pings touch — the admin runs the
    # recompute-day tool for these; applying never auto-recomputes money.
    affected_lagos_days: list[str]
