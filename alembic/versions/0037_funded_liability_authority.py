"""Add funded liability and production-start authority.

Revision ID: 0037_funded_liability_authority
Revises: 0036_invoice_authority_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037_funded_liability_authority"
down_revision: str | Sequence[str] | None = "0036_invoice_authority_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "campaign_financial_authorizations",
        _uuid("id"),
        _uuid("campaign_id"),
        _uuid("commercial_terms_id"),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("authority_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("authorized_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("funded_cash_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("max_driver_liability", sa.Numeric(14, 2), nullable=False),
        sa.Column("credit_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("credit_due_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("credit_approved_by_user_id", nullable=True),
        sa.Column("credit_terms", sa.JSON(), nullable=True),
        sa.Column("subsidy_reference", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        _uuid("created_by_user_id"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0", name="ck_campaign_financial_authorizations_revision"
        ),
        sa.CheckConstraint(
            "authority_type IN ('prepaid_cash', 'approved_credit', 'subsidy')",
            name="ck_campaign_financial_authorizations_type",
        ),
        sa.CheckConstraint(
            "length(currency) = 3", name="ck_campaign_financial_authorizations_currency"
        ),
        sa.CheckConstraint(
            "authorized_amount > 0 AND max_driver_liability > 0 "
            "AND max_driver_liability <= authorized_amount",
            name="ck_campaign_financial_authorizations_amounts",
        ),
        sa.CheckConstraint(
            "(authority_type = 'prepaid_cash' AND funded_cash_amount = authorized_amount "
            "AND credit_limit IS NULL AND credit_due_at IS NULL AND "
            "credit_approved_by_user_id IS NULL AND credit_terms IS NULL "
            "AND subsidy_reference IS NULL) OR "
            "(authority_type = 'approved_credit' AND funded_cash_amount = 0 "
            "AND credit_limit = authorized_amount AND credit_due_at IS NOT NULL AND "
            "credit_approved_by_user_id IS NOT NULL AND credit_terms IS NOT NULL "
            "AND subsidy_reference IS NULL) OR "
            "(authority_type = 'subsidy' AND funded_cash_amount = 0 "
            "AND credit_limit IS NULL AND credit_due_at IS NULL AND "
            "credit_approved_by_user_id IS NULL AND credit_terms IS NULL "
            "AND subsidy_reference IS NOT NULL)",
            name="ck_campaign_financial_authorizations_evidence",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["credit_approved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "revision_number", name="uq_campaign_financial_authorization_revision"
        ),
    )
    op.create_index(
        "ix_campaign_financial_authorizations_campaign_id",
        "campaign_financial_authorizations",
        ["campaign_id"],
    )
    op.create_table(
        "financial_authorization_allocations",
        _uuid("id"),
        _uuid("authorization_id"),
        _uuid("receipt_allocation_id"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_financial_authorization_allocations_amount"),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["campaign_financial_authorizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["receipt_allocation_id"], ["receipt_allocations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_id",
            "receipt_allocation_id",
            name="uq_financial_authorization_allocation_source",
        ),
    )
    op.create_table(
        "campaign_liability_reservations",
        _uuid("id"),
        _uuid("campaign_id"),
        _uuid("assignment_id"),
        _uuid("assignment_rule_binding_id"),
        _uuid("authorization_id", nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("covered_vehicle_days", sa.Integer(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(14, 2), nullable=False),
        sa.Column("daily_hours_cap", sa.Numeric(4, 2), nullable=False),
        sa.Column("requested_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reserved_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("formula_version", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_funding', 'reserved')",
            name="ck_campaign_liability_reservations_status",
        ),
        sa.CheckConstraint(
            "covered_vehicle_days > 0 AND hourly_rate >= 0 AND daily_hours_cap > 0 "
            "AND requested_amount > 0 AND formula_version <> ''",
            name="ck_campaign_liability_reservations_formula",
        ),
        sa.CheckConstraint(
            "(status = 'pending_funding' AND authorization_id IS NULL "
            "AND reserved_amount IS NULL AND reserved_at IS NULL) OR "
            "(status = 'reserved' AND authorization_id IS NOT NULL "
            "AND reserved_amount = requested_amount AND reserved_at IS NOT NULL)",
            name="ck_campaign_liability_reservations_state",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_rule_binding_id"], ["assignment_rule_bindings.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["campaign_financial_authorizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", name="uq_campaign_liability_reservations_assignment"),
    )
    op.create_index(
        "ix_campaign_liability_reservations_campaign_id",
        "campaign_liability_reservations",
        ["campaign_id"],
    )
    op.create_table(
        "expedited_production_waivers",
        _uuid("id"),
        _uuid("campaign_id"),
        _uuid("commercial_terms_id"),
        _uuid("requested_by_user_id"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        _uuid("accepted_by_user_id"),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wording_version", sa.String(128), nullable=False),
        sa.Column("accepted_wording_hash", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "accepted_at >= requested_at", name="ck_expedited_production_waivers_timeline"
        ),
        sa.CheckConstraint(
            "length(accepted_wording_hash) = 64 AND wording_version <> ''",
            name="ck_expedited_production_waivers_wording",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_expedited_production_waivers_campaign"),
    )
    op.create_table(
        "production_starts",
        _uuid("id"),
        _uuid("campaign_id"),
        _uuid("authorization_id"),
        sa.Column("authority_basis", sa.String(40), nullable=False),
        _uuid("waiver_id", nullable=True),
        sa.Column("fully_funded_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("started_by_user_id"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "authority_basis IN ('standard_window_elapsed', "
            "'advertiser_expedited_waiver', 'approved_credit')",
            name="ck_production_starts_authority_basis",
        ),
        sa.CheckConstraint(
            "(authority_basis = 'advertiser_expedited_waiver' AND waiver_id IS NOT NULL) OR "
            "(authority_basis <> 'advertiser_expedited_waiver' AND waiver_id IS NULL)",
            name="ck_production_starts_waiver_basis",
        ),
        sa.CheckConstraint(
            "(authority_basis IN ('standard_window_elapsed', 'advertiser_expedited_waiver') "
            "AND fully_funded_at IS NOT NULL) OR "
            "(authority_basis = 'approved_credit' AND fully_funded_at IS NULL)",
            name="ck_production_starts_funding_basis",
        ),
        sa.CheckConstraint(
            "fully_funded_at IS NULL OR started_at >= fully_funded_at",
            name="ck_production_starts_timeline",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["campaign_financial_authorizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["waiver_id"], ["expedited_production_waivers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_production_starts_campaign"),
    )

    for table in (
        "campaign_financial_authorizations",
        "financial_authorization_allocations",
        "expedited_production_waivers",
        "production_starts",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION enforce_liability_reservation_transition() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'liability reservation is durable';
          END IF;
          IF OLD.status = 'reserved' THEN
            RAISE EXCEPTION 'reserved liability is immutable';
          END IF;
          IF NOT (
            OLD.status = 'pending_funding' AND NEW.status = 'reserved'
            AND OLD.id = NEW.id AND OLD.campaign_id = NEW.campaign_id
            AND OLD.assignment_id = NEW.assignment_id
            AND OLD.assignment_rule_binding_id = NEW.assignment_rule_binding_id
            AND OLD.covered_vehicle_days = NEW.covered_vehicle_days
            AND OLD.hourly_rate = NEW.hourly_rate
            AND OLD.daily_hours_cap = NEW.daily_hours_cap
            AND OLD.requested_amount = NEW.requested_amount
            AND OLD.requested_at = NEW.requested_at
            AND OLD.formula_version = NEW.formula_version
          ) THEN
            RAISE EXCEPTION 'invalid liability reservation transition';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER campaign_liability_reservations_transition "
        "BEFORE UPDATE OR DELETE ON campaign_liability_reservations "
        "FOR EACH ROW EXECUTE FUNCTION enforce_liability_reservation_transition()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM campaign_financial_authorizations) "
            "OR EXISTS (SELECT 1 FROM financial_authorization_allocations) "
            "OR EXISTS (SELECT 1 FROM campaign_liability_reservations) "
            "OR EXISTS (SELECT 1 FROM expedited_production_waivers) "
            "OR EXISTS (SELECT 1 FROM production_starts)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0037 downgrade blocked: funded liability authority exists")
    op.execute(
        "DROP TRIGGER campaign_liability_reservations_transition ON campaign_liability_reservations"
    )
    op.execute("DROP FUNCTION enforce_liability_reservation_transition()")
    for table in (
        "production_starts",
        "expedited_production_waivers",
        "financial_authorization_allocations",
        "campaign_financial_authorizations",
    ):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.drop_table("production_starts")
    op.drop_table("expedited_production_waivers")
    op.drop_index(
        "ix_campaign_liability_reservations_campaign_id",
        table_name="campaign_liability_reservations",
    )
    op.drop_table("campaign_liability_reservations")
    op.drop_table("financial_authorization_allocations")
    op.drop_index(
        "ix_campaign_financial_authorizations_campaign_id",
        table_name="campaign_financial_authorizations",
    )
    op.drop_table("campaign_financial_authorizations")
