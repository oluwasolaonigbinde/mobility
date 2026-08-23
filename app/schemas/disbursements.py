from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models.disbursement import PayoutBatchStatus


class PayoutBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class PayoutBatchReserve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_entry_ids: list[UUID] = Field(min_length=1, max_length=500)


class PayoutBatchLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ledger_entry_id: UUID
    payee_version_id: UUID
    bank_account_version_id: UUID
    amount: Decimal
    currency: str
    instruction: dict[str, str]
    instruction_fingerprint: str
    idempotency_key: str
    reservation_active: bool

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return str(value)


class PayoutBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: PayoutBatchStatus
    currency: str
    total_amount: Decimal
    instruction_set_fingerprint: str | None
    provider_submission_reference: str | None
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    lines: list[PayoutBatchLineRead] = Field(default_factory=list)

    @field_serializer("total_amount")
    def serialize_total(self, value: Decimal) -> str:
        return str(value)


class PayoutBatchListRead(BaseModel):
    items: list[PayoutBatchRead]
    total: int
    limit: int
    offset: int
