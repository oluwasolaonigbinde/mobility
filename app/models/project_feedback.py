"""REQ-336/D172: notes sent with the site-wide feedback button on test versions."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

FeedbackStatus = Literal["opened", "resolved"]


class ProjectFeedbackItem(Base):
    __tablename__ = "project_feedback_items"
    __table_args__ = (
        CheckConstraint("status IN ('opened', 'resolved')", name="ck_project_feedback_status"),
        CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)",
            name="ck_project_feedback_resolved_at",
        ),
        CheckConstraint(
            "(screenshot IS NULL AND screenshot_width IS NULL AND screenshot_height IS NULL "
            "AND pin_x IS NULL AND pin_y IS NULL) OR (screenshot IS NOT NULL "
            "AND screenshot_width BETWEEN 1 AND 4000 AND screenshot_height BETWEEN 1 AND 4000 "
            "AND pin_x BETWEEN 0 AND 1 AND pin_y BETWEEN 0 AND 1)",
            name="ck_project_feedback_screenshot",
        ),
        Index("ix_project_feedback_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    page_path: Mapped[str] = mapped_column(String(500))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[FeedbackStatus] = mapped_column(String(16), default="opened")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Loaded only by the screenshot endpoint; lists and CSV never read the bytes.
    screenshot: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    screenshot_width: Mapped[int | None] = mapped_column(Integer)
    screenshot_height: Mapped[int | None] = mapped_column(Integer)
    pin_x: Mapped[float | None] = mapped_column(Float)
    pin_y: Mapped[float | None] = mapped_column(Float)
