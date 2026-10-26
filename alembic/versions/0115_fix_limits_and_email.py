"""Remove email receipt machinery; delivery records are sent or failed.

Revision ID: 0115_fix_limits_and_email
Revises: 0114_simplify_campaign_authority
"""

from alembic import op

revision = "0115_fix_limits_and_email"
down_revision = "0114_simplify_campaign_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("notification_delivery_receipts")
    op.execute("DROP FUNCTION reject_notification_delivery_receipt_mutation()")
    op.execute("UPDATE notifications SET status = 'sent' WHERE status = 'delivered'")
    op.drop_column("notifications", "delivered_at")
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_status", "notifications", "status IN ('pending', 'sent', 'failed')"
    )


def downgrade() -> None:
    raise RuntimeError("Removed pilot email receipts are not restored")
