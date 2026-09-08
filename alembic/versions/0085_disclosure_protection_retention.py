"""Retain disclosure protection without an unsupported source-retirement deadline.

Revision ID: 0085_disclosure_protection
Revises: 0084_payout_conservation
"""

import sqlalchemy as sa

from alembic import op

revision = "0085_disclosure_protection"
down_revision = "0084_payout_conservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "disclosure_query_decisions",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.execute("UPDATE disclosure_query_decisions SET expires_at = NULL")


def downgrade() -> None:
    op.execute("LOCK TABLE disclosure_query_decisions IN ACCESS EXCLUSIVE MODE NOWAIT")
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM disclosure_query_decisions)"))
        .scalar()
    ):
        raise RuntimeError(
            "Refusing to drop populated disclosure protection: 0085 downgrade blocked"
        )
    op.alter_column(
        "disclosure_query_decisions",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
