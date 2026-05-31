"""Create campaign zone table.

Revision ID: 0005_campaign_zones
Revises: 0004_campaigns_and_creatives
Create Date: 2026-05-31
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_campaign_zones"
down_revision: str | None = "0004_campaigns_and_creatives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class PostGISMultiPolygon(sa.types.UserDefinedType):
    def get_col_spec(self, **_: Any) -> str:
        return "geometry(MultiPolygon,4326)"


def upgrade() -> None:
    op.create_table(
        "campaign_zones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("zone_type", sa.Text(), nullable=False),
        sa.Column("geom", PostGISMultiPolygon(), nullable=False),
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
            "zone_type IN ('target', 'exclusion', 'bonus')",
            name="ck_campaign_zones_zone_type",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_zones_campaign_id", "campaign_zones", ["campaign_id"])
    op.create_index(
        "ix_campaign_zones_campaign_zone_type",
        "campaign_zones",
        ["campaign_id", "zone_type"],
    )
    op.create_index(
        "ix_campaign_zones_created_by_user_id",
        "campaign_zones",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_campaign_zones_geom",
        "campaign_zones",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_zones_geom", table_name="campaign_zones")
    op.drop_index("ix_campaign_zones_created_by_user_id", table_name="campaign_zones")
    op.drop_index("ix_campaign_zones_campaign_zone_type", table_name="campaign_zones")
    op.drop_index("ix_campaign_zones_campaign_id", table_name="campaign_zones")
    op.drop_table("campaign_zones")
