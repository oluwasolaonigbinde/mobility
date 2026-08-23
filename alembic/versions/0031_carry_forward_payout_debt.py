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
