"""Add append-only governed exposure-segment materializations."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0065_exposure_segments"
down_revision: str | Sequence[str] | None = "0064_budget_notifications_recovery"
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
        "exposure_segments",
        _uuid("id"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("facts_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_link_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("measurement_input_sha256", sa.String(64), nullable=False),
        sa.Column("measurement_result_sha256", sa.String(64), nullable=False),
        sa.Column("measurement_proof_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("releasable_cell_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_cell_count", sa.Integer(), nullable=False),
        sa.Column("reissue_of_segment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_exposure_segments_version"),
        sa.CheckConstraint(
            "releasable_cell_count >= 0 AND suppressed_cell_count >= 0",
            name="ck_exposure_segments_cell_counts",
        ),
        sa.CheckConstraint(
            "length(facts_fingerprint) = 64 "
            "AND length(snapshot_sha256) = 64 "
            "AND length(source_link_snapshot_sha256) = 64 "
            "AND length(measurement_input_sha256) = 64 "
            "AND length(measurement_result_sha256) = 64 "
            "AND length(measurement_proof_sha256) = 64",
            name="ck_exposure_segments_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["zone_id"], ["campaign_zones.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["retargeting_sources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_link_id"], ["retargeting_source_links.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["measurement_run_id"], ["measurement_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reissue_of_segment_id"], ["exposure_segments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_link_id", "version", name="uq_exposure_segments_link_version"
        ),
        sa.UniqueConstraint(
            "source_link_id",
            "facts_fingerprint",
            name="uq_exposure_segments_link_facts",
        ),
    )
    op.create_index(
        "ix_exposure_segments_scope",
        "exposure_segments",
        ["organization_id", "campaign_id", "zone_id", "created_at"],
    )
    op.create_index(
        "ix_exposure_segments_reissue", "exposure_segments", ["reissue_of_segment_id"]
    )
    op.create_table(
        "exposure_segment_cells",
        _uuid("id"),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coverage_cell", sa.String(64), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", sa.String(32), nullable=False),
        sa.Column("distinct_vehicle_count", sa.Integer(), nullable=False),
        sa.Column("trip_count", sa.Integer(), nullable=False),
        sa.Column("modelled_potential_contacts", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "distinct_vehicle_count >= 0 AND trip_count >= 0 "
            "AND modelled_potential_contacts >= 0",
            name="ck_exposure_segment_cells_counts",
        ),
        sa.CheckConstraint(
            "window_start_at < window_end_at", name="ck_exposure_segment_cells_window"
        ),
        sa.CheckConstraint(
            "context = 'vehicle_transit'", name="ck_exposure_segment_cells_context"
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["exposure_segments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "segment_id",
            "coverage_cell",
            "window_start_at",
            "window_end_at",
            "context",
            name="uq_exposure_segment_cells_identity",
        ),
    )
    op.create_index(
        "ix_exposure_segment_cells_segment",
        "exposure_segment_cells",
        ["segment_id", "coverage_cell"],
    )
    op.execute(
        "CREATE FUNCTION reject_exposure_segment_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'exposure segment evidence is append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    for table in ("exposure_segments", "exposure_segment_cells"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_exposure_segment_mutation()"
        )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM exposure_segments) OR "
                "EXISTS (SELECT 1 FROM exposure_segment_cells)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0065 downgrade blocked: immutable exposure segments exist")
    op.execute("DROP TRIGGER exposure_segment_cells_immutable ON exposure_segment_cells")
    op.execute("DROP TRIGGER exposure_segments_immutable ON exposure_segments")
    op.execute("DROP FUNCTION reject_exposure_segment_mutation()")
    op.drop_index("ix_exposure_segment_cells_segment", table_name="exposure_segment_cells")
    op.drop_table("exposure_segment_cells")
    op.drop_index("ix_exposure_segments_reissue", table_name="exposure_segments")
    op.drop_index("ix_exposure_segments_scope", table_name="exposure_segments")
    op.drop_table("exposure_segments")
