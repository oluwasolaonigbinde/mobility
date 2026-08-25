"""Add typed, append-only retargeting planning sources.

Revision ID: 0046_retargeting_sources
Revises: 0045_disclosure_query_history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0046_retargeting_sources"
down_revision: str | Sequence[str] | None = "0045_disclosure_query_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retargeting_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source_type IN ("
            "'website-traffic', 'digital-campaign-audience', 'CRM-upload-reference', "
            "'UTM-source', 'manual-insight')",
            name="ck_retargeting_sources_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deactivated')", name="ck_retargeting_sources_status"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_retargeting_sources_organization_created",
        "retargeting_sources",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "retargeting_source_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'deactivated')",
            name="ck_retargeting_source_events_event_type",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["retargeting_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "sequence_number", name="uq_retargeting_source_events_sequence"
        ),
    )
    op.create_index(
        "ix_retargeting_source_events_source_created",
        "retargeting_source_events",
        ["source_id", "created_at"],
    )
    op.create_table(
        "retargeting_source_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["retargeting_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_retargeting_source_idempotency_actor_operation_key",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION prevent_retargeting_source_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'retargeting_source_events are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_retargeting_source_events_append_only
        BEFORE UPDATE OR DELETE ON retargeting_source_events
        FOR EACH ROW EXECUTE FUNCTION prevent_retargeting_source_event_mutation();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM retargeting_sources LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM retargeting_source_events LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM retargeting_source_idempotency LIMIT 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "Refusing to drop populated retargeting source authority; "
            "history must be retained or explicitly migrated"
        )
    op.execute(
        "DROP TRIGGER trg_retargeting_source_events_append_only ON retargeting_source_events"
    )
    op.execute("DROP FUNCTION prevent_retargeting_source_event_mutation()")
    op.drop_table("retargeting_source_idempotency")
    op.drop_index(
        "ix_retargeting_source_events_source_created", table_name="retargeting_source_events"
    )
    op.drop_table("retargeting_source_events")
    op.drop_index("ix_retargeting_sources_organization_created", table_name="retargeting_sources")
    op.drop_table("retargeting_sources")
