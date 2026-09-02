"""Enforce one active campaign assignment per driver."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0078_campaign_assignment_driver_active"
down_revision: str | Sequence[str] | None = "0077_stored_object_deletions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_campaign_assignments_driver_active"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM campaign_assignments
                WHERE status = 'active'
                GROUP BY driver_profile_id
                HAVING count(*) > 1
              ) THEN
                RAISE EXCEPTION USING
                  ERRCODE = '23505',
                  CONSTRAINT = '{INDEX_NAME}',
                  MESSAGE = 'duplicate active campaign assignments exist for a driver',
                  HINT = 'Resolve duplicate active driver assignments explicitly before retrying';
              END IF;
            END
            $$
            """
        )
    )
    op.create_index(
        INDEX_NAME,
        "campaign_assignments",
        ["driver_profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="campaign_assignments")
