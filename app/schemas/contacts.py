from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class DriverPhoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=32)


class DriverPhoneVersionRead(BaseModel):
    id: UUID
    version: int
    masked_phone: str
    verified: bool
    recorded_at: datetime
    verified_at: datetime | None


class PhoneChallengeRead(BaseModel):
    id: UUID
    phone_version_id: UUID
    status: str
    attempt_count: int
    max_attempts: int
    expires_at: datetime
    verified_at: datetime | None

    @field_validator("expires_at", "verified_at")
    @classmethod
    def utc_dates(cls, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class DriverPhoneChallengeRead(PhoneChallengeRead):
    code: str
    terrax_number: str


class PhoneVerificationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    code: SecretStr = Field(repr=False, min_length=6, max_length=6)
    sender_phone: SecretStr = Field(repr=False, min_length=8, max_length=32)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        code = value.get_secret_value()
        if not code.isascii() or not code.isdigit():
            raise ValueError("Enter the six digits received")
        return value


class AdminPhoneChallengeRead(PhoneChallengeRead):
    driver_profile_id: UUID
    driver_name: str | None = None
    masked_phone: str


class AdminPhoneChallengeListRead(BaseModel):
    items: list[AdminPhoneChallengeRead]
    total: int
    limit: int
    offset: int


class WhatsappConsentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=128)
    notice_version: str = Field(min_length=1, max_length=64)


class WhatsappConsentRead(BaseModel):
    id: UUID
    version: int
    phone_version_id: UUID
    purpose: str
    notice_version: str
    granted_at: datetime
    withdrawn_at: datetime | None


class DriverContactStateRead(BaseModel):
    phone: DriverPhoneVersionRead | None
    whatsapp_consent: WhatsappConsentRead | None
    verification_available: bool = False
    challenge: PhoneChallengeRead | None = None


class ManualContactTaskComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["attempted", "reached", "failed"]
    note: str = Field(min_length=1, max_length=2000)


class ManualContactTaskRead(BaseModel):
    driver_name: str | None = None
    id: UUID
    driver_profile_id: UUID
    event_key: str
    purpose: str
    status: str
    masked_phone: str
    created_at: datetime
    completed_by_user_id: UUID | None
    completed_at: datetime | None
    completion_outcome: str | None
    provider_delivery_confirmed: bool = False


class ManualContactTaskListRead(BaseModel):
    items: list[ManualContactTaskRead]
    total: int
    limit: int
    offset: int
