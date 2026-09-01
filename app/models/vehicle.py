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
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VehicleType(StrEnum):
    CAR = "car"
    VAN = "van"
    MINIBUS = "minibus"
    BUS = "bus"
    MOTORCYCLE = "motorcycle"
    TRICYCLE = "tricycle"
    OTHER = "other"


class VehicleStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('car', 'van', 'minibus', 'bus', 'motorcycle', 'tricycle', 'other')",
            name="ck_vehicles_vehicle_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'inactive', 'suspended')",
            name="ck_vehicles_status",
        ),
        UniqueConstraint(
            "plate_country_code",
            "plate_number_normalized",
            name="uq_vehicles_plate_country_normalized",
        ),
        Index("ix_vehicles_status", "status"),
        Index(
            "ix_vehicles_plate_country_normalized",
            "plate_country_code",
            "plate_number_normalized",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_number_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    plate_country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    make: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    year: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_metadata: Mapped[dict[str, Any]] = mapped_column(
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
