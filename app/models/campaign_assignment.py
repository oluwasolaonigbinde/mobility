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
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignAssignmentStatus(StrEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class CampaignActivationEventType(StrEnum):
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class CampaignAssignment(Base):
    __tablename__ = "campaign_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('offered', 'accepted', 'declined', 'expired', 'active', "
            "'deactivated', 'cancelled', 'completed')",
            name="ck_campaign_assignments_status",
        ),
        CheckConstraint(
            "status != 'declined' OR declined_at IS NOT NULL",
            name="ck_campaign_assignments_declined_timestamp",
        ),
        CheckConstraint(
            "status != 'expired' OR expired_at IS NOT NULL",
            name="ck_campaign_assignments_expired_timestamp",
        ),
        CheckConstraint(
            "status != 'accepted' OR accepted_at IS NOT NULL OR offer_terms IS NULL",
            name="ck_campaign_assignments_accepted_timestamp",
        ),
        CheckConstraint(
            "accepted_at IS NULL OR status IN "
            "('accepted', 'active', 'deactivated', 'cancelled', 'completed')",
            name="ck_campaign_assignments_accepted_status_coherence",
        ),
        CheckConstraint(
            "declined_at IS NULL OR status = 'declined'",
            name="ck_campaign_assignments_declined_status_coherence",
        ),
        CheckConstraint(
            "expired_at IS NULL OR status = 'expired'",
            name="ck_campaign_assignments_expired_status_coherence",
        ),
        CheckConstraint(
            "status != 'offered' OR "
            "(offer_terms IS NULL AND offer_terms_sha256 IS NULL) OR "
            "(offer_terms IS NOT NULL AND offer_terms_sha256 IS NOT NULL)",
            name="ck_campaign_assignments_offer_snapshot_pair",
        ),
        Index("ix_campaign_assignments_campaign_id", "campaign_id"),
        Index("ix_campaign_assignments_driver_profile_id", "driver_profile_id"),
        Index("ix_campaign_assignments_vehicle_id", "vehicle_id"),
        Index("ix_campaign_assignments_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_assignments_driver_status", "driver_profile_id", "status"),
        Index("ix_campaign_assignments_vehicle_status", "vehicle_id", "status"),
        Index(
            "uq_campaign_assignments_vehicle_active",
            "vehicle_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_campaign_assignments_campaign_vehicle_non_terminal",
            "campaign_id",
            "vehicle_id",
            unique=True,
            sqlite_where=text("status IN ('offered', 'accepted', 'active', 'deactivated')"),
            postgresql_where=text("status IN ('offered', 'accepted', 'active', 'deactivated')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
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
    assigned_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    assignment_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    offer_terms: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    offer_terms_sha256: Mapped[str | None] = mapped_column(String(64))
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


class CampaignActivationEvent(Base):
    __tablename__ = "campaign_activation_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('assigned', 'accepted', 'declined', 'expired', "
            "'activated', 'deactivated', 'cancelled', 'completed')",
            name="ck_campaign_activation_events_event_type",
        ),
        CheckConstraint(
            "event_type != 'accepted' OR new_status = 'accepted' OR "
            "(offer_terms_sha256 IS NULL AND new_status IN "
            "('active', 'deactivated', 'cancelled', 'completed'))",
            name="ck_campaign_activation_events_accepted_status",
        ),
        CheckConstraint(
            "event_type != 'declined' OR new_status = 'declined'",
            name="ck_campaign_activation_events_declined_status",
        ),
        CheckConstraint(
            "event_type != 'expired' OR new_status = 'expired'",
            name="ck_campaign_activation_events_expired_status",
        ),
        Index(
            "uq_campaign_activation_events_assignment_terminal_decision",
            "assignment_id",
            unique=True,
            sqlite_where=text("event_type IN ('accepted', 'declined', 'expired')"),
            postgresql_where=text("event_type IN ('accepted', 'declined', 'expired')"),
        ),
        Index("ix_campaign_activation_events_assignment_id", "assignment_id"),
        Index("ix_campaign_activation_events_actor_user_id", "actor_user_id"),
        Index(
            "ix_campaign_activation_events_assignment_occurred",
            "assignment_id",
            "occurred_at",
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
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    offer_terms_sha256: Mapped[str | None] = mapped_column(String(64))
