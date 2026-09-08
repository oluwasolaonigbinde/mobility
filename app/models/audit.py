from datetime import datetime
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
    UniqueConstraint,
    event,
    func,
    text,
)
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


class AuditEventSubjectResolution(Base):
    __tablename__ = "audit_event_subject_resolutions"
    __table_args__ = (
        CheckConstraint("role IN ('actor', 'target')", name="ck_audit_subject_resolution_role"),
        CheckConstraint(
            "(outcome = 'resolved' AND subject_user_id IS NOT NULL) OR "
            "(outcome = 'not_recorded' AND role = 'actor' AND subject_user_id IS NULL) OR "
            "(outcome = 'unresolved' AND role = 'target' AND subject_user_id IS NULL)",
            name="ck_audit_subject_resolution_outcome",
        ),
        UniqueConstraint(
            "audit_event_id", "role", "subject_user_id", name="uq_audit_subject_resolution"
        ),
        Index(
            "uq_audit_subject_unresolved",
            "audit_event_id",
            "role",
            unique=True,
            postgresql_where=text("subject_user_id IS NULL"),
            sqlite_where=text("subject_user_id IS NULL"),
        ),
        Index("ix_audit_subject_user_event", "subject_user_id", "audit_event_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    audit_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    # Deliberately no users FK: attribution survives account/target retention.
    subject_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)


@event.listens_for(AuditEventSubjectResolution, "before_update")
@event.listens_for(AuditEventSubjectResolution, "before_delete")
def _reject_subject_resolution_mutation(_mapper, _connection, _target) -> None:
    raise ValueError("audit subject resolutions are append-only")


@event.listens_for(AuditEvent, "after_insert")
def _record_audit_subjects(_mapper, connection, target: AuditEvent) -> None:
    from app.services.audit_subjects import resolve_audit_subjects

    rows = resolve_audit_subjects(
        connection,
        actor_user_id=target.actor_user_id,
        entity_type=target.entity_type,
        entity_id=target.entity_id,
        action=target.action,
        metadata=target.event_metadata,
    )
    connection.execute(
        AuditEventSubjectResolution.__table__.insert(),
        [
            {
                "audit_event_id": target.id,
                "role": role,
                "subject_user_id": subject,
                "outcome": outcome,
            }
            for role, subject, outcome in rows
        ],
    )


def _scrub_audit_event_metadata(_mapper, _connection, target: AuditEvent) -> None:
    target.event_metadata = scrub_observability_value(
        target.event_metadata or {},
        semantic_context=target.entity_type,
    )


for _event_name in ("before_insert", "before_update"):
    if not event.contains(AuditEvent, _event_name, _scrub_audit_event_metadata):
        event.listen(AuditEvent, _event_name, _scrub_audit_event_metadata)
