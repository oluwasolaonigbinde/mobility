from uuid import UUID

from sqlalchemy import (
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportScheduleCursor(Base):
    __tablename__ = "report_schedule_cursors"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    campaign_id: Mapped[UUID | None] = mapped_column()
