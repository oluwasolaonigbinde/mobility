"""Add immutable vehicle profile revisions and sequenced review authority.

Revision ID: 0070_driver_vehicle_approval
Revises: 0069_w3_04b_review_authority
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0070_driver_vehicle_approval"
down_revision: str | Sequence[str] | None = "0069_w3_04b_review_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("plate_number_snapshot", sa.String(32), nullable=True),
        sa.Column("plate_number_normalized_snapshot", sa.String(32), nullable=True),
        sa.Column("plate_country_code_snapshot", sa.String(2), nullable=True),
        sa.Column("vehicle_type_snapshot", sa.String(32), nullable=True),
        sa.Column("make_snapshot", sa.String(128), nullable=True),
        sa.Column("model_snapshot", sa.String(128), nullable=True),
        sa.Column("year_snapshot", sa.Integer(), nullable=True),
        sa.Column("color_snapshot", sa.String(64), nullable=True),
    ):
        op.add_column("vehicle_evidence_submissions", column)
    op.add_column(
        "vehicle_evidence_submissions",
        sa.Column(
            "snapshot_trusted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE vehicle_evidence_submissions s SET "
        "plate_number_snapshot = v.plate_number, "
        "plate_number_normalized_snapshot = v.plate_number_normalized, "
        "plate_country_code_snapshot = v.plate_country_code, "
        "vehicle_type_snapshot = v.vehicle_type, make_snapshot = v.make, "
        "model_snapshot = v.model, year_snapshot = v.year, color_snapshot = v.color "
        "FROM vehicles v WHERE v.id = s.vehicle_id"
    )
    for name in (
        "plate_number_snapshot",
        "plate_number_normalized_snapshot",
        "plate_country_code_snapshot",
        "vehicle_type_snapshot",
    ):
        op.alter_column("vehicle_evidence_submissions", name, nullable=False)
    op.create_unique_constraint(
        "uq_vehicle_evidence_submissions_owner_request",
        "vehicle_evidence_submissions",
        ["created_by_user_id", "client_request_id"],
    )

    op.create_table(
        "vehicle_evidence_review_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("owner_match_confirmed", sa.Boolean(), nullable=False),
        sa.Column("vehicle_identity_confirmed", sa.Boolean(), nullable=False),
        sa.Column("roadworthy_confirmed", sa.Boolean(), nullable=False),
        sa.Column("pilot_car_confirmed", sa.Boolean(), nullable=False),
        sa.Column("documents_readable_confirmed", sa.Boolean(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("sequence > 0", name="ck_vehicle_review_decisions_sequence"),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'expired')",
            name="ck_vehicle_review_decisions_decision",
        ),
        sa.CheckConstraint(
            "reason_code IN ('complete_current_evidence', 'missing_evidence', "
            "'unsafe_evidence', 'expired_evidence', 'owner_mismatch', 'vehicle_identity_mismatch', "
            "'not_roadworthy', 'not_pilot_eligible', 'unreadable_evidence')",
            name="ck_vehicle_review_decisions_reason",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_vehicle_review_decisions_fingerprint",
        ),
        sa.CheckConstraint(
            "(decision = 'approved' AND reason_code = 'complete_current_evidence' "
            "AND owner_match_confirmed AND vehicle_identity_confirmed "
            "AND roadworthy_confirmed AND pilot_car_confirmed "
            "AND documents_readable_confirmed AND valid_until IS NOT NULL) OR "
            "(decision IN ('rejected', 'expired') "
            "AND reason_code <> 'complete_current_evidence')",
            name="ck_vehicle_review_decisions_facts",
        ),
        sa.CheckConstraint(
            "decision = 'expired' OR decided_by_user_id IS NOT NULL",
            name="ck_vehicle_review_decisions_admin_actor",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["vehicle_evidence_submissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "sequence",
            name="uq_vehicle_review_decisions_submission_sequence",
        ),
        sa.UniqueConstraint("client_request_id", name="uq_vehicle_review_decisions_client_request"),
    )
    op.create_index(
        "ix_vehicle_evidence_review_decisions_submission_id",
        "vehicle_evidence_review_decisions",
        ["submission_id"],
    )
    op.execute(
        "CREATE FUNCTION reject_vehicle_review_decision_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'vehicle review decisions are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER vehicle_review_decisions_immutable BEFORE UPDATE OR DELETE ON "
        "vehicle_evidence_review_decisions FOR EACH ROW EXECUTE FUNCTION "
        "reject_vehicle_review_decision_mutation()"
    )
    op.execute(
        "CREATE FUNCTION reject_vehicle_evidence_snapshot_mutation() RETURNS trigger AS $$ "
        "BEGIN IF ROW(NEW.vehicle_id, NEW.version, NEW.client_request_id, "
        "NEW.created_by_user_id, NEW.snapshot_trusted, NEW.plate_number_snapshot, "
        "NEW.plate_number_normalized_snapshot, NEW.plate_country_code_snapshot, "
        "NEW.vehicle_type_snapshot, NEW.make_snapshot, NEW.model_snapshot, "
        "NEW.year_snapshot, NEW.color_snapshot) IS DISTINCT FROM "
        "ROW(OLD.vehicle_id, OLD.version, OLD.client_request_id, OLD.created_by_user_id, "
        "OLD.snapshot_trusted, OLD.plate_number_snapshot, "
        "OLD.plate_number_normalized_snapshot, OLD.plate_country_code_snapshot, "
        "OLD.vehicle_type_snapshot, OLD.make_snapshot, OLD.model_snapshot, "
        "OLD.year_snapshot, OLD.color_snapshot) THEN "
        "RAISE EXCEPTION 'vehicle evidence snapshots are immutable'; END IF; RETURN NEW; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER vehicle_evidence_snapshots_immutable BEFORE UPDATE ON "
        "vehicle_evidence_submissions FOR EACH ROW EXECUTE FUNCTION "
        "reject_vehicle_evidence_snapshot_mutation()"
    )
    op.execute(
        "CREATE FUNCTION reject_vehicle_evidence_document_update() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'vehicle evidence documents are immutable'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER vehicle_evidence_documents_immutable BEFORE UPDATE ON "
        "vehicle_evidence_documents FOR EACH ROW EXECUTE FUNCTION "
        "reject_vehicle_evidence_document_update()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM vehicle_evidence_review_decisions) "
                "OR EXISTS (SELECT 1 FROM vehicle_evidence_submissions WHERE snapshot_trusted)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0070 downgrade blocked: vehicle approval authority exists")
    op.execute("DROP TRIGGER vehicle_evidence_documents_immutable ON vehicle_evidence_documents")
    op.execute("DROP FUNCTION reject_vehicle_evidence_document_update()")
    op.execute("DROP TRIGGER vehicle_evidence_snapshots_immutable ON vehicle_evidence_submissions")
    op.execute("DROP FUNCTION reject_vehicle_evidence_snapshot_mutation()")
    op.execute(
        "DROP TRIGGER vehicle_review_decisions_immutable ON vehicle_evidence_review_decisions"
    )
    op.execute("DROP FUNCTION reject_vehicle_review_decision_mutation()")
    op.drop_index(
        "ix_vehicle_evidence_review_decisions_submission_id",
        table_name="vehicle_evidence_review_decisions",
    )
    op.drop_table("vehicle_evidence_review_decisions")
    op.drop_constraint(
        "uq_vehicle_evidence_submissions_owner_request",
        "vehicle_evidence_submissions",
        type_="unique",
    )
    for name in (
        "snapshot_trusted",
        "color_snapshot",
        "year_snapshot",
        "model_snapshot",
        "make_snapshot",
        "vehicle_type_snapshot",
        "plate_country_code_snapshot",
        "plate_number_normalized_snapshot",
        "plate_number_snapshot",
    ):
        op.drop_column("vehicle_evidence_submissions", name)
