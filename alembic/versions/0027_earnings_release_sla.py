"""Add earnings release SLA and fraud-linked reversal authority.

Revision ID: 0027_earnings_release_sla
Revises: 0026_frozen_campaign_payment_window
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_earnings_release_sla"
down_revision: str | Sequence[str] | None = "0026_frozen_campaign_payment_window"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fraud_flags",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_fraud_flags_unresolved_sla",
        "fraud_flags",
        ["detected_at", "id"],
        postgresql_where=sa.text(
            "status IN ('open', 'acknowledged') AND escalated_at IS NULL"
        ),
        sqlite_where=sa.text(
            "status IN ('open', 'acknowledged') AND escalated_at IS NULL"
        ),
    )
    op.add_column(
        "earnings_ledger_entries",
        sa.Column(
            "source_fraud_flag_id",
            sa.Uuid(),
            sa.ForeignKey("fraud_flags.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_earnings_ledger_entries_source_fraud_flag_id",
        "earnings_ledger_entries",
        ["source_fraud_flag_id"],
        unique=True,
        postgresql_where=sa.text("source_fraud_flag_id IS NOT NULL"),
        sqlite_where=sa.text("source_fraud_flag_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM fraud_flags WHERE escalated_at IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM earnings_ledger_entries "
            "WHERE source_fraud_flag_id IS NOT NULL)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "0027 downgrade blocked: escalation or fraud reversal authority exists"
        )
    op.drop_index(
        "uq_earnings_ledger_entries_source_fraud_flag_id",
        table_name="earnings_ledger_entries",
    )
    op.drop_column("earnings_ledger_entries", "source_fraud_flag_id")
    op.drop_index("ix_fraud_flags_unresolved_sla", table_name="fraud_flags")
    op.drop_column("fraud_flags", "escalated_at")
