from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.kyc import KycSubmissionStatus


class DriverKycSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    nin: SecretStr
    bank_account_version_id: UUID
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


class VehicleEvidenceSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: UUID
    registration_file_id: UUID
    insurance_file_id: UUID
    vehicle_photo_file_id: UUID


class DriverKycSubmissionRead(BaseModel):
    id: UUID
    driver_profile_id: UUID
    version: int
    status: KycSubmissionStatus
    masked_nin: str
    bank_account_version_id: UUID
    document_file_ids: dict[str, UUID]
    encryption_algorithm: str
    encryption_key_version: int
    created_at: datetime


class VehicleEvidenceSubmissionRead(BaseModel):
    id: UUID
    vehicle_id: UUID
    version: int
    status: KycSubmissionStatus
    snapshot_trusted: bool
    plate_number: str
    plate_country_code: str
    vehicle_type: str
    make: str | None
    model: str | None
    year: int | None
    color: str | None
    document_file_ids: dict[str, UUID]
    created_at: datetime


class SensitiveRevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_]{2,63}$")


class NinRevealRead(BaseModel):
    nin: str


class FileKycRetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    reason: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_]{2,63}$")


class FileKycRetentionRead(BaseModel):
    policy_configured: bool
    dry_run: bool
    lock_acquired: bool
    eligible_submissions: int
    purged_submissions: int
    purged_files: int
