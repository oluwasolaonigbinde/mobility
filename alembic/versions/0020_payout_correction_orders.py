"""Maker-checker payout correction orders (MNY-06C, Q22).

Creates `payout_correction_orders`: projected campaign/Lagos-day corrections
with a draft -> pending_approval -> approved -> executed | rejected | stale
state machine, a DB-enforced approver <> creator CHECK, the PR12 projection
fingerprint, and the recorded execution result that makes execution
idempotent. Also adds `earnings_ledger_entries.release_at` (PR13): positive
correction deltas post as pending with their own release date; nothing
consumes the column yet — the release sweep is MNY-03A (PKG-02) scope.

Revision ID: 0020_payout_correction_orders
Revises: 0019_assignment_rule_bindings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_payout_correction_orders"
down_revision: str | Sequence[str] | None = "0019_assignment_rule_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payout_correction_orders",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lagos_day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "executed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "projected_delta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("projection_fingerprint", sa.Text(), nullable=True),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "execution_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'rejected',"
            " 'executed', 'stale')",
            name="ck_payout_correction_orders_status",
        ),
        sa.CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id",
            name="ck_payout_correction_orders_approver_not_creator",
        ),
    )
    op.create_index(
        "ix_payout_correction_orders_campaign_id",
        "payout_correction_orders",
        ["campaign_id"],
    )
    op.create_index(
        "ix_payout_correction_orders_campaign_day",
        "payout_correction_orders",
        ["campaign_id", "lagos_day"],
    )
    op.add_column(
        "earnings_ledger_entries",
        sa.Column("release_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    connection = op.get_bind()
    populated_order = connection.execute(
        sa.text("SELECT 1 FROM payout_correction_orders LIMIT 1")
    ).first()
    populated_release = connection.execute(
        sa.text(
            "SELECT 1 FROM earnings_ledger_entries "
            "WHERE release_at IS NOT NULL LIMIT 1"
        )
    ).first()
    if populated_order is not None or populated_release is not None:
        raise RuntimeError(
            "Refusing to downgrade 0020: payout correction orders or release "
            "timestamps contain authoritative financial state"
        )
    op.drop_column("earnings_ledger_entries", "release_at")
    op.drop_index(
        "ix_payout_correction_orders_campaign_day",
        table_name="payout_correction_orders",
    )
    op.drop_index(
        "ix_payout_correction_orders_campaign_id",
        table_name="payout_correction_orders",
    )
    op.drop_table("payout_correction_orders")
