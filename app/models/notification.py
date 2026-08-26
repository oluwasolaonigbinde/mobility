from datetime import UTC, datetime
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
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType(StrEnum):
    FRAUD_HOLD_RAISED = "fraud_hold_raised"
    FRAUD_REVIEW_RESOLVED = "fraud_review_resolved"
    FRAUD_DISPUTE_REPLIED = "fraud_dispute_replied"
    ACTIVITY_FLOOR_BREACHED = "activity_floor_breached"
    ACTIVITY_FLOOR_RECOVERED = "activity_floor_recovered"
    ASSIGNMENT_INACTIVE = "assignment_inactive"
    ASSIGNMENT_ACTIVITY_RECOVERED = "assignment_activity_recovered"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    TRANSACTIONAL_EMAIL = "transactional_email"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "length(trim(type_key)) > 0",
            name="ck_notifications_type_key",
        ),
        CheckConstraint(
            "length(trim(template_version)) > 0",
            name="ck_notifications_template_version",
        ),
        CheckConstraint(
            "channel IN ('in_app', 'transactional_email')",
            name="ck_notifications_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'delivered', 'failed')",
            name="ck_notifications_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notifications_attempt_count"),
        UniqueConstraint(
            "recipient_user_id",
            "channel",
            "dedupe_key",
            name="uq_notifications_recipient_channel_dedupe_key",
        ),
        UniqueConstraint(
            "provider_message_id",
            name="uq_notifications_provider_message_id",
        ),
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index(
            "ix_notifications_recipient_unread",
            "recipient_user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
        Index("ix_notifications_type_key", "type_key"),
        Index(
            "ix_notifications_email_dispatch",
            "status",
            "next_attempt_at",
            "delivery_claim_expires_at",
            postgresql_where=text("channel = 'transactional_email'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    type_key: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(
        String(16), default="v1", server_default=text("'v1'"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), default=dict, server_default=text("'{}'"), nullable=False
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(
        String(32),
        default=NotificationChannel.IN_APP.value,
        server_default=text("'in_app'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=NotificationStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_claim_token: Mapped[UUID | None] = mapped_column()
    delivery_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    dedupe_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationDeliveryReceipt(Base):
    __tablename__ = "notification_delivery_receipts"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('delivered', 'failed')",
            name="ck_notification_delivery_receipts_outcome",
        ),
        UniqueConstraint("notification_id", name="uq_notification_receipts_notification"),
        UniqueConstraint("provider_event_id", name="uq_notification_receipts_provider_event"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="RESTRICT"), nullable=False
    )
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(NotificationDeliveryReceipt, "before_update")
def reject_notification_receipt_update(_mapper, _connection, _target) -> None:
    raise ValueError("notification delivery receipts are immutable")


@event.listens_for(NotificationDeliveryReceipt, "before_delete")
def reject_notification_receipt_delete(_mapper, _connection, _target) -> None:
    raise ValueError("notification delivery receipts are append-only")


_FROZEN_EVIDENCE_FIELDS = frozenset(
    {
        "recipient_user_id",
        "type_key",
        "template_version",
        "channel",
        "payload",
        "dedupe_key",
        "dedupe_fingerprint",
        "created_at",
    }
)


@event.listens_for(Notification, "init", propagate=True)
def initialize_notification_defaults(_target, _args, kwargs) -> None:
    channel = kwargs.get("channel", NotificationChannel.IN_APP.value)
    channel = getattr(channel, "value", channel)
    if "status" not in kwargs:
        kwargs["status"] = (
            NotificationStatus.SENT.value
            if channel == NotificationChannel.IN_APP.value
            else NotificationStatus.PENDING.value
        )
    if "sent_at" not in kwargs:
        kwargs["sent_at"] = (
            datetime.now(UTC) if channel == NotificationChannel.IN_APP.value else None
        )


@event.listens_for(Notification, "before_update")
def reject_notification_evidence_mutation(_mapper, _connection, target: Notification) -> None:
    state = inspect(target)
    changed = sorted(
        field for field in _FROZEN_EVIDENCE_FIELDS if state.attrs[field].history.has_changes()
    )
    if changed:
        raise ValueError(f"notification evidence fields are immutable: {', '.join(changed)}")
