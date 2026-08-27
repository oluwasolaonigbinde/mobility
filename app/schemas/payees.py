from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.payee import PayeeType


class VerifiedBankAccountCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    account_name: SecretStr = Field(repr=False)
    account_number: SecretStr = Field(repr=False)
    bank_code: SecretStr = Field(repr=False)
    verification_reference: SecretStr = Field(repr=False)


class BankAccountRevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9_]+$")


class BankAccountPayoutVerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_reference: SecretStr = Field(repr=False, min_length=16, max_length=512)


class PayeeRead(BaseModel):
    id: UUID
    tenant_id: UUID
    payee_type: PayeeType
    subject_id: UUID
    version_id: UUID
    version: int
    created_at: datetime


class BankAccountVersionRead(BaseModel):
    id: UUID
    bank_account_id: UUID
    payee_version_id: UUID
    version: int
    encryption_algorithm: str
    encryption_key_version: int
    verified_at: datetime
    created_at: datetime
    payout_verified: bool = False
    payout_verified_at: datetime | None = None


class BankAccountRevealRead(BaseModel):
    account_name: str
    account_number: str
    bank_code: str
