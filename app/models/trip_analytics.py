from datetime import datetime
from decimal import Decimal
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripAnalyticsStatus(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_DATA = "insufficient_data"
    BLOCKED = "blocked"


class FraudFlagType(StrEnum):
    INSUFFICIENT_PINGS = "insufficient_pings"
    IMPOSSIBLE_SPEED = "impossible_speed"
    POOR_ACCURACY = "poor_accuracy"
    STATIONARY_TRIP = "stationary_trip"
    EXCESSIVE_PING_GAP = "excessive_ping_gap"
    FUTURE_TIMESTAMP = "future_timestamp"
    ROUTE_LOOPING = "route_looping"
    ROUTE_REPLAY = "route_replay"
    EXCLUSION_ZONE_PRESENCE = "exclusion_zone_presence"


class FraudFlagSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FraudFlagStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class TripAnalytics(Base):
    __tablename__ = "trip_analytics"
    __table_args__ = (
        CheckConstraint(
            "status IN ('computed', 'insufficient_data', 'blocked')",
            name="ck_trip_analytics_status",
        ),
        CheckConstraint("ping_count >= 0", name="ck_trip_analytics_ping_count_non_negative"),
        CheckConstraint(
            "valid_ping_count >= 0",
            name="ck_trip_analytics_valid_ping_count_non_negative",
        ),
        CheckConstraint(
            "invalid_ping_count >= 0",
            name="ck_trip_analytics_invalid_ping_count_non_negative",
        ),
        CheckConstraint(
            "duration_seconds >= 0",
            name="ck_trip_analytics_duration_seconds_non_negative",
        ),
        CheckConstraint(
            "active_tracking_seconds >= 0",
            name="ck_trip_analytics_active_tracking_seconds_non_negative",
        ),
        CheckConstraint(
            "moving_seconds >= 0",
            name="ck_trip_analytics_moving_seconds_non_negative",
        ),
        CheckConstraint(
            "stationary_seconds >= 0",
            name="ck_trip_analytics_stationary_seconds_non_negative",
        ),
        CheckConstraint("distance_m >= 0", name="ck_trip_analytics_distance_m_non_negative"),
        CheckConstraint(
            "poor_accuracy_ping_count >= 0",
            name="ck_trip_analytics_poor_accuracy_ping_count_non_negative",
        ),
        CheckConstraint(
            "target_zone_distance_m >= 0",
            name="ck_trip_analytics_target_zone_distance_m_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_distance_m >= 0",
            name="ck_trip_analytics_bonus_zone_distance_m_non_negative",
        ),
        CheckConstraint(
            "exclusion_zone_distance_m >= 0",
            name="ck_trip_analytics_exclusion_zone_distance_m_non_negative",
        ),
        CheckConstraint(
            "target_zone_seconds >= 0",
            name="ck_trip_analytics_target_zone_seconds_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_seconds >= 0",
            name="ck_trip_analytics_bonus_zone_seconds_non_negative",
        ),
        CheckConstraint(
            "exclusion_zone_seconds >= 0",
            name="ck_trip_analytics_exclusion_zone_seconds_non_negative",
        ),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 1",
            name="ck_trip_analytics_quality_score_range",
        ),
        UniqueConstraint("trip_session_id", name="uq_trip_analytics_trip_session_id"),
        Index("ix_trip_analytics_campaign_id", "campaign_id"),
        Index("ix_trip_analytics_assignment_id", "assignment_id"),
        Index("ix_trip_analytics_driver_profile_id", "driver_profile_id"),
        Index("ix_trip_analytics_vehicle_id", "vehicle_id"),
        Index("ix_trip_analytics_campaign_computed_at", "campaign_id", "computed_at"),
        Index(
            "ix_trip_analytics_driver_profile_computed_at",
            "driver_profile_id",
            "computed_at",
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
    formula_version: Mapped[str] = mapped_column(
        Text,
        default="route_analytics_v1",
        server_default=text("'route_analytics_v1'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    ping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_ping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_ping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_tracking_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    moving_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stationary_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    distance_m: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    avg_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    max_observed_speed_mps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    avg_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    poor_accuracy_ping_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_zone_distance_m: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=0,
        nullable=False,
    )
    bonus_zone_distance_m: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=0,
        nullable=False,
    )
    exclusion_zone_distance_m: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=0,
        nullable=False,
    )
    target_zone_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bonus_zone_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exclusion_zone_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analytics_metadata: Mapped[dict[str, Any]] = mapped_column(
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


class FraudFlag(Base):
    __tablename__ = "fraud_flags"
    __table_args__ = (
        CheckConstraint(
            "flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', "
            "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', "
            "'route_replay', 'exclusion_zone_presence')",
            name="ck_fraud_flags_flag_type",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_fraud_flags_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'confirmed', 'dismissed')",
            name="ck_fraud_flags_status",
        ),
        CheckConstraint(
            "(status = 'open' AND reviewed_by_user_id IS NULL "
            "AND reviewed_at IS NULL AND resolution_note IS NULL) OR "
            "(status = 'acknowledged' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL "
            "AND resolution_note IS NULL) OR "
            "(status IN ('confirmed', 'dismissed') "
            "AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND resolution_note IS NOT NULL "
            "AND length(trim(resolution_note)) BETWEEN 1 AND 2000)",
            name="ck_fraud_flags_review_evidence",
        ),
        Index("ix_fraud_flags_trip_session_id", "trip_session_id"),
        Index("ix_fraud_flags_trip_analytics_id", "trip_analytics_id"),
        Index("ix_fraud_flags_campaign_id", "campaign_id"),
        Index("ix_fraud_flags_driver_profile_id", "driver_profile_id"),
        Index("ix_fraud_flags_vehicle_id", "vehicle_id"),
        Index("ix_fraud_flags_flag_type", "flag_type"),
        Index("ix_fraud_flags_severity", "severity"),
        Index("ix_fraud_flags_status", "status"),
        Index("ix_fraud_flags_campaign_status", "campaign_id", "status"),
        Index(
            "uq_fraud_flags_trip_nonterminal_flag_type",
            "trip_session_id",
            "flag_type",
            unique=True,
            sqlite_where=text("status IN ('open', 'acknowledged', 'confirmed')"),
            postgresql_where=text("status IN ('open', 'acknowledged', 'confirmed')"),
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
    trip_analytics_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trip_analytics.id", ondelete="SET NULL"),
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
    flag_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default=FraudFlagStatus.OPEN.value,
        server_default=text("'open'"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
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
