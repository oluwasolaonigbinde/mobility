from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignEnquiry(Base):
    __tablename__ = "campaign_enquiries"
    __table_args__ = (
        CheckConstraint(
            "(organization_id IS NULL AND converted_at IS NULL AND converted_by_user_id IS NULL) "
            "OR (organization_id IS NOT NULL AND converted_at IS NOT NULL "
            "AND converted_by_user_id IS NOT NULL)",
            name="ck_campaign_enquiries_conversion",
        ),
        Index("ix_campaign_enquiries_created", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(32))
    brief: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("advertiser_organizations.id"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    converted_owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
