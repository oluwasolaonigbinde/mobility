"""Freeze accepted campaign payment windows on payout-v3 bindings.

Revision ID: 0026_frozen_campaign_payment_window
Revises: 0025_fraud_disputes_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_frozen_campaign_payment_window"
down_revision: str | Sequence[str] | None = "0025_fraud_disputes_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assignment_rule_bindings",
        sa.Column("campaign_window_start_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column("campaign_window_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "campaign_window_frozen",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM assignment_rule_bindings
            WHERE campaign_window_frozen
               OR campaign_window_start_at IS NOT NULL
               OR campaign_window_end_at IS NOT NULL
          ) THEN
            RAISE EXCEPTION '0026 downgrade blocked: accepted campaign windows are authoritative';
          END IF;
        END $$
        """
    )
    op.drop_column("assignment_rule_bindings", "campaign_window_frozen")
    op.drop_column("assignment_rule_bindings", "campaign_window_end_at")
    op.drop_column("assignment_rule_bindings", "campaign_window_start_at")
