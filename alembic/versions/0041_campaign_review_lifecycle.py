"""Add governed campaign submission and review evidence.

Revision ID: 0041_campaign_review_lifecycle
Revises: 0040_budget_policy_blocked_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0041_campaign_review_lifecycle"
down_revision: str | Sequence[str] | None = "0040_budget_policy_blocked_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CAMPAIGN_STATUSES = (
    "'draft', 'pending_review', 'approved', 'rejected', 'scheduled', "
    "'active', 'paused', 'completed', 'cancelled'"
)


def upgrade() -> None:
    op.drop_constraint("ck_campaigns_status", "campaigns", type_="check")
    op.create_check_constraint(
        "ck_campaigns_status",
        "campaigns",
        f"status IN ({CAMPAIGN_STATUSES})",
    )
    op.create_table(
        "campaign_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prior_status", sa.String(32), nullable=False),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_snapshot", sa.JSON(), nullable=True),
        sa.Column("reviewed_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("submission_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"prior_status IN ({CAMPAIGN_STATUSES})",
            name="ck_campaign_review_events_prior_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('pending_review', 'approved', 'rejected')",
            name="ck_campaign_review_events_new_status",
        ),
        sa.CheckConstraint(
            "(new_status = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0) OR "
            "(new_status != 'rejected' AND rejection_reason IS NULL)",
            name="ck_campaign_review_events_rejection_reason",
        ),
        sa.CheckConstraint(
            "(new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL "
            "AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR "
            "(new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL "
            "AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL)",
            name="ck_campaign_review_events_submission_binding",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["submission_event_id"], ["campaign_review_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_review_events_campaign_id", "campaign_review_events", ["campaign_id"]
    )
    op.create_index(
        "ix_campaign_review_events_actor_user_id", "campaign_review_events", ["actor_user_id"]
    )
    op.create_index(
        "ix_campaign_review_events_submission_event_id",
        "campaign_review_events",
        ["submission_event_id"],
    )
    op.execute(
        "CREATE TRIGGER campaign_review_events_append_only "
        "BEFORE UPDATE OR DELETE ON campaign_review_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM campaign_review_events) OR EXISTS "
                "(SELECT 1 FROM campaigns WHERE status IN "
                "('pending_review', 'approved', 'rejected'))"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0041 downgrade blocked: campaign review authority exists")

    op.execute("DROP TRIGGER campaign_review_events_append_only ON campaign_review_events")
    op.drop_index(
        "ix_campaign_review_events_submission_event_id", table_name="campaign_review_events"
    )
    op.drop_index("ix_campaign_review_events_actor_user_id", table_name="campaign_review_events")
    op.drop_index("ix_campaign_review_events_campaign_id", table_name="campaign_review_events")
    op.drop_table("campaign_review_events")
    op.drop_constraint("ck_campaigns_status", "campaigns", type_="check")
    op.create_check_constraint(
        "ck_campaigns_status",
        "campaigns",
        "status IN ('draft', 'scheduled', 'active', 'paused', 'completed', 'cancelled')",
    )
