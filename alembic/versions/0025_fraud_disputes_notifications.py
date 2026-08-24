"""Add driver fraud disputes and sanitized notification foundation.

Revision ID: 0025_fraud_disputes_notifications
Revises: 0024_fraud_review_holds
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025_fraud_disputes_notifications"
down_revision: str | Sequence[str] | None = "0024_fraud_review_holds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fraud_disputes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("fraud_flag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        sa.Column("replied_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('open', 'replied')", name="ck_fraud_disputes_status"),
        sa.CheckConstraint(
            "length(trim(message)) BETWEEN 1 AND 2000", name="ck_fraud_disputes_message"
        ),
        sa.CheckConstraint(
            "(status = 'open' AND replied_by_user_id IS NULL "
            "AND replied_at IS NULL AND reply_text IS NULL) OR "
            "(status = 'replied' AND replied_by_user_id IS NOT NULL AND replied_at IS NOT NULL "
            "AND reply_text IS NOT NULL AND length(trim(reply_text)) BETWEEN 1 AND 2000)",
            name="ck_fraud_disputes_reply_evidence",
        ),
        sa.ForeignKeyConstraint(["fraud_flag_id"], ["fraud_flags.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replied_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fraud_flag_id", name="uq_fraud_disputes_fraud_flag_id"),
    )
    op.create_index("ix_fraud_disputes_driver_profile_id", "fraud_disputes", ["driver_profile_id"])
    op.create_index("ix_fraud_disputes_status", "fraud_disputes", ["status"])
    op.create_index("ix_fraud_disputes_created_at", "fraud_disputes", ["created_at"])
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type_key", sa.String(length=64), nullable=False),
        sa.Column(
            "template_version", sa.String(length=16), server_default=sa.text("'v1'"), nullable=False
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "type_key IN ('fraud_hold_raised', 'fraud_review_resolved', 'fraud_dispute_replied')",
            name="ck_notifications_type_key",
        ),
        sa.CheckConstraint("template_version = 'v1'", name="ck_notifications_template_version"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_notifications_dedupe_key"),
    )
    op.create_index(
        "ix_notifications_recipient_created", "notifications", ["recipient_user_id", "created_at"]
    )
    op.create_index("ix_notifications_type_key", "notifications", ["type_key"])


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM fraud_disputes) OR EXISTS (SELECT 1 FROM notifications) THEN
            RAISE EXCEPTION '0025 downgrade blocked: disputes or notifications are authoritative';
          END IF;
        END $$
        """
    )
    op.drop_index("ix_notifications_type_key", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_fraud_disputes_created_at", table_name="fraud_disputes")
    op.drop_index("ix_fraud_disputes_status", table_name="fraud_disputes")
    op.drop_index("ix_fraud_disputes_driver_profile_id", table_name="fraud_disputes")
    op.drop_table("fraud_disputes")
