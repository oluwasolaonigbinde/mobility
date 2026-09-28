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
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComplaintParty(StrEnum):
    DRIVER = "driver"
    ADVERTISER = "advertiser"


class ComplaintStatus(StrEnum):
    OPEN = "open"  # waiting for Customer Service
    ANSWERED = "answered"  # Customer Service replied; waiting for the complainant
    RESOLVED = "resolved"


class ComplaintReferenceType(StrEnum):
    CAMPAIGN = "campaign"
    TRIP = "trip"
    PAYOUT = "payout"


class ComplaintAuthorSide(StrEnum):
    COMPLAINANT = "complainant"
    STAFF = "staff"


class Complaint(Base):
    """A driver's or advertiser's complaint, answered by Customer Service (D39(d))."""

    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint("party IN ('driver', 'advertiser')", name="ck_complaints_party"),
        CheckConstraint(
            "(party = 'driver' AND driver_profile_id IS NOT NULL "
            "AND advertiser_organization_id IS NULL) OR (party = 'advertiser' "
            "AND advertiser_organization_id IS NOT NULL AND driver_profile_id IS NULL)",
            name="ck_complaints_party_owner",
        ),
        CheckConstraint(
            "length(category) BETWEEN 1 AND 32 AND category = lower(trim(category)) "
            # No space; not NOT LIKE '% %', because metadata DDL doubles a literal %.
            "AND category = replace(category, ' ', '')",
            name="ck_complaints_category",
        ),
        CheckConstraint("status IN ('open', 'answered', 'resolved')", name="ck_complaints_status"),
        CheckConstraint(
            "(reference_type IS NULL AND campaign_id IS NULL AND trip_session_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'campaign' "
            "AND campaign_id IS NOT NULL AND trip_session_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'trip' "
            "AND party = 'driver' AND trip_session_id IS NOT NULL AND campaign_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'payout' "
            "AND party = 'driver' AND earnings_ledger_entry_id IS NOT NULL "
            "AND campaign_id IS NULL AND trip_session_id IS NULL)",
            name="ck_complaints_reference",
        ),
        CheckConstraint(
            "(status = 'resolved' AND resolved_at IS NOT NULL "
            "AND resolved_by_user_id IS NOT NULL) OR (status <> 'resolved' "
            "AND resolved_at IS NULL AND resolved_by_user_id IS NULL)",
            name="ck_complaints_resolution",
        ),
        CheckConstraint("revision >= 1", name="ck_complaints_revision"),
        UniqueConstraint(
            "raised_by_user_id",
            "client_request_id",
            name="uq_complaints_raiser_client_request",
        ),
        Index("ix_complaints_status_last_message", "status", "last_message_at"),
        Index("ix_complaints_driver_profile_id", "driver_profile_id"),
        Index("ix_complaints_advertiser_organization_id", "advertiser_organization_id"),
        Index("ix_complaints_assigned_to_user_id", "assigned_to_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    party: Mapped[str] = mapped_column(String(16), nullable=False)
    raised_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    driver_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="RESTRICT")
    )
    advertiser_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT")
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(16))
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT")
    )
    trip_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="RESTRICT")
    )
    earnings_ledger_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=ComplaintStatus.OPEN.value,
        server_default=text("'open'"),
        nullable=False,
    )
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ComplaintMessage(Base):
    """One append-only message in a complaint conversation; the first is the complaint."""

    __tablename__ = "complaint_messages"
    __table_args__ = (
        CheckConstraint(
            "author_side IN ('complainant', 'staff')", name="ck_complaint_messages_author_side"
        ),
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 2000", name="ck_complaint_messages_body"),
        CheckConstraint(
            "status_after IN ('open', 'answered', 'resolved')",
            name="ck_complaint_messages_status_after",
        ),
        UniqueConstraint(
            "complaint_id",
            "author_user_id",
            "client_request_id",
            name="uq_complaint_messages_author_client_request",
        ),
        Index("ix_complaint_messages_complaint_created", "complaint_id", "created_at"),
        Index("ix_complaint_messages_author_user_id", "author_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    complaint_id: Mapped[UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    author_side: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status_after: Mapped[str] = mapped_column(String(16), nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(ComplaintMessage, "before_update")
def reject_complaint_message_update(_mapper, _connection, _target) -> None:
    raise ValueError("complaint messages are immutable")


@event.listens_for(ComplaintMessage, "before_delete")
def reject_complaint_message_delete(_mapper, _connection, _target) -> None:
    raise ValueError("complaint messages are append-only")
