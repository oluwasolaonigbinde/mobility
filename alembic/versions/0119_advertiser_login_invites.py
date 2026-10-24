"""Reuse password tokens for explicit company login invitations (D130)."""

import sqlalchemy as sa

from alembic import op

revision = "0119_advertiser_login_invites"
down_revision = "0118_installation_review_json_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "password_reset_tokens",
        sa.Column("purpose", sa.String(32), nullable=False, server_default="password_reset"),
    )
    op.add_column("password_reset_tokens", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_password_reset_tokens_organization",
        "password_reset_tokens",
        "advertiser_organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("password_reset_tokens", "attempt_id", existing_type=sa.UUID(), nullable=True)
    op.create_check_constraint(
        "ck_password_reset_tokens_purpose",
        "password_reset_tokens",
        "(purpose = 'password_reset' AND attempt_id IS NOT NULL AND organization_id IS NULL) OR "
        "(purpose = 'advertiser_invite' AND attempt_id IS NULL AND organization_id IS NOT NULL)",
    )
    op.drop_column("campaign_enquiries", "converted_owner_user_id")


def downgrade() -> None:
    op.add_column(
        "campaign_enquiries", sa.Column("converted_owner_user_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "campaign_enquiries_converted_owner_user_id_fkey",
        "campaign_enquiries",
        "users",
        ["converted_owner_user_id"],
        ["id"],
    )
    op.drop_constraint("ck_password_reset_tokens_purpose", "password_reset_tokens", type_="check")
    op.execute("DELETE FROM password_reset_tokens WHERE purpose = 'advertiser_invite'")
    op.alter_column("password_reset_tokens", "attempt_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint(
        "fk_password_reset_tokens_organization", "password_reset_tokens", type_="foreignkey"
    )
    op.drop_column("password_reset_tokens", "organization_id")
    op.drop_column("password_reset_tokens", "purpose")
