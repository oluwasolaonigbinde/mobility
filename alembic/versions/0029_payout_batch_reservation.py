"""Add atomic payout batch reservation and provider submission authority.

Revision ID: 0029_payout_batch_reservation
Revises: 0028_protected_payee_accounts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029_payout_batch_reservation"
down_revision: str | Sequence[str] | None = "0028_protected_payee_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payout_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("instruction_set_fingerprint", sa.String(length=64)),
        sa.Column("provider_submission_reference", sa.Text()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'reserved', 'submitted')", name="ck_payout_batches_status"
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_batches_currency"),
        sa.CheckConstraint("total_amount >= 0", name="ck_payout_batches_total_non_negative"),
        sa.CheckConstraint(
            "(status = 'draft' AND instruction_set_fingerprint IS NULL) OR "
            "(status <> 'draft' AND instruction_set_fingerprint IS NOT NULL)",
            name="ck_payout_batches_reserved_fingerprint",
        ),
        sa.CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id",
            name="ck_payout_batches_maker_checker",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payout_batches_status_created", "payout_batches", ["status", "created_at"])
    op.create_table(
        "payout_batch_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payee_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_account_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("instruction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instruction_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("reservation_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount > 0", name="ck_payout_batch_lines_amount_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_batch_lines_currency"),
        sa.CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_batch_lines_instruction_fingerprint",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["payout_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["payee_version_id"], ["payee_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["bank_account_version_id"],
            ["payee_bank_account_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_payout_batch_lines_idempotency_key"),
    )
    op.create_index("ix_payout_batch_lines_batch_id", "payout_batch_lines", ["batch_id"])
    op.create_index(
        "ix_payout_batch_lines_ledger_entry_id", "payout_batch_lines", ["ledger_entry_id"]
    )
    op.create_index(
        "uq_payout_batch_lines_active_ledger_entry",
        "payout_batch_lines",
        ["ledger_entry_id"],
        unique=True,
        postgresql_where=sa.text("reservation_active = true"),
        sqlite_where=sa.text("reservation_active = true"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payout_batches) "
            "OR EXISTS (SELECT 1 FROM payout_batch_lines)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0029 downgrade blocked: payout batch authority exists")
    op.drop_index("uq_payout_batch_lines_active_ledger_entry", table_name="payout_batch_lines")
    op.drop_index("ix_payout_batch_lines_ledger_entry_id", table_name="payout_batch_lines")
    op.drop_index("ix_payout_batch_lines_batch_id", table_name="payout_batch_lines")
    op.drop_table("payout_batch_lines")
    op.drop_index("ix_payout_batches_status_created", table_name="payout_batches")
    op.drop_table("payout_batches")
