"""D118: one frozen campaign report, with CSV/PDF artifacts."""

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
    UniqueConstraint,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignReport(Base):
    __tablename__ = "campaign_reports"
    __table_args__ = (
        CheckConstraint("kind IN ('weekly','final','custom')", name="ck_campaign_reports_kind"),
        CheckConstraint("status IN ('queued','ready','failed')", name="ck_campaign_reports_status"),
        CheckConstraint(
            "(status = 'ready') = (ready_at IS NOT NULL) AND "
            "(status = 'queued' OR (processing_token IS NULL AND lease_expires_at IS NULL)) "
            "AND ((processing_token IS NULL) = (lease_expires_at IS NULL))",
            name="ck_campaign_reports_state",
        ),
        CheckConstraint("version > 0 AND attempts >= 0", name="ck_campaign_reports_counters"),
        CheckConstraint("period_start_at < period_end_at", name="ck_campaign_reports_period"),
        CheckConstraint("length(snapshot_sha256) = 64", name="ck_campaign_reports_snapshot_sha256"),
        UniqueConstraint(
            "requested_by_user_id", "client_request_id", name="uq_campaign_reports_request"
        ),
        Index(
            "uq_campaign_reports_window",
            "campaign_id",
            "kind",
            "period_end_at",
            "version",
            unique=True,
            postgresql_where=text("kind IN ('weekly','final')"),
        ),
        Index("ix_campaign_reports_scope", "organization_id", "created_at"),
        Index("ix_campaign_reports_due", "status", "next_attempt_at", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("advertiser_organizations.id"))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    requested_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    client_request_id: Mapped[UUID] = mapped_column()
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    rerun_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaign_reports.id"))
    period_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql")
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    processing_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


_MUTABLE = frozenset(
    {
        "status",
        "attempts",
        "processing_token",
        "lease_expires_at",
        "next_attempt_at",
        "error_code",
        "ready_at",
    }
)


@event.listens_for(CampaignReport, "before_update")
def keep_frozen_report(_mapper, _connection, target):
    state = inspect(target)
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    prior = state.attrs.status.history.deleted
    prior_status = prior[0] if prior else target.status
    if changed - _MUTABLE or (changed and prior_status == "ready"):
        raise ValueError("issued report facts are immutable; re-run creates a new report")


@event.listens_for(CampaignReport, "before_delete")
def keep_report_history(_mapper, _connection, _target):
    raise ValueError("campaign reports are append-only")
