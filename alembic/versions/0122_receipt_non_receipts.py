"""Append-only "payment not received" facts for reversed receipts (REQ-325).

The reversal kind itself is recorded in the reversal audit metadata (JSON), so it
needs no schema change.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0122_receipt_non_receipts"
down_revision = "0121_payout_recovery_offsets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipt_non_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "receipt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payment_receipts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("receipt_id", name="uq_receipt_non_receipts_receipt"),
    )
    op.execute(
        "CREATE TRIGGER receipt_non_receipts_append_only BEFORE DELETE OR UPDATE "
        "ON receipt_non_receipts FOR EACH ROW "
        "EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    op.drop_table("receipt_non_receipts")
