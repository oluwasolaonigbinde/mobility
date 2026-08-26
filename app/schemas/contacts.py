from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    sent_channel: str | None
    sent_at: datetime | None
    verified_at: datetime | None


class PhoneChallengeVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class PhoneChallengeSent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["whatsapp", "voice"]
    operator_evidence_reference: str = Field(min_length=1, max_length=255)
    provider_message_id: str = Field(min_length=1, max_length=255)


class AdminPhoneChallengeRead(PhoneChallengeRead):
    driver_profile_id: UUID
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


class ManualContactTaskComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["attempted", "reached", "failed"]
    note: str = Field(min_length=1, max_length=2000)


class ManualContactTaskRead(BaseModel):
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
