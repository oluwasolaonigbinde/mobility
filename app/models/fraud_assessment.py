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
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.db.base import Base


class FraudAssessmentStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    FLAGGED = "flagged"
    ERROR = "error"


SUCCESSFUL_FRAUD_ASSESSMENT_STATUSES = frozenset(
    {FraudAssessmentStatus.CLEAN.value, FraudAssessmentStatus.FLAGGED.value}
)


class FraudAssessment(Base):
    __tablename__ = "fraud_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'clean', 'flagged', 'error')",
            name="ck_fraud_assessments_status",
        ),
        CheckConstraint(
            "flags_count >= 0",
            name="ck_fraud_assessments_flags_count_non_negative",
        ),
        UniqueConstraint(
            "trip_session_id",
            name="uq_fraud_assessments_trip_session_id",
        ),
        Index("ix_fraud_assessments_status", "status"),
        Index("ix_fraud_assessments_trip_analytics_id", "trip_analytics_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    trip_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trip_analytics_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_analytics.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=FraudAssessmentStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_analytics_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    flags_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    flags_updated_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
