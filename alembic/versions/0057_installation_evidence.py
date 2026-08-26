"""Add assignment-bound installation evidence and display proofs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_installation_evidence"
down_revision: str | Sequence[str] | None = "0056_creative_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FILE_PURPOSES = "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', 'installation_evidence')"
FILE_SCOPE = (
    "(purpose = 'creative' AND organization_id IS NOT NULL "
    "AND subject_user_id IS NULL) OR "
    "(purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') "
    "AND organization_id IS NULL AND subject_user_id IS NOT NULL)"
)


def upgrade() -> None:
    for table_name in ("file_upload_intents", "stored_files"):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(f"ck_{table_name}_purpose", type_="check")
            batch.drop_constraint(f"ck_{table_name}_scope", type_="check")
            batch.create_check_constraint(f"ck_{table_name}_purpose", FILE_PURPOSES)
            batch.create_check_constraint(f"ck_{table_name}_scope", FILE_SCOPE)

    op.create_table(
        "installation_evidence_submissions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("required_views", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_installation_evidence_status",
        ),
        sa.CheckConstraint("revision > 0", name="ck_installation_evidence_revision_positive"),
        sa.CheckConstraint(
            "(status = 'pending_review' AND reviewed_by_user_id IS NULL "
            "AND reviewed_at IS NULL AND rejection_reason IS NULL "
            "AND approved_until IS NULL) OR "
            "(status = 'approved' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NULL "
            "AND approved_until IS NOT NULL) OR "
            "(status = 'rejected' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0 AND approved_until IS NULL) OR "
            "(status = 'expired' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND rejection_reason IS NULL "
            "AND approved_until IS NOT NULL)",
            name="ck_installation_evidence_review_coherence",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "revision",
            name="uq_installation_evidence_assignment_revision",
        ),
        sa.UniqueConstraint(
            "assignment_id",
            "submitted_by_user_id",
            "client_request_id",
            name="uq_installation_evidence_request",
        ),
    )
    op.create_index(
        "uq_installation_evidence_assignment_pending",
        "installation_evidence_submissions",
        ["assignment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_review'"),
        sqlite_where=sa.text("status = 'pending_review'"),
    )
    op.create_index(
        "ix_installation_evidence_assignment_status",
        "installation_evidence_submissions",
        ["assignment_id", "status"],
    )
    op.execute(
        "CREATE FUNCTION guard_installation_evidence_submission_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'installation evidence is append-only'; "
        "END IF; IF NEW.id IS DISTINCT FROM OLD.id OR "
        "NEW.assignment_id IS DISTINCT FROM OLD.assignment_id OR "
        "NEW.campaign_id IS DISTINCT FROM OLD.campaign_id OR "
        "NEW.driver_profile_id IS DISTINCT FROM OLD.driver_profile_id OR "
        "NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR "
        "NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id OR "
        "NEW.revision IS DISTINCT FROM OLD.revision OR "
        "NEW.client_request_id IS DISTINCT FROM OLD.client_request_id OR "
        "NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR "
        "NEW.device_id IS DISTINCT FROM OLD.device_id OR "
        "NEW.captured_at IS DISTINCT FROM OLD.captured_at OR "
        "NEW.required_views IS DISTINCT FROM OLD.required_views OR "
        "NEW.metadata IS DISTINCT FROM OLD.metadata OR "
        "NEW.submitted_at IS DISTINCT FROM OLD.submitted_at "
        "THEN RAISE EXCEPTION 'installation evidence is append-only'; END IF; "
        "RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER installation_evidence_submission_guard "
        "BEFORE UPDATE OR DELETE ON installation_evidence_submissions "
        "FOR EACH ROW EXECUTE FUNCTION guard_installation_evidence_submission_mutation()"
    )

    op.create_table(
        "installation_evidence_photos",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("view_code", sa.String(64), nullable=False),
        sa.Column("stored_file_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["installation_evidence_submissions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "view_code", name="uq_installation_evidence_photo_view"
        ),
        sa.UniqueConstraint("stored_file_id", name="uq_installation_evidence_photo_file"),
    )
    op.create_index(
        "ix_installation_evidence_photos_submission",
        "installation_evidence_photos",
        ["submission_id"],
    )
    op.execute(
        "CREATE TRIGGER installation_evidence_photos_append_only "
        "BEFORE UPDATE OR DELETE ON installation_evidence_photos "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )

    op.create_table(
        "display_proof_challenges",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("nonce_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_display_proof_challenge_expiry"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_submission_id"],
            ["installation_evidence_submissions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce_sha256", name="uq_display_proof_challenge_nonce"),
    )
    op.create_index(
        "ix_display_proof_challenge_assignment",
        "display_proof_challenges",
        ["assignment_id", "created_at"],
    )
    op.execute(
        "CREATE FUNCTION guard_display_proof_challenge_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "IF TG_OP = 'DELETE' OR NEW.id IS DISTINCT FROM OLD.id OR "
        "NEW.assignment_id IS DISTINCT FROM OLD.assignment_id OR "
        "NEW.evidence_submission_id IS DISTINCT FROM OLD.evidence_submission_id OR "
        "NEW.driver_profile_id IS DISTINCT FROM OLD.driver_profile_id OR "
        "NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR "
        "NEW.device_id IS DISTINCT FROM OLD.device_id OR "
        "NEW.nonce_sha256 IS DISTINCT FROM OLD.nonce_sha256 OR "
        "NEW.expires_at IS DISTINCT FROM OLD.expires_at OR "
        "NEW.created_at IS DISTINCT FROM OLD.created_at OR "
        "OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL "
        "THEN RAISE EXCEPTION 'display proof challenge is append-only'; END IF; "
        "RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER display_proof_challenge_guard "
        "BEFORE UPDATE OR DELETE ON display_proof_challenges "
        "FOR EACH ROW EXECUTE FUNCTION guard_display_proof_challenge_mutation()"
    )

    op.create_table(
        "display_proofs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("challenge_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("stored_file_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.CheckConstraint("valid_until > verified_at", name="ck_display_proof_validity"),
        sa.ForeignKeyConstraint(
            ["challenge_id"], ["display_proof_challenges.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_submission_id"],
            ["installation_evidence_submissions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_id", name="uq_display_proofs_challenge"),
        sa.UniqueConstraint("stored_file_id", name="uq_display_proofs_file"),
    )
    op.create_index(
        "ix_display_proofs_assignment_verified",
        "display_proofs",
        ["assignment_id", "verified_at"],
    )
    op.execute(
        "CREATE TRIGGER display_proofs_append_only "
        "BEFORE UPDATE OR DELETE ON display_proofs "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )

    with op.batch_alter_table("trip_sessions") as batch:
        batch.add_column(sa.Column("display_proof_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            "fk_trip_sessions_display_proof",
            "display_proofs",
            ["display_proof_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_trip_sessions_display_proof_id", "trip_sessions", ["display_proof_id"])


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM installation_evidence_submissions) OR "
            "EXISTS (SELECT 1 FROM display_proof_challenges) OR "
            "EXISTS (SELECT 1 FROM display_proofs) OR "
            "EXISTS (SELECT 1 FROM trip_sessions WHERE display_proof_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM stored_files WHERE purpose = 'installation_evidence')"
        )
    )
    if populated:
        raise RuntimeError("Cannot downgrade 0057 while installation evidence is populated")

    op.drop_index("ix_trip_sessions_display_proof_id", table_name="trip_sessions")
    with op.batch_alter_table("trip_sessions") as batch:
        batch.drop_constraint("fk_trip_sessions_display_proof", type_="foreignkey")
        batch.drop_column("display_proof_id")

    op.execute("DROP TRIGGER display_proofs_append_only ON display_proofs")
    op.drop_index("ix_display_proofs_assignment_verified", table_name="display_proofs")
    op.drop_table("display_proofs")
    op.execute("DROP TRIGGER display_proof_challenge_guard ON display_proof_challenges")
    op.drop_index("ix_display_proof_challenge_assignment", table_name="display_proof_challenges")
    op.drop_table("display_proof_challenges")
    op.execute("DROP FUNCTION guard_display_proof_challenge_mutation()")
    op.execute(
        "DROP TRIGGER installation_evidence_photos_append_only ON installation_evidence_photos"
    )
    op.drop_index(
        "ix_installation_evidence_photos_submission",
        table_name="installation_evidence_photos",
    )
    op.drop_table("installation_evidence_photos")
    op.execute(
        "DROP TRIGGER installation_evidence_submission_guard ON installation_evidence_submissions"
    )
    op.drop_index(
        "ix_installation_evidence_assignment_status",
        table_name="installation_evidence_submissions",
    )
    op.drop_index(
        "uq_installation_evidence_assignment_pending",
        table_name="installation_evidence_submissions",
    )
    op.drop_table("installation_evidence_submissions")
    op.execute("DROP FUNCTION guard_installation_evidence_submission_mutation()")

    old_purposes = "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence')"
    old_scope = (
        "(purpose = 'creative' AND organization_id IS NOT NULL "
        "AND subject_user_id IS NULL) OR "
        "(purpose IN ('driver_kyc', 'vehicle_evidence') "
        "AND organization_id IS NULL AND subject_user_id IS NOT NULL)"
    )
    for table_name in ("file_upload_intents", "stored_files"):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(f"ck_{table_name}_purpose", type_="check")
            batch.drop_constraint(f"ck_{table_name}_scope", type_="check")
            batch.create_check_constraint(f"ck_{table_name}_purpose", old_purposes)
            batch.create_check_constraint(f"ck_{table_name}_scope", old_scope)
