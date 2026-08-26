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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignChangeStatus(StrEnum):
    PENDING_ADMIN = "pending_admin"
    PENDING_FUNDING = "pending_funding"
    APPLIED = "applied"
    REJECTED = "rejected"


class CampaignChangeRequest(Base):
    __tablename__ = "campaign_change_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_admin', 'pending_funding', 'applied', 'rejected')",
            name="ck_campaign_change_requests_status",
        ),
        CheckConstraint(
            "requested_liability_amount >= 0 AND "
            "(reserved_liability_amount IS NULL OR reserved_liability_amount >= 0)",
            name="ck_campaign_change_requests_liability",
        ),
        CheckConstraint(
            "(status = 'applied' AND applied_at IS NOT NULL "
            "AND reserved_liability_amount IS NOT NULL) OR "
            "(status <> 'applied' AND applied_at IS NULL)",
            name="ck_campaign_change_requests_applied_state",
        ),
        CheckConstraint(
            "(reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND review_reason IS NULL) OR "
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND review_reason IS NOT NULL AND length(trim(review_reason)) > 0)",
            name="ck_campaign_change_requests_review_state",
        ),
        CheckConstraint(
            "(status = 'rejected' AND reviewed_by_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL) OR status <> 'rejected'",
            name="ck_campaign_change_requests_rejected_state",
        ),
        UniqueConstraint(
            "campaign_id",
            "requested_by_user_id",
            "client_request_id",
            name="uq_campaign_change_requests_retry",
        ),
        Index(
            "ix_campaign_change_requests_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_request_id: Mapped[UUID] = mapped_column(nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    classifications: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    impact_preview: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_liability_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reserved_liability_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_financial_authorizations.id", ondelete="RESTRICT")
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CampaignChangeRevision(Base):
    __tablename__ = "campaign_change_revisions"
    __table_args__ = (
        CheckConstraint("revision_number > 0", name="ck_campaign_change_revisions_number"),
        CheckConstraint(
            "length(snapshot_sha256) = 64", name="ck_campaign_change_revisions_digest"
        ),
        UniqueConstraint("request_id", name="uq_campaign_change_revisions_request"),
        UniqueConstraint(
            "campaign_id", "revision_number", name="uq_campaign_change_revisions_number"
        ),
        Index(
            "ix_campaign_change_revisions_campaign_effective",
            "campaign_id",
            "effective_from",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_change_requests.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
