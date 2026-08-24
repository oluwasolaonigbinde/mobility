"""Add verified issuer profiles and VAT-itemised numbered invoices.

Revision ID: 0035_vat_itemised_invoices
Revises: 0034_canonical_receipts_allocations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035_vat_itemised_invoices"
down_revision: str | Sequence[str] | None = "0034_canonical_receipts_allocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "invoice_issuer_profiles",
        _uuid("id"),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("tax_identification_number", sa.String(128), nullable=False),
        sa.Column("registered_address", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("invoice_wording", sa.Text(), nullable=False),
        sa.Column("numbering_prefix", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("external_input_reference", sa.String(255), nullable=False),
        _uuid("recorded_by_user_id"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verification_status IN ('synthetic', 'verified')",
            name="ck_invoice_issuer_profiles_verification",
        ),
        sa.CheckConstraint("length(country_code) = 2", name="ck_invoice_issuer_profiles_country"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_input_reference", name="uq_invoice_issuer_profiles_external_ref"
        ),
    )
    op.create_table(
        "invoice_number_sequences",
        _uuid("id"),
        _uuid("issuer_profile_id"),
        sa.Column("calendar_year", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.CheckConstraint("calendar_year >= 2020", name="ck_invoice_number_sequences_year"),
        sa.CheckConstraint("next_number > 0", name="ck_invoice_number_sequences_next"),
        sa.ForeignKeyConstraint(
            ["issuer_profile_id"], ["invoice_issuer_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer_profile_id", "calendar_year", name="uq_invoice_number_sequences_scope"
        ),
    )
    op.create_table(
        "invoices",
        _uuid("id"),
        _uuid("commercial_terms_id"),
        _uuid("campaign_id"),
        _uuid("organization_id"),
        _uuid("issuer_profile_id", nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("customer_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("issuer_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("line_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(7, 6), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        _uuid("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("issued_by_user_id", nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'issued', 'void')", name="ck_invoices_status"),
        sa.CheckConstraint("length(currency) = 3", name="ck_invoices_currency"),
        sa.CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 "
            "AND tax_amount >= 0 AND gross_amount >= 0",
            name="ck_invoices_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "gross_amount = net_amount + tax_amount", name="ck_invoices_total_conservation"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND invoice_number IS NULL AND issued_at IS NULL) OR "
            "(status IN ('issued', 'void') AND invoice_number IS NOT NULL "
            "AND issued_at IS NOT NULL)",
            name="ck_invoices_issuance_state",
        ),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["issuer_profile_id"], ["invoice_issuer_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("commercial_terms_id", name="uq_invoices_commercial_terms"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_number"),
    )
    op.create_index("ix_invoices_campaign_id", "invoices", ["campaign_id"])
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])
    op.execute(
        """
        CREATE FUNCTION protect_issued_invoice() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' OR OLD.issued_at IS NOT NULL THEN
            RAISE EXCEPTION 'issued invoice is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER invoices_issued_immutable BEFORE UPDATE OR DELETE ON invoices "
        "FOR EACH ROW EXECUTE FUNCTION protect_issued_invoice()"
    )
    op.execute(
        "CREATE TRIGGER invoice_issuer_profiles_append_only BEFORE UPDATE OR DELETE ON "
        "invoice_issuer_profiles FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM invoices) "
            "OR EXISTS (SELECT 1 FROM invoice_issuer_profiles) "
            "OR EXISTS (SELECT 1 FROM invoice_number_sequences)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0035 downgrade blocked: invoice authority exists")
    op.execute("DROP TRIGGER invoice_issuer_profiles_append_only ON invoice_issuer_profiles")
    op.execute("DROP TRIGGER invoices_issued_immutable ON invoices")
    op.execute("DROP FUNCTION protect_issued_invoice()")
    op.drop_index("ix_invoices_organization_id", table_name="invoices")
    op.drop_index("ix_invoices_campaign_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("invoice_number_sequences")
    op.drop_table("invoice_issuer_profiles")
