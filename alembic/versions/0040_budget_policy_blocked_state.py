"""Add fail-closed budget-policy evaluation state.

Revision ID: 0040_budget_policy_blocked_state
Revises: 0039_billing_corrections_refunds
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0040_budget_policy_blocked_state"
down_revision: str | Sequence[str] | None = "0039_billing_corrections_refunds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_policy_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_key", sa.String(64), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("external_gate", sa.String(64), nullable=False),
        sa.Column("campaign_budget_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("campaign_daily_budget_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("policy_version", sa.String(128), nullable=True),
        sa.Column("billing_spend_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("alert_threshold_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("pause_threshold_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("pause_applied", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state = 'blocked_external_policy'",
            name="ck_budget_policy_evaluations_state",
        ),
        sa.CheckConstraint(
            "external_gate = 'EXT-BUDGET-POLICY'",
            name="ck_budget_policy_evaluations_external_gate",
        ),
        sa.CheckConstraint(
            "(campaign_budget_amount IS NOT NULL OR campaign_daily_budget_amount IS NOT NULL) "
            "AND (campaign_budget_amount IS NULL OR campaign_budget_amount >= 0) "
            "AND (campaign_daily_budget_amount IS NULL OR campaign_daily_budget_amount >= 0)",
            name="ck_budget_policy_evaluations_campaign_budget",
        ),
        sa.CheckConstraint(
            "length(currency) = 3",
            name="ck_budget_policy_evaluations_currency",
        ),
        sa.CheckConstraint(
            "policy_version IS NULL AND billing_spend_amount IS NULL "
            "AND alert_threshold_amount IS NULL AND pause_threshold_amount IS NULL "
            "AND pause_applied = false",
            name="ck_budget_policy_evaluations_blocked_fields",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "evaluation_key", name="uq_budget_policy_evaluation_key"
        ),
    )
    op.create_index(
        "ix_budget_policy_evaluations_campaign_id",
        "budget_policy_evaluations",
        ["campaign_id"],
    )
    op.execute(
        "CREATE TRIGGER budget_policy_evaluations_append_only "
        "BEFORE UPDATE OR DELETE ON budget_policy_evaluations "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM budget_policy_evaluations)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0040 downgrade blocked: budget-policy evidence exists")
    op.execute("DROP TRIGGER budget_policy_evaluations_append_only ON budget_policy_evaluations")
    op.drop_index(
        "ix_budget_policy_evaluations_campaign_id",
        table_name="budget_policy_evaluations",
    )
    op.drop_table("budget_policy_evaluations")
