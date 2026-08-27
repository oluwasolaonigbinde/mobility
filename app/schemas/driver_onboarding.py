from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.kyc import KycReviewReason, KycSubmissionStatus
from app.schemas.stored_files import FileUploadCreate, PresignedPostRead


class PersonPayeeStageStatus(StrEnum):
    NOT_SUBMITTED = "not_submitted"
    PENDING_REVIEW = KycSubmissionStatus.PENDING_REVIEW
    APPROVED = KycSubmissionStatus.APPROVED
    REJECTED = KycSubmissionStatus.REJECTED
    EXPIRED = KycSubmissionStatus.EXPIRED


class ApplicantFileUploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_access_token: SecretStr = Field(repr=False)
    upload: FileUploadCreate


class ApplicantFileUploadConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_access_token: SecretStr = Field(repr=False)


class ApplicantFileUploadRead(BaseModel):
    upload_id: UUID
    expires_at: datetime
    upload: PresignedPostRead


class ApplicantStoredFileRead(BaseModel):
    id: UUID
    scan_status: str


class PersonPayeeSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_access_token: SecretStr = Field(repr=False)
    client_request_id: UUID
    nin: SecretStr = Field(repr=False)
    account_name: SecretStr = Field(repr=False)
    account_number: SecretStr = Field(repr=False)
    bank_code: SecretStr = Field(repr=False)
    driver_license_file_id: UUID
    driver_photo_file_id: UUID
    signed_agreement_file_id: UUID

    @field_validator("nin")
    @classmethod
    def validate_nin(cls, value: SecretStr) -> SecretStr:
        plaintext = value.get_secret_value()
        if len(plaintext) != 11 or not plaintext.isascii() or not plaintext.isdigit():
            raise ValueError("NIN must contain exactly 11 ASCII digits")
        return value


class PersonPayeeStageRead(BaseModel):
    status: PersonPayeeStageStatus
    submission_id: UUID | None = None
    version: int | None = None
    masked_nin: str | None = None
    bank_account_verified: bool = False
    reason_code: KycReviewReason | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None


class PersonPayeeReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    decision: KycSubmissionStatus
    reason_code: KycReviewReason
    identity_match_confirmed: bool = False
    bank_account_match_confirmed: bool = False
    documents_readable_confirmed: bool = False

    @field_validator("decision")
    @classmethod
    def validate_terminal_decision(cls, value: KycSubmissionStatus) -> KycSubmissionStatus:
        if value == KycSubmissionStatus.PENDING_REVIEW:
            raise ValueError("Review decisions must be approved, rejected or expired")
        return value


class AdminPersonPayeeStageRead(PersonPayeeStageRead):
    document_file_ids: dict[str, UUID] = Field(default_factory=dict)
    bank_account_version_id: UUID | None = None
    encryption_algorithm: str | None = None
    encryption_key_version: int | None = None
    decided_by_user_id: UUID | None = None
