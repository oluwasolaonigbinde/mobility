from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.stored_file import FilePurpose, FileScanStatus

MAX_CREATIVE_BYTES = 25 * 1024 * 1024
CREATIVE_CONTENT_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp", "video/mp4"}
)


class FileUploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    purpose: FilePurpose
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=MAX_CREATIVE_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(character in normalized for character in ("/", "\\", "\x00")):
            raise ValueError("Filename must be a plain file name")
        return normalized

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in CREATIVE_CONTENT_TYPES:
            raise ValueError("Content type is not allowed for creative uploads")
        return normalized

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()


class PresignedPostRead(BaseModel):
    url: str
    fields: dict[str, str]


class FileUploadRead(BaseModel):
    upload_id: UUID
    expires_at: datetime
    upload: PresignedPostRead


class StoredFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    purpose: FilePurpose
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    scan_status: FileScanStatus
    created_at: datetime


class FileAccessPurpose(StrEnum):
    CAMPAIGN_PREVIEW = "campaign_preview"
    CREATIVE_REVIEW = "creative_review"
    SECURITY_REVIEW = "security_review"
    INCIDENT_RESPONSE = "incident_response"


class FileDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: FileAccessPurpose
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 10:
            raise ValueError("A specific file-access reason is required")
        return normalized


class FileDownloadRead(BaseModel):
    url: str
    expires_in_seconds: int
