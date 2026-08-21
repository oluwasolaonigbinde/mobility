from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FraudDisputeStatus(StrEnum):
    OPEN = "open"
    REPLIED = "replied"


class FraudDispute(Base):
    __tablename__ = "fraud_disputes"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'replied')", name="ck_fraud_disputes_status"),
        CheckConstraint(
            "length(trim(message)) BETWEEN 1 AND 2000",
            name="ck_fraud_disputes_message",
        ),
        UniqueConstraint("fraud_flag_id", name="uq_fraud_disputes_fraud_flag_id"),
        CheckConstraint(
            "(status = 'open' AND replied_by_user_id IS NULL AND replied_at IS NULL "
            "AND reply_text IS NULL) OR (status = 'replied' "
            "AND replied_by_user_id IS NOT NULL AND replied_at IS NOT NULL "
            "AND reply_text IS NOT NULL AND length(trim(reply_text)) BETWEEN 1 AND 2000)",
            name="ck_fraud_disputes_reply_evidence",
        ),
        Index("ix_fraud_disputes_driver_profile_id", "driver_profile_id"),
        Index("ix_fraud_disputes_status", "status"),
        Index("ix_fraud_disputes_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    fraud_flag_id: Mapped[UUID] = mapped_column(
        ForeignKey("fraud_flags.id", ondelete="RESTRICT"), nullable=False
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default=FraudDisputeStatus.OPEN.value,
        server_default=text("'open'"),
        nullable=False,
    )
    replied_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
