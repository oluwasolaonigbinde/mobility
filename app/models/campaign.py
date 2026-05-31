from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CreativeType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    HTML = "html"
    TEXT = "text"
    OTHER = "other"


class CreativePlacement(StrEnum):
    VEHICLE_EXTERIOR = "vehicle_exterior"
    VEHICLE_INTERIOR = "vehicle_interior"
    DIGITAL_SCREEN = "digital_screen"
    PRINT = "print"
    OTHER = "other"


class CreativeStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_campaigns_status",
        ),
        CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name="ck_campaigns_budget_amount_non_negative",
        ),
        CheckConstraint(
            "daily_budget_amount IS NULL OR daily_budget_amount >= 0",
            name="ck_campaigns_daily_budget_amount_non_negative",
        ),
        CheckConstraint(
            "budget_amount IS NULL OR daily_budget_amount IS NULL "
            "OR daily_budget_amount <= budget_amount",
            name="ck_campaigns_daily_budget_not_exceed_budget",
        ),
        CheckConstraint(
            "start_at IS NULL OR end_at IS NULL OR start_at < end_at",
            name="ck_campaigns_date_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    daily_budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    campaign_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CampaignCreative(Base):
    __tablename__ = "campaign_creatives"
    __table_args__ = (
        CheckConstraint(
            "creative_type IN ('image', 'video', 'html', 'text', 'other')",
            name="ck_campaign_creatives_creative_type",
        ),
        CheckConstraint(
            "placement IN ('vehicle_exterior', 'vehicle_interior', "
            "'digital_screen', 'print', 'other')",
            name="ck_campaign_creatives_placement",
        ),
        CheckConstraint(
            "status IN ('draft', 'ready', 'archived')",
            name="ck_campaign_creatives_status",
        ),
        CheckConstraint(
            "width_px IS NULL OR width_px > 0",
            name="ck_campaign_creatives_width_positive",
        ),
        CheckConstraint(
            "height_px IS NULL OR height_px > 0",
            name="ck_campaign_creatives_height_positive",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0",
            name="ck_campaign_creatives_duration_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    creative_type: Mapped[str] = mapped_column(String(32), nullable=False)
    placement: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    creative_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
