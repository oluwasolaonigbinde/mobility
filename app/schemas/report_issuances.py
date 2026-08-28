from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.report_issuance import ReportArtifactFormat, ReportIssuanceStatus


class ReportIssuanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    reissue_of_id: UUID | None = None


class ReportArtifactRead(BaseModel):
    format: ReportArtifactFormat
    filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


class ReportIssuanceRead(BaseModel):
    id: UUID
    measurement_run_id: UUID
    campaign_id: UUID
    version: int
    reissue_of_id: UUID | None
    status: ReportIssuanceStatus
    synthetic: bool
    schema_version: str
    renderer_version: str
    worker_attempts: int
    error_code: str | None
    artifacts: list[ReportArtifactRead]
    created_at: datetime
    ready_at: datetime | None


class ReportArtifactDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 10:
            raise ValueError("A specific report-access reason is required")
        return normalized


class ReportArtifactDownloadRead(BaseModel):
    url: str
    expires_in_seconds: int
    filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
