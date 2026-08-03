from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db.base import Base


class PostGISPoint(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "geometry(Point,4326)"


@compiles(PostGISPoint, "sqlite")
def compile_sqlite_point(_: PostGISPoint, __, **___: Any) -> str:
    return "TEXT"


class TripSessionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class TripSession(Base):
    __tablename__ = "trip_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="ck_trip_sessions_status"),
        Index("ix_trip_sessions_assignment_id", "assignment_id"),
        Index("ix_trip_sessions_campaign_id", "campaign_id"),
        Index("ix_trip_sessions_driver_profile_id", "driver_profile_id"),
        Index("ix_trip_sessions_vehicle_id", "vehicle_id"),
        Index("ix_trip_sessions_driver_status", "driver_profile_id", "status"),
        Index("ix_trip_sessions_vehicle_status", "vehicle_id", "status"),
        Index("ix_trip_sessions_campaign_started_at", "campaign_id", "started_at"),
        Index(
            "uq_trip_sessions_driver_profile_active",
            "driver_profile_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_trip_sessions_vehicle_active",
            "vehicle_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    trip_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
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


class LocationPingBatch(Base):
    __tablename__ = "location_ping_batches"
    __table_args__ = (
        CheckConstraint(
            "pings_accepted >= 0",
            name="ck_location_ping_batches_pings_accepted_non_negative",
        ),
        UniqueConstraint(
            "trip_session_id",
            "idempotency_key",
            name="uq_location_ping_batches_trip_idempotency_key",
        ),
        Index("ix_location_ping_batches_trip_session_id", "trip_session_id"),
        Index(
            "ix_location_ping_batches_trip_received_at",
            "trip_session_id",
            "received_at",
        ),
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
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    pings_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    batch_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LocationPing(Base):
    __tablename__ = "location_pings"
    __table_args__ = (
        CheckConstraint(
            "sequence_number IS NULL OR sequence_number >= 0",
            name="ck_location_pings_sequence_number_non_negative",
        ),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_location_pings_latitude"),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_location_pings_longitude",
        ),
        CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0",
            name="ck_location_pings_accuracy_non_negative",
        ),
        CheckConstraint(
            "speed_mps IS NULL OR speed_mps >= 0",
            name="ck_location_pings_speed_non_negative",
        ),
        CheckConstraint(
            "heading_degrees IS NULL OR (heading_degrees >= 0 AND heading_degrees < 360)",
            name="ck_location_pings_heading_degrees",
        ),
        CheckConstraint(
            "altitude_m IS NULL OR (altitude_m >= -500 AND altitude_m <= 10000)",
            name="ck_location_pings_altitude_m",
        ),
        Index("ix_location_pings_trip_session_id", "trip_session_id"),
        Index("ix_location_pings_trip_recorded_at", "trip_session_id", "recorded_at"),
        Index("ix_location_pings_batch_id", "batch_id"),
        Index("ix_location_pings_geom", "geom", postgresql_using="gist"),
    )

    # Composite PK (id, recorded_at): the table is range-partitioned by
    # recorded_at (migration 0014) and PostgreSQL requires the partition key
    # in every unique constraint. Partitioning itself is declared only in the
    # migration — metadata.create_all (SQLite units, PostGIS test schemas)
    # must keep producing a plain insertable table.
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    trip_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("location_ping_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sequence_number: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_degrees: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[str] = mapped_column(PostGISPoint(), nullable=False)
    ping_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
