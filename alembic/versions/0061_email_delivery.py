"""Add provider-neutral email delivery claims and signed receipts.

Revision ID: 0061_email_delivery
Revises: 0060_evidence_verifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0061_email_delivery"
down_revision: str | Sequence[str] | None = "0060_evidence_verifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "notifications",
        sa.Column("delivery_claim_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("delivery_claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications", sa.Column("last_error_code", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_notifications_email_dispatch",
        "notifications",
        ["status", "next_attempt_at", "delivery_claim_expires_at"],
        postgresql_where=sa.text("channel = 'transactional_email'"),
    )
    op.create_table(
        "notification_delivery_receipts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("signing_key_id", sa.String(64), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('delivered', 'failed')",
            name="ck_notification_delivery_receipts_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", name="uq_notification_receipts_notification"
        ),
        sa.UniqueConstraint(
            "provider_event_id", name="uq_notification_receipts_provider_event"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_notification_delivery_receipt_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'notification delivery receipts are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER notification_delivery_receipts_immutable BEFORE UPDATE OR DELETE ON "
        "notification_delivery_receipts FOR EACH ROW EXECUTE FUNCTION "
        "reject_notification_delivery_receipt_mutation()"
    )


def downgrade() -> None:
    populated = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notification_delivery_receipts) OR EXISTS ("
            "SELECT 1 FROM notifications WHERE next_attempt_at IS NOT NULL "
            "OR delivery_claim_token IS NOT NULL OR delivery_claim_expires_at IS NOT NULL "
            "OR last_error_code IS NOT NULL)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0061 downgrade blocked: email delivery authority exists")
    op.execute(
        "DROP TRIGGER notification_delivery_receipts_immutable ON "
        "notification_delivery_receipts"
    )
    op.execute("DROP FUNCTION reject_notification_delivery_receipt_mutation()")
    op.drop_table("notification_delivery_receipts")
    op.drop_index("ix_notifications_email_dispatch", table_name="notifications")
    op.drop_column("notifications", "last_error_code")
    op.drop_column("notifications", "delivery_claim_expires_at")
    op.drop_column("notifications", "delivery_claim_token")
    op.drop_column("notifications", "next_attempt_at")
