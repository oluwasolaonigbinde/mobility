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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    column,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.functions import FunctionElement

from app.db.base import Base
from app.models.stored_file import StoredFile


class CharacterLength(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(CharacterLength)
def compile_character_length(element, compiler, **kwargs) -> str:
    return f"char_length({compiler.process(element.clauses, **kwargs)})"


@compiles(CharacterLength, "sqlite")
def compile_sqlite_character_length(element, compiler, **kwargs) -> str:
    return f"length({compiler.process(element.clauses, **kwargs)})"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
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
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    # Legacy pre-review state. It remains readable but is never launch authority.
    READY = "ready"
    ARCHIVED = "archived"


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'rejected', "
            "'scheduled', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_campaigns_status",
        ),
        CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name="ck_campaigns_budget_amount_non_negative",
        ),
        CheckConstraint(
            CharacterLength(column("currency")) == 3,
            name="ck_campaigns_currency_length",
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
        Index("ix_campaigns_organization_status", "organization_id", "status"),
        Index("ix_campaigns_start_end", "start_at", "end_at"),
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
    currency: Mapped[str] = mapped_column(
        String(3), server_default=text("'NGN'"), nullable=False
    )
    campaign_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(postgresql.JSONB(), "postgresql"),
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


class CampaignReviewEvent(Base):
    __tablename__ = "campaign_review_events"
    __table_args__ = (
        CheckConstraint(
            "prior_status IN ('draft', 'pending_review', 'approved', 'rejected', "
            "'scheduled', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_campaign_review_events_prior_status",
        ),
        CheckConstraint(
            "new_status IN ('pending_review', 'approved', 'rejected')",
            name="ck_campaign_review_events_new_status",
        ),
        CheckConstraint(
            "(new_status = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0) OR "
            "(new_status != 'rejected' AND rejection_reason IS NULL)",
            name="ck_campaign_review_events_rejection_reason",
        ),
        CheckConstraint(
            "(new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL "
            "AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR "
            "(new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL "
            "AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL)",
            name="ck_campaign_review_events_submission_binding",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prior_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reviewed_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    submission_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_review_events.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
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
            "status IN ('draft', 'pending_review', 'approved', 'rejected', "
            "'ready', 'archived')",
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
        CheckConstraint(
            "stored_file_id IS NULL OR asset_url IS NULL",
            name="ck_campaign_creatives_managed_asset_url",
        ),
        UniqueConstraint("stored_file_id", name="uq_campaign_creatives_stored_file"),
        Index("ix_campaign_creatives_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_creatives_creative_type", "creative_type"),
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
    stored_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"),
        index=False,
    )
    stored_file: Mapped[StoredFile | None] = relationship(lazy="selectin")
    asset_url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    creative_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(postgresql.JSONB(), "postgresql"),
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


class CreativeReviewEvent(Base):
    __tablename__ = "creative_review_events"
    __table_args__ = (
        CheckConstraint(
            "prior_status IN ('draft', 'pending_review', 'approved', 'rejected', "
            "'ready', 'archived')",
            name="ck_creative_review_events_prior_status",
        ),
        CheckConstraint(
            "new_status IN ('pending_review', 'approved', 'rejected')",
            name="ck_creative_review_events_new_status",
        ),
        CheckConstraint(
            "(new_status = 'rejected' AND rejection_reason IS NOT NULL "
            "AND length(trim(rejection_reason)) > 0) OR "
            "(new_status != 'rejected' AND rejection_reason IS NULL)",
            name="ck_creative_review_events_rejection_reason",
        ),
        CheckConstraint(
            "(new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL "
            "AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR "
            "(new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL "
            "AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL)",
            name="ck_creative_review_events_submission_binding",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    creative_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_creatives.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prior_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reviewed_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    submission_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("creative_review_events.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
