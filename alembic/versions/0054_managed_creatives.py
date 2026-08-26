"""Bind campaign creatives to clean managed stored files."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_managed_creatives"
down_revision: str | Sequence[str] | None = "0053_file_scanning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("campaign_creatives") as batch:
        batch.add_column(sa.Column("stored_file_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            "fk_campaign_creatives_stored_file",
            "stored_files",
            ["stored_file_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_campaign_creatives_stored_file",
            ["stored_file_id"],
        )
        batch.create_check_constraint(
            "ck_campaign_creatives_managed_asset_url",
            "stored_file_id IS NULL OR asset_url IS NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM campaign_creatives WHERE stored_file_id IS NOT NULL LIMIT 1)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0054 downgrade blocked: managed creative bindings are populated")
    with op.batch_alter_table("campaign_creatives") as batch:
        batch.drop_constraint("ck_campaign_creatives_managed_asset_url", type_="check")
        batch.drop_constraint("uq_campaign_creatives_stored_file", type_="unique")
        batch.drop_constraint("fk_campaign_creatives_stored_file", type_="foreignkey")
        batch.drop_column("stored_file_id")
