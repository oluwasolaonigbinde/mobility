from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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


class EarningsLedgerEntryStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    VOIDED = "voided"
    REVERSED = "reversed"


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
    base_rate_per_km: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    base_rate_per_active_hour: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    target_zone_bonus_rate_per_km: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    bonus_zone_bonus_rate_per_km: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    estimated_impression_rate_per_1000: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    min_payout_per_trip: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    max_payout_per_trip: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    low_fraud_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.9000"),
        server_default=text("0.9000"),
        nullable=False,
    )
    medium_fraud_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.7000"),
        server_default=text("0.7000"),
        nullable=False,
    )
    high_fraud_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.2500"),
        server_default=text("0.2500"),
        nullable=False,
    )
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
    distance_component: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    active_time_component: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    target_zone_bonus_component: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    bonus_zone_bonus_component: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    impression_component: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    gross_payout: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
    quality_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    fraud_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    cap_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        server_default=text("0"),
        nullable=False,
    )
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
            "entry_type IN ('trip_payout', 'adjustment', 'reversal')",
            name="ck_earnings_ledger_entries_entry_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'available', 'voided', 'reversed')",
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
