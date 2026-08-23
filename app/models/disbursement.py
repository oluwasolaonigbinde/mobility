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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PayoutBatchStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    SUBMITTED = "submitted"


class PayoutBatch(Base):
    __tablename__ = "payout_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'reserved', 'submitted')", name="ck_payout_batches_status"
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
        Index("ix_payout_batch_lines_batch_id", "batch_id"),
        Index("ix_payout_batch_lines_ledger_entry_id", "ledger_entry_id"),
        Index(
            "uq_payout_batch_lines_active_ledger_entry",
            "ledger_entry_id",
            unique=True,
            sqlite_where=text("reservation_active = true"),
            postgresql_where=text("reservation_active = true"),
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
    reservation_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
