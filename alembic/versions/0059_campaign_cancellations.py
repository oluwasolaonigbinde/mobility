"""Add immutable campaign cancellation cutoff and settlement authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_campaign_cancellations"
down_revision: str | Sequence[str] | None = "0058_campaign_changes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_cancellations",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("prior_status", sa.String(32), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("commercial_terms_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("production_start_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("funding_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refund_eligibility_ends_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("disposition", sa.String(40), nullable=False),
        sa.Column("refundable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("released_liability_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cancelled_assignment_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "prior_status IN ('approved', 'scheduled', 'active', 'paused')",
            name="ck_campaign_cancellations_prior_status",
        ),
        sa.CheckConstraint(
            "disposition IN ('cash_refund_due', 'cash_refund_not_due', "
            "'credit_settlement_due', 'no_settlement')",
            name="ck_campaign_cancellations_disposition",
        ),
        sa.CheckConstraint(
            "length(currency) = 3 AND refundable_amount >= 0 "
            "AND released_liability_amount >= 0",
            name="ck_campaign_cancellations_amounts",
        ),
        sa.CheckConstraint(
            "(disposition = 'cash_refund_due' AND commercial_terms_id IS NOT NULL "
            "AND funding_authorized_at IS NOT NULL "
            "AND refund_eligibility_ends_at IS NOT NULL "
            "AND cutoff_at < refund_eligibility_ends_at AND refundable_amount > 0) OR "
            "(disposition <> 'cash_refund_due' AND refundable_amount = 0)",
            name="ck_campaign_cancellations_settlement_evidence",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["production_start_id"], ["production_starts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_campaign_cancellations_campaign"),
    )
    op.create_index(
        "ix_campaign_cancellations_campaign_id", "campaign_cancellations", ["campaign_id"]
    )
    op.create_table(
        "campaign_cancellation_settlement_revisions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cancellation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_campaign_cancellation_settlement_revisions_number",
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name="ck_campaign_cancellation_settlement_revisions_digest",
        ),
        sa.ForeignKeyConstraint(
            ["cancellation_id"], ["campaign_cancellations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cancellation_id",
            "revision_number",
            name="uq_campaign_cancellation_settlement_revisions_number",
        ),
    )
    op.create_index(
        "ix_campaign_cancellation_settlement_revisions_cancellation_id",
        "campaign_cancellation_settlement_revisions",
        ["cancellation_id"],
    )
    op.create_index(
        "ix_campaign_cancellation_settlement_revisions_campaign_id",
        "campaign_cancellation_settlement_revisions",
        ["campaign_id"],
    )
    for table in (
        "campaign_cancellations",
        "campaign_cancellation_settlement_revisions",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
        )

    op.execute(
        "DROP TRIGGER campaign_liability_reservations_transition "
        "ON campaign_liability_reservations"
    )
    op.execute("DROP FUNCTION enforce_liability_reservation_transition()")
    op.drop_constraint(
        "ck_campaign_liability_reservations_state",
        "campaign_liability_reservations",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_liability_reservations_status",
        "campaign_liability_reservations",
        type_="check",
    )
    op.add_column(
        "campaign_liability_reservations",
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_liability_reservations",
        sa.Column("release_cancellation_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_campaign_liability_reservations_release_cancellation_id",
        "campaign_liability_reservations",
        "campaign_cancellations",
        ["release_cancellation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_campaign_liability_reservations_status",
        "campaign_liability_reservations",
        "status IN ('pending_funding', 'reserved', 'released')",
    )
    op.create_check_constraint(
        "ck_campaign_liability_reservations_state",
        "campaign_liability_reservations",
        "(status = 'pending_funding' AND authorization_id IS NULL "
        "AND reserved_amount IS NULL AND reserved_at IS NULL "
        "AND released_at IS NULL AND release_cancellation_id IS NULL) OR "
        "(status = 'reserved' AND authorization_id IS NOT NULL "
        "AND reserved_amount = requested_amount AND reserved_at IS NOT NULL "
        "AND released_at IS NULL AND release_cancellation_id IS NULL) OR "
        "(status = 'released' AND released_at IS NOT NULL "
        "AND release_cancellation_id IS NOT NULL AND ((authorization_id IS NULL "
        "AND reserved_amount IS NULL AND reserved_at IS NULL) OR "
        "(authorization_id IS NOT NULL AND reserved_amount = requested_amount "
        "AND reserved_at IS NOT NULL)))",
    )
    op.execute(
        """
        CREATE FUNCTION enforce_liability_reservation_transition() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'liability reservation is durable';
          END IF;
          IF OLD.status = 'released' THEN
            RAISE EXCEPTION 'released liability is immutable';
          END IF;
          IF OLD.id IS DISTINCT FROM NEW.id
             OR OLD.campaign_id IS DISTINCT FROM NEW.campaign_id
             OR OLD.assignment_id IS DISTINCT FROM NEW.assignment_id
             OR OLD.assignment_rule_binding_id IS DISTINCT FROM NEW.assignment_rule_binding_id
             OR OLD.covered_vehicle_days IS DISTINCT FROM NEW.covered_vehicle_days
             OR OLD.hourly_rate IS DISTINCT FROM NEW.hourly_rate
             OR OLD.daily_hours_cap IS DISTINCT FROM NEW.daily_hours_cap
             OR OLD.requested_amount IS DISTINCT FROM NEW.requested_amount
             OR OLD.requested_at IS DISTINCT FROM NEW.requested_at
             OR OLD.formula_version IS DISTINCT FROM NEW.formula_version THEN
            RAISE EXCEPTION 'invalid liability reservation transition';
          END IF;
          IF OLD.status = 'pending_funding' AND NEW.status = 'reserved'
             AND NEW.authorization_id IS NOT NULL
             AND NEW.reserved_amount = NEW.requested_amount
             AND NEW.reserved_at IS NOT NULL
             AND NEW.released_at IS NULL
             AND NEW.release_cancellation_id IS NULL THEN
            RETURN NEW;
          END IF;
          IF OLD.status IN ('pending_funding', 'reserved') AND NEW.status = 'released'
             AND NEW.authorization_id IS NOT DISTINCT FROM OLD.authorization_id
             AND NEW.reserved_amount IS NOT DISTINCT FROM OLD.reserved_amount
             AND NEW.reserved_at IS NOT DISTINCT FROM OLD.reserved_at
             AND NEW.released_at IS NOT NULL
             AND NEW.release_cancellation_id IS NOT NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'invalid liability reservation transition';
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
    populated = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM campaign_cancellations) OR "
            "EXISTS (SELECT 1 FROM campaign_cancellation_settlement_revisions) OR "
            "EXISTS (SELECT 1 FROM campaign_liability_reservations "
            "WHERE status = 'released')"
        )
    )
    if populated:
        raise RuntimeError("Cannot downgrade 0059 while campaign cancellations are populated")

    op.execute(
        "DROP TRIGGER campaign_liability_reservations_transition "
        "ON campaign_liability_reservations"
    )
    op.execute("DROP FUNCTION enforce_liability_reservation_transition()")
    op.drop_constraint(
        "ck_campaign_liability_reservations_state",
        "campaign_liability_reservations",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_liability_reservations_status",
        "campaign_liability_reservations",
        type_="check",
    )
    op.drop_constraint(
        "fk_campaign_liability_reservations_release_cancellation_id",
        "campaign_liability_reservations",
        type_="foreignkey",
    )
    op.drop_column("campaign_liability_reservations", "release_cancellation_id")
    op.drop_column("campaign_liability_reservations", "released_at")
    op.create_check_constraint(
        "ck_campaign_liability_reservations_status",
        "campaign_liability_reservations",
        "status IN ('pending_funding', 'reserved')",
    )
    op.create_check_constraint(
        "ck_campaign_liability_reservations_state",
        "campaign_liability_reservations",
        "(status = 'pending_funding' AND authorization_id IS NULL "
        "AND reserved_amount IS NULL AND reserved_at IS NULL) OR "
        "(status = 'reserved' AND authorization_id IS NOT NULL "
        "AND reserved_amount = requested_amount AND reserved_at IS NOT NULL)",
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

    for table in (
        "campaign_cancellation_settlement_revisions",
        "campaign_cancellations",
    ):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.drop_index(
        "ix_campaign_cancellation_settlement_revisions_campaign_id",
        table_name="campaign_cancellation_settlement_revisions",
    )
    op.drop_index(
        "ix_campaign_cancellation_settlement_revisions_cancellation_id",
        table_name="campaign_cancellation_settlement_revisions",
    )
    op.drop_table("campaign_cancellation_settlement_revisions")
    op.drop_index(
        "ix_campaign_cancellations_campaign_id", table_name="campaign_cancellations"
    )
    op.drop_table("campaign_cancellations")
