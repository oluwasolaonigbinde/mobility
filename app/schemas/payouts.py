from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from app.models.payout import (
    CampaignPayoutRuleStatus,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculationStatus,
    PayoutCorrectionOrderStatus,
)
from app.schemas.campaigns import ensure_timezone_aware


class DecimalStringMixin(BaseModel):
    @field_serializer(
        "ledger_net_total",
        "gross_payout",
        "final_payout",
        "amount",
        "pending_amount",
        "available_amount",
        "paid_amount",
        "voided_amount",
        "lifetime_earned_amount",
        "released_available_amount",
        "cash_paid_amount",
        "carry_forward_debt_amount",
        "batch_payable_amount",
        "final_payout_total",
        "gross_payout_total",
        "daily_rate_naira",
        "daily_target_miles",
        "deduction_per_mile_naira",
        "minimum_miles",
        "outside_area_weight",
        check_fields=False,
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        return str(value)


def normalize_currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    return normalized


class CampaignPayoutRuleRead(DecimalStringMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    formula_version: str
    status: CampaignPayoutRuleStatus
    currency: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignPayoutRuleListResponse(BaseModel):
    items: list[CampaignPayoutRuleRead]
    total: int
    limit: int
    offset: int


class CampaignPayoutV4RevisionCreate(BaseModel):
    """Staff set the day rate and target; D43 fixes the remaining pay rules."""

    model_config = ConfigDict(extra="forbid")

    effective_from: datetime
    daily_rate_naira: Decimal = Field(gt=Decimal("0"), max_digits=14, decimal_places=2)
    daily_target_miles: Decimal = Field(gt=Decimal("0"), max_digits=10, decimal_places=3)
    reason: str

    @field_validator("effective_from")
    @classmethod
    def validate_effective_from(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Datetime must include timezone information")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("reason must not be empty")
        return trimmed


class CampaignPayoutRuleRevisionRead(DecimalStringMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    payout_rule_id: UUID
    revision_number: int
    effective_from: datetime
    daily_rate_naira: Decimal | None = None
    daily_target_miles: Decimal | None = None
    shortfall_strategy: str | None = None
    deduction_per_mile_naira: Decimal | None = None
    minimum_miles: Decimal | None = None
    outside_area_weight: Decimal | None = None
    currency: str
    eligibility_params: dict[str, Any]
    formula_version: str
    reason: str
    created_by_user_id: UUID
    created_at: datetime


class CampaignPayoutRuleRevisionListResponse(BaseModel):
    items: list[CampaignPayoutRuleRevisionRead]
    total: int
    limit: int
    offset: int


class CalculatePayoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payout_rule_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PayoutLedgerEntrySummary(DecimalStringMixin):
    id: UUID
    status: EarningsLedgerEntryStatus
    amount: Decimal
    currency: str


class EarningsWorkDayRead(DecimalStringMixin):
    day: date
    amount: Decimal


class EarningsLedgerEntryRead(PayoutLedgerEntrySummary):
    payout_calculation_id: UUID | None
    driver_profile_id: UUID
    campaign_id: UUID
    trip_session_id: UUID | None
    vehicle_id: UUID | None
    entry_type: EarningsLedgerEntryType
    description: str | None
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    work_days: list[EarningsWorkDayRead] = Field(default_factory=list)
    paid_at: datetime | None = None
    paying_tonight: bool = False
    payment_on_hold: bool = False


class DriverMoneyMixin(BaseModel):
    @field_serializer("amount", "today", "this_week", "total", "on_hold", check_fields=False)
    def serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01")))


class DriverEarningsDayRead(DriverMoneyMixin):
    day: date
    currency: str
    amount: Decimal
    status: Literal["on_hold", "paid", "paying_tonight", "being_checked"]
    paid_at: datetime | None
    trip_ids: list[UUID]


class DriverEarningsTotalsRead(DriverMoneyMixin):
    currency: str
    today: Decimal
    this_week: Decimal
    total: Decimal
    on_hold: Decimal


class DriverEarningsDaysRead(BaseModel):
    """REQ-208: the driver's daily earnings and headline totals in one read."""

    totals: list[DriverEarningsTotalsRead]
    days: list[DriverEarningsDayRead]


class PayoutCalculationRead(DecimalStringMixin):
    id: UUID
    trip_session_id: UUID
    trip_analytics_id: UUID
    impression_estimate_id: UUID
    payout_rule_id: UUID
    assignment_id: UUID
    campaign_id: UUID
    driver_profile_id: UUID
    vehicle_id: UUID
    formula_version: str
    status: PayoutCalculationStatus
    currency: str
    gross_payout: Decimal
    final_payout: Decimal
    eligible_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    inputs_fingerprint: str | None
    calculated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    ledger_entry: PayoutLedgerEntrySummary | None = None
    created_at: datetime
    updated_at: datetime


class AdminPayoutCalculationRead(PayoutCalculationRead):
    trip_started_at: datetime
    campaign_name: str


class PayoutCalculationListResponse(BaseModel):
    items: list[AdminPayoutCalculationRead]
    total: int
    limit: int
    offset: int


class EarningsLedgerEntryListResponse(BaseModel):
    items: list[EarningsLedgerEntryRead]
    total: int
    limit: int
    offset: int


class DriverEarningsCurrencySummary(DecimalStringMixin):
    currency: str
    pending_amount: Decimal
    available_amount: Decimal
    paid_amount: Decimal
    voided_amount: Decimal
    lifetime_earned_amount: Decimal
    released_available_amount: Decimal
    cash_paid_amount: Decimal
    carry_forward_debt_amount: Decimal
    batch_payable_amount: Decimal
    ledger_entry_count: int


class DriverEarningsSummary(BaseModel):
    driver_profile_id: UUID
    totals_by_currency: list[DriverEarningsCurrencySummary]


class CampaignCostCurrencySummary(DecimalStringMixin):
    currency: str
    final_payout_total: Decimal
    gross_payout_total: Decimal
    ledger_net_total: Decimal
    calculated_trip_count: int
    blocked_trip_count: int
    insufficient_data_trip_count: int
    ledger_entry_count: int


class CampaignCostSummary(BaseModel):
    campaign_id: UUID
    formula_version: str
    formula_versions: list[str]
    totals_by_currency: list[CampaignCostCurrencySummary]
    start_at: datetime | None
    end_at: datetime | None


class RecomputePayoutDayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    driver_profile_id: UUID
    lagos_date: date
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecomputeDayTripResult(DecimalStringMixin):
    trip_session_id: UUID
    payout_calculation_id: UUID | None
    previous_posted_amount: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    eligible_seconds: int
    entry_id: UUID | None
    entry_type: EarningsLedgerEntryType | None
    voided: bool

    @field_serializer(
        "previous_posted_amount",
        "target_amount",
        "delta_amount",
    )
    def serialize_signed_decimal(self, value: Decimal) -> str:
        return str(value)


class RecomputePayoutDayResult(BaseModel):
    campaign_id: UUID
    driver_profile_id: UUID
    lagos_date: date
    trips: list[RecomputeDayTripResult]
    adjustment_count: int
    reversal_count: int


class PayoutCorrectionOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    lagos_day: date
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("reason must not be empty")
        return trimmed


class PayoutCorrectionOrderExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Q22: positive deltas post as pending with their OWN release date — no
    # default is invented, so executing an order with positive deltas without
    # release_at fails with 400.
    release_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("release_at")
    @classmethod
    def validate_release_at(cls, value: datetime | None) -> datetime | None:
        return ensure_timezone_aware(value)


class PayoutCorrectionOrderRead(BaseModel):
    campaign_name: str | None = None
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    lagos_day: date
    status: PayoutCorrectionOrderStatus
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    executed_by_user_id: UUID | None
    reason: str
    projected_delta: dict[str, Any] | None
    projection_fingerprint: str | None
    projected_at: datetime | None
    decided_at: datetime | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    created_at: datetime


class PayoutCorrectionOrderListResponse(BaseModel):
    items: list[PayoutCorrectionOrderRead]
    total: int
    limit: int
    offset: int


class PayoutDayProjection(BaseModel):
    campaign_id: UUID
    lagos_day: date
    projected_delta: dict[str, Any]
    projection_fingerprint: str


class DriverTripDailyRateDay(DecimalStringMixin):
    """payout_v4: one Nigeria-time day of a trip — metres counted and the pay
    this trip added to that day."""

    lagos_day: date
    distance_m: int
    amount: Decimal


class DriverTripEarningsBreakdown(DecimalStringMixin):
    trip_session_id: UUID
    formula_version: str
    currency: str
    amount: Decimal
    eligible_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    superseded_by_recompute: bool
    entries: list[EarningsLedgerEntryRead]
    daily_rate_days: list[DriverTripDailyRateDay] | None = None
