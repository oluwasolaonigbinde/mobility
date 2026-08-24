from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.db.base import Base


class RouteReplayStatus(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


SUCCESSFUL_ROUTE_REPLAY_STATUSES = frozenset(
    {RouteReplayStatus.COMPUTED.value, RouteReplayStatus.INSUFFICIENT_DATA.value}
)


class RouteReplaySignature(Base):
    __tablename__ = "route_replay_signatures"
    __table_args__ = (
        CheckConstraint(
            "status IN ('computed', 'insufficient_data', 'error')",
            name="ck_route_replay_signatures_status",
        ),
        CheckConstraint(
            "point_count >= 0",
            name="ck_route_replay_signatures_point_count_non_negative",
        ),
        CheckConstraint(
            "(status = 'computed' AND payload_fingerprint IS NOT NULL "
            "AND normalized_fingerprint IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'insufficient_data' AND payload_fingerprint IS NULL "
            "AND normalized_fingerprint IS NULL AND error_code IS NULL) OR "
            "(status = 'error' AND payload_fingerprint IS NULL "
            "AND normalized_fingerprint IS NULL AND error_code IS NOT NULL)",
            name="ck_route_replay_signatures_outcome_fields",
        ),
        Index(
            "uq_route_replay_signatures_trip_session_id",
            "trip_session_id",
            unique=True,
        ),
        Index(
            "ix_route_replay_signatures_payload_lookup",
            "detector_version",
            "payload_fingerprint",
        ),
        Index(
            "ix_route_replay_signatures_normalized_lookup",
            "detector_version",
            "normalized_fingerprint",
        ),
        Index("ix_route_replay_signatures_trip_analytics_id", "trip_analytics_id"),
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
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    detector_config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_analytics_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_fingerprint: Mapped[str | None] = mapped_column(String(64))
    normalized_fingerprint: Mapped[str | None] = mapped_column(String(64))
    point_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
