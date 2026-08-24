"""Add currency-scoped carry-forward payout debt and allocation provenance.

Revision ID: 0031_carry_forward_payout_debt
Revises: 0030_provider_line_reconciliation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031_carry_forward_payout_debt"
down_revision: str | Sequence[str] | None = "0030_provider_line_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_column(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.drop_constraint(
        "ck_earnings_ledger_entries_entry_type", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_entry_type",
        "earnings_ledger_entries",
        "entry_type IN ('trip_payout', 'adjustment', 'reversal', 'debt_remainder')",
    )
    op.create_table(
        "driver_currency_debt_accounts",
        _uuid_column("id"),
        _uuid_column("driver_profile_id"),
        _uuid_column("driver_user_id"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("outstanding_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("lifetime_incurred_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("lifetime_allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_driver_debt_accounts_currency"),
        sa.CheckConstraint(
            "outstanding_amount >= 0 AND lifetime_incurred_amount >= 0 "
            "AND lifetime_allocated_amount >= 0",
            name="ck_driver_debt_accounts_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "lifetime_incurred_amount = outstanding_amount + lifetime_allocated_amount",
            name="ck_driver_debt_accounts_conservation",
        ),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "driver_profile_id",
            "currency",
            name="uq_driver_debt_accounts_driver_currency",
        ),
    )
    op.create_table(
        "payout_debt_obligations",
        _uuid_column("id"),
        _uuid_column("debt_account_id"),
        _uuid_column("source_reversal_entry_id"),
        _uuid_column("correction_order_id", nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("original_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("outstanding_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_debt_obligations_currency"),
        sa.CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0 "
            "AND outstanding_amount <= original_amount",
            name="ck_payout_debt_obligations_amounts",
        ),
        sa.ForeignKeyConstraint(
            ["debt_account_id"], ["driver_currency_debt_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_reversal_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["correction_order_id"], ["payout_correction_orders.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_reversal_entry_id", name="uq_payout_debt_obligations_source_reversal"
        ),
    )
    op.create_index(
        "ix_payout_debt_obligations_account",
        "payout_debt_obligations",
        ["debt_account_id", "created_at"],
    )
    op.create_table(
        "payout_debt_paid_sources",
        _uuid_column("id"),
        _uuid_column("debt_obligation_id"),
        _uuid_column("paid_ledger_entry_id"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["debt_obligation_id"], ["payout_debt_obligations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["paid_ledger_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "debt_obligation_id",
            "paid_ledger_entry_id",
            name="uq_payout_debt_paid_sources_obligation_entry",
        ),
    )
    op.create_table(
        "payout_debt_settlements",
        _uuid_column("id"),
        _uuid_column("source_credit_entry_id"),
        _uuid_column("remainder_entry_id", nullable=True),
        sa.Column("original_credit_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        _uuid_column("created_by_user_id"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "original_credit_amount > 0 AND allocated_amount > 0 "
            "AND allocated_amount <= original_credit_amount",
            name="ck_payout_debt_settlements_amounts",
        ),
        sa.CheckConstraint(
            "(allocated_amount = original_credit_amount AND remainder_entry_id IS NULL) OR "
            "(allocated_amount < original_credit_amount AND remainder_entry_id IS NOT NULL)",
            name="ck_payout_debt_settlements_remainder",
        ),
        sa.ForeignKeyConstraint(
            ["source_credit_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["remainder_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_credit_entry_id", name="uq_payout_debt_settlements_source_credit"
        ),
        sa.UniqueConstraint("remainder_entry_id", name="uq_payout_debt_settlements_remainder"),
        sa.UniqueConstraint("idempotency_key", name="uq_payout_debt_settlements_idempotency"),
    )
    op.create_table(
        "payout_debt_allocations",
        _uuid_column("id"),
        _uuid_column("settlement_id"),
        _uuid_column("debt_obligation_id"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount > 0", name="ck_payout_debt_allocations_amount_positive"),
        sa.ForeignKeyConstraint(
            ["settlement_id"], ["payout_debt_settlements.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["debt_obligation_id"], ["payout_debt_obligations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "settlement_id",
            "debt_obligation_id",
            name="uq_payout_debt_allocations_settlement_obligation",
        ),
    )
    _backfill_available_paid_reversal_debt()


def _backfill_available_paid_reversal_debt() -> None:
    """Bring legacy, already-available reversals into debt authority.

    This exactly matches the runtime entry point: an available reversal is
    debt, with same-trip paid sources linked when they exist. An affected
    driver/currency with a live non-succeeded reservation is unsafe because
    the reservation was made before debt eligibility existed, so fail before
    inserting any authority rows.
    """
    bind = op.get_bind()
    eligible = """
        r.entry_type = 'reversal'
        AND r.status = 'available'
        AND r.amount > 0
    """
    unsafe = bind.execute(
        sa.text(
            f"""
            SELECT r.id
            FROM earnings_ledger_entries r
            WHERE {eligible}
              AND EXISTS (
                SELECT 1
                FROM payout_batch_lines line
                JOIN earnings_ledger_entries reserved
                  ON reserved.id = line.ledger_entry_id
                WHERE line.reservation_active = true
                  AND line.status <> 'succeeded'
                  AND reserved.driver_profile_id = r.driver_profile_id
                  AND reserved.currency = r.currency
              )
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if unsafe is not None:
        raise RuntimeError(
            "0031 upgrade blocked: active payout reservation conflicts with eligible reversal debt"
        )

    # Every statement is conflict-safe. Alembic normally applies a revision
    # once, but this preserves conservation if an operator replays the
    # migration-local work after an interrupted disposable-environment run.
    bind.execute(
        sa.text(
            f"""
            INSERT INTO driver_currency_debt_accounts
              (id, driver_profile_id, driver_user_id, currency,
               outstanding_amount, lifetime_incurred_amount, lifetime_allocated_amount)
            SELECT gen_random_uuid(), r.driver_profile_id, r.driver_user_id, r.currency,
                   0, 0, 0
            FROM earnings_ledger_entries r
            WHERE {eligible}
            GROUP BY r.driver_profile_id, r.driver_user_id, r.currency
            ON CONFLICT (driver_profile_id, currency) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO payout_debt_obligations
              (id, debt_account_id, source_reversal_entry_id, correction_order_id,
               currency, original_amount, outstanding_amount)
            SELECT gen_random_uuid(), account.id, r.id, NULL,
                   r.currency, r.amount, r.amount
            FROM earnings_ledger_entries r
            JOIN driver_currency_debt_accounts account
              ON account.driver_profile_id = r.driver_profile_id
             AND account.currency = r.currency
            WHERE {eligible}
            ON CONFLICT (source_reversal_entry_id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO payout_debt_paid_sources
              (id, debt_obligation_id, paid_ledger_entry_id)
            SELECT gen_random_uuid(), obligation.id, paid.id
            FROM payout_debt_obligations obligation
            JOIN earnings_ledger_entries reversal
              ON reversal.id = obligation.source_reversal_entry_id
            JOIN earnings_ledger_entries paid
              ON paid.driver_profile_id = reversal.driver_profile_id
             AND paid.trip_session_id = reversal.trip_session_id
             AND paid.currency = reversal.currency
             AND paid.status = 'paid'
             AND paid.entry_type <> 'reversal'
            ON CONFLICT (debt_obligation_id, paid_ledger_entry_id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            WITH obligation_totals AS (
              SELECT debt_account_id, COALESCE(SUM(outstanding_amount), 0) AS outstanding
              FROM payout_debt_obligations
              GROUP BY debt_account_id
            )
            UPDATE driver_currency_debt_accounts account
            SET outstanding_amount = totals.outstanding,
                lifetime_incurred_amount = totals.outstanding + account.lifetime_allocated_amount
            FROM obligation_totals totals
            WHERE account.id = totals.debt_account_id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM driver_currency_debt_accounts) "
            "OR EXISTS (SELECT 1 FROM payout_debt_obligations) "
            "OR EXISTS (SELECT 1 FROM payout_debt_paid_sources) "
            "OR EXISTS (SELECT 1 FROM payout_debt_settlements) "
            "OR EXISTS (SELECT 1 FROM payout_debt_allocations) "
            "OR EXISTS (SELECT 1 FROM earnings_ledger_entries "
            "WHERE entry_type = 'debt_remainder')"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0031 downgrade blocked: carry-forward debt authority exists")

    op.drop_table("payout_debt_allocations")
    op.drop_table("payout_debt_settlements")
    op.drop_table("payout_debt_paid_sources")
    op.drop_index("ix_payout_debt_obligations_account", table_name="payout_debt_obligations")
    op.drop_table("payout_debt_obligations")
    op.drop_table("driver_currency_debt_accounts")
    op.drop_constraint(
        "ck_earnings_ledger_entries_entry_type", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_entry_type",
        "earnings_ledger_entries",
        "entry_type IN ('trip_payout', 'adjustment', 'reversal')",
    )
