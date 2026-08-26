"""Add private upload intents and managed stored-file authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052_stored_files"
down_revision: str | Sequence[str] | None = "0051_canonical_impression_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, generated: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.Uuid(as_uuid=True),
        server_default=sa.text("gen_random_uuid()") if generated else None,
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "file_upload_intents",
        _uuid("id", generated=True),
        _uuid("organization_id"),
        _uuid("uploader_user_id"),
        _uuid("client_request_id"),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("declared_content_type", sa.String(255), nullable=False),
        sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("purpose IN ('creative')", name="ck_file_upload_intents_purpose"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'expired')",
            name="ck_file_upload_intents_status",
        ),
        sa.CheckConstraint("declared_size_bytes > 0", name="ck_file_upload_intents_size_positive"),
        sa.CheckConstraint(
            "length(declared_sha256) = 64", name="ck_file_upload_intents_sha256_length"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["advertiser_organizations.id"],
            ondelete="RESTRICT",
            name="fk_file_upload_intents_organization",
        ),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_file_upload_intents_uploader",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_file_upload_intents_object_key"),
        sa.UniqueConstraint(
            "organization_id",
            "uploader_user_id",
            "client_request_id",
            name="uq_file_upload_intents_scope_request",
        ),
    )
    op.create_index(
        "ix_file_upload_intents_status_expires",
        "file_upload_intents",
        ["status", "expires_at"],
    )
    op.create_table(
        "stored_files",
        _uuid("id", generated=True),
        _uuid("upload_intent_id"),
        _uuid("organization_id"),
        _uuid("uploader_user_id"),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("scan_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("purpose IN ('creative')", name="ck_stored_files_purpose"),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'error')",
            name="ck_stored_files_scan_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_stored_files_size_positive"),
        sa.CheckConstraint("length(checksum_sha256) = 64", name="ck_stored_files_sha256_length"),
        sa.ForeignKeyConstraint(
            ["upload_intent_id"],
            ["file_upload_intents.id"],
            ondelete="RESTRICT",
            name="fk_stored_files_upload_intent",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["advertiser_organizations.id"],
            ondelete="RESTRICT",
            name="fk_stored_files_organization",
        ),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_stored_files_uploader",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_intent_id", name="uq_stored_files_upload_intent"),
        sa.UniqueConstraint("storage_key", name="uq_stored_files_storage_key"),
    )
    op.create_index(
        "ix_stored_files_organization_created",
        "stored_files",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM file_upload_intents LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM stored_files LIMIT 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0052 downgrade blocked: stored-file authority is populated")
    op.drop_index("ix_stored_files_organization_created", table_name="stored_files")
    op.drop_table("stored_files")
    op.drop_index("ix_file_upload_intents_status_expires", table_name="file_upload_intents")
    op.drop_table("file_upload_intents")
