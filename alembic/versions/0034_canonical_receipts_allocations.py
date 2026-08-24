"""Add canonical immutable payment receipts and bounded allocations.

Revision ID: 0034_canonical_receipts_allocations
Revises: 0033_advertiser_company_profiles
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034_canonical_receipts_allocations"
down_revision: str | Sequence[str] | None = "0033_advertiser_company_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "payment_receipts",
        _uuid("id"),
        _uuid("organization_id"),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_transaction_id", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payer_name", sa.String(255), nullable=False),
        sa.Column("evidence_reference", sa.String(255), nullable=False),
        _uuid("observed_by_user_id", nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "method IN ('manual_transfer', 'gateway')", name="ck_payment_receipts_method"
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_payment_receipts_currency"),
        sa.CheckConstraint("amount > 0", name="ck_payment_receipts_amount_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["observed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_transaction_id", name="uq_payment_receipts_external_transaction"
        ),
    )
    op.create_index("ix_payment_receipts_organization_id", "payment_receipts", ["organization_id"])
    op.create_table(
        "receipt_reconciliations",
        _uuid("id"),
        _uuid("receipt_id"),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("expected_currency", sa.String(3), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        _uuid("reconciled_by_user_id"),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(expected_currency) = 3", name="ck_receipt_reconciliations_currency"
        ),
        sa.CheckConstraint(
            "expected_amount > 0", name="ck_receipt_reconciliations_amount_positive"
        ),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reconciled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id", name="uq_receipt_reconciliations_receipt"),
    )
    op.create_index(
        "ix_receipt_reconciliations_receipt_id", "receipt_reconciliations", ["receipt_id"]
    )
    op.create_table(
        "receipt_lifecycle_events",
        _uuid("id"),
        _uuid("receipt_id"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        _uuid("actor_user_id", nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('observed', 'reconciled', 'confirmed', 'reversed')",
            name="ck_receipt_lifecycle_events_status",
        ),
        sa.CheckConstraint("sequence_number BETWEEN 1 AND 4", name="ck_receipt_lifecycle_sequence"),
        sa.CheckConstraint(
            "(status = 'observed' AND sequence_number = 1) OR "
            "(status = 'reconciled' AND sequence_number = 2) OR "
            "(status = 'confirmed' AND sequence_number = 3) OR "
            "(status = 'reversed' AND sequence_number = 4)",
            name="ck_receipt_lifecycle_status_sequence",
        ),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id", "status", name="uq_receipt_lifecycle_status"),
        sa.UniqueConstraint("receipt_id", "sequence_number", name="uq_receipt_lifecycle_sequence"),
    )
    op.create_index(
        "ix_receipt_lifecycle_events_receipt_id", "receipt_lifecycle_events", ["receipt_id"]
    )
    op.create_table(
        "receipt_allocations",
        _uuid("id"),
        _uuid("receipt_id"),
        _uuid("commercial_terms_id"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        _uuid("allocated_by_user_id"),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_receipt_allocations_amount_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_receipt_allocations_currency"),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["allocated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receipt_id", "commercial_terms_id", name="uq_receipt_allocations_terms"
        ),
    )
    op.create_index("ix_receipt_allocations_receipt_id", "receipt_allocations", ["receipt_id"])
    op.create_index(
        "ix_receipt_allocations_commercial_terms_id", "receipt_allocations", ["commercial_terms_id"]
    )

    op.execute(
        """
        CREATE FUNCTION reject_receipt_authority_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'receipt authority is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "payment_receipts",
        "receipt_reconciliations",
        "receipt_lifecycle_events",
        "receipt_allocations",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payment_receipts) "
            "OR EXISTS (SELECT 1 FROM receipt_reconciliations) "
            "OR EXISTS (SELECT 1 FROM receipt_lifecycle_events) "
            "OR EXISTS (SELECT 1 FROM receipt_allocations)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0034 downgrade blocked: canonical receipt authority exists")
    for table in (
        "receipt_allocations",
        "receipt_lifecycle_events",
        "receipt_reconciliations",
        "payment_receipts",
    ):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_receipt_authority_mutation()")
    op.drop_index("ix_receipt_allocations_commercial_terms_id", table_name="receipt_allocations")
    op.drop_index("ix_receipt_allocations_receipt_id", table_name="receipt_allocations")
    op.drop_table("receipt_allocations")
    op.drop_index("ix_receipt_lifecycle_events_receipt_id", table_name="receipt_lifecycle_events")
    op.drop_table("receipt_lifecycle_events")
    op.drop_index("ix_receipt_reconciliations_receipt_id", table_name="receipt_reconciliations")
    op.drop_table("receipt_reconciliations")
    op.drop_index("ix_payment_receipts_organization_id", table_name="payment_receipts")
    op.drop_table("payment_receipts")
