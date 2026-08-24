"""Add verified provider line reconciliation and paid finality.

Revision ID: 0030_provider_line_reconciliation
Revises: 0029_payout_batch_reservation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0030_provider_line_reconciliation"
down_revision: str | Sequence[str] | None = "0029_payout_batch_reservation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_payout_batches_status", "payout_batches", type_="check")
    op.create_check_constraint(
        "ck_payout_batches_status",
        "payout_batches",
        "status IN ('draft', 'reserved', 'submitted', 'reconciled', 'completed', 'failed', 'void')",
    )
    op.add_column(
        "payout_batch_lines",
        sa.Column("status", sa.String(length=16), server_default="reserved", nullable=False),
    )
    op.add_column("payout_batch_lines", sa.Column("provider_transfer_reference", sa.Text()))
    op.add_column(
        "payout_batch_lines",
        sa.Column(
            "reconciled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column("payout_batch_lines", sa.Column("reconciled_at", sa.DateTime(timezone=True)))
    op.add_column(
        "payout_batch_lines",
        sa.Column("last_provider_evidence_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "ck_payout_batch_lines_status",
        "payout_batch_lines",
        "status IN ('reserved', 'submitted', 'succeeded', 'failed', 'void')",
    )
    op.create_check_constraint(
        "ck_payout_batch_lines_provider_state",
        "payout_batch_lines",
        "(status IN ('reserved', 'void') AND provider_transfer_reference IS NULL) OR "
        "(status IN ('submitted', 'succeeded', 'failed') "
        "AND provider_transfer_reference IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_payout_batch_lines_active_state",
        "payout_batch_lines",
        "(status = 'void' AND reservation_active = false) OR "
        "(status <> 'void' AND reservation_active = true)",
    )
    op.create_index(
        "uq_payout_batch_lines_provider_transfer_reference",
        "payout_batch_lines",
        ["provider_transfer_reference"],
        unique=True,
        postgresql_where=sa.text("provider_transfer_reference IS NOT NULL"),
        sqlite_where=sa.text("provider_transfer_reference IS NOT NULL"),
    )
    op.create_table(
        "payout_line_reconciliation_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("reconciled_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source IN ('webhook', 'poll')", name="ck_payout_line_events_source"),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'failed')", name="ck_payout_line_events_outcome"
        ),
        sa.CheckConstraint(
            "length(evidence_fingerprint) = 64",
            name="ck_payout_line_events_evidence_fingerprint",
        ),
        sa.ForeignKeyConstraint(["line_id"], ["payout_batch_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reconciled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id", name="uq_payout_line_events_provider_event_id"),
    )
    op.create_index(
        "ix_payout_line_events_line_id", "payout_line_reconciliation_events", ["line_id"]
    )
    op.drop_constraint(
        "ck_earnings_ledger_entries_status", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_status",
        "earnings_ledger_entries",
        "status IN ('pending', 'available', 'voided', 'reversed', 'paid')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payout_line_reconciliation_events) "
            "OR EXISTS (SELECT 1 FROM payout_batch_lines "
            "WHERE status <> 'reserved' OR provider_transfer_reference IS NOT NULL "
            "OR reconciled_by_user_id IS NOT NULL OR reconciled_at IS NOT NULL "
            "OR last_provider_evidence_at IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM payout_batches "
            "WHERE status IN ('reconciled', 'completed', 'failed', 'void')) "
            "OR EXISTS (SELECT 1 FROM earnings_ledger_entries WHERE status = 'paid')"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0030 downgrade blocked: provider reconciliation authority exists")

    op.drop_constraint(
        "ck_earnings_ledger_entries_status", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_status",
        "earnings_ledger_entries",
        "status IN ('pending', 'available', 'voided', 'reversed')",
    )
    op.drop_index("ix_payout_line_events_line_id", table_name="payout_line_reconciliation_events")
    op.drop_table("payout_line_reconciliation_events")
    op.drop_index(
        "uq_payout_batch_lines_provider_transfer_reference",
        table_name="payout_batch_lines",
    )
    op.drop_constraint("ck_payout_batch_lines_active_state", "payout_batch_lines", type_="check")
    op.drop_constraint("ck_payout_batch_lines_provider_state", "payout_batch_lines", type_="check")
    op.drop_constraint("ck_payout_batch_lines_status", "payout_batch_lines", type_="check")
    op.drop_column("payout_batch_lines", "last_provider_evidence_at")
    op.drop_column("payout_batch_lines", "reconciled_at")
    op.drop_column("payout_batch_lines", "reconciled_by_user_id")
    op.drop_column("payout_batch_lines", "provider_transfer_reference")
    op.drop_column("payout_batch_lines", "status")
    op.drop_constraint("ck_payout_batches_status", "payout_batches", type_="check")
    op.create_check_constraint(
        "ck_payout_batches_status",
        "payout_batches",
        "status IN ('draft', 'reserved', 'submitted')",
    )
