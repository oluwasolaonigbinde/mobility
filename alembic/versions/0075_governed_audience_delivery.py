"""Add governed audience aggregates and immutable delivery approvals."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0075_governed_audience_delivery"
down_revision: str | Sequence[str] | None = "0074_trip_evidence_manifest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exposure_segments", sa.Column("aggregate_formula_version", sa.String(64))
    )
    op.add_column(
        "exposure_segments", sa.Column("aggregate_authority_sha256", sa.String(64))
    )
    op.add_column(
        "exposure_segments", sa.Column("disclosure_policy_sha256", sa.String(64))
    )
    op.add_column(
        "exposure_segments",
        sa.Column(
            "synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_exposure_segments_governance",
        "exposure_segments",
        "(aggregate_formula_version IS NULL "
        "AND aggregate_authority_sha256 IS NULL "
        "AND disclosure_policy_sha256 IS NULL) OR "
        "(aggregate_formula_version IS NOT NULL "
        "AND aggregate_authority_sha256 IS NOT NULL "
        "AND disclosure_policy_sha256 IS NOT NULL "
        "AND length(trim(aggregate_formula_version)) > 0 "
        "AND length(aggregate_authority_sha256) = 64 "
        "AND length(disclosure_policy_sha256) = 64)",
    )
    op.add_column("exposure_segment_cells", sa.Column("resolution_m", sa.Integer()))
    op.add_column(
        "exposure_segment_cells", sa.Column("distinct_day_count", sa.Integer())
    )
    op.add_column(
        "exposure_segment_cells", sa.Column("max_contributor_share", sa.Numeric(8, 7))
    )
    op.create_check_constraint(
        "ck_exposure_segment_cells_governance",
        "exposure_segment_cells",
        "(resolution_m IS NULL AND distinct_day_count IS NULL "
        "AND max_contributor_share IS NULL) OR "
        "(resolution_m IS NOT NULL AND distinct_day_count IS NOT NULL "
        "AND max_contributor_share IS NOT NULL "
        "AND resolution_m >= 50 AND distinct_day_count >= 0 "
        "AND max_contributor_share >= 0 AND max_contributor_share <= 1)",
    )

    op.create_table(
        "audience_delivery_approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("purpose_code", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_account_reference", sa.String(255)),
        sa.Column("budget_ceiling", sa.Numeric(20, 2)),
        sa.Column("legal_approval_reference", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column(
            "synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('csv_export', 'ad_platform_activation')",
            name="ck_audience_delivery_approvals_operation",
        ),
        sa.CheckConstraint(
            "valid_from < valid_until",
            name="ck_audience_delivery_approvals_window",
        ),
        sa.CheckConstraint(
            "(operation = 'csv_export' "
            "AND purpose_code = 'aggregate_campaign_planning' "
            "AND provider = 'controlled-csv-v1' "
            "AND provider_account_reference IS NULL AND budget_ceiling IS NULL) OR "
            "(operation = 'ad_platform_activation' "
            "AND purpose_code = 'aggregate_contextual_activation' "
            "AND provider_account_reference IS NOT NULL AND budget_ceiling >= 0)",
            name="ck_audience_delivery_approvals_operation_fields",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64 AND length(snapshot_sha256) = 64",
            name="ck_audience_delivery_approvals_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["exposure_segments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "approved_by_user_id",
            "idempotency_key",
            name="uq_audience_delivery_approvals_actor_key",
        ),
    )
    op.create_index(
        "ix_audience_delivery_approvals_scope",
        "audience_delivery_approvals",
        [
            "organization_id",
            "campaign_id",
            "segment_id",
            "operation",
            "valid_until",
        ],
    )
    op.execute(
        "CREATE FUNCTION reject_audience_delivery_approval_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'audience delivery approvals are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER audience_delivery_approvals_immutable BEFORE UPDATE OR DELETE ON "
        "audience_delivery_approvals FOR EACH ROW EXECUTE FUNCTION "
        "reject_audience_delivery_approval_mutation()"
    )

    op.add_column(
        "audience_deliveries",
        sa.Column("approval_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "audience_deliveries", sa.Column("approval_snapshot_sha256", sa.String(64))
    )
    op.add_column("audience_deliveries", sa.Column("purpose_code", sa.String(64)))
    op.create_foreign_key(
        "fk_audience_deliveries_approval_id",
        "audience_deliveries",
        "audience_delivery_approvals",
        ["approval_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_audience_deliveries_approval_cluster",
        "audience_deliveries",
        "(approval_id IS NULL AND approval_snapshot_sha256 IS NULL "
        "AND purpose_code IS NULL) OR "
        "(approval_id IS NOT NULL AND approval_snapshot_sha256 IS NOT NULL "
        "AND purpose_code IS NOT NULL "
        "AND length(approval_snapshot_sha256) = 64 "
        "AND length(trim(purpose_code)) > 0)",
    )



def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM audience_delivery_approvals) OR EXISTS "
                "(SELECT 1 FROM exposure_segments WHERE aggregate_authority_sha256 IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0075 downgrade blocked: governed audience evidence exists")
    op.drop_constraint(
        "ck_audience_deliveries_approval_cluster",
        "audience_deliveries",
        type_="check",
    )
    op.drop_constraint(
        "fk_audience_deliveries_approval_id", "audience_deliveries", type_="foreignkey"
    )
    op.drop_column("audience_deliveries", "purpose_code")
    op.drop_column("audience_deliveries", "approval_snapshot_sha256")
    op.drop_column("audience_deliveries", "approval_id")
    op.execute(
        "DROP TRIGGER audience_delivery_approvals_immutable "
        "ON audience_delivery_approvals"
    )
    op.execute("DROP FUNCTION reject_audience_delivery_approval_mutation()")
    op.drop_index(
        "ix_audience_delivery_approvals_scope",
        table_name="audience_delivery_approvals",
    )
    op.drop_table("audience_delivery_approvals")
    op.drop_constraint(
        "ck_exposure_segment_cells_governance",
        "exposure_segment_cells",
        type_="check",
    )
    op.drop_column("exposure_segment_cells", "max_contributor_share")
    op.drop_column("exposure_segment_cells", "distinct_day_count")
    op.drop_column("exposure_segment_cells", "resolution_m")
    op.drop_constraint(
        "ck_exposure_segments_governance", "exposure_segments", type_="check"
    )
    op.drop_column("exposure_segments", "synthetic")
    op.drop_column("exposure_segments", "disclosure_policy_sha256")
    op.drop_column("exposure_segments", "aggregate_authority_sha256")
    op.drop_column("exposure_segments", "aggregate_formula_version")
