"""Create payout rules, calculations, and earnings ledger.

Revision ID: 0010_payouts_and_earnings
Revises: 0009_impression_estimation
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_payouts_and_earnings"
down_revision: str | None = "0009_impression_estimation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_payout_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "formula_version",
            sa.Text(),
            server_default=sa.text("'payout_v1'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "base_rate_per_km",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "base_rate_per_active_hour",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_bonus_rate_per_km",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_bonus_rate_per_km",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "estimated_impression_rate_per_1000",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "min_payout_per_trip",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("max_payout_per_trip", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "low_fraud_multiplier",
            sa.Numeric(5, 4),
            server_default=sa.text("0.9000"),
            nullable=False,
        ),
        sa.Column(
            "medium_fraud_multiplier",
            sa.Numeric(5, 4),
            server_default=sa.text("0.7000"),
            nullable=False,
        ),
        sa.Column(
            "high_fraud_multiplier",
            sa.Numeric(5, 4),
            server_default=sa.text("0.2500"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_campaign_payout_rules_status",
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_campaign_payout_rules_currency"),
        sa.CheckConstraint(
            "base_rate_per_km >= 0",
            name="ck_campaign_payout_rules_base_rate_per_km_non_negative",
        ),
        sa.CheckConstraint(
            "base_rate_per_active_hour >= 0",
            name="ck_campaign_payout_rules_base_rate_per_active_hour_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_bonus_rate_per_km >= 0",
            name="ck_campaign_payout_rules_target_bonus_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_bonus_rate_per_km >= 0",
            name="ck_campaign_payout_rules_bonus_zone_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_impression_rate_per_1000 >= 0",
            name="ck_campaign_payout_rules_impression_rate_non_negative",
        ),
        sa.CheckConstraint(
            "min_payout_per_trip >= 0",
            name="ck_campaign_payout_rules_min_payout_non_negative",
        ),
        sa.CheckConstraint(
            "max_payout_per_trip IS NULL OR max_payout_per_trip >= min_payout_per_trip",
            name="ck_campaign_payout_rules_max_gte_min",
        ),
        sa.CheckConstraint(
            "low_fraud_multiplier >= 0 AND low_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_low_fraud_multiplier_range",
        ),
        sa.CheckConstraint(
            "medium_fraud_multiplier >= 0 AND medium_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_medium_fraud_multiplier_range",
        ),
        sa.CheckConstraint(
            "high_fraud_multiplier >= 0 AND high_fraud_multiplier <= 1",
            name="ck_campaign_payout_rules_high_fraud_multiplier_range",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_payout_rules_campaign_id",
        "campaign_payout_rules",
        ["campaign_id"],
    )
    op.create_index(
        "ix_campaign_payout_rules_campaign_status",
        "campaign_payout_rules",
        ["campaign_id", "status"],
    )
    op.create_index(
        "uq_campaign_payout_rules_active_campaign",
        "campaign_payout_rules",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "payout_calculations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_analytics_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("impression_estimate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payout_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "formula_version",
            sa.Text(),
            server_default=sa.text("'payout_v1'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "distance_component",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "active_time_component",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_bonus_component",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_bonus_component",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "impression_component",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("gross_payout", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("quality_multiplier", sa.Numeric(5, 4), nullable=False),
        sa.Column("fraud_multiplier", sa.Numeric(5, 4), nullable=False),
        sa.Column("cap_adjustment", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("final_payout", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('calculated', 'insufficient_data', 'blocked')",
            name="ck_payout_calculations_status",
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_calculations_currency"),
        sa.CheckConstraint(
            "distance_component >= 0",
            name="ck_payout_calculations_distance_component_non_negative",
        ),
        sa.CheckConstraint(
            "active_time_component >= 0",
            name="ck_payout_calculations_active_time_component_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_bonus_component >= 0",
            name="ck_payout_calculations_target_zone_component_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_bonus_component >= 0",
            name="ck_payout_calculations_bonus_zone_component_non_negative",
        ),
        sa.CheckConstraint(
            "impression_component >= 0",
            name="ck_payout_calculations_impression_component_non_negative",
        ),
        sa.CheckConstraint("gross_payout >= 0", name="ck_payout_calculations_gross_non_negative"),
        sa.CheckConstraint("final_payout >= 0", name="ck_payout_calculations_final_non_negative"),
        sa.CheckConstraint(
            "quality_multiplier >= 0 AND quality_multiplier <= 1",
            name="ck_payout_calculations_quality_multiplier_range",
        ),
        sa.CheckConstraint(
            "fraud_multiplier >= 0 AND fraud_multiplier <= 1",
            name="ck_payout_calculations_fraud_multiplier_range",
        ),
        sa.ForeignKeyConstraint(["trip_session_id"], ["trip_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_analytics_id"], ["trip_analytics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["impression_estimate_id"],
            ["impression_estimates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["payout_rule_id"],
            ["campaign_payout_rules.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["campaign_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_session_id",
            "formula_version",
            "payout_rule_id",
            name="uq_payout_calculations_trip_formula_rule",
        ),
    )
    op.create_index(
        "ix_payout_calculations_trip_analytics_id",
        "payout_calculations",
        ["trip_analytics_id"],
    )
    op.create_index(
        "ix_payout_calculations_impression_estimate_id",
        "payout_calculations",
        ["impression_estimate_id"],
    )
    op.create_index("ix_payout_calculations_campaign_id", "payout_calculations", ["campaign_id"])
    op.create_index(
        "ix_payout_calculations_assignment_id",
        "payout_calculations",
        ["assignment_id"],
    )
    op.create_index(
        "ix_payout_calculations_driver_profile_id",
        "payout_calculations",
        ["driver_profile_id"],
    )
    op.create_index("ix_payout_calculations_vehicle_id", "payout_calculations", ["vehicle_id"])
    op.create_index(
        "ix_payout_calculations_campaign_calculated_at",
        "payout_calculations",
        ["campaign_id", "calculated_at"],
    )
    op.create_index(
        "ix_payout_calculations_driver_profile_calculated_at",
        "payout_calculations",
        ["driver_profile_id", "calculated_at"],
    )
    op.create_index(
        "ix_payout_calculations_campaign_status",
        "payout_calculations",
        ["campaign_id", "status"],
    )

    op.create_table(
        "earnings_ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payout_calculation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('trip_payout', 'adjustment', 'reversal')",
            name="ck_earnings_ledger_entries_entry_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'available', 'voided', 'reversed')",
            name="ck_earnings_ledger_entries_status",
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_earnings_ledger_entries_currency"),
        sa.CheckConstraint("amount >= 0", name="ck_earnings_ledger_entries_amount_non_negative"),
        sa.ForeignKeyConstraint(
            ["payout_calculation_id"],
            ["payout_calculations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_session_id"], ["trip_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_earnings_ledger_entries_payout_calculation_id",
        "earnings_ledger_entries",
        ["payout_calculation_id"],
        unique=True,
        postgresql_where=sa.text("payout_calculation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_earnings_ledger_entries_driver_profile_id",
        "earnings_ledger_entries",
        ["driver_profile_id"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_driver_user_id",
        "earnings_ledger_entries",
        ["driver_user_id"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_campaign_id",
        "earnings_ledger_entries",
        ["campaign_id"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_trip_session_id",
        "earnings_ledger_entries",
        ["trip_session_id"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_vehicle_id",
        "earnings_ledger_entries",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_driver_occurred_at",
        "earnings_ledger_entries",
        ["driver_profile_id", "occurred_at"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_campaign_occurred_at",
        "earnings_ledger_entries",
        ["campaign_id", "occurred_at"],
    )
    op.create_index(
        "ix_earnings_ledger_entries_driver_status",
        "earnings_ledger_entries",
        ["driver_profile_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_earnings_ledger_entries_driver_status", table_name="earnings_ledger_entries")
    op.drop_index(
        "ix_earnings_ledger_entries_campaign_occurred_at",
        table_name="earnings_ledger_entries",
    )
    op.drop_index(
        "ix_earnings_ledger_entries_driver_occurred_at",
        table_name="earnings_ledger_entries",
    )
    op.drop_index("ix_earnings_ledger_entries_vehicle_id", table_name="earnings_ledger_entries")
    op.drop_index(
        "ix_earnings_ledger_entries_trip_session_id",
        table_name="earnings_ledger_entries",
    )
    op.drop_index("ix_earnings_ledger_entries_campaign_id", table_name="earnings_ledger_entries")
    op.drop_index("ix_earnings_ledger_entries_driver_user_id", table_name="earnings_ledger_entries")
    op.drop_index(
        "ix_earnings_ledger_entries_driver_profile_id",
        table_name="earnings_ledger_entries",
    )
    op.drop_index(
        "uq_earnings_ledger_entries_payout_calculation_id",
        table_name="earnings_ledger_entries",
    )
    op.drop_table("earnings_ledger_entries")

    op.drop_index("ix_payout_calculations_campaign_status", table_name="payout_calculations")
    op.drop_index(
        "ix_payout_calculations_driver_profile_calculated_at",
        table_name="payout_calculations",
    )
    op.drop_index(
        "ix_payout_calculations_campaign_calculated_at",
        table_name="payout_calculations",
    )
    op.drop_index("ix_payout_calculations_vehicle_id", table_name="payout_calculations")
    op.drop_index("ix_payout_calculations_driver_profile_id", table_name="payout_calculations")
    op.drop_index("ix_payout_calculations_assignment_id", table_name="payout_calculations")
    op.drop_index("ix_payout_calculations_campaign_id", table_name="payout_calculations")
    op.drop_index(
        "ix_payout_calculations_impression_estimate_id",
        table_name="payout_calculations",
    )
    op.drop_index("ix_payout_calculations_trip_analytics_id", table_name="payout_calculations")
    op.drop_table("payout_calculations")

    op.drop_index("uq_campaign_payout_rules_active_campaign", table_name="campaign_payout_rules")
    op.drop_index("ix_campaign_payout_rules_campaign_status", table_name="campaign_payout_rules")
    op.drop_index("ix_campaign_payout_rules_campaign_id", table_name="campaign_payout_rules")
    op.drop_table("campaign_payout_rules")
