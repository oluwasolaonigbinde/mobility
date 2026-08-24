"""Add versioned commercial quotations and immutable accepted terms.

Revision ID: 0032_commercial_quotation_terms
Revises: 0031_carry_forward_payout_debt
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032_commercial_quotation_terms"
down_revision: str | Sequence[str] | None = "0031_carry_forward_payout_debt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_column(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "commercial_quote_requests",
        _uuid_column("id"),
        _uuid_column("campaign_id"),
        _uuid_column("organization_id"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "request_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _uuid_column("requested_by_user_id"),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source IN ('in_platform', 'external_recorded')",
            name="ck_commercial_quote_requests_source",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_commercial_quote_requests_campaign"),
    )
    op.create_index(
        "ix_commercial_quote_requests_campaign_id", "commercial_quote_requests", ["campaign_id"]
    )
    op.create_index(
        "ix_commercial_quote_requests_organization_id",
        "commercial_quote_requests",
        ["organization_id"],
    )

    op.create_table(
        "commercial_quotation_revisions",
        _uuid_column("id"),
        _uuid_column("quote_request_id"),
        _uuid_column("campaign_id"),
        _uuid_column("organization_id"),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("quote_reference", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("line_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("production_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("production_cost_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_class", sa.String(40), nullable=False),
        sa.Column(
            "payment_terms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "standard_production_wait_hours",
            sa.Integer(),
            server_default=sa.text("24"),
            nullable=False,
        ),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(7, 6), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        _uuid_column("created_by_user_id"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision_number > 0", name="ck_commercial_quote_revision_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_commercial_quote_currency"),
        sa.CheckConstraint(
            "payment_class IN ('standard_prepaid', 'approved_corporate_credit')",
            name="ck_commercial_quote_payment_class",
        ),
        sa.CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 AND tax_amount >= 0 "
            "AND gross_amount >= 0 AND production_cost_amount >= 0",
            name="ck_commercial_quote_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "gross_amount = net_amount + tax_amount", name="ck_commercial_quote_total_conservation"
        ),
        sa.CheckConstraint(
            "standard_production_wait_hours = 24", name="ck_commercial_quote_standard_wait"
        ),
        sa.ForeignKeyConstraint(
            ["quote_request_id"], ["commercial_quote_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quote_request_id", "revision_number", name="uq_commercial_quote_request_revision"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "quote_reference",
            "revision_number",
            name="uq_commercial_quote_reference_revision",
        ),
    )
    op.create_index(
        "ix_commercial_quotation_revisions_campaign_id",
        "commercial_quotation_revisions",
        ["campaign_id"],
    )

    op.create_table(
        "commercial_terms",
        _uuid_column("id"),
        _uuid_column("campaign_id"),
        _uuid_column("organization_id"),
        _uuid_column("quotation_revision_id"),
        sa.Column("quote_reference", sa.String(128), nullable=False),
        sa.Column("quotation_revision_number", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("line_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("production_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("production_cost_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_class", sa.String(40), nullable=False),
        sa.Column("payment_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("standard_production_wait_hours", sa.Integer(), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(7, 6), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("acceptance_method", sa.String(32), nullable=False),
        _uuid_column("accepted_by_user_id", nullable=True),
        _uuid_column("recorded_by_user_id"),
        sa.Column("external_acceptance_reference", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "acceptance_method IN ('in_platform', 'external_recorded')",
            name="ck_commercial_terms_acceptance_method",
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_commercial_terms_currency"),
        sa.CheckConstraint(
            "payment_class IN ('standard_prepaid', 'approved_corporate_credit')",
            name="ck_commercial_terms_payment_class",
        ),
        sa.CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 AND tax_amount >= 0 "
            "AND gross_amount >= 0 AND production_cost_amount >= 0",
            name="ck_commercial_terms_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "gross_amount = net_amount + tax_amount", name="ck_commercial_terms_total_conservation"
        ),
        sa.CheckConstraint(
            "standard_production_wait_hours = 24", name="ck_commercial_terms_standard_wait"
        ),
        sa.CheckConstraint(
            "(acceptance_method = 'in_platform' AND accepted_by_user_id IS NOT NULL "
            "AND external_acceptance_reference IS NULL) OR "
            "(acceptance_method = 'external_recorded' AND accepted_by_user_id IS NULL "
            "AND external_acceptance_reference IS NOT NULL)",
            name="ck_commercial_terms_acceptance_evidence",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["quotation_revision_id"], ["commercial_quotation_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_commercial_terms_campaign"),
        sa.UniqueConstraint("quotation_revision_id", name="uq_commercial_terms_quote_revision"),
    )
    op.create_index("ix_commercial_terms_campaign_id", "commercial_terms", ["campaign_id"])

    op.execute(
        """
        CREATE FUNCTION reject_commercial_authority_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'commercial quotation authority is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER commercial_quotation_revisions_append_only
          BEFORE UPDATE OR DELETE ON commercial_quotation_revisions
          FOR EACH ROW EXECUTE FUNCTION reject_commercial_authority_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER commercial_terms_append_only
          BEFORE UPDATE OR DELETE ON commercial_terms
          FOR EACH ROW EXECUTE FUNCTION reject_commercial_authority_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM commercial_quote_requests) "
            "OR EXISTS (SELECT 1 FROM commercial_quotation_revisions) "
            "OR EXISTS (SELECT 1 FROM commercial_terms)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0032 downgrade blocked: commercial quotation authority exists")
    op.execute("DROP TRIGGER commercial_terms_append_only ON commercial_terms")
    op.execute(
        "DROP TRIGGER commercial_quotation_revisions_append_only ON commercial_quotation_revisions"
    )
    op.execute("DROP FUNCTION reject_commercial_authority_mutation()")
    op.drop_index("ix_commercial_terms_campaign_id", table_name="commercial_terms")
    op.drop_table("commercial_terms")
    op.drop_index(
        "ix_commercial_quotation_revisions_campaign_id", table_name="commercial_quotation_revisions"
    )
    op.drop_table("commercial_quotation_revisions")
    op.drop_index(
        "ix_commercial_quote_requests_organization_id", table_name="commercial_quote_requests"
    )
    op.drop_index(
        "ix_commercial_quote_requests_campaign_id", table_name="commercial_quote_requests"
    )
    op.drop_table("commercial_quote_requests")
