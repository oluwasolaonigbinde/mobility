from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "period_start_at", "period_end_at", name="uq_report_schedule_window"
        ),
        CheckConstraint("period_start_at < period_end_at", name="ck_report_schedule_period"),
        CheckConstraint("kind IN ('weekly','final')", name="ck_report_schedule_kind"),
        CheckConstraint("state IN ('pending','error','complete')", name="ck_report_schedule_state"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"))
    period_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    measurement_request_id: Mapped[UUID] = mapped_column(default=uuid4)
    issuance_request_id: Mapped[UUID] = mapped_column(default=uuid4)
    measurement_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("measurement_runs.id"))
    report_issuance_id: Mapped[UUID | None] = mapped_column(ForeignKey("report_issuances.id"))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportScheduleCursor(Base):
    __tablename__ = "report_schedule_cursors"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    campaign_id: Mapped[UUID | None] = mapped_column()
