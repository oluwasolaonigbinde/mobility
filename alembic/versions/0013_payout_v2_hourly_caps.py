"""Payout engine v2: hourly pay + daily caps (D2, D4; Q4, Q5).

Extends campaign_payout_rules and payout_calculations for the payout_v2
model while freezing payout_v1 history: v1 columns relax to nullable (values
on existing rows are never rewritten), a model XOR check keeps every rule row
valid for exactly one model, and a partial unique index guarantees at most one
trip_payout ledger entry per trip across formula versions.

Revision ID: 0013_payout_v2_hourly_caps
Revises: 0012_audit_event_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_payout_v2_hourly_caps"
down_revision: str | Sequence[str] | None = "0012_audit_event_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULE_V1_RATE_COLUMNS = (
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
)
RULE_V1_MULTIPLIER_COLUMNS = (
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
)
CALCULATION_V1_DEFAULTED_COLUMNS = (
    "distance_component",
    "active_time_component",
    "target_zone_bonus_component",
    "bonus_zone_bonus_component",
    "impression_component",
    "cap_adjustment",
)
CALCULATION_V1_NO_DEFAULT_COLUMNS = (
    "quality_multiplier",
    "fraud_multiplier",
)

RULE_MODEL_XOR_SQL = (
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

CALCULATION_V2_FIELDS_SQL = (
    "formula_version <> 'payout_v2' OR ("
    "eligible_seconds IS NOT NULL"
    " AND payable_seconds IS NOT NULL"
    " AND excluded_seconds_by_reason IS NOT NULL"
    " AND inputs_fingerprint IS NOT NULL"
    ")"
)


def upgrade() -> None:
    # campaign_payout_rules: v1 columns relax (values frozen, defaults removed
    # so a v2 INSERT that omits them stays NULL and satisfies the model XOR).
    for column in RULE_V1_RATE_COLUMNS + RULE_V1_MULTIPLIER_COLUMNS:
        op.alter_column(
            "campaign_payout_rules",
            column,
            existing_type=sa.Numeric(14, 2)
            if column in RULE_V1_RATE_COLUMNS
            else sa.Numeric(5, 4),
            nullable=True,
            server_default=None,
        )
    op.add_column(
        "campaign_payout_rules",
        sa.Column("hourly_rate_naira", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "campaign_payout_rules",
        sa.Column("daily_payable_hours_cap", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "campaign_payout_rules",
        sa.Column(
            "eligibility_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_campaign_payout_rules_hourly_rate_non_negative",
        "campaign_payout_rules",
        "hourly_rate_naira IS NULL OR hourly_rate_naira >= 0",
    )
    op.create_check_constraint(
        "ck_campaign_payout_rules_daily_cap_range",
        "campaign_payout_rules",
        "daily_payable_hours_cap IS NULL OR "
        "(daily_payable_hours_cap > 0 AND daily_payable_hours_cap <= 24)",
    )
    op.create_check_constraint(
        "ck_campaign_payout_rules_model_xor",
        "campaign_payout_rules",
        RULE_MODEL_XOR_SQL,
    )

    # payout_calculations: v1 component columns relax; the analytics/estimate
    # FKs deliberately stay NOT NULL (architecture 16.1).
    for column in CALCULATION_V1_DEFAULTED_COLUMNS:
        op.alter_column(
            "payout_calculations",
            column,
            existing_type=sa.Numeric(14, 2),
            nullable=True,
            server_default=None,
        )
    for column in CALCULATION_V1_NO_DEFAULT_COLUMNS:
        op.alter_column(
            "payout_calculations",
            column,
            existing_type=sa.Numeric(5, 4),
            nullable=True,
        )
    op.add_column(
        "payout_calculations",
        sa.Column("eligible_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "payout_calculations",
        sa.Column("payable_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "payout_calculations",
        sa.Column(
            "excluded_seconds_by_reason",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "payout_calculations",
        sa.Column("inputs_fingerprint", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_payout_calculations_eligible_seconds_non_negative",
        "payout_calculations",
        "eligible_seconds IS NULL OR eligible_seconds >= 0",
    )
    op.create_check_constraint(
        "ck_payout_calculations_payable_seconds_non_negative",
        "payout_calculations",
        "payable_seconds IS NULL OR payable_seconds >= 0",
    )
    op.create_check_constraint(
        "ck_payout_calculations_payable_lte_eligible",
        "payout_calculations",
        "payable_seconds IS NULL OR eligible_seconds IS NULL OR "
        "payable_seconds <= eligible_seconds",
    )
    op.create_check_constraint(
        "ck_payout_calculations_v2_time_fields",
        "payout_calculations",
        CALCULATION_V2_FIELDS_SQL,
    )

    # One trip_payout entry per trip across formula versions: the cross-model
    # double-pay guard for campaigns switching payout_v1 -> payout_v2.
    # Pre-flight: refuse (never auto-delete) if historical duplicates exist —
    # possible pre-0013 via explicit-rule admin recomputes after a rule change.
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT trip_session_id, count(*) FROM earnings_ledger_entries "
            "WHERE entry_type = 'trip_payout' AND trip_session_id IS NOT NULL "
            "GROUP BY trip_session_id HAVING count(*) > 1 LIMIT 5"
        )
    ).all()
    if duplicates:
        offending = ", ".join(str(row[0]) for row in duplicates)
        raise RuntimeError(
            "Cannot apply 0013: trips with multiple trip_payout ledger entries "
            f"exist (first ids: {offending}). Resolve the duplicates manually "
            "first - money rows are never auto-deleted."
        )
    op.create_index(
        "uq_earnings_ledger_entries_trip_payout_per_trip",
        "earnings_ledger_entries",
        ["trip_session_id"],
        unique=True,
        postgresql_where=sa.text("entry_type = 'trip_payout'"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    v2_rules = connection.execute(
        sa.text(
            "SELECT count(*) FROM campaign_payout_rules "
            "WHERE formula_version = 'payout_v2'"
        )
    ).scalar()
    v2_calculations = connection.execute(
        sa.text(
            "SELECT count(*) FROM payout_calculations "
            "WHERE formula_version = 'payout_v2'"
        )
    ).scalar()
    if (v2_rules or 0) or (v2_calculations or 0):
        raise RuntimeError(
            "Cannot downgrade 0013 while payout_v2 rows exist: "
            f"{v2_rules} rule(s), {v2_calculations} calculation(s). "
            "Money values are never invented on downgrade."
        )

    op.drop_index(
        "uq_earnings_ledger_entries_trip_payout_per_trip",
        table_name="earnings_ledger_entries",
    )
    op.drop_constraint(
        "ck_payout_calculations_v2_time_fields", "payout_calculations", type_="check"
    )
    op.drop_constraint(
        "ck_payout_calculations_payable_lte_eligible",
        "payout_calculations",
        type_="check",
    )
    op.drop_constraint(
        "ck_payout_calculations_payable_seconds_non_negative",
        "payout_calculations",
        type_="check",
    )
    op.drop_constraint(
        "ck_payout_calculations_eligible_seconds_non_negative",
        "payout_calculations",
        type_="check",
    )
    op.drop_column("payout_calculations", "inputs_fingerprint")
    op.drop_column("payout_calculations", "excluded_seconds_by_reason")
    op.drop_column("payout_calculations", "payable_seconds")
    op.drop_column("payout_calculations", "eligible_seconds")
    for column in CALCULATION_V1_NO_DEFAULT_COLUMNS:
        op.alter_column(
            "payout_calculations",
            column,
            existing_type=sa.Numeric(5, 4),
            nullable=False,
        )
    for column in CALCULATION_V1_DEFAULTED_COLUMNS:
        op.alter_column(
            "payout_calculations",
            column,
            existing_type=sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        )
    op.drop_constraint(
        "ck_campaign_payout_rules_model_xor", "campaign_payout_rules", type_="check"
    )
    op.drop_constraint(
        "ck_campaign_payout_rules_daily_cap_range",
        "campaign_payout_rules",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_payout_rules_hourly_rate_non_negative",
        "campaign_payout_rules",
        type_="check",
    )
    op.drop_column("campaign_payout_rules", "eligibility_params")
    op.drop_column("campaign_payout_rules", "daily_payable_hours_cap")
    op.drop_column("campaign_payout_rules", "hourly_rate_naira")
    for column in RULE_V1_MULTIPLIER_COLUMNS:
        op.alter_column(
            "campaign_payout_rules",
            column,
            existing_type=sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text(
                {
                    "low_fraud_multiplier": "0.9000",
                    "medium_fraud_multiplier": "0.7000",
                    "high_fraud_multiplier": "0.2500",
                }[column]
            ),
        )
    for column in RULE_V1_RATE_COLUMNS:
        op.alter_column(
            "campaign_payout_rules",
            column,
            existing_type=sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        )
