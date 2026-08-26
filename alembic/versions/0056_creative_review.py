"""Add immutable managed-creative review authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056_creative_review"
down_revision: str | Sequence[str] | None = "0055_kyc_key_custody"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CREATIVE_STATUSES = (
    "status IN ('draft', 'pending_review', 'approved', 'rejected', 'ready', 'archived')"
)


def upgrade() -> None:
    with op.batch_alter_table("campaign_creatives") as batch:
        batch.drop_constraint("ck_campaign_creatives_status", type_="check")
        batch.create_check_constraint("ck_campaign_creatives_status", CREATIVE_STATUSES)
    op.create_table(
        "creative_review_events",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("creative_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("prior_status", sa.String(32), nullable=False),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_snapshot", sa.JSON(), nullable=True),
        sa.Column("reviewed_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("submission_event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "prior_status IN ('draft', 'pending_review', 'approved', 'rejected', "
            "'ready', 'archived')",
            name="ck_creative_review_events_prior_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('pending_review', 'approved', 'rejected')",
            name="ck_creative_review_events_new_status",
        ),
        sa.CheckConstraint(
            "(new_status = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0) OR "
            "(new_status != 'rejected' AND rejection_reason IS NULL)",
            name="ck_creative_review_events_rejection_reason",
        ),
        sa.CheckConstraint(
            "(new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL "
            "AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR "
            "(new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL "
            "AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL)",
            name="ck_creative_review_events_submission_binding",
        ),
        sa.ForeignKeyConstraint(
            ["creative_id"],
            ["campaign_creatives.id"],
            ondelete="RESTRICT",
            name="fk_creative_review_events_creative",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_creative_review_events_actor",
        ),
        sa.ForeignKeyConstraint(
            ["submission_event_id"],
            ["creative_review_events.id"],
            ondelete="RESTRICT",
            name="fk_creative_review_events_submission",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_review_events_creative_id", "creative_review_events", ["creative_id"]
    )
    op.create_index(
        "ix_creative_review_events_actor_user_id",
        "creative_review_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_creative_review_events_submission_event_id",
        "creative_review_events",
        ["submission_event_id"],
    )
    op.execute(
        "CREATE TRIGGER creative_review_events_append_only "
        "BEFORE UPDATE OR DELETE ON creative_review_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    event_count = bind.scalar(sa.text("SELECT count(*) FROM creative_review_events"))
    review_status_count = bind.scalar(
        sa.text(
            "SELECT count(*) FROM campaign_creatives "
            "WHERE status IN ('pending_review', 'approved', 'rejected')"
        )
    )
    if event_count or review_status_count:
        raise RuntimeError(
            "Cannot downgrade 0056 while creative review authority is populated"
        )
    op.execute("DROP TRIGGER creative_review_events_append_only ON creative_review_events")
    op.drop_index(
        "ix_creative_review_events_submission_event_id", table_name="creative_review_events"
    )
    op.drop_index(
        "ix_creative_review_events_actor_user_id", table_name="creative_review_events"
    )
    op.drop_index("ix_creative_review_events_creative_id", table_name="creative_review_events")
    op.drop_table("creative_review_events")
    with op.batch_alter_table("campaign_creatives") as batch:
        batch.drop_constraint("ck_campaign_creatives_status", type_="check")
        batch.create_check_constraint(
            "ck_campaign_creatives_status", "status IN ('draft', 'ready', 'archived')"
        )
