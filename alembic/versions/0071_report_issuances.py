"""Add bounded campaign report issuance and immutable artifact authority.

Revision ID: 0071_report_issuances
Revises: 0070_driver_vehicle_approval
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0071_report_issuances"
down_revision: str | Sequence[str] | None = "0070_driver_vehicle_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_stored_files_purpose", "stored_files", type_="check")
    op.drop_constraint("ck_stored_files_scope", "stored_files", type_="check")
    op.alter_column("stored_files", "upload_intent_id", nullable=True)
    op.create_check_constraint(
        "ck_stored_files_purpose",
        "stored_files",
        "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', "
        "'installation_evidence', 'report_export')",
    )
    op.create_check_constraint(
        "ck_stored_files_scope",
        "stored_files",
        "(purpose IN ('creative', 'report_export') AND organization_id IS NOT NULL "
        "AND subject_user_id IS NULL) OR "
        "(purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') "
        "AND organization_id IS NULL AND subject_user_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_stored_files_generated_source",
        "stored_files",
        "(purpose = 'report_export' AND upload_intent_id IS NULL) OR "
        "(purpose <> 'report_export' AND upload_intent_id IS NOT NULL)",
    )

    op.create_table(
        "report_issuances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("reissue_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("authority_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("result_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("proof_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("report_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("renderer_version", sa.String(64), nullable=False),
        sa.Column("method_revision", sa.String(255), nullable=False),
        sa.Column("roi_decision", sa.String(16), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("worker_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processing_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_report_issuances_version_positive"),
        sa.CheckConstraint("worker_attempts >= 0", name="ck_report_issuances_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')",
            name="ck_report_issuances_status",
        ),
        sa.CheckConstraint(
            "roi_decision IN ('OMIT', 'INCLUDE')",
            name="ck_report_issuances_roi_decision",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64 AND length(snapshot_sha256) = 64 "
            "AND length(authority_fingerprint) = 64 "
            "AND length(input_manifest_sha256) = 64 "
            "AND length(result_manifest_sha256) = 64 "
            "AND length(proof_manifest_sha256) = 64 "
            "AND length(report_snapshot_sha256) = 64",
            name="ck_report_issuances_fingerprints",
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND processing_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND ready_at IS NULL) OR "
            "(status = 'ready' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NOT NULL "
            "AND last_error_code IS NULL) OR "
            "(status = 'failed' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NULL "
            "AND last_error_code IS NOT NULL) OR "
            "(status = 'queued' AND processing_token IS NULL "
            "AND lease_expires_at IS NULL AND ready_at IS NULL)",
            name="ck_report_issuances_status_fields",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["measurement_run_id"], ["measurement_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reissue_of_id"], ["report_issuances.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "requested_by_user_id",
            "client_request_id",
            name="uq_report_issuances_actor_request",
        ),
        sa.UniqueConstraint(
            "measurement_run_id", "version", name="uq_report_issuances_run_version"
        ),
    )
    op.create_index(
        "uq_report_issuances_initial_run",
        "report_issuances",
        ["measurement_run_id"],
        unique=True,
        postgresql_where=sa.text("reissue_of_id IS NULL"),
    )
    op.create_index(
        "ix_report_issuances_due",
        "report_issuances",
        ["status", "next_attempt_at", "lease_expires_at", "created_at"],
    )
    op.create_index(
        "ix_report_issuances_scope",
        "report_issuances",
        ["organization_id", "campaign_id", "created_at"],
    )

    op.create_table(
        "report_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_issuance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stored_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("renderer_version", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("format IN ('csv', 'pdf')", name="ck_report_artifacts_format"),
        sa.CheckConstraint("size_bytes > 0", name="ck_report_artifacts_size_positive"),
        sa.CheckConstraint("length(checksum_sha256) = 64", name="ck_report_artifacts_sha256"),
        sa.ForeignKeyConstraint(
            ["report_issuance_id"], ["report_issuances.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_issuance_id", "format", name="uq_report_artifacts_issuance_format"
        ),
        sa.UniqueConstraint("stored_file_id", name="uq_report_artifacts_stored_file"),
    )
    op.create_index(
        "ix_report_artifacts_issuance",
        "report_artifacts",
        ["report_issuance_id", "created_at"],
    )
    op.execute(
        "CREATE FUNCTION reject_report_issuance_frozen_mutation() RETURNS trigger AS $$ "
        "BEGIN IF ROW(NEW.organization_id, NEW.campaign_id, NEW.measurement_run_id, "
        "NEW.requested_by_user_id, NEW.client_request_id, NEW.request_fingerprint, "
        "NEW.reissue_of_id, NEW.version, NEW.snapshot, NEW.snapshot_sha256, "
        "NEW.authority_fingerprint, NEW.input_manifest_sha256, NEW.result_manifest_sha256, "
        "NEW.proof_manifest_sha256, NEW.report_snapshot_sha256, NEW.schema_version, "
        "NEW.renderer_version, NEW.method_revision, NEW.roi_decision, NEW.synthetic, "
        "NEW.created_at) IS DISTINCT FROM ROW(OLD.organization_id, OLD.campaign_id, "
        "OLD.measurement_run_id, OLD.requested_by_user_id, OLD.client_request_id, "
        "OLD.request_fingerprint, OLD.reissue_of_id, OLD.version, OLD.snapshot, "
        "OLD.snapshot_sha256, OLD.authority_fingerprint, OLD.input_manifest_sha256, "
        "OLD.result_manifest_sha256, OLD.proof_manifest_sha256, OLD.report_snapshot_sha256, "
        "OLD.schema_version, OLD.renderer_version, OLD.method_revision, OLD.roi_decision, "
        "OLD.synthetic, OLD.created_at) THEN RAISE EXCEPTION "
        "'report issuance frozen authority is immutable'; END IF; RETURN NEW; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_issuances_frozen_immutable BEFORE UPDATE ON report_issuances "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_issuance_frozen_mutation()"
    )
    op.execute(
        "CREATE FUNCTION reject_report_issuance_delete() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'report issuances are append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_issuances_no_delete BEFORE DELETE ON report_issuances "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_issuance_delete()"
    )
    op.execute(
        "CREATE FUNCTION reject_report_artifact_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'report artifacts are immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_artifacts_immutable BEFORE UPDATE OR DELETE ON report_artifacts "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_artifact_mutation()"
    )
    op.execute(
        "CREATE FUNCTION reject_report_artifact_file_mutation() RETURNS trigger AS $$ "
        "BEGIN IF EXISTS (SELECT 1 FROM report_artifacts "
        "WHERE stored_file_id = OLD.id) THEN RAISE EXCEPTION "
        "'report artifact stored file is immutable'; END IF; "
        "IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER report_artifact_files_immutable BEFORE UPDATE OR DELETE ON stored_files "
        "FOR EACH ROW EXECUTE FUNCTION reject_report_artifact_file_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM report_issuances) OR EXISTS "
                "(SELECT 1 FROM stored_files WHERE purpose = 'report_export')"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0071 downgrade blocked: issued report evidence exists")
    op.execute("DROP TRIGGER report_artifact_files_immutable ON stored_files")
    op.execute("DROP FUNCTION reject_report_artifact_file_mutation()")
    op.execute("DROP TRIGGER report_artifacts_immutable ON report_artifacts")
    op.execute("DROP FUNCTION reject_report_artifact_mutation()")
    op.execute("DROP TRIGGER report_issuances_no_delete ON report_issuances")
    op.execute("DROP FUNCTION reject_report_issuance_delete()")
    op.execute("DROP TRIGGER report_issuances_frozen_immutable ON report_issuances")
    op.execute("DROP FUNCTION reject_report_issuance_frozen_mutation()")
    op.drop_index("ix_report_artifacts_issuance", table_name="report_artifacts")
    op.drop_table("report_artifacts")
    op.drop_index("ix_report_issuances_scope", table_name="report_issuances")
    op.drop_index("ix_report_issuances_due", table_name="report_issuances")
    op.drop_index("uq_report_issuances_initial_run", table_name="report_issuances")
    op.drop_table("report_issuances")
    op.drop_constraint("ck_stored_files_generated_source", "stored_files", type_="check")
    op.drop_constraint("ck_stored_files_scope", "stored_files", type_="check")
    op.drop_constraint("ck_stored_files_purpose", "stored_files", type_="check")
    op.alter_column("stored_files", "upload_intent_id", nullable=False)
    op.create_check_constraint(
        "ck_stored_files_scope",
        "stored_files",
        "(purpose = 'creative' AND organization_id IS NOT NULL "
        "AND subject_user_id IS NULL) OR "
        "(purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') "
        "AND organization_id IS NULL AND subject_user_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_stored_files_purpose",
        "stored_files",
        "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', 'installation_evidence')",
    )
