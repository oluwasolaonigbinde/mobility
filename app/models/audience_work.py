"""Durable fair scan position; immutable runs and links remain the work authority."""

from uuid import UUID

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AudienceSweepCursor(Base):
    __tablename__ = "audience_sweep_cursors"
    __table_args__ = (
        CheckConstraint(
            "(measurement_run_id IS NULL) = (source_link_id IS NULL)",
            name="ck_audience_sweep_cursor_pair",
        ),
    )

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    measurement_run_id: Mapped[UUID | None] = mapped_column()
    source_link_id: Mapped[UUID | None] = mapped_column()
