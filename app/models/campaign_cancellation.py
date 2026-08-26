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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignCancellationDisposition(StrEnum):
    CASH_REFUND_DUE = "cash_refund_due"
    CASH_REFUND_NOT_DUE = "cash_refund_not_due"
    CREDIT_SETTLEMENT_DUE = "credit_settlement_due"
    NO_SETTLEMENT = "no_settlement"


class CampaignCancellation(Base):
    __tablename__ = "campaign_cancellations"
    __table_args__ = (
        CheckConstraint(
            "prior_status IN ('approved', 'scheduled', 'active', 'paused')",
            name="ck_campaign_cancellations_prior_status",
        ),
        CheckConstraint(
            "disposition IN ('cash_refund_due', 'cash_refund_not_due', "
            "'credit_settlement_due', 'no_settlement')",
            name="ck_campaign_cancellations_disposition",
        ),
        CheckConstraint(
            "length(currency) = 3 AND refundable_amount >= 0 "
            "AND released_liability_amount >= 0",
            name="ck_campaign_cancellations_amounts",
        ),
        CheckConstraint(
            "(disposition = 'cash_refund_due' AND commercial_terms_id IS NOT NULL "
            "AND funding_authorized_at IS NOT NULL AND refund_eligibility_ends_at IS NOT NULL "
            "AND cutoff_at < refund_eligibility_ends_at AND refundable_amount > 0) OR "
            "(disposition <> 'cash_refund_due' AND refundable_amount = 0)",
            name="ck_campaign_cancellations_settlement_evidence",
        ),
        UniqueConstraint("campaign_id", name="uq_campaign_cancellations_campaign"),
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
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    prior_status: Mapped[str] = mapped_column(String(32), nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    commercial_terms_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("commercial_terms.id", ondelete="RESTRICT")
    )
    production_start_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("production_starts.id", ondelete="RESTRICT")
    )
    funding_authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_eligibility_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    disposition: Mapped[str] = mapped_column(String(40), nullable=False)
    refundable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    released_liability_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    cancelled_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CampaignCancellationSettlementRevision(Base):
    __tablename__ = "campaign_cancellation_settlement_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_campaign_cancellation_settlement_revisions_number",
        ),
        CheckConstraint(
            "length(snapshot_sha256) = 64",
            name="ck_campaign_cancellation_settlement_revisions_digest",
        ),
        UniqueConstraint(
            "cancellation_id",
            "revision_number",
            name="uq_campaign_cancellation_settlement_revisions_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    cancellation_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_cancellations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
