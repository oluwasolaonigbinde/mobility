"""Add superseding driver account-setup authority.

Revision ID: 0089_driver_account_setup
Revises: 0088_report_publication_writes
"""

import sqlalchemy as sa

from alembic import op

revision = "0089_driver_account_setup"
down_revision = "0088_report_publication_writes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE driver_application_access_tokens IN SHARE ROW EXCLUSIVE MODE NOWAIT")
    op.add_column(
        "driver_application_access_tokens",
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "driver_account_setup_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("driver_applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "issued_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(token_sha256) = 64", name="ck_driver_setup_tokens_hash"),
        sa.CheckConstraint(
            "length(evidence_sha256) = 64", name="ck_driver_setup_tokens_evidence_hash"
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_driver_setup_tokens_request_hash"
        ),
        sa.CheckConstraint("session_version > 0", name="ck_driver_setup_tokens_session_version"),
        sa.CheckConstraint("expires_at > created_at", name="ck_driver_setup_tokens_expiry"),
        sa.UniqueConstraint("token_sha256", name="uq_driver_setup_tokens_hash"),
        sa.UniqueConstraint(
            "client_request_id", name="uq_driver_setup_tokens_client_request"
        ),
    )
    op.create_index(
        "ix_driver_setup_tokens_application_created",
        "driver_account_setup_tokens",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_driver_setup_tokens_application_created",
        table_name="driver_account_setup_tokens",
    )
    op.drop_table("driver_account_setup_tokens")
    op.drop_column("driver_application_access_tokens", "invalidated_at")
