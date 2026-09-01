"""Add terminal driver-application lifecycle states.

Revision ID: 0072_driver_application_terminal_status
Revises: 0071_report_issuances
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_driver_application_terminal_status"
down_revision: str | Sequence[str] | None = "0071_report_issuances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_driver_applications_status", "driver_applications", type_="check")
    op.create_check_constraint(
        "ck_driver_applications_status",
        "driver_applications",
        "status IN ('pending', 'approved', 'rejected')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    terminal_rows = bool(
        bind.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM driver_applications WHERE status <> 'pending')")
        ).scalar_one()
    )
    if terminal_rows:
        raise RuntimeError(
            "0072 downgrade blocked: terminal driver application evidence is authoritative"
        )
    op.drop_constraint("ck_driver_applications_status", "driver_applications", type_="check")
    op.create_check_constraint(
        "ck_driver_applications_status",
        "driver_applications",
        "status = 'pending'",
    )
