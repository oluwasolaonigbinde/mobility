"""Complete the payout_v3 acceptance-time terms freeze.

0019 through 0021 are one unreleased delivery lane and must be deployed
together. An interim 0019 binding cannot be truthfully upgraded because it
did not store the accepted geometry or fully resolved classifier settings.
Fail the migration before changing the schema if such rows exist; operators
must resolve them explicitly instead of fabricating frozen payout terms.

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
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM assignment_rule_bindings) THEN "
            "RAISE EXCEPTION '0021 cannot upgrade pre-existing payout bindings: "
            "acceptance-time geometry and resolved eligibility were not stored'; "
            "END IF; END $$;"
        )
    )
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
