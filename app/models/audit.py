from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, event, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.observability import scrub_observability_value
from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    # Declared to match migrations 0002/0012 so autogenerate compares clean
    # (S4's empty-diff gate); no DB change.
    __table_args__ = (
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
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


def _scrub_audit_event_metadata(_mapper, _connection, target: AuditEvent) -> None:
    target.event_metadata = scrub_observability_value(
        target.event_metadata or {},
        semantic_context=target.entity_type,
    )


for _event_name in ("before_insert", "before_update"):
    if not event.contains(AuditEvent, _event_name, _scrub_audit_event_metadata):
        event.listen(AuditEvent, _event_name, _scrub_audit_event_metadata)
