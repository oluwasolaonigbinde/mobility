from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DriverApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DriverApplication(Base):
    """Public driver-joining authority, separate from profile metadata.

    The submitted contact snapshot is intentionally allowlisted.  The status
    reference is stored only as a digest; the plaintext is returned once to a
    public applicant and is never part of an admin projection.
    """

    __tablename__ = "driver_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_driver_applications_status",
        ),
        UniqueConstraint("user_id", name="uq_driver_applications_user_id"),
        UniqueConstraint("driver_profile_id", name="uq_driver_applications_driver_profile_id"),
        UniqueConstraint(
            "status_reference_sha256",
            name="uq_driver_applications_status_reference_sha256",
        ),
        Index("ix_driver_applications_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=DriverApplicationStatus.PENDING.value
    )
    status_reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    service_city: Mapped[str | None] = mapped_column(String(128))
    country_code: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DriverApplicationAccessToken(Base):
    """Digest-only, expiring mutation authority delivered to the applicant email."""

    __tablename__ = "driver_application_access_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_sha256) = 64",
            name="ck_driver_application_access_tokens_hash",
        ),
        UniqueConstraint("token_sha256", name="uq_driver_application_access_tokens_hash"),
        Index(
            "ix_driver_application_access_tokens_application_created",
            "application_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_applications.id", ondelete="RESTRICT"), nullable=False
    )
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DriverAccountSetupToken(Base):
    """Digest-only administrator-issued authority for initial driver activation."""

    __tablename__ = "driver_account_setup_tokens"
    __table_args__ = (
        CheckConstraint("length(token_sha256) = 64", name="ck_driver_setup_tokens_hash"),
        CheckConstraint(
            "length(evidence_sha256) = 64", name="ck_driver_setup_tokens_evidence_hash"
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="ck_driver_setup_tokens_request_hash"
        ),
        CheckConstraint("session_version > 0", name="ck_driver_setup_tokens_session_version"),
        CheckConstraint("expires_at > created_at", name="ck_driver_setup_tokens_expiry"),
        UniqueConstraint("token_sha256", name="uq_driver_setup_tokens_hash"),
        UniqueConstraint("client_request_id", name="uq_driver_setup_tokens_client_request"),
        Index("ix_driver_setup_tokens_application_created", "application_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_applications.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    issued_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
