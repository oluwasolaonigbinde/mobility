"""Add immutable driver person/payee review decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0068_driver_person_payee_review"
down_revision: str | Sequence[str] | None = "0067_exposure_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "driver_kyc_review_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("identity_match_confirmed", sa.Boolean(), nullable=False),
        sa.Column("bank_account_match_confirmed", sa.Boolean(), nullable=False),
        sa.Column("documents_readable_confirmed", sa.Boolean(), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'expired')",
            name="ck_driver_kyc_review_decisions_decision",
        ),
        sa.CheckConstraint(
            "reason_code IN ('complete_current_evidence', 'missing_evidence', "
            "'rejected_evidence', 'expired_evidence', 'unsafe_evidence', "
            "'identity_mismatch', 'bank_account_mismatch', 'unreadable_evidence')",
            name="ck_driver_kyc_review_decisions_reason",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_driver_kyc_review_decisions_fingerprint",
        ),
        sa.CheckConstraint(
            "(decision = 'approved' AND reason_code = 'complete_current_evidence' "
            "AND identity_match_confirmed AND bank_account_match_confirmed "
            "AND documents_readable_confirmed) OR "
            "(decision IN ('rejected', 'expired') "
            "AND reason_code <> 'complete_current_evidence')",
            name="ck_driver_kyc_review_decisions_facts",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["driver_kyc_submissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", name="uq_driver_kyc_review_decisions_submission"),
        sa.UniqueConstraint(
            "client_request_id", name="uq_driver_kyc_review_decisions_client_request"
        ),
    )
    op.create_index(
        "ix_driver_kyc_review_decisions_submission_id",
        "driver_kyc_review_decisions",
        ["submission_id"],
    )
    op.execute(
        "CREATE FUNCTION reject_driver_kyc_review_decision_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'driver KYC review decisions are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER driver_kyc_review_decisions_immutable BEFORE UPDATE OR DELETE ON "
        "driver_kyc_review_decisions FOR EACH ROW EXECUTE FUNCTION "
        "reject_driver_kyc_review_decision_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM driver_kyc_review_decisions)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0068 downgrade blocked: immutable driver person/payee decisions exist")
    op.execute("DROP TRIGGER driver_kyc_review_decisions_immutable ON driver_kyc_review_decisions")
    op.execute("DROP FUNCTION reject_driver_kyc_review_decision_mutation()")
    op.drop_index(
        "ix_driver_kyc_review_decisions_submission_id",
        table_name="driver_kyc_review_decisions",
    )
    op.drop_table("driver_kyc_review_decisions")
