import hashlib
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignPayoutRuleStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PayoutCalculationStatus(StrEnum):
    CALCULATED = "calculated"
    INSUFFICIENT_DATA = "insufficient_data"
    BLOCKED = "blocked"


class EarningsLedgerEntryType(StrEnum):
    TRIP_PAYOUT = "trip_payout"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"
    DEBT_REMAINDER = "debt_remainder"


class EarningsLedgerEntryStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    VOIDED = "voided"
    REVERSED = "reversed"
    PAID = "paid"


class PayoutCorrectionOrderStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    STALE = "stale"


PAYOUT_RULE_MODEL_XOR_SQL = (
    "("
    "formula_version <> 'payout_v2'"
    " AND hourly_rate_naira IS NULL"
    " AND daily_payable_hours_cap IS NULL"
    " AND eligibility_params IS NULL"
    " AND base_rate_per_km IS NOT NULL"
    " AND base_rate_per_active_hour IS NOT NULL"
    " AND target_zone_bonus_rate_per_km IS NOT NULL"
    " AND bonus_zone_bonus_rate_per_km IS NOT NULL"
    " AND estimated_impression_rate_per_1000 IS NOT NULL"
    " AND min_payout_per_trip IS NOT NULL"
    " AND low_fraud_multiplier IS NOT NULL"
    " AND medium_fraud_multiplier IS NOT NULL"
    " AND high_fraud_multiplier IS NOT NULL"
    ") OR ("
    "formula_version = 'payout_v2'"
    " AND hourly_rate_naira IS NOT NULL"
    " AND daily_payable_hours_cap IS NOT NULL"
    " AND base_rate_per_km IS NULL"
    " AND base_rate_per_active_hour IS NULL"
    " AND target_zone_bonus_rate_per_km IS NULL"
    " AND bonus_zone_bonus_rate_per_km IS NULL"
    " AND estimated_impression_rate_per_1000 IS NULL"
    " AND min_payout_per_trip IS NULL"
    " AND max_payout_per_trip IS NULL"
    " AND low_fraud_multiplier IS NULL"
    " AND medium_fraud_multiplier IS NULL"
    " AND high_fraud_multiplier IS NULL"
    ")"
)


