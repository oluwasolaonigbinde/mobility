"""Add governed effective-dated campaign changes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_campaign_changes"
down_revision: str | Sequence[str] | None = "0057_installation_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_change_requests",
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
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("classifications", sa.JSON(), nullable=False),
        sa.Column("impact_preview", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_liability_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reserved_liability_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("authorization_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_admin', 'pending_funding', 'applied', 'rejected')",
            name="ck_campaign_change_requests_status",
        ),
        sa.CheckConstraint(
            "requested_liability_amount >= 0 AND "
            "(reserved_liability_amount IS NULL OR reserved_liability_amount >= 0)",
            name="ck_campaign_change_requests_liability",
        ),
        sa.CheckConstraint(
            "(status = 'applied' AND applied_at IS NOT NULL "
            "AND reserved_liability_amount IS NOT NULL) OR "
            "(status <> 'applied' AND applied_at IS NULL)",
            name="ck_campaign_change_requests_applied_state",
        ),
        sa.CheckConstraint(
            "(reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND review_reason IS NULL) OR "
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND review_reason IS NOT NULL AND length(trim(review_reason)) > 0)",
            name="ck_campaign_change_requests_review_state",
        ),
        sa.CheckConstraint(
            "(status = 'rejected' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL) OR status <> 'rejected'",
            name="ck_campaign_change_requests_rejected_state",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["campaign_financial_authorizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "requested_by_user_id",
            "client_request_id",
            name="uq_campaign_change_requests_retry",
        ),
    )
    op.create_index(
        "ix_campaign_change_requests_campaign_id",
        "campaign_change_requests",
        ["campaign_id"],
    )
    op.create_index(
        "ix_campaign_change_requests_status_created",
        "campaign_change_requests",
        ["status", "created_at"],
    )
    op.execute(
        "CREATE FUNCTION guard_campaign_change_request_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'campaign change request is append-only'; "
        "END IF; IF NEW.id IS DISTINCT FROM OLD.id OR "
        "NEW.campaign_id IS DISTINCT FROM OLD.campaign_id OR "
        "NEW.organization_id IS DISTINCT FROM OLD.organization_id OR "
        "NEW.requested_by_user_id IS DISTINCT FROM OLD.requested_by_user_id OR "
        "NEW.client_request_id IS DISTINCT FROM OLD.client_request_id OR "
        "NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR "
        "NEW.proposed_changes::jsonb IS DISTINCT FROM OLD.proposed_changes::jsonb OR "
        "NEW.classifications::jsonb IS DISTINCT FROM OLD.classifications::jsonb OR "
        "NEW.impact_preview::jsonb IS DISTINCT FROM OLD.impact_preview::jsonb OR "
        "NEW.requested_liability_amount IS DISTINCT FROM OLD.requested_liability_amount OR "
        "NEW.created_at IS DISTINCT FROM OLD.created_at "
        "THEN RAISE EXCEPTION 'campaign change request is append-only'; END IF; "
        "IF OLD.reviewed_by_user_id IS NOT NULL AND ("
        "NEW.reviewed_by_user_id IS DISTINCT FROM OLD.reviewed_by_user_id OR "
        "NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at OR "
        "NEW.review_reason IS DISTINCT FROM OLD.review_reason) "
        "THEN RAISE EXCEPTION 'campaign change review evidence is immutable'; END IF; "
        "IF OLD.status IN ('applied', 'rejected') OR NOT ("
        "(OLD.status = 'pending_admin' AND NEW.status IN "
        "('pending_admin', 'pending_funding', 'applied', 'rejected')) OR "
        "(OLD.status = 'pending_funding' AND NEW.status IN "
        "('pending_funding', 'applied', 'rejected'))) "
        "THEN RAISE EXCEPTION 'campaign change transition is invalid'; END IF; "
        "RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER campaign_change_request_guard "
        "BEFORE UPDATE OR DELETE ON campaign_change_requests "
        "FOR EACH ROW EXECUTE FUNCTION guard_campaign_change_request_mutation()"
    )

    op.create_table(
        "campaign_change_revisions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("applied_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number > 0", name="ck_campaign_change_revisions_number"
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name="ck_campaign_change_revisions_digest",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["campaign_change_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["applied_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_campaign_change_revisions_request"),
        sa.UniqueConstraint(
            "campaign_id",
            "revision_number",
            name="uq_campaign_change_revisions_number",
        ),
    )
    op.create_index(
        "ix_campaign_change_revisions_campaign_id",
        "campaign_change_revisions",
        ["campaign_id"],
    )
    op.create_index(
        "ix_campaign_change_revisions_campaign_effective",
        "campaign_change_revisions",
        ["campaign_id", "effective_from"],
    )
    op.execute(
        "CREATE TRIGGER campaign_change_revisions_append_only "
        "BEFORE UPDATE OR DELETE ON campaign_change_revisions "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM campaign_change_requests) OR "
            "EXISTS (SELECT 1 FROM campaign_change_revisions)"
        )
    )
    if populated:
        raise RuntimeError("Cannot downgrade 0058 while campaign changes are populated")
    op.execute(
        "DROP TRIGGER campaign_change_revisions_append_only ON campaign_change_revisions"
    )
    op.drop_index(
        "ix_campaign_change_revisions_campaign_effective",
        table_name="campaign_change_revisions",
    )
    op.drop_index(
        "ix_campaign_change_revisions_campaign_id",
        table_name="campaign_change_revisions",
    )
    op.drop_table("campaign_change_revisions")
    op.execute("DROP TRIGGER campaign_change_request_guard ON campaign_change_requests")
    op.execute("DROP FUNCTION guard_campaign_change_request_mutation()")
    op.drop_index(
        "ix_campaign_change_requests_status_created",
        table_name="campaign_change_requests",
    )
    op.drop_index(
        "ix_campaign_change_requests_campaign_id",
        table_name="campaign_change_requests",
    )
    op.drop_table("campaign_change_requests")
