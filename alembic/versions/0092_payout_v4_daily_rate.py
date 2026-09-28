"""payout_v4 daily-rate model: rule branch, revision/binding terms, per-day distance.

D39 (Batch B): a daily rate for reaching a daily distance target. Every pay
value is a required field of an audited v4 revision; nothing here defaults a
client value. payout_v1-v3 rows keep their shapes and are never repriced.

Revision ID: 0092_payout_v4_daily_rate
Revises: 0091_budget_urgent_threshold
"""

import sqlalchemy as sa

from alembic import op

revision = "0092_payout_v4_daily_rate"
down_revision = "0091_budget_urgent_threshold"
branch_labels = None
depends_on = None

RULES = "campaign_payout_rules"
REVISIONS = "campaign_payout_rule_revisions"
BINDINGS = "assignment_rule_bindings"
CALCULATIONS = "payout_calculations"
RULE_XOR = "ck_campaign_payout_rules_model_xor"

V1_FIELDS = (
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
)
ALL_RATE_FIELDS = (*V1_FIELDS, "max_payout_per_trip")


def _all(fields: tuple[str, ...], predicate: str) -> str:
    return "".join(f" AND {field} {predicate}" for field in fields)


V1_BRANCH = (
    "(formula_version NOT IN ('payout_v2', 'payout_v4')"
    " AND hourly_rate_naira IS NULL AND daily_payable_hours_cap IS NULL"
    " AND eligibility_params IS NULL" + _all(V1_FIELDS, "IS NOT NULL") + ")"
)
V2_BRANCH = (
    "(formula_version = 'payout_v2'"
    " AND hourly_rate_naira IS NOT NULL AND daily_payable_hours_cap IS NOT NULL"
    + _all(ALL_RATE_FIELDS, "IS NULL")
    + ")"
)
V4_BRANCH = (
    "(formula_version = 'payout_v4'"
    " AND hourly_rate_naira IS NULL AND daily_payable_hours_cap IS NULL"
    " AND eligibility_params IS NULL" + _all(ALL_RATE_FIELDS, "IS NULL") + ")"
)
RULE_XOR_V4 = f"{V1_BRANCH} OR {V2_BRANCH} OR {V4_BRANCH}"
# 0013's original two-branch shape, restored on downgrade.
RULE_XOR_LEGACY = (
    "(formula_version <> 'payout_v2'"
    " AND hourly_rate_naira IS NULL AND daily_payable_hours_cap IS NULL"
    " AND eligibility_params IS NULL" + _all(V1_FIELDS, "IS NOT NULL") + ") OR " + V2_BRANCH
)

V4_COLUMNS = (
    "daily_rate_naira",
    "daily_target_miles",
    "shortfall_strategy",
    "deduction_per_mile_naira",
    "minimum_miles",
    "outside_area_weight",
)
# Shared by revisions and bindings: the hourly shape (v3) or the complete
# daily-rate shape (v4), never a mixture.
TERMS_SHAPE = (
    "(formula_version <> 'payout_v4' AND hourly_rate_naira IS NOT NULL"
    + _all(V4_COLUMNS, "IS NULL")
    + ") OR (formula_version = 'payout_v4'"
    " AND hourly_rate_naira IS NULL AND premium_hourly_rate_naira IS NULL"
    " AND daily_payable_hours_cap IS NULL"
    # Explicit IS NOT NULL: a comparison with NULL would let the CHECK pass.
    " AND daily_rate_naira IS NOT NULL AND daily_target_miles IS NOT NULL"
    " AND minimum_miles IS NOT NULL AND outside_area_weight IS NOT NULL"
    " AND shortfall_strategy IS NOT NULL"
    " AND daily_rate_naira > 0 AND daily_target_miles > 0"
    " AND minimum_miles >= 0 AND minimum_miles <= daily_target_miles"
    " AND outside_area_weight >= 0 AND outside_area_weight <= 1"
    " AND ((shortfall_strategy = 'proportional' AND deduction_per_mile_naira IS NULL)"
    " OR (shortfall_strategy = 'per_mile_deduction' AND deduction_per_mile_naira IS NOT NULL"
    " AND deduction_per_mile_naira > 0)))"
)


def _terms_check(table: str) -> str:
    return f"ck_{table}_terms_shape"


def _add_v4_terms(table: str) -> None:
    op.add_column(table, sa.Column("daily_rate_naira", sa.Numeric(14, 2)))
    op.add_column(table, sa.Column("daily_target_miles", sa.Numeric(10, 3)))
    op.add_column(table, sa.Column("shortfall_strategy", sa.Text()))
    op.add_column(table, sa.Column("deduction_per_mile_naira", sa.Numeric(14, 2)))
    op.add_column(table, sa.Column("minimum_miles", sa.Numeric(10, 3)))
    op.add_column(table, sa.Column("outside_area_weight", sa.Numeric(5, 4)))
    op.alter_column(table, "hourly_rate_naira", existing_type=sa.Numeric(14, 2), nullable=True)
    op.create_check_constraint(_terms_check(table), table, TERMS_SHAPE)


def _drop_v4_terms(table: str) -> None:
    op.drop_constraint(_terms_check(table), table, type_="check")
    op.alter_column(table, "hourly_rate_naira", existing_type=sa.Numeric(14, 2), nullable=False)
    for column in reversed(V4_COLUMNS):
        op.drop_column(table, column)


def upgrade() -> None:
    op.drop_constraint(RULE_XOR, RULES, type_="check")
    op.create_check_constraint(RULE_XOR, RULES, RULE_XOR_V4)
    _add_v4_terms(REVISIONS)
    _add_v4_terms(BINDINGS)
    # Whole metres credited and the money increment per Africa/Lagos day.
    # Required for payout_v4 rows by the engine; older rows keep NULL.
    op.add_column(CALCULATIONS, sa.Column("distance_m_by_day", sa.JSON()))
    op.add_column(CALCULATIONS, sa.Column("amount_by_day", sa.JSON()))


def downgrade() -> None:
    bind = op.get_bind()
    counts = {
        table: bind.scalar(
            sa.text(f"SELECT count(*) FROM {table} WHERE formula_version = 'payout_v4'")
        )
        for table in (RULES, REVISIONS, BINDINGS, CALCULATIONS)
    }
    blocking = {table: count for table, count in counts.items() if count}
    if blocking:
        # Dropping the columns would erase accepted daily-rate terms and money.
        raise RuntimeError(f"0092 downgrade blocked: payout_v4 rows exist {blocking}")
    op.drop_column(CALCULATIONS, "amount_by_day")
    op.drop_column(CALCULATIONS, "distance_m_by_day")
    _drop_v4_terms(BINDINGS)
    _drop_v4_terms(REVISIONS)
    op.drop_constraint(RULE_XOR, RULES, type_="check")
    op.create_check_constraint(RULE_XOR, RULES, RULE_XOR_LEGACY)
