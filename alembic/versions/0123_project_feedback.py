"""Notes from the test-version feedback button (REQ-336/D172)."""

import sqlalchemy as sa

from alembic import op

revision = "0123_project_feedback"
down_revision = "0122_receipt_non_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_feedback_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("page_path", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitter_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("screenshot", sa.LargeBinary(), nullable=True),
        sa.Column("screenshot_width", sa.Integer(), nullable=True),
        sa.Column("screenshot_height", sa.Integer(), nullable=True),
        sa.Column("pin_x", sa.Float(), nullable=True),
        sa.Column("pin_y", sa.Float(), nullable=True),
        sa.CheckConstraint("status IN ('opened', 'resolved')", name="ck_project_feedback_status"),
        sa.CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)",
            name="ck_project_feedback_resolved_at",
        ),
        sa.CheckConstraint(
            "(screenshot IS NULL AND screenshot_width IS NULL AND screenshot_height IS NULL "
            "AND pin_x IS NULL AND pin_y IS NULL) OR (screenshot IS NOT NULL "
            "AND screenshot_width BETWEEN 1 AND 4000 AND screenshot_height BETWEEN 1 AND 4000 "
            "AND pin_x BETWEEN 0 AND 1 AND pin_y BETWEEN 0 AND 1)",
            name="ck_project_feedback_screenshot",
        ),
    )
    op.create_index(
        "ix_project_feedback_status_created",
        "project_feedback_items",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_feedback_status_created", table_name="project_feedback_items")
    op.drop_table("project_feedback_items")
