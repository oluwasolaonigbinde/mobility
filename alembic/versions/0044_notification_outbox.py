"""Add the shared notification outbox, read state, and advertiser preference.

Revision ID: 0044_notification_outbox
Revises: 0043_campaign_review_lifecycle
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0044_notification_outbox"
down_revision: str | Sequence[str] | None = "0043_campaign_review_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_TYPES = (
    "'fraud_hold_raised', 'fraud_review_resolved', 'fraud_dispute_replied'"
)


def _fingerprint(row: Mapping[str, Any]) -> str:
    document = {
        "recipient_user_id": str(row["recipient_user_id"]),
        "type_key": row["type_key"],
        "template_version": row["template_version"],
        "channel": row["channel"],
        "payload": row["payload"],
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def upgrade() -> None:
    op.drop_constraint("ck_notifications_type_key", "notifications", type_="check")
    op.drop_constraint("ck_notifications_template_version", "notifications", type_="check")
    op.drop_constraint("uq_notifications_dedupe_key", "notifications", type_="unique")
    op.alter_column("notifications", "dedupe_key", existing_type=sa.String(255), nullable=True)

    op.add_column("notifications", sa.Column("channel", sa.String(32), nullable=True))
    op.add_column("notifications", sa.Column("status", sa.String(32), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "notifications", sa.Column("provider_message_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("dedupe_fingerprint", sa.String(64), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE notifications SET channel = 'in_app', status = 'sent', sent_at = created_at"
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, recipient_user_id, type_key, template_version, channel, payload "
            "FROM notifications ORDER BY id"
        )
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE notifications SET dedupe_fingerprint = :fingerprint WHERE id = :id"
            ),
            {"id": row["id"], "fingerprint": _fingerprint(row)},
        )

    op.alter_column(
        "notifications",
        "channel",
        existing_type=sa.String(32),
        server_default=sa.text("'in_app'"),
        nullable=False,
    )
    op.alter_column(
        "notifications",
        "status",
        existing_type=sa.String(32),
        server_default=sa.text("'pending'"),
        nullable=False,
    )
    op.alter_column(
        "notifications",
        "dedupe_fingerprint",
        existing_type=sa.String(64),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_notifications_type_key", "notifications", "length(trim(type_key)) > 0"
    )
    op.create_check_constraint(
        "ck_notifications_template_version",
        "notifications",
        "length(trim(template_version)) > 0",
    )
    op.create_check_constraint(
        "ck_notifications_channel",
        "notifications",
        "channel IN ('in_app', 'transactional_email')",
    )
    op.create_check_constraint(
        "ck_notifications_status",
        "notifications",
        "status IN ('pending', 'sent', 'delivered', 'failed')",
    )
    op.create_check_constraint(
        "ck_notifications_attempt_count", "notifications", "attempt_count >= 0"
    )
    op.create_unique_constraint(
        "uq_notifications_recipient_channel_dedupe_key",
        "notifications",
        ["recipient_user_id", "channel", "dedupe_key"],
    )
    op.create_unique_constraint(
        "uq_notifications_provider_message_id",
        "notifications",
        ["provider_message_id"],
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ["recipient_user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    op.create_table(
        "advertiser_organization_notification_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "advertiser_organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "transactional_email_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["advertiser_organization_id"],
            ["advertiser_organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "advertiser_organization_id",
            name="uq_advertiser_org_notification_preferences_organization",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION reject_notification_evidence_mutation() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'notification evidence is append-only';
          END IF;
          IF NEW.recipient_user_id IS DISTINCT FROM OLD.recipient_user_id
             OR NEW.type_key IS DISTINCT FROM OLD.type_key
             OR NEW.template_version IS DISTINCT FROM OLD.template_version
             OR NEW.channel IS DISTINCT FROM OLD.channel
             OR NEW.payload IS DISTINCT FROM OLD.payload
             OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key
             OR NEW.dedupe_fingerprint IS DISTINCT FROM OLD.dedupe_fingerprint
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'notification evidence fields are immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER notifications_evidence_immutable BEFORE UPDATE OR DELETE ON "
        "notifications FOR EACH ROW EXECUTE FUNCTION reject_notification_evidence_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM advertiser_organization_notification_preferences) "
                "OR EXISTS (SELECT 1 FROM notifications WHERE dedupe_key IS NULL "
                "OR channel <> 'in_app' OR status <> 'sent' OR attempt_count <> 0 "
                "OR provider_message_id IS NOT NULL OR sent_at IS DISTINCT FROM created_at "
                "OR delivered_at IS NOT NULL OR read_at IS NOT NULL "
                f"OR type_key NOT IN ({LEGACY_TYPES}) OR template_version <> 'v1')"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0044 downgrade blocked: notification outbox authority exists")

    op.execute("DROP TRIGGER notifications_evidence_immutable ON notifications")
    op.execute("DROP FUNCTION reject_notification_evidence_mutation()")
    op.drop_table("advertiser_organization_notification_preferences")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_constraint(
        "uq_notifications_recipient_channel_dedupe_key", "notifications", type_="unique"
    )
    op.drop_constraint(
        "uq_notifications_provider_message_id", "notifications", type_="unique"
    )
    op.drop_constraint("ck_notifications_attempt_count", "notifications", type_="check")
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.drop_constraint("ck_notifications_channel", "notifications", type_="check")
    op.drop_constraint("ck_notifications_template_version", "notifications", type_="check")
    op.drop_constraint("ck_notifications_type_key", "notifications", type_="check")
    for column in (
        "read_at",
        "delivered_at",
        "sent_at",
        "dedupe_fingerprint",
        "provider_message_id",
        "attempt_count",
        "status",
        "channel",
    ):
        op.drop_column("notifications", column)
    op.alter_column(
        "notifications", "dedupe_key", existing_type=sa.String(255), nullable=False
    )
    op.create_check_constraint(
        "ck_notifications_type_key",
        "notifications",
        f"type_key IN ({LEGACY_TYPES})",
    )
    op.create_check_constraint(
        "ck_notifications_template_version", "notifications", "template_version = 'v1'"
    )
    op.create_unique_constraint(
        "uq_notifications_dedupe_key", "notifications", ["dedupe_key"]
    )
