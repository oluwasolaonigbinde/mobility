"""Add immutable aggregate export and activation delivery receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0066_audience_deliveries"
down_revision: str | Sequence[str] | None = "0065_exposure_segments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audience_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("adapter_name", sa.String(64), nullable=False),
        sa.Column(
            "synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("status", sa.String(16), server_default="completed", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('csv_export', 'ad_platform_activation')",
            name="ck_audience_deliveries_operation",
        ),
        sa.CheckConstraint(
            "status = 'completed'", name="ck_audience_deliveries_status"
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64 AND length(payload_sha256) = 64 "
            "AND length(result_sha256) = 64",
            name="ck_audience_deliveries_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["exposure_segments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_audience_deliveries_actor_operation_key",
        ),
    )
    op.create_index(
        "ix_audience_deliveries_scope",
        "audience_deliveries",
        ["organization_id", "campaign_id", "segment_id", "created_at"],
    )
    op.execute(
        "CREATE FUNCTION reject_audience_delivery_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'audience delivery receipts are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER audience_deliveries_immutable BEFORE UPDATE OR DELETE ON "
        "audience_deliveries FOR EACH ROW EXECUTE FUNCTION "
        "reject_audience_delivery_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM audience_deliveries)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0066 downgrade blocked: immutable audience deliveries exist")
    op.execute("DROP TRIGGER audience_deliveries_immutable ON audience_deliveries")
    op.execute("DROP FUNCTION reject_audience_delivery_mutation()")
    op.drop_index("ix_audience_deliveries_scope", table_name="audience_deliveries")
    op.drop_table("audience_deliveries")
