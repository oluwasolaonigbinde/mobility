"""Add exact payout verification and applicant mutation authority.

Revision ID: 0069_w3_04b_review_authority
Revises: 0068_driver_person_payee_review
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0069_w3_04b_review_authority"
down_revision: str | Sequence[str] | None = "0068_driver_person_payee_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payee_bank_account_payout_verifications",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("bank_account_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("verification_reference_sha256", sa.String(64), nullable=False),
        sa.Column("verified_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(verification_reference_sha256) = 64",
            name="ck_payee_bank_account_payout_verifications_hash",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_version_id"],
            ["payee_bank_account_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bank_account_version_id",
            name="uq_payee_bank_account_payout_verifications_version",
        ),
    )
    op.create_index(
        "ix_payee_payout_verifications_version",
        "payee_bank_account_payout_verifications",
        ["bank_account_version_id"],
    )
    op.execute(
        "INSERT INTO payee_bank_account_payout_verifications "
        "(id, bank_account_version_id, verification_reference_sha256, "
        "verified_by_user_id, created_at) "
        "SELECT gen_random_uuid(), v.id, v.verification_reference_sha256, "
        "v.verified_by_user_id, v.verified_at "
        "FROM payee_bank_account_versions v "
        "JOIN payee_bank_accounts a ON a.id = v.bank_account_id "
        "WHERE EXISTS (SELECT 1 FROM audit_events e "
        "WHERE e.actor_user_id = v.verified_by_user_id "
        "AND e.action = 'admin.bank_account.verified' "
        "AND e.entity_type = 'payee_bank_account' "
        "AND e.entity_id = a.id::text "
        "AND e.metadata->>'bank_account_version' = v.version::text)"
    )
    op.execute(
        "CREATE FUNCTION reject_payee_payout_verification_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'payout bank-account verifications are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER payee_bank_account_payout_verifications_immutable "
        "BEFORE UPDATE OR DELETE ON payee_bank_account_payout_verifications "
        "FOR EACH ROW EXECUTE FUNCTION reject_payee_payout_verification_mutation()"
    )

    op.create_table(
        "driver_application_access_tokens",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(token_sha256) = 64", name="ck_driver_application_access_tokens_hash"
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["driver_applications.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256", name="uq_driver_application_access_tokens_hash"),
    )
    op.create_index(
        "ix_driver_application_access_tokens_application_created",
        "driver_application_access_tokens",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM driver_application_access_tokens) "
                "OR EXISTS (SELECT 1 FROM payee_bank_account_payout_verifications)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0069 downgrade blocked: onboarding or payout authority exists")
    op.drop_index(
        "ix_driver_application_access_tokens_application_created",
        table_name="driver_application_access_tokens",
    )
    op.drop_table("driver_application_access_tokens")
    op.execute(
        "DROP TRIGGER payee_bank_account_payout_verifications_immutable "
        "ON payee_bank_account_payout_verifications"
    )
    op.execute("DROP FUNCTION reject_payee_payout_verification_mutation()")
    op.drop_index(
        "ix_payee_payout_verifications_version",
        table_name="payee_bank_account_payout_verifications",
    )
    op.drop_table("payee_bank_account_payout_verifications")
