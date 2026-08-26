"""Add manual cross-store data-subject request evidence.

Revision ID: 0062_data_subject_requests
Revises: 0061_email_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0062_data_subject_requests"
down_revision: str | Sequence[str] | None = "0061_email_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subject_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("opened_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "identity_verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "request_type IN ('access', 'rectification', 'erasure')",
            name="ck_data_subject_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'identity_verified', 'completed')",
            name="ck_data_subject_requests_status",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_data_subject_requests_fingerprint",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND identity_verified_at IS NULL "
            "AND identity_verified_by_user_id IS NULL AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(status = 'identity_verified' AND identity_verified_at IS NOT NULL "
            "AND identity_verified_by_user_id IS NOT NULL AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL) OR "
            "(status = 'completed' AND identity_verified_at IS NOT NULL "
            "AND identity_verified_by_user_id IS NOT NULL AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL)",
            name="ck_data_subject_requests_lifecycle",
        ),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["identity_verified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "opened_by_user_id",
            "client_request_id",
            name="uq_data_subject_requests_actor_request",
        ),
    )
    op.create_index(
        "ix_data_subject_requests_subject_user_id",
        "data_subject_requests",
        ["subject_user_id"],
    )
    op.create_table(
        "data_subject_location_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location", sa.String(32), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("data_class_counts", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_reference", sa.String(255), nullable=False),
        sa.Column("exception_reference", sa.String(255), nullable=True),
        sa.Column("assessed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "location IN ('database', 'object_storage', 'device_queue', "
            "'operational_logs', 'backups', 'processors')",
            name="ck_data_subject_location_assessments_location",
        ),
        sa.CheckConstraint(
            "disposition IN ('provided', 'rectified', 'erased', 'not_found', "
            "'retained_exception')",
            name="ck_data_subject_location_assessments_disposition",
        ),
        sa.CheckConstraint(
            "record_count >= 0", name="ck_data_subject_assessments_count"
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_data_subject_assessments_fingerprint",
        ),
        sa.CheckConstraint(
            "length(trim(evidence_reference)) > 0",
            name="ck_data_subject_assessments_evidence",
        ),
        sa.CheckConstraint(
            "(disposition = 'retained_exception' AND exception_reference IS NOT NULL "
            "AND length(trim(exception_reference)) > 0) OR "
            "(disposition <> 'retained_exception' AND exception_reference IS NULL)",
            name="ck_data_subject_assessments_exception",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["data_subject_requests.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["assessed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id", "location", name="uq_data_subject_assessments_request_location"
        ),
        sa.UniqueConstraint(
            "assessed_by_user_id",
            "client_request_id",
            name="uq_data_subject_assessments_actor_request",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION reject_data_subject_assessment_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'data subject location assessments are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER data_subject_location_assessments_immutable "
        "BEFORE UPDATE OR DELETE ON data_subject_location_assessments FOR EACH ROW "
        "EXECUTE FUNCTION reject_data_subject_assessment_mutation()"
    )
    op.execute(
        """
        CREATE FUNCTION validate_data_subject_request_mutation() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'data subject requests are append-only evidence';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.subject_user_id IS DISTINCT FROM OLD.subject_user_id
             OR NEW.request_type IS DISTINCT FROM OLD.request_type
             OR NEW.opened_by_user_id IS DISTINCT FROM OLD.opened_by_user_id
             OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'data subject request identity is immutable';
          END IF;
          IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
            (OLD.status = 'open' AND NEW.status = 'identity_verified') OR
            (OLD.status = 'identity_verified' AND NEW.status = 'completed')
          ) THEN
            RAISE EXCEPTION 'invalid data subject request status transition';
          END IF;
          IF OLD.identity_verified_at IS NOT NULL AND (
             NEW.identity_verified_at IS DISTINCT FROM OLD.identity_verified_at OR
             NEW.identity_verified_by_user_id IS DISTINCT FROM OLD.identity_verified_by_user_id
          ) THEN
            RAISE EXCEPTION 'identity verification evidence is immutable';
          END IF;
          IF OLD.completed_at IS NOT NULL AND (
             NEW.completed_at IS DISTINCT FROM OLD.completed_at OR
             NEW.completed_by_user_id IS DISTINCT FROM OLD.completed_by_user_id
          ) THEN
            RAISE EXCEPTION 'completion evidence is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER data_subject_requests_guard "
        "BEFORE UPDATE OR DELETE ON data_subject_requests FOR EACH ROW "
        "EXECUTE FUNCTION validate_data_subject_request_mutation()"
    )


def downgrade() -> None:
    populated = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM data_subject_requests) OR "
            "EXISTS (SELECT 1 FROM data_subject_location_assessments)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0062 downgrade blocked: data-subject request evidence exists")
    op.execute("DROP TRIGGER IF EXISTS data_subject_requests_guard ON data_subject_requests")
    op.execute("DROP FUNCTION IF EXISTS validate_data_subject_request_mutation()")
    op.execute(
        "DROP TRIGGER data_subject_location_assessments_immutable ON "
        "data_subject_location_assessments"
    )
    op.execute("DROP FUNCTION reject_data_subject_assessment_mutation()")
    op.drop_table("data_subject_location_assessments")
    op.drop_index(
        "ix_data_subject_requests_subject_user_id", table_name="data_subject_requests"
    )
    op.drop_table("data_subject_requests")
