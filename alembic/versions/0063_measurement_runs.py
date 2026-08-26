"""Add immutable measurement runs and proof bindings.

Revision ID: 0063_measurement_runs
Revises: 0062_data_subject_requests
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0063_measurement_runs"
down_revision: str | Sequence[str] | None = "0062_data_subject_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "measurement_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("test_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("formula_version", sa.String(64), nullable=False),
        sa.Column("method_revision", sa.String(255), nullable=False),
        sa.Column("roi_method_revision", sa.String(255), nullable=True),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("input_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("result_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("result_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("proof_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("proof_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("report_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("report_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("reissue_of_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('performance_only', 'roi_enabled')",
            name="ck_measurement_runs_mode",
        ),
        sa.CheckConstraint("period_start_at < period_end_at", name="ck_measurement_runs_period"),
        sa.CheckConstraint(
            "(mode = 'performance_only' AND roi_method_revision IS NULL) OR "
            "(mode = 'roi_enabled' AND roi_method_revision IS NOT NULL "
            "AND length(trim(roi_method_revision)) > 0)",
            name="ck_measurement_runs_roi_method",
        ),
        sa.CheckConstraint(
            "length(input_manifest_sha256) = 64 "
            "AND length(result_manifest_sha256) = 64 "
            "AND length(proof_manifest_sha256) = 64 "
            "AND length(report_snapshot_sha256) = 64 "
            "AND length(request_fingerprint) = 64",
            name="ck_measurement_runs_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reissue_of_run_id"], ["measurement_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "created_by_user_id",
            "client_request_id",
            name="uq_measurement_runs_actor_request",
        ),
    )
    op.create_index(
        "ix_measurement_runs_campaign_period",
        "measurement_runs",
        ["campaign_id", "period_start_at", "period_end_at", "created_at"],
    )
    op.create_index(
        "ix_measurement_runs_organization",
        "measurement_runs",
        ["organization_id", "created_at"],
    )
    op.create_index("ix_measurement_runs_reissue", "measurement_runs", ["reissue_of_run_id"])
    op.create_table(
        "measurement_run_proof_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("measurement_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activation_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creative_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "installation_evidence_submission_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("activation_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("binding_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(activation_snapshot_sha256) = 64 AND length(binding_fingerprint) = 64",
            name="ck_measurement_run_proof_binding_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["measurement_run_id"], ["measurement_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["activation_event_id"], ["campaign_activation_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["creative_id"], ["campaign_creatives.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["installation_evidence_submission_id"],
            ["installation_evidence_submissions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measurement_run_id",
            "assignment_id",
            name="uq_measurement_run_proof_assignment",
        ),
    )
    op.create_index(
        "ix_measurement_run_proof_activation",
        "measurement_run_proof_bindings",
        ["activation_event_id"],
    )
    op.create_index(
        "ix_measurement_run_proof_creative",
        "measurement_run_proof_bindings",
        ["creative_id"],
    )
    op.create_index(
        "ix_measurement_run_proof_evidence",
        "measurement_run_proof_bindings",
        ["installation_evidence_submission_id"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_measurement_evidence_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'measurement evidence is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER measurement_runs_immutable BEFORE UPDATE OR DELETE ON "
        "measurement_runs FOR EACH ROW EXECUTE FUNCTION reject_measurement_evidence_mutation()"
    )
    op.execute(
        "CREATE TRIGGER measurement_run_proof_bindings_immutable BEFORE UPDATE OR DELETE ON "
        "measurement_run_proof_bindings FOR EACH ROW "
        "EXECUTE FUNCTION reject_measurement_evidence_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM measurement_runs) OR "
                "EXISTS (SELECT 1 FROM measurement_run_proof_bindings)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0063 downgrade blocked: immutable measurement evidence exists")
    op.execute(
        "DROP TRIGGER measurement_run_proof_bindings_immutable ON measurement_run_proof_bindings"
    )
    op.execute("DROP TRIGGER measurement_runs_immutable ON measurement_runs")
    op.execute("DROP FUNCTION reject_measurement_evidence_mutation()")
    op.drop_table("measurement_run_proof_bindings")
    op.drop_index("ix_measurement_runs_reissue", table_name="measurement_runs")
    op.drop_index("ix_measurement_runs_organization", table_name="measurement_runs")
    op.drop_index("ix_measurement_runs_campaign_period", table_name="measurement_runs")
    op.drop_table("measurement_runs")
