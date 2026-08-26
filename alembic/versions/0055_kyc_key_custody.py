"""Add subject-scoped files and versioned protected KYC evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_kyc_key_custody"
down_revision: str | Sequence[str] | None = "0054_managed_creatives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, generated: bool = False, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.Uuid(as_uuid=True),
        server_default=sa.text("gen_random_uuid()") if generated else None,
        nullable=nullable,
    )


def _expand_file_scope(table: str) -> None:
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column("subject_user_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            f"fk_{table}_subject_user",
            "users",
            ["subject_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=True)
        batch.drop_constraint(f"ck_{table}_purpose", type_="check")
        batch.create_check_constraint(
            f"ck_{table}_purpose",
            "purpose IN ('creative', 'driver_kyc', 'vehicle_evidence')",
        )
        batch.create_check_constraint(
            f"ck_{table}_scope",
            "(purpose = 'creative' AND organization_id IS NOT NULL "
            "AND subject_user_id IS NULL) OR "
            "(purpose IN ('driver_kyc', 'vehicle_evidence') "
            "AND organization_id IS NULL AND subject_user_id IS NOT NULL)",
        )
        if table == "file_upload_intents":
            batch.create_unique_constraint(
                "uq_file_upload_intents_subject_request",
                ["subject_user_id", "uploader_user_id", "client_request_id"],
            )


def upgrade() -> None:
    _expand_file_scope("file_upload_intents")
    _expand_file_scope("stored_files")
    op.create_index(
        "ix_stored_files_subject_created", "stored_files", ["subject_user_id", "created_at"]
    )
    op.create_table(
        "driver_kyc_submissions",
        _uuid("id", generated=True),
        _uuid("driver_profile_id"),
        _uuid("nin_record_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        _uuid("client_request_id"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("encrypted_nin", sa.JSON(), nullable=False),
        sa.Column("encryption_algorithm", sa.String(32), nullable=False),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("nin_last_four", sa.String(4), nullable=False),
        _uuid("bank_account_version_id"),
        _uuid("created_by_user_id"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_driver_kyc_submissions_version"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_driver_kyc_submissions_status",
        ),
        sa.CheckConstraint(
            "encryption_algorithm = 'AES-256-GCM'",
            name="ck_driver_kyc_submissions_algorithm",
        ),
        sa.CheckConstraint(
            "encryption_key_version > 0", name="ck_driver_kyc_submissions_key_version"
        ),
        sa.CheckConstraint(
            "length(nin_last_four) = 4", name="ck_driver_kyc_submissions_nin_last_four"
        ),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="RESTRICT",
            name="fk_driver_kyc_submissions_profile",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_version_id"],
            ["payee_bank_account_versions.id"],
            ondelete="RESTRICT",
            name="fk_driver_kyc_submissions_bank_version",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_driver_kyc_submissions_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "driver_profile_id", "version", name="uq_driver_kyc_submissions_profile_version"
        ),
        sa.UniqueConstraint(
            "driver_profile_id",
            "client_request_id",
            name="uq_driver_kyc_submissions_profile_request",
        ),
    )
    op.create_index(
        "ix_driver_kyc_submissions_driver_profile_id",
        "driver_kyc_submissions",
        ["driver_profile_id"],
    )
    op.create_index(
        "ix_driver_kyc_submissions_nin_record_id",
        "driver_kyc_submissions",
        ["nin_record_id"],
    )
    op.create_table(
        "driver_kyc_documents",
        _uuid("id", generated=True),
        _uuid("submission_id"),
        _uuid("stored_file_id"),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('driver_license', 'driver_photo', 'signed_agreement')",
            name="ck_driver_kyc_documents_type",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["driver_kyc_submissions.id"],
            ondelete="RESTRICT",
            name="fk_driver_kyc_documents_submission",
        ),
        sa.ForeignKeyConstraint(
            ["stored_file_id"],
            ["stored_files.id"],
            ondelete="RESTRICT",
            name="fk_driver_kyc_documents_file",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "document_type", name="uq_driver_kyc_documents_submission_type"
        ),
    )
    op.create_index(
        "ix_driver_kyc_documents_submission_id", "driver_kyc_documents", ["submission_id"]
    )
    op.create_table(
        "vehicle_evidence_submissions",
        _uuid("id", generated=True),
        _uuid("vehicle_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        _uuid("client_request_id"),
        sa.Column("status", sa.String(32), nullable=False),
        _uuid("created_by_user_id"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_vehicle_evidence_submissions_version"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'expired')",
            name="ck_vehicle_evidence_submissions_status",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_submissions_vehicle",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_submissions_creator",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vehicle_id", "version", name="uq_vehicle_evidence_submissions_vehicle_version"
        ),
        sa.UniqueConstraint(
            "vehicle_id",
            "client_request_id",
            name="uq_vehicle_evidence_submissions_vehicle_request",
        ),
    )
    op.create_index(
        "ix_vehicle_evidence_submissions_vehicle_id",
        "vehicle_evidence_submissions",
        ["vehicle_id"],
    )
    op.create_table(
        "vehicle_evidence_documents",
        _uuid("id", generated=True),
        _uuid("submission_id"),
        _uuid("stored_file_id"),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('registration', 'insurance', 'vehicle_photo')",
            name="ck_vehicle_evidence_documents_type",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["vehicle_evidence_submissions.id"],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_documents_submission",
        ),
        sa.ForeignKeyConstraint(
            ["stored_file_id"],
            ["stored_files.id"],
            ondelete="RESTRICT",
            name="fk_vehicle_evidence_documents_file",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "document_type",
            name="uq_vehicle_evidence_documents_submission_type",
        ),
    )
    op.create_index(
        "ix_vehicle_evidence_documents_submission_id",
        "vehicle_evidence_documents",
        ["submission_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM driver_kyc_submissions LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM vehicle_evidence_submissions LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM file_upload_intents "
            "WHERE subject_user_id IS NOT NULL LIMIT 1) OR "
            "EXISTS (SELECT 1 FROM stored_files WHERE subject_user_id IS NOT NULL LIMIT 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0055 downgrade blocked: protected KYC/file authority is populated")
    op.drop_index(
        "ix_vehicle_evidence_documents_submission_id", table_name="vehicle_evidence_documents"
    )
    op.drop_table("vehicle_evidence_documents")
    op.drop_index(
        "ix_vehicle_evidence_submissions_vehicle_id", table_name="vehicle_evidence_submissions"
    )
    op.drop_table("vehicle_evidence_submissions")
    op.drop_index("ix_driver_kyc_documents_submission_id", table_name="driver_kyc_documents")
    op.drop_table("driver_kyc_documents")
    op.drop_index(
        "ix_driver_kyc_submissions_driver_profile_id", table_name="driver_kyc_submissions"
    )
    op.drop_index(
        "ix_driver_kyc_submissions_nin_record_id", table_name="driver_kyc_submissions"
    )
    op.drop_table("driver_kyc_submissions")
    op.drop_index("ix_stored_files_subject_created", table_name="stored_files")
    for table in ("stored_files", "file_upload_intents"):
        with op.batch_alter_table(table) as batch:
            if table == "file_upload_intents":
                batch.drop_constraint(
                    "uq_file_upload_intents_subject_request", type_="unique"
                )
            batch.drop_constraint(f"ck_{table}_scope", type_="check")
            batch.drop_constraint(f"ck_{table}_purpose", type_="check")
            batch.create_check_constraint(f"ck_{table}_purpose", "purpose IN ('creative')")
            batch.drop_constraint(f"fk_{table}_subject_user", type_="foreignkey")
            batch.drop_column("subject_user_id")
            batch.alter_column("organization_id", existing_type=sa.Uuid(), nullable=False)
