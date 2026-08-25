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


class RetargetingSourceLink(Base):
    __tablename__ = "retargeting_source_links"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'removed')", name="ck_retargeting_source_links_status"
        ),
        Index("ix_retargeting_source_links_source_created", "source_id", "created_at"),
        Index(
            "uq_retargeting_source_links_active_identity",
            "source_id",
            "campaign_id",
            "zone_id",
            "start_at",
            "end_at",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_sources.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    zone_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_zones.id", ondelete="RESTRICT"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    zone_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetargetingSourceLinkEvent(Base):
    __tablename__ = "retargeting_source_link_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'removed')",
            name="ck_retargeting_source_link_events_event_type",
        ),
        UniqueConstraint(
            "link_id", "sequence_number", name="uq_retargeting_source_link_events_sequence"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    link_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_source_links.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetargetingSourceLinkIdempotency(Base):
    __tablename__ = "retargeting_source_link_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_retargeting_source_link_idempotency_actor_operation_key",
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
    link_id: Mapped[UUID] = mapped_column(
        ForeignKey("retargeting_source_links.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
