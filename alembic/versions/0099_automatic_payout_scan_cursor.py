"""Bound automatic candidate work while progressing past excluded earnings.

Revision ID: 0099_automatic_payout_scan_cursor
Revises: 0098_paystack_edge_case_evidence
"""

import sqlalchemy as sa

from alembic import op

revision = "0099_automatic_payout_scan_cursor"
down_revision = "0098_paystack_edge_case_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payout_automatic_controls",
        sa.Column("candidate_cursor_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payout_automatic_controls", sa.Column("candidate_cursor_id", sa.Uuid(), nullable=True)
    )
    op.create_check_constraint(
        "ck_payout_automatic_controls_cursor_pair",
        "payout_automatic_controls",
        "(candidate_cursor_at IS NULL) = (candidate_cursor_id IS NULL)",
    )


def downgrade() -> None:
    # Scan progress is disposable operational state, not money or accepted terms.
    op.drop_constraint(
        "ck_payout_automatic_controls_cursor_pair", "payout_automatic_controls", type_="check"
    )
    op.drop_column("payout_automatic_controls", "candidate_cursor_id")
    op.drop_column("payout_automatic_controls", "candidate_cursor_at")
