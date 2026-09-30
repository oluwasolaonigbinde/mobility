"""Preserve Paystack event kind and explicit unallocated confirmed cash.

Revision ID: 0098_paystack_edge_case_evidence
Revises: 0097_payout_provider_event_queue
"""

import sqlalchemy as sa

from alembic import op

revision = "0098_paystack_edge_case_evidence"
down_revision = "0097_payout_provider_event_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payout_provider_events",
        sa.Column("provider_event_type", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE payout_provider_events SET provider_event_type = "
        "split_part(provider_event_id, ':', 1)"
    )
    op.alter_column("payout_provider_events", "provider_event_type", nullable=False)

    op.drop_constraint(
        "ck_payment_gateway_attempts_outcome",
        "payment_gateway_processing_attempts",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_gateway_attempts_result",
        "payment_gateway_processing_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payment_gateway_attempts_outcome",
        "payment_gateway_processing_attempts",
        "outcome IN ('confirmed', 'confirmed_unallocated', 'ignored_failed', 'failed')",
    )
    op.create_check_constraint(
        "ck_payment_gateway_attempts_result",
        "payment_gateway_processing_attempts",
        "(outcome = 'confirmed' AND receipt_id IS NOT NULL AND allocation_id IS NOT NULL "
        "AND error_code IS NULL) OR "
        "(outcome = 'confirmed_unallocated' AND receipt_id IS NOT NULL "
        "AND allocation_id IS NULL AND error_code IS NULL) OR "
        "(outcome = 'ignored_failed' AND receipt_id IS NULL AND allocation_id IS NULL "
        "AND error_code IS NULL) OR "
        "(outcome = 'failed' AND receipt_id IS NULL AND allocation_id IS NULL "
        "AND error_code IS NOT NULL)",
    )


def downgrade() -> None:
    unallocated = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM payment_gateway_processing_attempts "
            "WHERE outcome = 'confirmed_unallocated'"
        )
    )
    if unallocated:
        raise RuntimeError(
            f"0098 downgrade blocked: {unallocated} unallocated confirmed payment rows exist"
        )
    op.drop_constraint(
        "ck_payment_gateway_attempts_result",
        "payment_gateway_processing_attempts",
        type_="check",
    )
    op.drop_constraint(
        "ck_payment_gateway_attempts_outcome",
        "payment_gateway_processing_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payment_gateway_attempts_outcome",
        "payment_gateway_processing_attempts",
        "outcome IN ('confirmed', 'ignored_failed', 'failed')",
    )
    op.create_check_constraint(
        "ck_payment_gateway_attempts_result",
        "payment_gateway_processing_attempts",
        "(outcome = 'confirmed' AND receipt_id IS NOT NULL AND allocation_id IS NOT NULL "
        "AND error_code IS NULL) OR "
        "(outcome = 'ignored_failed' AND receipt_id IS NULL AND allocation_id IS NULL "
        "AND error_code IS NULL) OR "
        "(outcome = 'failed' AND receipt_id IS NULL AND allocation_id IS NULL "
        "AND error_code IS NOT NULL)",
    )
    op.drop_column("payout_provider_events", "provider_event_type")
