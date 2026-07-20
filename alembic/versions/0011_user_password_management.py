"""Add forced password change and session revocation fields.

Revision ID: 0011_user_password_management
Revises: 0010_payouts_and_earnings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_user_password_management"
down_revision: str | None = "0010_payouts_and_earnings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
    op.drop_column("users", "must_change_password")
