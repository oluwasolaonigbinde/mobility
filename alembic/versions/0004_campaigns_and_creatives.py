"""Create campaign and campaign creative tables.

Revision ID: 0004_campaigns_and_creatives
Revises: 0003_driver_vehicle_foundations
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_campaigns_and_creatives"
down_revision: str | None = "0003_driver_vehicle_foundations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("budget_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("daily_budget_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="NGN", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_campaigns_status",
        ),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_campaigns_currency_length"),
        sa.CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name="ck_campaigns_budget_amount_non_negative",
        ),
        sa.CheckConstraint(
            "daily_budget_amount IS NULL OR daily_budget_amount >= 0",
            name="ck_campaigns_daily_budget_amount_non_negative",
        ),
        sa.CheckConstraint(
            "budget_amount IS NULL OR daily_budget_amount IS NULL "
            "OR daily_budget_amount <= budget_amount",
            name="ck_campaigns_daily_budget_not_exceed_budget",
        ),
        sa.CheckConstraint(
            "start_at IS NULL OR end_at IS NULL OR start_at < end_at",
            name="ck_campaigns_date_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["advertiser_organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_organization_id", "campaigns", ["organization_id"])
    op.create_index(
        "ix_campaigns_organization_status",
        "campaigns",
        ["organization_id", "status"],
    )
    op.create_index("ix_campaigns_start_end", "campaigns", ["start_at", "end_at"])
    op.create_index("ix_campaigns_created_by_user_id", "campaigns", ["created_by_user_id"])

    op.create_table(
        "campaign_creatives",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("creative_type", sa.String(length=32), nullable=False),
        sa.Column("placement", sa.String(length=32), nullable=False),
        sa.Column("asset_url", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "creative_type IN ('image', 'video', 'html', 'text', 'other')",
            name="ck_campaign_creatives_creative_type",
        ),
        sa.CheckConstraint(
            "placement IN ('vehicle_exterior', 'vehicle_interior', "
            "'digital_screen', 'print', 'other')",
            name="ck_campaign_creatives_placement",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'archived')",
            name="ck_campaign_creatives_status",
        ),
        sa.CheckConstraint(
            "width_px IS NULL OR width_px > 0",
            name="ck_campaign_creatives_width_positive",
        ),
        sa.CheckConstraint(
            "height_px IS NULL OR height_px > 0",
            name="ck_campaign_creatives_height_positive",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0",
            name="ck_campaign_creatives_duration_positive",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_creatives_campaign_id", "campaign_creatives", ["campaign_id"])
    op.create_index(
        "ix_campaign_creatives_campaign_status",
        "campaign_creatives",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_campaign_creatives_creative_type",
        "campaign_creatives",
        ["creative_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_creatives_creative_type", table_name="campaign_creatives")
    op.drop_index("ix_campaign_creatives_campaign_status", table_name="campaign_creatives")
    op.drop_index("ix_campaign_creatives_campaign_id", table_name="campaign_creatives")
    op.drop_table("campaign_creatives")
    op.drop_index("ix_campaigns_created_by_user_id", table_name="campaigns")
    op.drop_index("ix_campaigns_start_end", table_name="campaigns")
    op.drop_index("ix_campaigns_organization_status", table_name="campaigns")
    op.drop_index("ix_campaigns_organization_id", table_name="campaigns")
    op.drop_table("campaigns")
