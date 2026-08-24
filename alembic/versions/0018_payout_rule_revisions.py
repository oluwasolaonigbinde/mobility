"""Immutable effective-dated payout-rule revisions (MNY-06A, D18).

Creates append-only `campaign_payout_rule_revisions` and backfills exactly one
revision per campaign from its ACTIVE payout_v2 rule (at most one exists per
campaign via uq_campaign_payout_rules_active_campaign): revision_number = 1,
effective_from = the rule row's created_at, values copied verbatim,
formula_version = 'payout_v3' — the v3 genesis snapshot only (PR3). payout_v2
pricing keeps reading the frozen rule row, so this migration moves no money.
payout_v1 rules and inactive rules are not backfilled: revisions require the
hourly value set and represent the campaign's governing chain. Pre-migration
mutation history is not reconstructed — the old update path audited field
names only (PR9).

Revision ID: 0018_payout_rule_revisions
Revises: 0017_seal_review_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_payout_rule_revisions"
down_revision: str | Sequence[str] | None = "0017_seal_review_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL_REASON = (
    "backfill: values as observed at migration 0018; pre-migration mutation"
    " history not reconstructed (names-only audit)"
)


def upgrade() -> None:
    op.create_table(
        "campaign_payout_rule_revisions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payout_rule_id",
            sa.Uuid(),
            sa.ForeignKey("campaign_payout_rules.id"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
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
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_campaign_payout_rule_revisions_number_ge_1",
        ),
        sa.CheckConstraint(
            "hourly_rate_naira >= 0",
            name="ck_campaign_payout_rule_revisions_hourly_rate_non_negative",
        ),
        sa.CheckConstraint(
            "premium_hourly_rate_naira IS NULL OR premium_hourly_rate_naira >= 0",
            name="ck_campaign_payout_rule_revisions_premium_rate_non_negative",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "revision_number",
            name="uq_campaign_payout_rule_revisions_campaign_number",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "effective_from",
            name="uq_campaign_payout_rule_revisions_campaign_effective",
        ),
    )
    op.create_index(
        "ix_campaign_payout_rule_revisions_campaign_id",
        "campaign_payout_rule_revisions",
        ["campaign_id"],
    )
    op.create_index(
        "ix_campaign_payout_rule_revisions_payout_rule_id",
        "campaign_payout_rule_revisions",
        ["payout_rule_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO campaign_payout_rule_revisions
                (id, campaign_id, payout_rule_id, revision_number, effective_from,
                 hourly_rate_naira, premium_hourly_rate_naira,
                 daily_payable_hours_cap, eligibility_params, formula_version,
                 reason, created_by_user_id, created_at)
            SELECT gen_random_uuid(), r.campaign_id, r.id, 1, r.created_at,
                   r.hourly_rate_naira, NULL,
                   r.daily_payable_hours_cap,
                   COALESCE(r.eligibility_params, '{}'::jsonb), 'payout_v3',
                   :reason, r.created_by_user_id, now()
            FROM campaign_payout_rules r
            WHERE r.formula_version = 'payout_v2'
              AND r.status = 'active'
            """
        ).bindparams(reason=BACKFILL_REASON)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM campaign_payout_rule_revisions) THEN "
            "RAISE EXCEPTION '0018 downgrade blocked: payout rule revisions exist'; "
            "END IF; END $$;"
        )
    )
    op.drop_index(
        "ix_campaign_payout_rule_revisions_payout_rule_id",
        table_name="campaign_payout_rule_revisions",
    )
    op.drop_index(
        "ix_campaign_payout_rule_revisions_campaign_id",
        table_name="campaign_payout_rule_revisions",
    )
    op.drop_table("campaign_payout_rule_revisions")
