"""Persist the bounded audience catch-up scan position.

Revision ID: 0107_audience_sweep_cursor
Revises: 0106_development_baseline
"""

import sqlalchemy as sa

from alembic import op

revision = "0107_audience_sweep_cursor"
down_revision = "0106_development_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audience_sweep_cursors",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("measurement_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_link_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(measurement_run_id IS NULL) = (source_link_id IS NULL)",
            name="ck_audience_sweep_cursor_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("audience_sweep_cursors")
