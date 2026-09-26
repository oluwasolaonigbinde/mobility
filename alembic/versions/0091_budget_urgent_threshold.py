"""Add the urgent budget alert level between the warning and the pause.

Revision ID: 0091_budget_urgent_threshold
Revises: 0090_single_active_advertiser_membership
"""

import sqlalchemy as sa

from alembic import op

revision = "0091_budget_urgent_threshold"
down_revision = "0090_single_active_advertiser_membership"
branch_labels = None
depends_on = None

TABLE = "budget_policy_evaluations"
STATE_CHECK = "ck_budget_policy_evaluations_state"
URGENT_CHECK = "ck_budget_policy_evaluations_urgent"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("urgent_threshold_amount", sa.Numeric(14, 2)))
    op.drop_constraint(STATE_CHECK, TABLE, type_="check")
    op.create_check_constraint(
        STATE_CHECK,
        TABLE,
        "state IN ('blocked_external_policy', 'within_budget', "
        "'alert_threshold', 'urgent_threshold', 'pause_threshold')",
    )
    # Existing rows are two-level decisions and keep a null urgent amount.
    op.create_check_constraint(
        URGENT_CHECK,
        TABLE,
        "(state = 'blocked_external_policy' AND urgent_threshold_amount IS NULL) OR "
        "(state NOT IN ('blocked_external_policy', 'urgent_threshold') "
        "AND urgent_threshold_amount IS NULL) OR "
        "(state <> 'blocked_external_policy' AND urgent_threshold_amount IS NOT NULL "
        "AND urgent_threshold_amount > alert_threshold_amount "
        "AND urgent_threshold_amount < pause_threshold_amount)",
    )


def downgrade() -> None:
    urgent_rows = op.get_bind().scalar(
        sa.text(f"SELECT count(*) FROM {TABLE} WHERE urgent_threshold_amount IS NOT NULL")
    )
    if urgent_rows:
        # Dropping the column would erase recorded budget decisions.
        raise RuntimeError(
            f"0091 downgrade blocked: {urgent_rows} budget evaluation(s) record an urgent level"
        )
    op.drop_constraint(URGENT_CHECK, TABLE, type_="check")
    op.drop_constraint(STATE_CHECK, TABLE, type_="check")
    op.create_check_constraint(
        STATE_CHECK,
        TABLE,
        "state IN ('blocked_external_policy', 'within_budget', "
        "'alert_threshold', 'pause_threshold')",
    )
    op.drop_column(TABLE, "urgent_threshold_amount")
