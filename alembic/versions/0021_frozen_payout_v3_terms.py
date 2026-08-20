"""Complete the payout_v3 acceptance-time terms freeze.

Revision ID: 0021_frozen_payout_v3_terms
Revises: 0020_payout_correction_orders
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_frozen_payout_v3_terms"
down_revision: str | Sequence[str] | None = "0020_payout_correction_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def upgrade() -> None:
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "resolved_eligibility_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "premium_zone_geometry_wkts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "exclusion_zone_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "exclusion_zone_geometry_hash",
            sa.Text(),
            server_default=sa.text(f"'{EMPTY_SHA256}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column(
            "exclusion_zone_geometry_wkts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("assignment_rule_bindings", "exclusion_zone_geometry_wkts")
    op.drop_column("assignment_rule_bindings", "exclusion_zone_geometry_hash")
    op.drop_column("assignment_rule_bindings", "exclusion_zone_ids")
    op.drop_column("assignment_rule_bindings", "premium_zone_geometry_wkts")
    op.drop_column("assignment_rule_bindings", "resolved_eligibility_params")
