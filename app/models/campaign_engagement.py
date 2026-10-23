"""Artwork destinations and counts only: no scan event or visitor record exists."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArtworkLink(Base):
    __tablename__ = "artwork_links"

    creative_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_creatives.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArtworkScanDay(Base):
    __tablename__ = "artwork_scan_days"
    __table_args__ = (CheckConstraint("scans >= 0", name="ck_artwork_scan_days_non_negative"),)

    creative_id: Mapped[UUID] = mapped_column(
        ForeignKey("artwork_links.creative_id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    scans: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
