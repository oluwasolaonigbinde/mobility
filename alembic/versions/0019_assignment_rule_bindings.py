"""Acceptance-time payout value freeze (MNY-06B, D18/Q4).

Creates `assignment_rule_bindings`: one row per accepted assignment,
snapshotting the campaign revision effective at acceptance (rates, cap,
eligibility params, formula version) plus the frozen premium tier area
(target-zone ids + deterministic geometry hash, PR11) and the fail-closed
stationary policy marker (EXT-RM2-POLICY). Create only — no backfill:
assignments accepted before this migration have no binding and keep
payout_v2 exactly as before.

Revision ID: 0019_assignment_rule_bindings
Revises: 0018_payout_rule_revisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_assignment_rule_bindings"
down_revision: str | Sequence[str] | None = "0018_payout_rule_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assignment_rule_bindings",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("campaign_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("campaign_payout_rule_revisions.id"),
            nullable=False,
        ),
        sa.Column("hourly_rate_naira", sa.Numeric(14, 2), nullable=False),
        sa.Column("premium_hourly_rate_naira", sa.Numeric(14, 2), nullable=True),
        sa.Column("daily_payable_hours_cap", sa.Numeric(4, 2), nullable=True),
        sa.Column(
            "eligibility_params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("formula_version", sa.Text(), nullable=False),
        sa.Column(
            "premium_zone_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("premium_zone_geometry_hash", sa.Text(), nullable=False),
        sa.Column(
            "stationary_policy_marker",
            sa.Text(),
            server_default=sa.text("'ext-rm2-fail-closed'"),
            nullable=False,
        ),
        sa.Column(
            "bound_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "hourly_rate_naira >= 0",
            name="ck_assignment_rule_bindings_hourly_rate_non_negative",
        ),
        sa.CheckConstraint(
            "premium_hourly_rate_naira IS NULL OR premium_hourly_rate_naira >= 0",
            name="ck_assignment_rule_bindings_premium_rate_non_negative",
        ),
        sa.UniqueConstraint(
            "assignment_id",
            name="uq_assignment_rule_bindings_assignment_id",
        ),
    )
    op.create_index(
        "ix_assignment_rule_bindings_revision_id",
        "assignment_rule_bindings",
        ["revision_id"],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM assignment_rule_bindings) THEN "
            "RAISE EXCEPTION '0019 downgrade blocked: assignment payout bindings exist'; "
            "END IF; END $$;"
        )
    )
    op.drop_index(
        "ix_assignment_rule_bindings_revision_id",
        table_name="assignment_rule_bindings",
    )
    op.drop_table("assignment_rule_bindings")
