"""Replace staff-send verification with driver-only reverse verification.

Revision ID: 0100_reverse_phone_verification
Revises: 0099_automatic_payout_scan_cursor
"""

import sqlalchemy as sa

from alembic import op

revision = "0100_reverse_phone_verification"
down_revision = "0099_automatic_payout_scan_cursor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_phone_challenges_send_evidence", "phone_verification_challenges", type_="check"
    )
    op.drop_constraint("ck_phone_challenges_status", "phone_verification_challenges", type_="check")
    op.execute(
        "UPDATE phone_verification_challenges SET status = 'expired' "
        "WHERE status IN ('pending_operator', 'sent')"
    )
    for name in (
        "sent_by_user_id",
        "sent_channel",
        "sent_at",
        "operator_evidence_reference",
        "provider_message_id",
    ):
        op.drop_column("phone_verification_challenges", name)
    op.add_column(
        "phone_verification_challenges",
        sa.Column(
            "verified_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_phone_challenges_status",
        "phone_verification_challenges",
        "status IN ('pending', 'verified', 'expired', 'exhausted')",
    )


def downgrade() -> None:
    raise RuntimeError("Reverse phone verification replaces the obsolete development flow")
