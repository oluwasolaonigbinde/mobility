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
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONEmptyObjectServerDefault


class AssignmentActivityFlagType(StrEnum):
    VERIFIED_HOURS_FLOOR = "verified_hours_floor"
    INACTIVITY = "inactivity"


class AssignmentActivityFlagStatus(StrEnum):
    OPEN = "open"
    RECOVERED = "recovered"


class AssignmentActivityFlagEventType(StrEnum):
    OPENED = "opened"
    RECOVERED = "recovered"


class AssignmentActivityFlag(Base):
    """Current operational state for one assignment activity condition.

    The row is deliberately separate from fraud flags: this is an operations
    signal and never changes assignment, trip, or money state. Immutable
    occurrence evidence lives in ``AssignmentActivityFlagEvent`` rows.
    """

    __tablename__ = "assignment_activity_flags"
    __table_args__ = (
        CheckConstraint(
            "flag_type IN ('verified_hours_floor', 'inactivity')",
            name="ck_assignment_activity_flags_type",
        ),
        CheckConstraint(
            "status IN ('open', 'recovered')",
            name="ck_assignment_activity_flags_status",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_assignment_activity_flags_window",
        ),
        CheckConstraint(
            "threshold_seconds IS NULL OR threshold_seconds > 0",
            name="ck_assignment_activity_flags_threshold",
        ),
        CheckConstraint(
            "observed_seconds >= 0",
            name="ck_assignment_activity_flags_observed",
        ),
        CheckConstraint(
            "(status = 'open' AND recovered_at IS NULL) OR "
            "(status = 'recovered' AND recovered_at IS NOT NULL)",
            name="ck_assignment_activity_flags_recovery_coherence",
        ),
        UniqueConstraint(
            "assignment_id",
            "flag_type",
            "window_start",
            "window_end",
            name="uq_assignment_activity_flags_assignment_type_window",
        ),
        Index("ix_assignment_activity_flags_status", "status"),
        Index(
            "ix_assignment_activity_flags_assignment_status",
            "assignment_id",
            "status",
        ),
        Index(
            "ix_assignment_activity_flags_driver_status",
            "driver_profile_id",
            "status",
        ),
        Index(
            "ix_assignment_activity_flags_window",
            "window_start",
            "window_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    flag_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default=AssignmentActivityFlagStatus.OPEN.value,
        server_default=text("'open'"),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    threshold_seconds: Mapped[int | None] = mapped_column(Integer)
    observed_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_verified_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_evidence: Mapped[dict[str, Any]] = mapped_column(
        "evidence",
        JSON,
        default=dict,
        server_default=JSONEmptyObjectServerDefault(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AssignmentActivityFlagEvent(Base):
    """Append-only evidence for an activity flag occurrence or recovery."""

    __tablename__ = "assignment_activity_flag_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('opened', 'recovered')",
            name="ck_assignment_activity_flag_events_type",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_assignment_activity_flag_events_sequence",
        ),
        CheckConstraint(
            "observed_seconds >= 0",
            name="ck_assignment_activity_flag_events_observed",
        ),
        UniqueConstraint(
            "flag_id",
            "sequence_number",
            name="uq_assignment_activity_flag_events_sequence",
        ),
        Index(
            "ix_assignment_activity_flag_events_flag_created",
            "flag_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    flag_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignment_activity_flags.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=JSONEmptyObjectServerDefault(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_FROZEN_EVENT_FIELDS = frozenset(
    {
        "flag_id",
        "assignment_id",
        "sequence_number",
        "event_type",
        "occurred_at",
        "observed_seconds",
        "evidence",
        "created_at",
    }
)


@event.listens_for(AssignmentActivityFlagEvent, "before_update")
def reject_activity_event_mutation(
    _mapper, _connection, target: AssignmentActivityFlagEvent
) -> None:
    state = inspect(target)
    changed = sorted(
        field for field in _FROZEN_EVENT_FIELDS if state.attrs[field].history.has_changes()
    )
    if changed:
        raise ValueError("assignment activity flag evidence is immutable: " + ", ".join(changed))
