"""Add provider-neutral payment gateway event processing.

Revision ID: 0038_payment_gateway_events
Revises: 0037_funded_liability_authority
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_payment_gateway_events"
down_revision: str | Sequence[str] | None = "0037_funded_liability_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "payment_gateway_events",
        _uuid("id"),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("external_transaction_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("commercial_terms_reference", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payer_name", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('payment_confirmed', 'payment_failed')",
            name="ck_payment_gateway_events_type",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payment_gateway_events_amount"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payment_gateway_events_currency"),
        sa.CheckConstraint(
            "length(evidence_fingerprint) = 64", name="ck_payment_gateway_events_fingerprint"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_gateway_events_provider_event"
        ),
    )
    op.add_column(
        "receipt_reconciliations",
        sa.Column("verification_source", sa.String(32), server_default="manual", nullable=False),
    )
    op.add_column(
        "receipt_reconciliations",
        sa.Column("provider_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("receipt_reconciliations", "reconciled_by_user_id", nullable=True)
    op.create_foreign_key(
        "fk_receipt_reconciliations_provider_event_id",
        "receipt_reconciliations",
        "payment_gateway_events",
        ["provider_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_receipt_reconciliations_provider_event",
        "receipt_reconciliations",
        ["provider_event_id"],
    )
    op.create_check_constraint(
        "ck_receipt_reconciliations_verification_source",
        "receipt_reconciliations",
        "(verification_source = 'manual' AND reconciled_by_user_id IS NOT NULL "
        "AND provider_event_id IS NULL) OR "
        "(verification_source = 'provider' AND reconciled_by_user_id IS NULL "
        "AND provider_event_id IS NOT NULL)",
    )
    op.add_column(
        "receipt_allocations",
        sa.Column("allocation_source", sa.String(32), server_default="manual", nullable=False),
    )
    op.add_column(
        "receipt_allocations",
        sa.Column("provider_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.alter_column("receipt_allocations", "allocated_by_user_id", nullable=True)
    op.create_foreign_key(
        "fk_receipt_allocations_provider_event_id",
        "receipt_allocations",
        "payment_gateway_events",
        ["provider_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_receipt_allocations_provider_event",
        "receipt_allocations",
        ["provider_event_id"],
    )
    op.create_check_constraint(
        "ck_receipt_allocations_source",
        "receipt_allocations",
        "(allocation_source = 'manual' AND allocated_by_user_id IS NOT NULL "
        "AND provider_event_id IS NULL) OR "
        "(allocation_source = 'provider' AND allocated_by_user_id IS NULL "
        "AND provider_event_id IS NOT NULL)",
    )
    op.create_table(
        "payment_gateway_processing_attempts",
        _uuid("id"),
        _uuid("gateway_event_id"),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        _uuid("receipt_id", nullable=True),
        _uuid("allocation_id", nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number > 0", name="ck_payment_gateway_attempts_number"),
        sa.CheckConstraint(
            "outcome IN ('confirmed', 'ignored_failed', 'failed')",
            name="ck_payment_gateway_attempts_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'confirmed' AND receipt_id IS NOT NULL AND allocation_id IS NOT NULL "
            "AND error_code IS NULL) OR "
            "(outcome = 'ignored_failed' AND receipt_id IS NULL AND allocation_id IS NULL "
            "AND error_code IS NULL) OR "
            "(outcome = 'failed' AND receipt_id IS NULL AND allocation_id IS NULL "
            "AND error_code IS NOT NULL)",
            name="ck_payment_gateway_attempts_result",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_event_id"], ["payment_gateway_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["receipt_id"], ["payment_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["allocation_id"], ["receipt_allocations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "gateway_event_id", "attempt_number", name="uq_payment_gateway_attempt_sequence"
        ),
    )
    op.create_index(
        "ix_payment_gateway_processing_attempts_gateway_event_id",
        "payment_gateway_processing_attempts",
        ["gateway_event_id"],
    )
    for table in ("payment_gateway_events", "payment_gateway_processing_attempts"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payment_gateway_events) "
            "OR EXISTS (SELECT 1 FROM payment_gateway_processing_attempts) "
            "OR EXISTS (SELECT 1 FROM receipt_reconciliations "
            "WHERE verification_source = 'provider') "
            "OR EXISTS (SELECT 1 FROM receipt_allocations WHERE allocation_source = 'provider')"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0038 downgrade blocked: payment gateway authority exists")
    for table in ("payment_gateway_processing_attempts", "payment_gateway_events"):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.drop_index(
        "ix_payment_gateway_processing_attempts_gateway_event_id",
        table_name="payment_gateway_processing_attempts",
    )
    op.drop_table("payment_gateway_processing_attempts")
    op.drop_constraint("ck_receipt_allocations_source", "receipt_allocations", type_="check")
    op.drop_constraint(
        "uq_receipt_allocations_provider_event",
        "receipt_allocations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_receipt_allocations_provider_event_id",
        "receipt_allocations",
        type_="foreignkey",
    )
    op.drop_column("receipt_allocations", "provider_event_id")
    op.drop_column("receipt_allocations", "allocation_source")
    op.alter_column("receipt_allocations", "allocated_by_user_id", nullable=False)
    op.drop_constraint(
        "uq_receipt_reconciliations_provider_event",
        "receipt_reconciliations",
        type_="unique",
    )
    op.drop_constraint(
        "ck_receipt_reconciliations_verification_source",
        "receipt_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "fk_receipt_reconciliations_provider_event_id",
        "receipt_reconciliations",
        type_="foreignkey",
    )
    op.drop_column("receipt_reconciliations", "provider_event_id")
    op.drop_column("receipt_reconciliations", "verification_source")
    op.alter_column("receipt_reconciliations", "reconciled_by_user_id", nullable=False)
    op.drop_table("payment_gateway_events")
