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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PhoneChallengeStatus(StrEnum):
    PENDING_OPERATOR = "pending_operator"
    SENT = "sent"
    VERIFIED = "verified"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class ManualContactTaskStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"


class PasswordResetAttempt(Base):
    __tablename__ = "password_reset_attempts"
    __table_args__ = (
        CheckConstraint("length(email_digest) = 64", name="ck_password_reset_attempt_email_hash"),
        CheckConstraint("length(ip_digest) = 64", name="ck_password_reset_attempt_ip_hash"),
        Index("ix_password_reset_attempt_email", "email_digest", "requested_at"),
        Index("ix_password_reset_attempt_ip", "ip_digest", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    email_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="ck_password_reset_tokens_hash"),
        CheckConstraint("expires_at > created_at", name="ck_password_reset_tokens_expiry"),
        CheckConstraint("session_version > 0", name="ck_password_reset_tokens_session_version"),
        UniqueConstraint("attempt_id", name="uq_password_reset_tokens_attempt"),
        UniqueConstraint("token_hash", name="uq_password_reset_tokens_hash"),
        Index("ix_password_reset_tokens_user", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("password_reset_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverPhoneVersion(Base):
    __tablename__ = "driver_phone_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_driver_phone_versions_version"),
        CheckConstraint("length(phone_fingerprint) = 64", name="ck_driver_phone_versions_hash"),
        CheckConstraint("length(masked_phone) > 0", name="ck_driver_phone_versions_mask"),
        UniqueConstraint("driver_profile_id", "version", name="uq_driver_phone_version"),
        Index("ix_driver_phone_versions_profile", "driver_profile_id", "version"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    phone_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    masked_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PhoneVerificationChallenge(Base):
    __tablename__ = "phone_verification_challenges"
    __table_args__ = (
        CheckConstraint("length(code_hash) = 64", name="ck_phone_challenges_hash"),
        CheckConstraint("max_attempts > 0", name="ck_phone_challenges_max_attempts"),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_phone_challenges_attempt_count",
        ),
        CheckConstraint(
            "status IN ('pending_operator', 'sent', 'verified', 'expired', 'exhausted')",
            name="ck_phone_challenges_status",
        ),
        CheckConstraint("expires_at > created_at", name="ck_phone_challenges_expiry"),
        CheckConstraint(
            "(sent_by_user_id IS NULL AND sent_channel IS NULL AND sent_at IS NULL "
            "AND operator_evidence_reference IS NULL AND provider_message_id IS NULL) OR "
            "(sent_by_user_id IS NOT NULL AND sent_channel IN ('whatsapp', 'voice') "
            "AND sent_at IS NOT NULL AND length(trim(operator_evidence_reference)) > 0 "
            "AND length(trim(provider_message_id)) > 0)",
            name="ck_phone_challenges_send_evidence",
        ),
        Index("ix_phone_challenges_version", "phone_version_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    phone_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_phone_versions.id", ondelete="RESTRICT"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    sent_channel: Mapped[str | None] = mapped_column(String(16))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator_evidence_reference: Mapped[str | None] = mapped_column(String(255))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WhatsappConsent(Base):
    __tablename__ = "whatsapp_consents"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_whatsapp_consents_version"),
        CheckConstraint("length(trim(purpose)) > 0", name="ck_whatsapp_consents_purpose"),
        CheckConstraint(
            "length(trim(notice_version)) > 0", name="ck_whatsapp_consents_notice_version"
        ),
        CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= granted_at",
            name="ck_whatsapp_consents_timeline",
        ),
        UniqueConstraint("driver_profile_id", "version", name="uq_whatsapp_consent_version"),
        Index("ix_whatsapp_consents_profile", "driver_profile_id", "version"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    phone_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_phone_versions.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualDriverContactTask(Base):
    __tablename__ = "manual_driver_contact_tasks"
    __table_args__ = (
        CheckConstraint("length(trim(event_key)) > 0", name="ck_manual_contact_event_key"),
        CheckConstraint("length(trim(purpose)) > 0", name="ck_manual_contact_purpose"),
        CheckConstraint("status IN ('open', 'completed')", name="ck_manual_contact_status"),
        CheckConstraint(
            "(status = 'open' AND completed_by_user_id IS NULL AND completed_at IS NULL "
            "AND completion_outcome IS NULL AND completion_note IS NULL) OR "
            "(status = 'completed' AND completed_by_user_id IS NOT NULL "
            "AND completed_at IS NOT NULL AND completion_outcome IN "
            "('attempted', 'reached', 'failed') AND length(trim(completion_note)) > 0)",
            name="ck_manual_contact_completion",
        ),
        UniqueConstraint("driver_profile_id", "event_key", name="uq_manual_contact_event"),
        Index("ix_manual_contact_tasks_status", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    phone_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_phone_versions.id", ondelete="RESTRICT"), nullable=False
    )
    consent_id: Mapped[UUID] = mapped_column(
        ForeignKey("whatsapp_consents.id", ondelete="RESTRICT"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_outcome: Mapped[str | None] = mapped_column(String(16))
    completion_note: Mapped[str | None] = mapped_column(Text)
