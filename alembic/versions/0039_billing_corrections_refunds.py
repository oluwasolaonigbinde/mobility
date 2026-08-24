"""Add immutable billing corrections and refund settlements.

Revision ID: 0039_billing_corrections_refunds
Revises: 0038_payment_gateway_events
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039_billing_corrections_refunds"
down_revision: str | Sequence[str] | None = "0038_payment_gateway_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "invoice_corrections",
        _uuid("id"),
        _uuid("invoice_id"),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("correction_number", sa.String(96), nullable=False),
        sa.Column("correction_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _uuid("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "correction_type IN ('credit_note', 'debit_note')",
            name="ck_invoice_corrections_type",
        ),
        sa.CheckConstraint("sequence_number > 0", name="ck_invoice_corrections_sequence"),
        sa.CheckConstraint("length(currency) = 3", name="ck_invoice_corrections_currency"),
        sa.CheckConstraint(
            "net_amount >= 0 AND tax_amount >= 0 AND gross_amount > 0 "
            "AND gross_amount = net_amount + tax_amount",
            name="ck_invoice_corrections_amounts",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id", "sequence_number", name="uq_invoice_corrections_sequence"
        ),
        sa.UniqueConstraint("correction_number", name="uq_invoice_corrections_number"),
    )
    op.create_index("ix_invoice_corrections_invoice_id", "invoice_corrections", ["invoice_id"])
    op.create_table(
        "refund_settlements",
        _uuid("id"),
        _uuid("commercial_terms_id"),
        _uuid("campaign_id"),
        _uuid("receipt_id", nullable=True),
        _uuid("production_start_id", nullable=True),
        _uuid("waiver_id", nullable=True),
        sa.Column("disposition", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("funding_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligibility_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_provider", sa.String(64), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _uuid("recorded_by_user_id"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('refund_recorded', 'credit_settlement_recorded')",
            name="ck_refund_settlements_disposition",
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_refund_settlements_currency"),
        sa.CheckConstraint(
            "(disposition = 'refund_recorded' AND receipt_id IS NOT NULL AND amount > 0 "
            "AND funding_authorized_at IS NOT NULL AND eligibility_ends_at IS NOT NULL) OR "
            "(disposition = 'credit_settlement_recorded' AND receipt_id IS NULL "
            "AND amount = 0 AND funding_authorized_at IS NULL AND eligibility_ends_at IS NULL)",
            name="ck_refund_settlements_authority",
        ),
        sa.CheckConstraint(
            "eligibility_ends_at IS NULL OR recorded_at < eligibility_ends_at",
            name="ck_refund_settlements_eligibility_window",
        ),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_start_id"], ["production_starts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["waiver_id"], ["expedited_production_waivers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "settlement_provider",
            "external_reference",
            name="uq_refund_settlements_external_reference",
        ),
    )
    op.create_index(
        "ix_refund_settlements_commercial_terms_id",
        "refund_settlements",
        ["commercial_terms_id"],
    )
    op.create_index("ix_refund_settlements_campaign_id", "refund_settlements", ["campaign_id"])
    for table in ("invoice_corrections", "refund_settlements"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
        )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM invoice_corrections) "
                "OR EXISTS (SELECT 1 FROM refund_settlements)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0039 downgrade blocked: correction or refund authority exists")
    for table in ("refund_settlements", "invoice_corrections"):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.drop_index("ix_refund_settlements_campaign_id", table_name="refund_settlements")
    op.drop_index("ix_refund_settlements_commercial_terms_id", table_name="refund_settlements")
    op.drop_table("refund_settlements")
    op.drop_index("ix_invoice_corrections_invoice_id", table_name="invoice_corrections")
    op.drop_table("invoice_corrections")
