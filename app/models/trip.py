from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PostGISGeometry


class TripSessionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
    # Sealed = "all intended data received (or grace expired)"; the ONLY
    # status the money chain may process (RM3). ended -> sealed is one-way.
    SEALED = "sealed"


class TripSealReason(StrEnum):
    CLIENT_COMPLETE = "client_complete"
    LATE_DATA_COMPLETE = "late_data_complete"
    GRACE_EXPIRED = "grace_expired"
    MIGRATION_BACKFILL = "migration_backfill"


class TripSession(Base):
    __tablename__ = "trip_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'ended', 'sealed')", name="ck_trip_sessions_status"
        ),
        CheckConstraint(
            "(status = 'sealed') = (sealed_at IS NOT NULL AND seal_reason IS NOT NULL)",
            name="ck_trip_sessions_sealed_fields",
        ),
        CheckConstraint(
            "seal_reason IS NULL OR seal_reason IN "
            "('client_complete', 'late_data_complete', 'grace_expired', 'migration_backfill')",
            name="ck_trip_sessions_seal_reason",
        ),
        Index("ix_trip_sessions_assignment_id", "assignment_id"),
        Index("ix_trip_sessions_campaign_id", "campaign_id"),
        Index("ix_trip_sessions_driver_profile_id", "driver_profile_id"),
        Index("ix_trip_sessions_vehicle_id", "vehicle_id"),
        Index("ix_trip_sessions_display_proof_id", "display_proof_id"),
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
    display_proof_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("display_proofs.id", ondelete="RESTRICT")
    )
    started_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    # Client finalization watermark, reported on /end (RM3). batch count is
    # the seal predicate input; ping count and the completeness claim are
    # diagnostic evidence only.
    client_batch_count: Mapped[int | None] = mapped_column(Integer)
    client_ping_count: Mapped[int | None] = mapped_column(Integer)
    client_complete: Mapped[bool | None] = mapped_column(Boolean)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seal_reason: Mapped[str | None] = mapped_column(Text)
    trip_metadata: Mapped[dict[str, Any]] = mapped_column(
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


class QuarantinedPingBatchStatus(StrEnum):
    QUARANTINED = "quarantined"
    APPLIED = "applied"
    DISCARDED = "discarded"


class QuarantinedPingBatch(Base):
    """A ping batch that arrived after its trip was sealed (RM3).

    Evidence-preserving: the full payload is stored, no location_pings rows
    are written, and only an audited admin action may apply or discard it.
    Applying never auto-recomputes money — payout_v2 is write-once and the
    corrective path stays the admin recompute-day tool (§16.1).
    """

    __tablename__ = "quarantined_ping_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('quarantined', 'applied', 'discarded')",
            name="ck_quarantined_ping_batches_status",
        ),
        CheckConstraint(
            "(status = 'quarantined') = (resolved_at IS NULL)",
            name="ck_quarantined_ping_batches_resolution",
        ),
        # Resolution facts travel together: a resolved row always names its
        # actor and note, and only applied rows carry an applied batch.
        CheckConstraint(
            "(status = 'quarantined') = (resolved_by_user_id IS NULL AND resolution_note IS NULL)",
            name="ck_quarantined_ping_batches_resolution_actor",
        ),
        CheckConstraint(
            "applied_batch_id IS NULL OR status = 'applied'",
            name="ck_quarantined_ping_batches_applied_batch",
        ),
        UniqueConstraint(
            "trip_session_id",
            "idempotency_key",
            name="uq_quarantined_ping_batches_trip_idempotency_key",
        ),
        Index("ix_quarantined_ping_batches_trip_session_id", "trip_session_id"),
        Index("ix_quarantined_ping_batches_status", "status"),
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
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=QuarantinedPingBatchStatus.QUARANTINED.value,
        server_default=text("'quarantined'"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    applied_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("location_ping_batches.id", ondelete="SET NULL")
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
    geom: Mapped[str] = mapped_column(PostGISGeometry("Point", 4326), nullable=False)
    ping_metadata: Mapped[dict[str, Any]] = mapped_column(
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
