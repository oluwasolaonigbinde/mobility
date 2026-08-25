"""Add immutable retargeting source-to-campaign target-zone links."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0047_retargeting_source_links"
down_revision: str | Sequence[str] | None = "0046_retargeting_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "retargeting_source_links",
        _uuid("id"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("campaign_fingerprint", sa.String(64), nullable=False),
        sa.Column("zone_fingerprint", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active', 'removed')", name="ck_retargeting_source_links_status"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["retargeting_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["zone_id"], ["campaign_zones.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_retargeting_source_links_source_created",
        "retargeting_source_links",
        ["source_id", "created_at"],
    )
    op.create_index(
        "uq_retargeting_source_links_active_identity",
        "retargeting_source_links",
        ["source_id", "campaign_id", "zone_id", "start_at", "end_at"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "retargeting_source_link_events",
        _uuid("id"),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'removed')",
            name="ck_retargeting_source_link_events_event_type",
        ),
        sa.ForeignKeyConstraint(["link_id"], ["retargeting_source_links.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "link_id", "sequence_number", name="uq_retargeting_source_link_events_sequence"
        ),
    )
    op.create_table(
        "retargeting_source_link_idempotency",
        _uuid("id"),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["link_id"], ["retargeting_source_links.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_retargeting_source_link_idempotency_actor_operation_key",
        ),
    )
    op.execute(
        "CREATE FUNCTION prevent_retargeting_source_link_event_mutation() "
        "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
        "'retargeting_source_link_events are append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_retargeting_source_link_events_append_only "
        "BEFORE UPDATE OR DELETE ON retargeting_source_link_events FOR EACH ROW "
        "EXECUTE FUNCTION prevent_retargeting_source_link_event_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM retargeting_source_links LIMIT 1) "
                "OR EXISTS (SELECT 1 FROM retargeting_source_link_events LIMIT 1) "
                "OR EXISTS (SELECT 1 FROM retargeting_source_link_idempotency LIMIT 1)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("Refusing to drop populated retargeting source-link authority")
    op.execute(
        "DROP TRIGGER trg_retargeting_source_link_events_append_only "
        "ON retargeting_source_link_events"
    )
    op.execute("DROP FUNCTION prevent_retargeting_source_link_event_mutation()")
    op.drop_table("retargeting_source_link_idempotency")
    op.drop_table("retargeting_source_link_events")
    op.drop_index(
        "uq_retargeting_source_links_active_identity", table_name="retargeting_source_links"
    )
    op.drop_index(
        "ix_retargeting_source_links_source_created", table_name="retargeting_source_links"
    )
    op.drop_table("retargeting_source_links")
