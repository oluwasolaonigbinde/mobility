"""Queue Paystack transfer evidence before money-state reconciliation.

Revision ID: 0097_payout_provider_event_queue
Revises: 0096_payment_checkout_intents
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0097_payout_provider_event_queue"
down_revision = "0096_payment_checkout_intents"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "payout_provider_events",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("provider_transfer_reference", sa.String(length=255), nullable=False),
        sa.Column("provider_reference", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("provider_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'failed')", name="ck_payout_provider_events_outcome"
        ),
        sa.CheckConstraint("amount > 0", name="ck_payout_provider_events_amount"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_provider_events_currency"),
        sa.CheckConstraint(
            "length(evidence_fingerprint) = 64", name="ck_payout_provider_events_fingerprint"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payout_provider_events_identity"
        ),
    )
    op.create_table(
        "payout_provider_event_processing_attempts",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider_event_id", UUID, nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("reconciliation_event_id", UUID, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number > 0", name="ck_payout_provider_attempts_number"),
        sa.CheckConstraint(
            "outcome IN ('processed', 'failed')", name="ck_payout_provider_attempts_outcome"
        ),
        sa.CheckConstraint(
            "(outcome = 'processed' AND reconciliation_event_id IS NOT NULL "
            "AND error_code IS NULL) OR (outcome = 'failed' "
            "AND reconciliation_event_id IS NULL AND error_code IS NOT NULL)",
            name="ck_payout_provider_attempts_result",
        ),
        sa.ForeignKeyConstraint(
            ["provider_event_id"], ["payout_provider_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_event_id"],
            ["payout_line_reconciliation_events.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_id", "attempt_number", name="uq_payout_provider_attempt_sequence"
        ),
    )
    op.create_index(
        "ix_payout_provider_event_processing_attempts_provider_event_id",
        "payout_provider_event_processing_attempts",
        ["provider_event_id"],
    )


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM payout_provider_events"))
    if count:
        raise RuntimeError(f"0097 downgrade blocked: {count} payout provider event rows exist")
    op.drop_index(
        "ix_payout_provider_event_processing_attempts_provider_event_id",
        table_name="payout_provider_event_processing_attempts",
    )
    op.drop_table("payout_provider_event_processing_attempts")
    op.drop_table("payout_provider_events")