class CampaignPayoutRule(Base):
    __tablename__ = "campaign_payout_rules"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_campaign_payout_rules_status"),
        CheckConstraint("length(currency) = 3", name="ck_campaign_payout_rules_currency"),
        CheckConstraint(
            "base_rate_per_km >= 0",
            name="ck_campaign_payout_rules_base_rate_per_km_non_negative",
        ),
        CheckConstraint(
            "base_rate_per_active_hour >= 0",
            name="ck_campaign_payout_rules_base_rate_per_active_hour_non_negative",
        ),
        CheckConstraint(
            "target_zone_bonus_rate_per_km >= 0",
            name="ck_campaign_payout_rules_target_bonus_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_bonus_rate_per_km >= 0",
            name="ck_campaign_payout_rules_bonus_zone_non_negative",
        ),
        CheckConstraint(
            "estimated_impression_rate_per_1000 >= 0",
            name="ck_campaign_payout_rules_impression_rate_non_negative",
        ),
        CheckConstraint(
            "min_payout_per_trip >= 0",
            name="ck_campaign_payout_rules_min_payout_non_negative",
        ),
        CheckConstraint(
            "max_payout_per_trip IS NULL OR max_payout_per_trip >= min_payout_per_trip",
            name="ck_campaign_payout_rules_max_gte_min",
        ),
        CheckConstraint(
            "low_fraud_multiplier >= 0 AND low_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_low_fraud_multiplier_range",
        ),
        CheckConstraint(
            "medium_fraud_multiplier >= 0 AND medium_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_medium_fraud_multiplier_range",
        ),
        CheckConstraint(
            "high_fraud_multiplier >= 0 AND high_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_high_fraud_multiplier_range",
        ),
        CheckConstraint(
            "hourly_rate_naira IS NULL OR hourly_rate_naira >= 0",
            name="ck_campaign_payout_rules_hourly_rate_non_negative",
        ),
        CheckConstraint(
            "daily_payable_hours_cap IS NULL OR "
            "(daily_payable_hours_cap > 0 AND daily_payable_hours_cap <= 24)",
            name="ck_campaign_payout_rules_daily_cap_range",
        ),
        CheckConstraint(PAYOUT_RULE_MODEL_XOR_SQL, name="ck_campaign_payout_rules_model_xor"),
        Index("ix_campaign_payout_rules_campaign_id", "campaign_id"),
        Index("ix_campaign_payout_rules_campaign_status", "campaign_id", "status"),
        Index(
            "uq_campaign_payout_rules_active_campaign",
            "campaign_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    formula_version: Mapped[str] = mapped_column(
        Text,
        default="payout_v1",
        server_default=text("'payout_v1'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    base_rate_per_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    base_rate_per_active_hour: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_zone_bonus_rate_per_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bonus_zone_bonus_rate_per_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimated_impression_rate_per_1000: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_payout_per_trip: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_payout_per_trip: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    low_fraud_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    medium_fraud_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    high_fraud_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    hourly_rate_naira: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    daily_payable_hours_cap: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    eligibility_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rule_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CampaignPayoutRuleRevision(Base):
    """Append-only effective-dated payout value revisions (MNY-06A, D18).

    The revision current at time T is the row with the greatest
    effective_from <= T. Non-overlap is by construction: no update/delete
    path exists, uq(campaign_id, effective_from) makes boundaries
    deterministic, and uq(campaign_id, revision_number) serializes
    concurrent supersedes fail-closed (PR1). Revisions are payout_v3-only
    value sources; payout_v2 keeps pricing from the frozen rule row (PR3).
    """

    __tablename__ = "campaign_payout_rule_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number >= 1",
            name="ck_campaign_payout_rule_revisions_number_ge_1",
        ),
        CheckConstraint(
            "hourly_rate_naira >= 0",
            name="ck_campaign_payout_rule_revisions_hourly_rate_non_negative",
        ),
        CheckConstraint(
            "premium_hourly_rate_naira IS NULL OR premium_hourly_rate_naira >= 0",
            name="ck_campaign_payout_rule_revisions_premium_rate_non_negative",
        ),
        UniqueConstraint(
            "campaign_id",
            "revision_number",
            name="uq_campaign_payout_rule_revisions_campaign_number",
        ),
        UniqueConstraint(
            "campaign_id",
            "effective_from",
            name="uq_campaign_payout_rule_revisions_campaign_effective",
        ),
        Index("ix_campaign_payout_rule_revisions_campaign_id", "campaign_id"),
        Index("ix_campaign_payout_rule_revisions_payout_rule_id", "payout_rule_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    payout_rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_payout_rules.id"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hourly_rate_naira: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    premium_hourly_rate_naira: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    daily_payable_hours_cap: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    eligibility_params: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AssignmentRuleBinding(Base):
    """Acceptance-time payout value freeze (MNY-06B, D18/Q4).

    Created inside the accept transaction: the campaign's revision effective
    at acceptance is snapshotted verbatim so later revisions can NEVER
    reprice accepted work. The premium tier area is frozen as the campaign's
    target-zone ids plus a deterministic geometry hash (PR11); the stationary
    sub-window policy stays fail-closed and is only recorded as a marker
    (EXT-RM2-POLICY). Assignments accepted before revisions existed have no
    binding and keep payout_v2 exactly as before.
    """

    __tablename__ = "assignment_rule_bindings"
    __table_args__ = (
        CheckConstraint(
            "hourly_rate_naira >= 0",
            name="ck_assignment_rule_bindings_hourly_rate_non_negative",
        ),
        CheckConstraint(
            "premium_hourly_rate_naira IS NULL OR premium_hourly_rate_naira >= 0",
            name="ck_assignment_rule_bindings_premium_rate_non_negative",
        ),
        UniqueConstraint(
            "assignment_id",
            name="uq_assignment_rule_bindings_assignment_id",
        ),
        Index("ix_assignment_rule_bindings_revision_id", "revision_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_payout_rule_revisions.id"),
        nullable=False,
    )
    hourly_rate_naira: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    premium_hourly_rate_naira: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    daily_payable_hours_cap: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    eligibility_params: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    resolved_eligibility_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    formula_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Campaign target-zone ids (as strings) frozen at binding time (PR11).
    premium_zone_ids: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    premium_zone_geometry_hash: Mapped[str] = mapped_column(Text, nullable=False)
    premium_zone_geometry_wkts: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    exclusion_zone_ids: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    exclusion_zone_geometry_hash: Mapped[str] = mapped_column(
        Text,
        default=hashlib.sha256(b"").hexdigest(),
        server_default=text("'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'"),
        nullable=False,
    )
    exclusion_zone_geometry_wkts: Mapped[list[Any]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    stationary_policy_marker: Mapped[str] = mapped_column(
        Text,
        default="ext-rm2-fail-closed",
        server_default=text("'ext-rm2-fail-closed'"),
        nullable=False,
    )
    campaign_window_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_window_frozen: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PayoutCorrectionOrder(Base):
    """Maker-checker retroactive recompute authority (MNY-06C, Q22).

    A named adjuster PROJECTS a campaign/Lagos-day correction (the PR6 core in
    dry-run) into a draft order; a DIFFERENT admin approves it (enforced at
    the service layer and by the approver CHECK below); execution re-verifies
    the PR12 projection fingerprint and runs the same core in execution mode.
    States: draft -> pending_approval -> approved -> executed, with rejected
    (from pending_approval) and stale (fingerprint drift detected at approve
    or execute) as terminal ends — a stale order is never revived, re-project
    a new one. Executed orders are idempotent: re-execution returns the
    recorded execution_result and never recomputes.
    """

    __tablename__ = "payout_correction_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'rejected', 'executed', 'stale')",
            name="ck_payout_correction_orders_status",
        ),
        CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id",
            name="ck_payout_correction_orders_approver_not_creator",
        ),
        Index("ix_payout_correction_orders_campaign_id", "campaign_id"),
        Index(
            "ix_payout_correction_orders_campaign_day",
            "campaign_id",
            "lagos_day",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    lagos_day: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    executed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    projected_delta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    projection_fingerprint: Mapped[str | None] = mapped_column(Text)
    projected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PayoutCalculation(Base):
    __tablename__ = "payout_calculations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('calculated', 'insufficient_data', 'blocked')",
            name="ck_payout_calculations_status",
        ),
        CheckConstraint("length(currency) = 3", name="ck_payout_calculations_currency"),
        CheckConstraint(
            "distance_component >= 0",
            name="ck_payout_calculations_distance_component_non_negative",
        ),
        CheckConstraint(
            "active_time_component >= 0",
            name="ck_payout_calculations_active_time_component_non_negative",
        ),
        CheckConstraint(
            "target_zone_bonus_component >= 0",
            name="ck_payout_calculations_target_zone_component_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_bonus_component >= 0",
            name="ck_payout_calculations_bonus_zone_component_non_negative",
        ),
        CheckConstraint(
            "impression_component >= 0",
            name="ck_payout_calculations_impression_component_non_negative",
        ),
        CheckConstraint("gross_payout >= 0", name="ck_payout_calculations_gross_non_negative"),
        CheckConstraint("final_payout >= 0", name="ck_payout_calculations_final_non_negative"),
        CheckConstraint(
            "quality_multiplier >= 0 AND quality_multiplier <= 1",
            name="ck_payout_calculations_quality_multiplier_range",
        ),
        CheckConstraint(
            "fraud_multiplier >= 0 AND fraud_multiplier <= 1",
            name="ck_payout_calculations_fraud_multiplier_range",
        ),
        CheckConstraint(
            "eligible_seconds IS NULL OR eligible_seconds >= 0",
            name="ck_payout_calculations_eligible_seconds_non_negative",
        ),
        CheckConstraint(
            "payable_seconds IS NULL OR payable_seconds >= 0",
            name="ck_payout_calculations_payable_seconds_non_negative",
        ),
        CheckConstraint(
            "payable_seconds IS NULL OR eligible_seconds IS NULL OR "
            "payable_seconds <= eligible_seconds",
            name="ck_payout_calculations_payable_lte_eligible",
        ),
        CheckConstraint(
            "formula_version <> 'payout_v2' OR ("
            "eligible_seconds IS NOT NULL"
            " AND payable_seconds IS NOT NULL"
            " AND excluded_seconds_by_reason IS NOT NULL"
            " AND inputs_fingerprint IS NOT NULL"
            ")",
            name="ck_payout_calculations_v2_time_fields",
        ),
        UniqueConstraint(
            "trip_session_id",
            "formula_version",
            "payout_rule_id",
            name="uq_payout_calculations_trip_formula_rule",
        ),
        Index("ix_payout_calculations_trip_analytics_id", "trip_analytics_id"),
        Index("ix_payout_calculations_impression_estimate_id", "impression_estimate_id"),
        Index("ix_payout_calculations_campaign_id", "campaign_id"),
        Index("ix_payout_calculations_assignment_id", "assignment_id"),
        Index("ix_payout_calculations_driver_profile_id", "driver_profile_id"),
        Index("ix_payout_calculations_vehicle_id", "vehicle_id"),
        Index("ix_payout_calculations_campaign_calculated_at", "campaign_id", "calculated_at"),
        Index(
            "ix_payout_calculations_driver_profile_calculated_at",
            "driver_profile_id",
            "calculated_at",
        ),
        Index("ix_payout_calculations_campaign_status", "campaign_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    trip_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trip_analytics_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_analytics.id", ondelete="CASCADE"),
        nullable=False,
    )
    impression_estimate_id: Mapped[UUID] = mapped_column(
        ForeignKey("impression_estimates.id", ondelete="CASCADE"),
        nullable=False,
    )
    payout_rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_payout_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(
        Text,
        default="payout_v1",
        server_default=text("'payout_v1'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    distance_component: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    active_time_component: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_zone_bonus_component: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bonus_zone_bonus_component: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    impression_component: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    gross_payout: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    quality_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    fraud_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    cap_adjustment: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    eligible_seconds: Mapped[int | None] = mapped_column(Integer)
    payable_seconds: Mapped[int | None] = mapped_column(Integer)
    # Payable seconds charged to each Africa/Lagos calendar day (ISO date ->
    # seconds), summing to payable_seconds. A cross-midnight trip charges each
    # day's own cap (RM1, D4/D14); this is the stored allocation the cap
    # accounting and recompute-day read back.
    payable_seconds_by_day: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    excluded_seconds_by_reason: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    inputs_fingerprint: Mapped[str | None] = mapped_column(Text)
    final_payout: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payout_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EarningsLedgerEntry(Base):
    __tablename__ = "earnings_ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('trip_payout', 'adjustment', 'reversal', 'debt_remainder')",
            name="ck_earnings_ledger_entries_entry_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'available', 'voided', 'reversed', 'paid')",
            name="ck_earnings_ledger_entries_status",
        ),
        CheckConstraint("length(currency) = 3", name="ck_earnings_ledger_entries_currency"),
        CheckConstraint("amount >= 0", name="ck_earnings_ledger_entries_amount_non_negative"),
        Index(
            "uq_earnings_ledger_entries_payout_calculation_id",
            "payout_calculation_id",
            unique=True,
            sqlite_where=text("payout_calculation_id IS NOT NULL"),
            postgresql_where=text("payout_calculation_id IS NOT NULL"),
        ),
        Index(
            "uq_earnings_ledger_entries_trip_payout_per_trip",
            "trip_session_id",
            unique=True,
            sqlite_where=text("entry_type = 'trip_payout'"),
            postgresql_where=text("entry_type = 'trip_payout'"),
        ),
        Index(
            "uq_earnings_ledger_entries_source_fraud_flag_id",
            "source_fraud_flag_id",
            unique=True,
            sqlite_where=text("source_fraud_flag_id IS NOT NULL"),
            postgresql_where=text("source_fraud_flag_id IS NOT NULL"),
        ),
        Index("ix_earnings_ledger_entries_driver_profile_id", "driver_profile_id"),
        Index("ix_earnings_ledger_entries_driver_user_id", "driver_user_id"),
        Index("ix_earnings_ledger_entries_campaign_id", "campaign_id"),
        Index("ix_earnings_ledger_entries_trip_session_id", "trip_session_id"),
        Index("ix_earnings_ledger_entries_vehicle_id", "vehicle_id"),
        Index("ix_earnings_ledger_entries_driver_occurred_at", "driver_profile_id", "occurred_at"),
        Index("ix_earnings_ledger_entries_campaign_occurred_at", "campaign_id", "occurred_at"),
        Index("ix_earnings_ledger_entries_driver_status", "driver_profile_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    payout_calculation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payout_calculations.id", ondelete="RESTRICT"),
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    trip_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="SET NULL"),
    )
    vehicle_id: Mapped[UUID | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"))
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Q22: positive correction-order deltas remain pending until this release
    # time; the MNY-03A sweep rechecks it under the authoritative trip scope.
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_fraud_flag_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fraud_flags.id", ondelete="RESTRICT")
    )
    ledger_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
