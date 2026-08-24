"""Add protected, versioned payee and verified bank-account authority.

Revision ID: 0028_protected_payee_accounts
Revises: 0027_earnings_release_sla
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028_protected_payee_accounts"
down_revision: str | Sequence[str] | None = "0027_earnings_release_sla"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payees",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payee_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("payee_type = 'driver'", name="ck_payees_type"),
        sa.ForeignKeyConstraint(["tenant_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "payee_type", "subject_id", name="uq_payees_tenant_type_subject"
        ),
    )
    op.create_index("ix_payees_tenant_id", "payees", ["tenant_id"])
    op.create_table(
        "payee_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payee_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_payee_versions_positive_version"),
        sa.CheckConstraint("payee_type = 'driver'", name="ck_payee_versions_type"),
        sa.ForeignKeyConstraint(["payee_id"], ["payees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payee_id", "version", name="uq_payee_versions_payee_version"),
    )
    op.create_index("ix_payee_versions_payee_id", "payee_versions", ["payee_id"])
    op.create_table(
        "payee_bank_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["payee_id"], ["payees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payee_id", name="uq_payee_bank_accounts_payee_id"),
    )
    op.create_index("ix_payee_bank_accounts_payee_id", "payee_bank_accounts", ["payee_id"])
    op.create_table(
        "payee_bank_account_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payee_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encrypted_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("encryption_algorithm", sa.String(length=32), nullable=False),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("verification_reference_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_payee_bank_account_versions_positive_version"),
        sa.CheckConstraint(
            "encryption_algorithm = 'AES-256-GCM'",
            name="ck_payee_bank_account_versions_algorithm",
        ),
        sa.CheckConstraint(
            "encryption_key_version > 0",
            name="ck_payee_bank_account_versions_positive_key_version",
        ),
        sa.CheckConstraint(
            "length(verification_reference_sha256) = 64",
            name="ck_payee_bank_account_versions_verification_hash",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_id"], ["payee_bank_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["payee_version_id"], ["payee_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bank_account_id",
            "version",
            name="uq_payee_bank_account_versions_account_version",
        ),
    )
    op.create_index(
        "ix_payee_bank_account_versions_bank_account_id",
        "payee_bank_account_versions",
        ["bank_account_id"],
    )
    op.create_index(
        "ix_payee_bank_account_versions_payee_version_id",
        "payee_bank_account_versions",
        ["payee_version_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payees) "
            "OR EXISTS (SELECT 1 FROM payee_versions) "
            "OR EXISTS (SELECT 1 FROM payee_bank_accounts) "
            "OR EXISTS (SELECT 1 FROM payee_bank_account_versions)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0028 downgrade blocked: payee or bank-account authority exists")

    op.drop_index(
        "ix_payee_bank_account_versions_payee_version_id",
        table_name="payee_bank_account_versions",
    )
    op.drop_index(
        "ix_payee_bank_account_versions_bank_account_id",
        table_name="payee_bank_account_versions",
    )
    op.drop_table("payee_bank_account_versions")
    op.drop_index("ix_payee_bank_accounts_payee_id", table_name="payee_bank_accounts")
    op.drop_table("payee_bank_accounts")
    op.drop_index("ix_payee_versions_payee_id", table_name="payee_versions")
    op.drop_table("payee_versions")
    op.drop_index("ix_payees_tenant_id", table_name="payees")
    op.drop_table("payees")
