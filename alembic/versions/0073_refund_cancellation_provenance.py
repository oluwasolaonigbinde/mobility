"""Bind cash refund settlements to frozen campaign cancellations.

Revision ID: 0073_refund_cancellation_provenance
Revises: 0072_driver_application_terminal_status
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_refund_cancellation_provenance"
down_revision: str | Sequence[str] | None = "0072_driver_application_terminal_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refund_settlements",
        sa.Column("cancellation_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "refund_settlements",
        sa.Column("eligibility_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_refund_settlements_cancellation_id",
        "refund_settlements",
        "campaign_cancellations",
        ["cancellation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_refund_settlements_cancellation_id",
        "refund_settlements",
        ["cancellation_id"],
    )

    op.drop_constraint("ck_refund_settlements_authority", "refund_settlements", type_="check")
    op.drop_constraint(
        "ck_refund_settlements_eligibility_window",
        "refund_settlements",
        type_="check",
    )
    op.execute("DROP TRIGGER refund_settlements_append_only ON refund_settlements")
    op.execute(
        """
        WITH exact_cancellation AS (
            SELECT
                rs.id AS settlement_id,
                cancellation.id AS cancellation_id,
                cancellation.cutoff_at AS eligibility_evaluated_at
            FROM refund_settlements AS rs
            JOIN campaign_cancellations AS cancellation
              ON cancellation.campaign_id = rs.campaign_id
             AND cancellation.commercial_terms_id = rs.commercial_terms_id
             AND cancellation.currency = rs.currency
             AND cancellation.disposition = 'cash_refund_due'
             AND cancellation.funding_authorized_at = rs.funding_authorized_at
             AND cancellation.refund_eligibility_ends_at = rs.eligibility_ends_at
             AND cancellation.production_start_id IS NOT DISTINCT FROM rs.production_start_id
             AND cancellation.cutoff_at <= rs.recorded_at
             AND cancellation.cutoff_at < cancellation.refund_eligibility_ends_at
            WHERE rs.disposition = 'refund_recorded'
              AND (
                  SELECT COALESCE(SUM(other.amount), 0)
                  FROM refund_settlements AS other
                  WHERE other.campaign_id = cancellation.campaign_id
                    AND other.disposition = 'refund_recorded'
              ) <= cancellation.refundable_amount
        )
        UPDATE refund_settlements AS settlement
        SET cancellation_id = exact_cancellation.cancellation_id,
            eligibility_evaluated_at = exact_cancellation.eligibility_evaluated_at
        FROM exact_cancellation
        WHERE settlement.id = exact_cancellation.settlement_id
        """
    )
    op.execute(
        "CREATE TRIGGER refund_settlements_append_only "
        "BEFORE UPDATE OR DELETE ON refund_settlements "
        "FOR EACH ROW EXECUTE FUNCTION reject_receipt_authority_mutation()"
    )

    op.create_check_constraint(
        "ck_refund_settlements_authority",
        "refund_settlements",
        "(disposition = 'refund_recorded' AND receipt_id IS NOT NULL AND amount > 0 "
        "AND funding_authorized_at IS NOT NULL AND eligibility_ends_at IS NOT NULL) OR "
        "(disposition = 'credit_settlement_recorded' AND receipt_id IS NULL "
        "AND amount = 0 AND funding_authorized_at IS NULL AND eligibility_ends_at IS NULL "
        "AND cancellation_id IS NULL AND eligibility_evaluated_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_refund_settlements_frozen_provenance",
        "refund_settlements",
        "(cancellation_id IS NULL AND eligibility_evaluated_at IS NULL) OR "
        "(cancellation_id IS NOT NULL AND eligibility_evaluated_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_refund_settlements_eligibility_window",
        "refund_settlements",
        "eligibility_evaluated_at IS NULL OR eligibility_evaluated_at < eligibility_ends_at",
    )


def downgrade() -> None:
    bind = op.get_bind()
    frozen_provenance = bool(
        bind.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM refund_settlements "
                "WHERE cancellation_id IS NOT NULL "
                "OR eligibility_evaluated_at IS NOT NULL)"
            )
        ).scalar_one()
    )
    if frozen_provenance:
        raise RuntimeError(
            "0073 downgrade blocked: frozen refund cancellation provenance is authoritative"
        )

    op.drop_constraint(
        "ck_refund_settlements_frozen_provenance",
        "refund_settlements",
        type_="check",
    )
    op.drop_constraint(
        "ck_refund_settlements_eligibility_window",
        "refund_settlements",
        type_="check",
    )
    op.drop_constraint("ck_refund_settlements_authority", "refund_settlements", type_="check")
    op.create_check_constraint(
        "ck_refund_settlements_authority",
        "refund_settlements",
        "(disposition = 'refund_recorded' AND receipt_id IS NOT NULL AND amount > 0 "
        "AND funding_authorized_at IS NOT NULL AND eligibility_ends_at IS NOT NULL) OR "
        "(disposition = 'credit_settlement_recorded' AND receipt_id IS NULL "
        "AND amount = 0 AND funding_authorized_at IS NULL AND eligibility_ends_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_refund_settlements_eligibility_window",
        "refund_settlements",
        "eligibility_ends_at IS NULL OR recorded_at < eligibility_ends_at",
    )
    op.drop_index("ix_refund_settlements_cancellation_id", table_name="refund_settlements")
    op.drop_constraint(
        "fk_refund_settlements_cancellation_id",
        "refund_settlements",
        type_="foreignkey",
    )
    op.drop_column("refund_settlements", "eligibility_evaluated_at")
    op.drop_column("refund_settlements", "cancellation_id")
