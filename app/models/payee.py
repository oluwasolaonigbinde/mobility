from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PayeeType(StrEnum):
    DRIVER = "driver"


class Payee(Base):
    """Stable payee identity; all payout-facing attributes live in versions."""

    __tablename__ = "payees"
    __table_args__ = (
        CheckConstraint("payee_type = 'driver'", name="ck_payees_type"),
        UniqueConstraint(
            "tenant_id",
            "payee_type",
            "subject_id",
            name="uq_payees_tenant_type_subject",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payee_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayeeVersion(Base):
    """Immutable exact payee snapshot frozen by later payout instructions."""

    __tablename__ = "payee_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_payee_versions_positive_version"),
        CheckConstraint("payee_type = 'driver'", name="ck_payee_versions_type"),
        UniqueConstraint("payee_id", "version", name="uq_payee_versions_payee_version"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    payee_id: Mapped[UUID] = mapped_column(
        ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payee_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayeeBankAccount(Base):
    """Stable account identity. Pilot policy permits one account chain per payee."""

    __tablename__ = "payee_bank_accounts"
    __table_args__ = (UniqueConstraint("payee_id", name="uq_payee_bank_accounts_payee_id"),)

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    payee_id: Mapped[UUID] = mapped_column(
        ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayeeBankAccountVersion(Base):
    """Immutable verified and encrypted account snapshot."""

    __tablename__ = "payee_bank_account_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_payee_bank_account_versions_positive_version"),
        CheckConstraint(
            "encryption_algorithm = 'AES-256-GCM'",
            name="ck_payee_bank_account_versions_algorithm",
        ),
        CheckConstraint(
            "encryption_key_version > 0",
            name="ck_payee_bank_account_versions_positive_key_version",
        ),
        CheckConstraint(
            "length(verification_reference_sha256) = 64",
            name="ck_payee_bank_account_versions_verification_hash",
        ),
        UniqueConstraint(
            "bank_account_id",
            "version",
            name="uq_payee_bank_account_versions_account_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    bank_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_bank_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payee_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("payee_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    encrypted_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    encryption_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verified_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
