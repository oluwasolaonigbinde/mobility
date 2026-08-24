from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RetargetingSource(Base):
    __tablename__ = "retargeting_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('website-traffic', 'digital-campaign-audience', "
            "'CRM-upload-reference', 'UTM-source', 'manual-insight')",
            name="ck_retargeting_sources_source_type",
        ),
        CheckConstraint(
            "status IN ('active', 'deactivated')",
            name="ck_retargeting_sources_status",
        ),
        Index("ix_retargeting_sources_organization_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetargetingSourceEvent(Base):
    __tablename__ = "retargeting_source_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'deactivated')",
            name="ck_retargeting_source_events_event_type",
        ),
        UniqueConstraint(
            "source_id", "sequence_number", name="uq_retargeting_source_events_sequence"
        ),
        Index("ix_retargeting_source_events_source_created", "source_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_sources.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetargetingSourceIdempotency(Base):
    __tablename__ = "retargeting_source_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_retargeting_source_idempotency_actor_operation_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_sources.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
