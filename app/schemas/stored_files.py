from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.stored_file import FilePurpose, FileScanStatus

MB = 1024 * 1024
_IMAGES = frozenset({"image/jpeg", "image/png", "image/webp"})
_DOCUMENTS = _IMAGES | {"application/pdf"}
# Per-purpose upload policy: the developer recommendation adopted under client
# answer #12 ("file types and sizes as recommended", 24 Sep 2026).
UPLOAD_POLICY: dict[FilePurpose, tuple[int, frozenset[str]]] = {
    FilePurpose.CREATIVE: (25 * MB, _DOCUMENTS | {"video/mp4"}),
    FilePurpose.DRIVER_KYC: (10 * MB, _DOCUMENTS),
    # Registration and insurance papers as well as vehicle photos.
    FilePurpose.VEHICLE_EVIDENCE: (20 * MB, _DOCUMENTS),
    FilePurpose.INSTALLATION_EVIDENCE: (20 * MB, _IMAGES),
}
MAX_UPLOAD_BYTES = max(limit for limit, _ in UPLOAD_POLICY.values())


class FileUploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    purpose: FilePurpose
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=MAX_UPLOAD_BYTES)
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
        return value.strip().lower()

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_purpose_policy(self) -> "FileUploadCreate":
        policy = UPLOAD_POLICY.get(self.purpose)
        if policy is None:
            raise ValueError("This file purpose cannot be uploaded")
        max_bytes, content_types = policy
        if self.content_type not in content_types:
            raise ValueError("This file type is not allowed for this upload")
        if self.size_bytes > max_bytes:
            raise ValueError(f"This file is larger than the {max_bytes // MB} MB limit")
        return self


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
    organization_id: UUID | None
    subject_user_id: UUID | None
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
    KYC_REVIEW = "kyc_review"
    INSTALLATION_REVIEW = "installation_review"
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
