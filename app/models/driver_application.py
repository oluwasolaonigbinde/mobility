from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DriverApplicationStatus(StrEnum):
    PENDING = "pending"


class DriverApplication(Base):
    """Public driver-joining authority, separate from profile metadata.

    The submitted contact snapshot is intentionally allowlisted.  The status
    reference is stored only as a digest; the plaintext is returned once to a
    public applicant and is never part of an admin projection.
    """

    __tablename__ = "driver_applications"
    __table_args__ = (
        CheckConstraint(
            "status = 'pending'",
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
