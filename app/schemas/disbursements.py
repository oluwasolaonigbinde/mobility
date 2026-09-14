from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_serializer,
    field_validator,
)

from app.models.disbursement import PayoutBatchLineStatus, PayoutBatchStatus


class PayoutBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3)
    request_id: UUID | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class PayoutBatchReserve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_entry_ids: list[UUID] = Field(min_length=1, max_length=500)


class PayoutDebtAllocate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_debt_currency(cls, value: str) -> str:
        return value.strip().upper()


class DriverMoneyBalanceRead(BaseModel):
    driver_profile_id: UUID
    currency: str
    earned_net: Decimal
    released_available: Decimal
    reserved: Decimal
    in_flight: Decimal
    terminal_failed: Decimal
    cash_paid: Decimal
    carry_forward_debt: Decimal
    batch_payable: Decimal

    @field_serializer(
        "earned_net",
        "released_available",
        "reserved",
        "in_flight",
        "terminal_failed",
        "cash_paid",
        "carry_forward_debt",
        "batch_payable",
    )
    def serialize_balance(self, value: Decimal) -> str:
        return str(value)


class PayoutDebtAllocationRead(BaseModel):
    balance: DriverMoneyBalanceRead
    settlement_ids: list[UUID]
    remainder_entry_ids: list[UUID]


class PayoutBatchLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ledger_entry_id: UUID
    predecessor_line_id: UUID | None
    payee_version_id: UUID
    bank_account_version_id: UUID
    amount: Decimal
    currency: str
    instruction: dict[str, str]
    instruction_fingerprint: str
    idempotency_key: str
    status: PayoutBatchLineStatus
    provider_transfer_reference: str | None
    reconciled_by_user_id: UUID | None
    reconciled_at: datetime | None
    last_provider_evidence_at: datetime | None
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


Money = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class CurrencyAmountRead(BaseModel):
    currency: str
    amount: Money


class EligiblePaymentRead(BaseModel):
    ledger_entry_id: UUID
    driver_profile_id: UUID
    driver_name: str
    payee_name: str | None
    campaign_name: str
    occurred_at: datetime
    amount: Money
    currency: str
    debt_deducted: Money
    carry_forward_debt: Money
    destination_verified: bool
    bank_account_version_id: UUID | None
    eligible: bool
    ineligibility_reasons: list[str]


class EligiblePaymentListRead(BaseModel):
    items: list[EligiblePaymentRead]
    total: int
    limit: int
    offset: int
    page_eligible_totals: list[CurrencyAmountRead]


class PayoutSelectionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    ledger_entry_ids: list[UUID] = Field(min_length=1, max_length=100)


class PayoutSelectionPreviewRead(BaseModel):
    currency: str
    total_amount: Money
    ledger_entry_ids: list[UUID]


class PayoutBatchSummaryRead(BaseModel):
    id: UUID
    status: PayoutBatchStatus
    currency: str
    total_amount: Money
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    maker_name: str
    checker_name: str | None
    created_at: datetime
    approved_at: datetime | None
    submitted_at: datetime | None
    line_count: int
    outcomes: dict[str, int]


class PayoutBatchSummaryListRead(BaseModel):
    items: list[PayoutBatchSummaryRead]
    total: int
    limit: int
    offset: int


class PayoutOperationLineRead(BaseModel):
    id: UUID
    ledger_entry_id: UUID
    driver_name: str
    payee_name: str
    bank_account_version_id: UUID
    amount: Money
    currency: str
    status: str
    outcome: str
    idempotency_key: str
    provider_transfer_reference: str | None
    reconciled_at: datetime | None
    reconciler_name: str | None


class PayoutBatchDetailRead(BaseModel):
    summary: PayoutBatchSummaryRead
    lines: list[PayoutOperationLineRead]
    total: int
    limit: int
    offset: int


class PayoutLineHistoryEventRead(BaseModel):
    id: UUID
    outcome: str
    source: str
    applied: bool
    provider_occurred_at: datetime
    created_at: datetime


class PayoutLineHistoryRead(BaseModel):
    items: list[PayoutLineHistoryEventRead]
    latest_submission_outcome: str | None
    total: int
    limit: int
    offset: int


class CampaignDriverMoneyRead(BaseModel):
    driver_profile_id: UUID
    driver_name: str
    currency: str
    earned_net: Money
    unbatched_available: Money
    reserved: Money = Field(
        description="Active reserved payout instructions, independent of ledger payment status."
    )
    in_flight: Money = Field(
        description=(
            "Unresolved provider exposure across scoped payout-line chains, "
            "including replacements of paid credits."
        )
    )
    terminal_failed: Money
    cash_paid: Money = Field(description="Economic ledger amount paid, counting each credit once.")
    provider_verified_paid: Money = Field(
        description=(
            "Total amount of verified successful payout lines, "
            "including duplicate transfers in a replacement chain."
        )
    )
    driver_wide_debt: Money


class CancellationPositionRead(BaseModel):
    cutoff_at: datetime
    disposition: str
    currency: str
    refundable_amount: Money


class RecordedSettlementRead(BaseModel):
    id: UUID
    disposition: str
    currency: str
    amount: Money
    recorded_at: datetime


class CampaignMoneyPositionRead(BaseModel):
    campaign_id: UUID
    campaign_name: str
    items: list[CampaignDriverMoneyRead]
    total: int
    limit: int
    offset: int
    cancellation: CancellationPositionRead | None
    settlements: list[RecordedSettlementRead]
    settlements_total: int
    external_blockers: list[str]
