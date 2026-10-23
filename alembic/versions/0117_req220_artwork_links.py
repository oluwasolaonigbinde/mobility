"""Per-artwork short links and daily aggregate scan counts (REQ-223)."""

import sqlalchemy as sa

from alembic import op

revision = "0117_req220_artwork_links"
down_revision = "0116_campaign_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artwork_links",
        sa.Column("creative_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["creative_id"], ["campaign_creatives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("creative_id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "artwork_scan_days",
        sa.Column("creative_id", sa.UUID(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("scans", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("scans >= 0", name="ck_artwork_scan_days_non_negative"),
        sa.ForeignKeyConstraint(["creative_id"], ["artwork_links.creative_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("creative_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("artwork_scan_days")
    op.drop_table("artwork_links")
