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


class QuoteRequestSource(StrEnum):
    IN_PLATFORM = "in_platform"
    EXTERNAL_RECORDED = "external_recorded"


class PaymentClass(StrEnum):
    STANDARD_PREPAID = "standard_prepaid"
    APPROVED_CORPORATE_CREDIT = "approved_corporate_credit"


class AcceptanceMethod(StrEnum):
    IN_PLATFORM = "in_platform"
    EXTERNAL_RECORDED = "external_recorded"


class CommercialQuoteRequest(Base):
    __tablename__ = "commercial_quote_requests"
    __table_args__ = (
        CheckConstraint(
            "source IN ('in_platform', 'external_recorded')",
            name="ck_commercial_quote_requests_source",
        ),
        UniqueConstraint("campaign_id", name="uq_commercial_quote_requests_campaign"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    request_details: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommercialQuotationRevision(Base):
    __tablename__ = "commercial_quotation_revisions"
    __table_args__ = (
        CheckConstraint("revision_number > 0", name="ck_commercial_quote_revision_positive"),
        CheckConstraint("length(currency) = 3", name="ck_commercial_quote_currency"),
        CheckConstraint(
            "payment_class IN ('standard_prepaid', 'approved_corporate_credit')",
            name="ck_commercial_quote_payment_class",
        ),
        CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 "
            "AND tax_amount >= 0 AND gross_amount >= 0 "
            "AND production_cost_amount >= 0",
            name="ck_commercial_quote_amounts_non_negative",
        ),
        CheckConstraint(
            "gross_amount = net_amount + tax_amount",
            name="ck_commercial_quote_total_conservation",
        ),
        CheckConstraint(
            "standard_production_wait_hours = 24",
            name="ck_commercial_quote_standard_wait",
        ),
        UniqueConstraint(
            "quote_request_id",
            "revision_number",
            name="uq_commercial_quote_request_revision",
        ),
        UniqueConstraint(
            "organization_id",
            "quote_reference",
            "revision_number",
            name="uq_commercial_quote_reference_revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    quote_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_quote_requests.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    production_scope: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    production_cost_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_class: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_terms: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    standard_production_wait_hours: Mapped[int] = mapped_column(
        Integer, default=24, server_default=text("24"), nullable=False
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommercialTerms(Base):
    __tablename__ = "commercial_terms"
    __table_args__ = (
        CheckConstraint(
            "acceptance_method IN ('in_platform', 'external_recorded')",
            name="ck_commercial_terms_acceptance_method",
        ),
        CheckConstraint("length(currency) = 3", name="ck_commercial_terms_currency"),
        CheckConstraint(
            "payment_class IN ('standard_prepaid', 'approved_corporate_credit')",
            name="ck_commercial_terms_payment_class",
        ),
        CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 "
            "AND tax_amount >= 0 AND gross_amount >= 0 "
            "AND production_cost_amount >= 0",
            name="ck_commercial_terms_amounts_non_negative",
        ),
        CheckConstraint(
            "gross_amount = net_amount + tax_amount",
            name="ck_commercial_terms_total_conservation",
        ),
        CheckConstraint(
            "standard_production_wait_hours = 24",
            name="ck_commercial_terms_standard_wait",
        ),
        CheckConstraint(
            "(acceptance_method = 'in_platform' AND accepted_by_user_id IS NOT NULL "
            "AND external_acceptance_reference IS NULL) OR "
            "(acceptance_method = 'external_recorded' AND accepted_by_user_id IS NULL "
            "AND external_acceptance_reference IS NOT NULL)",
            name="ck_commercial_terms_acceptance_evidence",
        ),
        UniqueConstraint("campaign_id", name="uq_commercial_terms_campaign"),
        UniqueConstraint("quotation_revision_id", name="uq_commercial_terms_quote_revision"),
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
    quotation_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_quotation_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    quote_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    quotation_revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    production_scope: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    production_cost_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_class: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_terms: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    standard_production_wait_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    acceptance_method: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    external_acceptance_reference: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
