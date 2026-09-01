from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DriverOnboardingStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class DriverProfile(Base):
    __tablename__ = "driver_profiles"
    __table_args__ = (
        CheckConstraint(
            "onboarding_status IN ('pending', 'active', 'suspended', 'rejected')",
            name="ck_driver_profiles_onboarding_status",
        ),
        UniqueConstraint("user_id", name="uq_driver_profiles_user_id"),
        Index("ix_driver_profiles_user_id", "user_id"),
        Index("ix_driver_profiles_onboarding_status", "onboarding_status"),
        Index("ix_driver_profiles_country_city", "country_code", "service_city"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    onboarding_status: Mapped[str] = mapped_column(String(32), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(128))
    service_city: Mapped[str | None] = mapped_column(String(128))
    country_code: Mapped[str | None] = mapped_column(String(2))
    profile_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(postgresql.JSONB(), "postgresql"),
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
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
