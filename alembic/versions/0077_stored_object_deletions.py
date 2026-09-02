"""Add recoverable stored-object deletion intents and receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0077_stored_object_deletions"
down_revision: str | Sequence[str] | None = "0076_dsr_assessment_truth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_object_deletions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("stored_file_id", postgresql.UUID(as_uuid=True)),
        sa.Column("upload_intent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("owner_type", sa.String(64), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("storage_key_sha256", sa.String(64), nullable=False),
        sa.Column("object_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "state",
            sa.String(32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("provider_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        sa.CheckConstraint(
            "state IN ('pending', 'provider_deleted', 'completed')",
            name="ck_stored_object_deletions_state",
        ),
        sa.CheckConstraint(
            "length(storage_key_sha256) = 64",
            name="ck_stored_object_deletions_key_hash",
        ),
        sa.CheckConstraint(
            "length(object_checksum_sha256) = 64",
            name="ck_stored_object_deletions_object_checksum",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_stored_object_deletions_fingerprint",
        ),
        sa.CheckConstraint(
            "(organization_id IS NOT NULL) <> (subject_user_id IS NOT NULL)",
            name="ck_stored_object_deletions_scope",
        ),
        sa.CheckConstraint(
            "(state = 'pending' AND provider_deleted_at IS NULL AND completed_at IS NULL) OR "
            "(state = 'provider_deleted' AND provider_deleted_at IS NOT NULL "
            "AND completed_at IS NULL) OR "
            "(state = 'completed' AND provider_deleted_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_stored_object_deletions_timeline",
        ),
        sa.ForeignKeyConstraint(["stored_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["upload_intent_id"], ["file_upload_intents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_fingerprint",
            name="uq_stored_object_deletions_request_fingerprint",
        ),
    )
    op.create_index(
        "ix_stored_object_deletions_state_created",
        "stored_object_deletions",
        ["state", "created_at"],
    )
    op.create_index(
        "ix_stored_object_deletions_owner",
        "stored_object_deletions",
        ["owner_type", "owner_id"],
    )
    op.create_index(
        "ix_stored_object_deletions_stored_file_id",
        "stored_object_deletions",
        ["stored_file_id"],
    )
    op.create_index(
        "ix_stored_object_deletions_upload_intent_id",
        "stored_object_deletions",
        ["upload_intent_id"],
    )
    op.create_index(
        "ix_stored_object_deletions_organization_id",
        "stored_object_deletions",
        ["organization_id"],
    )
    op.create_index(
        "ix_stored_object_deletions_subject_user_id",
        "stored_object_deletions",
        ["subject_user_id"],
    )
    op.execute(
        """
        CREATE FUNCTION guard_stored_object_deletion_receipt()
        RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'stored-object deletion receipts are append-only';
          END IF;
          IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
             OR NEW.subject_user_id IS DISTINCT FROM OLD.subject_user_id
             OR NEW.owner_type IS DISTINCT FROM OLD.owner_type
             OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
             OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
             OR NEW.storage_key_sha256 IS DISTINCT FROM OLD.storage_key_sha256
             OR NEW.object_checksum_sha256 IS DISTINCT FROM OLD.object_checksum_sha256
             OR NEW.reason IS DISTINCT FROM OLD.reason
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'stored-object deletion identity is immutable';
          END IF;
          IF NEW.state IS DISTINCT FROM OLD.state
             AND NOT (
               (OLD.state = 'pending' AND NEW.state = 'provider_deleted')
               OR (OLD.state = 'provider_deleted' AND NEW.state = 'completed')
             ) THEN
            RAISE EXCEPTION 'stored-object deletion state transition is invalid';
          END IF;
          IF NEW.state IS NOT DISTINCT FROM OLD.state
             AND (NEW.provider_deleted_at IS DISTINCT FROM OLD.provider_deleted_at
                  OR NEW.completed_at IS DISTINCT FROM OLD.completed_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          IF OLD.state = 'pending' AND NEW.state = 'provider_deleted'
             AND (OLD.provider_deleted_at IS NOT NULL
                  OR NEW.provider_deleted_at IS NULL
                  OR NEW.completed_at IS DISTINCT FROM OLD.completed_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          IF OLD.state = 'provider_deleted' AND NEW.state = 'completed'
             AND (OLD.completed_at IS NOT NULL
                  OR NEW.completed_at IS NULL
                  OR NEW.provider_deleted_at IS DISTINCT FROM OLD.provider_deleted_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stored_object_deletion_receipt_guard
        BEFORE UPDATE OR DELETE ON stored_object_deletions
        FOR EACH ROW EXECUTE FUNCTION guard_stored_object_deletion_receipt()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_reference_to_deleting_stored_object()
        RETURNS trigger AS $$
        BEGIN
          PERFORM id FROM stored_files WHERE id = NEW.stored_file_id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM stored_object_deletions
            WHERE stored_file_id = NEW.stored_file_id AND state <> 'completed'
          ) THEN
            RAISE EXCEPTION 'stored object has an active deletion intent';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "campaign_creatives",
        "driver_kyc_documents",
        "vehicle_evidence_documents",
        "installation_evidence_photos",
        "display_proofs",
        "report_artifacts",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_deletion_fence "
            f"BEFORE INSERT OR UPDATE OF stored_file_id ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_reference_to_deleting_stored_object()"
        )


def downgrade() -> None:
    for table_name in (
        "campaign_creatives",
        "driver_kyc_documents",
        "vehicle_evidence_documents",
        "installation_evidence_photos",
        "display_proofs",
        "report_artifacts",
    ):
        op.execute(f"DROP TRIGGER trg_{table_name}_deletion_fence ON {table_name}")
    op.execute("DROP FUNCTION reject_reference_to_deleting_stored_object()")
    op.execute("DROP TRIGGER trg_stored_object_deletion_receipt_guard ON stored_object_deletions")
    op.execute("DROP FUNCTION guard_stored_object_deletion_receipt()")
    op.drop_table("stored_object_deletions")
