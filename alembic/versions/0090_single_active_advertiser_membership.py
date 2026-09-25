"""Enforce one active advertiser-organization membership per login (D29).

Revision ID: 0090_single_active_advertiser_membership
Revises: 0089_driver_account_setup
"""

import sqlalchemy as sa

from alembic import op

revision = "0090_single_active_advertiser_membership"
down_revision = "0089_driver_account_setup"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_organization_memberships_user_active"

# Operators run this to find the logins that must be resolved by hand.
CONFLICT_QUERY = (
    "SELECT user_id, count(*) AS active_memberships "
    "FROM organization_memberships WHERE status = 'active' "
    "GROUP BY user_id HAVING count(*) > 1"
)


def upgrade() -> None:
    op.execute("LOCK TABLE organization_memberships IN SHARE ROW EXCLUSIVE MODE NOWAIT")
    conflicts = op.get_bind().execute(sa.text(CONFLICT_QUERY)).all()
    if conflicts:
        # Choosing which company an advertiser keeps is an operator decision,
        # so existing conflicts are refused rather than repaired.
        raise RuntimeError(
            f"0090 blocked: {len(conflicts)} login(s) hold more than one active advertiser "
            f"membership. Disable all but one for each before upgrading: {CONFLICT_QUERY}"
        )
    op.create_index(
        INDEX_NAME,
        "organization_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="organization_memberships")
