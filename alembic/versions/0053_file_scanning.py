"""Add fail-closed stored-file scan authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0053_file_scanning"
down_revision: str | Sequence[str] | None = "0052_stored_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stored_files", sa.Column("actual_content_type", sa.String(255)))
    op.add_column(
        "stored_files",
        sa.Column("scan_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("stored_files", sa.Column("scan_error_code", sa.String(64)))
    op.add_column("stored_files", sa.Column("malware_signature", sa.String(255)))
    op.add_column("stored_files", sa.Column("next_scan_at", sa.DateTime(timezone=True)))
    op.add_column("stored_files", sa.Column("scanned_at", sa.DateTime(timezone=True)))
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_stored_files_scan_status", "stored_files", type_="check")
        op.create_check_constraint(
            "ck_stored_files_scan_status",
            "stored_files",
            "scan_status IN ('pending', 'clean', 'infected', 'rejected', 'error')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE stored_files SET scan_status = 'error' WHERE scan_status = 'rejected'")
    )
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_stored_files_scan_status", "stored_files", type_="check")
        op.create_check_constraint(
            "ck_stored_files_scan_status",
            "stored_files",
            "scan_status IN ('pending', 'clean', 'infected', 'error')",
        )
    for column in (
        "scanned_at",
        "next_scan_at",
        "malware_signature",
        "scan_error_code",
        "scan_attempts",
        "actual_content_type",
    ):
        op.drop_column("stored_files", column)
