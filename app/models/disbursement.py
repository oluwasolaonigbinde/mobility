from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PayoutBatchStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    SUBMITTED = "submitted"
    RECONCILED = "reconciled"
    COMPLETED = "completed"
    FAILED = "failed"
    VOID = "void"


class PayoutBatchLineStatus(StrEnum):
    RESERVED = "reserved"
    SUBMITTED = "submitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VOID = "void"


class PayoutBatch(Base):
    __tablename__ = "payout_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'reserved', 'submitted', 'reconciled', "
            "'completed', 'failed', 'void')",
            name="ck_payout_batches_status",
        ),
        CheckConstraint("length(currency) = 3", name="ck_payout_batches_currency"),
        CheckConstraint("total_amount >= 0", name="ck_payout_batches_total_non_negative"),
        CheckConstraint(
            "(status = 'draft' AND instruction_set_fingerprint IS NULL) OR "
            "(status <> 'draft' AND instruction_set_fingerprint IS NOT NULL)",
            name="ck_payout_batches_reserved_fingerprint",
        ),
        CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> created_by_user_id",
            name="ck_payout_batches_maker_checker",
        ),
        Index("ix_payout_batches_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    instruction_set_fingerprint: Mapped[str | None] = mapped_column(String(64))
    provider_submission_reference: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutBatchLine(Base):
    __tablename__ = "payout_batch_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payout_batch_lines_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_payout_batch_lines_currency"),
        CheckConstraint(
            "length(instruction_fingerprint) = 64",
            name="ck_payout_batch_lines_instruction_fingerprint",
        ),
        CheckConstraint(
            "status IN ('reserved', 'submitted', 'succeeded', 'failed', 'void')",
            name="ck_payout_batch_lines_status",
        ),
        CheckConstraint(
            "(status IN ('reserved', 'void') AND provider_transfer_reference IS NULL) OR "
            "(status IN ('submitted', 'succeeded', 'failed') "
            "AND provider_transfer_reference IS NOT NULL)",
            name="ck_payout_batch_lines_provider_state",
        ),
        CheckConstraint(
            "(status = 'void' AND reservation_active = false) OR "
            "(status <> 'void' AND reservation_active = true)",
            name="ck_payout_batch_lines_active_state",
        ),
        Index("ix_payout_batch_lines_batch_id", "batch_id"),
        Index("ix_payout_batch_lines_ledger_entry_id", "ledger_entry_id"),
        Index(
            "uq_payout_batch_lines_active_ledger_entry",
            "ledger_entry_id",
            unique=True,
            sqlite_where=text("reservation_active = true"),
            postgresql_where=text("reservation_active = true"),
        ),
        Index(
            "uq_payout_batch_lines_provider_transfer_reference",
            "provider_transfer_reference",
            unique=True,
            sqlite_where=text("provider_transfer_reference IS NOT NULL"),
            postgresql_where=text("provider_transfer_reference IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batches.id", ondelete="RESTRICT"), nullable=False
    )
    ledger_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), nullable=False
    )
    payee_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_versions.id", ondelete="RESTRICT"), nullable=False
    )
    bank_account_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_bank_account_versions.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    instruction: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    instruction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16),
        default=PayoutBatchLineStatus.RESERVED,
        server_default=text("'reserved'"),
        nullable=False,
    )
    provider_transfer_reference: Mapped[str | None] = mapped_column(Text)
    reconciled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_provider_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutLineReconciliationEvent(Base):
    __tablename__ = "payout_line_reconciliation_events"
    __table_args__ = (
        CheckConstraint("source IN ('webhook', 'poll')", name="ck_payout_line_events_source"),
        CheckConstraint("outcome IN ('succeeded', 'failed')", name="ck_payout_line_events_outcome"),
        CheckConstraint(
            "length(evidence_fingerprint) = 64",
            name="ck_payout_line_events_evidence_fingerprint",
        ),
        Index("ix_payout_line_events_line_id", "line_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    line_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_batch_lines.id", ondelete="RESTRICT"), nullable=False
    )
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reconciled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DriverCurrencyDebtAccount(Base):
    __tablename__ = "driver_currency_debt_accounts"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="ck_driver_debt_accounts_currency"),
        CheckConstraint(
            "outstanding_amount >= 0 AND lifetime_incurred_amount >= 0 "
            "AND lifetime_allocated_amount >= 0",
            name="ck_driver_debt_accounts_amounts_non_negative",
        ),
        CheckConstraint(
            "lifetime_incurred_amount = outstanding_amount + lifetime_allocated_amount",
            name="ck_driver_debt_accounts_conservation",
        ),
        UniqueConstraint(
            "driver_profile_id", "currency", name="uq_driver_debt_accounts_driver_currency"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    driver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lifetime_incurred_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lifetime_allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PayoutDebtObligation(Base):
    __tablename__ = "payout_debt_obligations"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="ck_payout_debt_obligations_currency"),
        CheckConstraint(
            "original_amount > 0 AND outstanding_amount >= 0 "
            "AND outstanding_amount <= original_amount",
            name="ck_payout_debt_obligations_amounts",
        ),
        Index("ix_payout_debt_obligations_account", "debt_account_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    debt_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_currency_debt_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    source_reversal_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    correction_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payout_correction_orders.id", ondelete="RESTRICT")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtPaidSource(Base):
    __tablename__ = "payout_debt_paid_sources"
    __table_args__ = (
        UniqueConstraint(
            "debt_obligation_id",
            "paid_ledger_entry_id",
            name="uq_payout_debt_paid_sources_obligation_entry",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    debt_obligation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_obligations.id", ondelete="RESTRICT"), nullable=False
    )
    paid_ledger_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtSettlement(Base):
    __tablename__ = "payout_debt_settlements"
    __table_args__ = (
        CheckConstraint(
            "original_credit_amount > 0 AND allocated_amount > 0 "
            "AND allocated_amount <= original_credit_amount",
            name="ck_payout_debt_settlements_amounts",
        ),
        CheckConstraint(
            "(allocated_amount = original_credit_amount AND remainder_entry_id IS NULL) OR "
            "(allocated_amount < original_credit_amount AND remainder_entry_id IS NOT NULL)",
            name="ck_payout_debt_settlements_remainder",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    source_credit_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    remainder_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"), unique=True
    )
    original_credit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayoutDebtAllocation(Base):
    __tablename__ = "payout_debt_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payout_debt_allocations_amount_positive"),
        UniqueConstraint(
            "settlement_id",
            "debt_obligation_id",
            name="uq_payout_debt_allocations_settlement_obligation",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    settlement_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_settlements.id", ondelete="RESTRICT"), nullable=False
    )
    debt_obligation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payout_debt_obligations.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
