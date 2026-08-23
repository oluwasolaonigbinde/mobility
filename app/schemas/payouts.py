from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models.payout import (
    CampaignPayoutRuleStatus,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculationStatus,
    PayoutCorrectionOrderStatus,
)
from app.schemas.campaigns import ensure_timezone_aware

REQUIRED_PAYOUT_RULE_UPDATE_FIELDS = {
    "status",
    "currency",
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
    "hourly_rate_naira",
    "daily_payable_hours_cap",
}


class DecimalStringMixin(BaseModel):
    @field_serializer(
        "hourly_rate_naira",
        "premium_hourly_rate_naira",
        "daily_payable_hours_cap",
        "ledger_net_total",
        "hourly_rate",
        "base_hourly_rate",
        "premium_hourly_rate",
        "base_amount",
        "premium_amount",
        "base_rate_per_km",
        "base_rate_per_active_hour",
        "target_zone_bonus_rate_per_km",
        "bonus_zone_bonus_rate_per_km",
        "estimated_impression_rate_per_1000",
        "min_payout_per_trip",
        "max_payout_per_trip",
        "low_fraud_multiplier",
        "medium_fraud_multiplier",
        "high_fraud_multiplier",
        "distance_component",
        "active_time_component",
        "target_zone_bonus_component",
        "bonus_zone_bonus_component",
        "impression_component",
        "gross_payout",
        "quality_multiplier",
        "fraud_multiplier",
        "cap_adjustment",
        "final_payout",
        "amount",
        "pending_amount",
        "available_amount",
        "paid_amount",
        "voided_amount",
        "lifetime_earned_amount",
        "final_payout_total",
        "gross_payout_total",
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
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a 3-letter code")
    return normalized


class CampaignPayoutRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula_version: str | None = None
    status: CampaignPayoutRuleStatus = CampaignPayoutRuleStatus.ACTIVE
    currency: str | None = None
    base_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    base_rate_per_active_hour: Decimal | None = Field(default=None, ge=Decimal("0"))
    target_zone_bonus_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    bonus_zone_bonus_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    estimated_impression_rate_per_1000: Decimal | None = Field(default=None, ge=Decimal("0"))
    min_payout_per_trip: Decimal | None = Field(default=None, ge=Decimal("0"))
    max_payout_per_trip: Decimal | None = Field(default=None, ge=Decimal("0"))
    low_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    medium_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    high_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    hourly_rate_naira: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_payable_hours_cap: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        le=Decimal("24"),
    )
    eligibility_params: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value)

    @model_validator(mode="after")
    def validate_caps(self) -> "CampaignPayoutRuleCreate":
        if (
            self.max_payout_per_trip is not None
            and self.min_payout_per_trip is not None
            and self.max_payout_per_trip < self.min_payout_per_trip
        ):
            raise ValueError("max_payout_per_trip must be greater than or equal to min")
        return self


class CampaignPayoutRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CampaignPayoutRuleStatus | None = None
    currency: str | None = None
    base_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    base_rate_per_active_hour: Decimal | None = Field(default=None, ge=Decimal("0"))
    target_zone_bonus_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    bonus_zone_bonus_rate_per_km: Decimal | None = Field(default=None, ge=Decimal("0"))
    estimated_impression_rate_per_1000: Decimal | None = Field(default=None, ge=Decimal("0"))
    min_payout_per_trip: Decimal | None = Field(default=None, ge=Decimal("0"))
    max_payout_per_trip: Decimal | None = Field(default=None, ge=Decimal("0"))
    low_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    medium_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    high_fraud_multiplier: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    hourly_rate_naira: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_payable_hours_cap: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        le=Decimal("24"),
    )
    eligibility_params: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value)

    @model_validator(mode="after")
    def validate_caps(self) -> "CampaignPayoutRuleUpdate":
        null_fields = sorted(
            field
            for field in REQUIRED_PAYOUT_RULE_UPDATE_FIELDS
            if field in self.model_fields_set and getattr(self, field) is None
        )
        if null_fields:
            raise ValueError(f"{', '.join(null_fields)} must not be null")
        if (
            self.max_payout_per_trip is not None
            and self.min_payout_per_trip is not None
            and self.max_payout_per_trip < self.min_payout_per_trip
        ):
            raise ValueError("max_payout_per_trip must be greater than or equal to min")
        return self


class CampaignPayoutRuleRead(DecimalStringMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    formula_version: str
    status: CampaignPayoutRuleStatus
    currency: str
    base_rate_per_km: Decimal | None
    base_rate_per_active_hour: Decimal | None
    target_zone_bonus_rate_per_km: Decimal | None
    bonus_zone_bonus_rate_per_km: Decimal | None
    estimated_impression_rate_per_1000: Decimal | None
    min_payout_per_trip: Decimal | None
    max_payout_per_trip: Decimal | None
    low_fraud_multiplier: Decimal | None
    medium_fraud_multiplier: Decimal | None
    high_fraud_multiplier: Decimal | None
    hourly_rate_naira: Decimal | None
    daily_payable_hours_cap: Decimal | None
    eligibility_params: dict[str, Any] | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignPayoutRuleListResponse(BaseModel):
    items: list[CampaignPayoutRuleRead]
    total: int
    limit: int
    offset: int


class CampaignPayoutRuleRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_from: datetime
    hourly_rate_naira: Decimal = Field(ge=Decimal("0"))
    premium_hourly_rate_naira: Decimal | None = Field(default=None, ge=Decimal("0"))
    daily_payable_hours_cap: Decimal = Field(gt=Decimal("0"), le=Decimal("24"))
    eligibility_params: dict[str, Any] = Field(default_factory=dict)
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
    hourly_rate_naira: Decimal
    premium_hourly_rate_naira: Decimal | None
    daily_payable_hours_cap: Decimal | None
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
    distance_component: Decimal | None
    active_time_component: Decimal | None
    target_zone_bonus_component: Decimal | None
    bonus_zone_bonus_component: Decimal | None
    impression_component: Decimal | None
    gross_payout: Decimal
    quality_multiplier: Decimal | None
    fraud_multiplier: Decimal | None
    cap_adjustment: Decimal | None
    final_payout: Decimal
    eligible_seconds: int | None
    payable_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    inputs_fingerprint: str | None
    calculated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    ledger_entry: PayoutLedgerEntrySummary | None = None
    created_at: datetime
    updated_at: datetime


class PayoutCalculationListResponse(BaseModel):
    items: list[PayoutCalculationRead]
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
    payable_seconds: int
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
    cap_seconds: int
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


class DriverTripEarningsCapProgress(BaseModel):
    lagos_day: date
    cap_seconds: int
    day_payable_seconds: int


class DriverTripEarningsBreakdown(DecimalStringMixin):
    trip_session_id: UUID
    formula_version: str
    currency: str
    amount: Decimal
    eligible_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    hourly_rate: Decimal | None
    capped_seconds: int | None
    base_payable_seconds: int | None
    premium_payable_seconds: int | None
    base_hourly_rate: Decimal | None
    premium_hourly_rate: Decimal | None
    base_amount: Decimal | None
    premium_amount: Decimal | None
    superseded_by_recompute: bool
    entries: list[EarningsLedgerEntryRead]
    cap: DriverTripEarningsCapProgress | None
