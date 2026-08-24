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


class ReceiptMethod(StrEnum):
    MANUAL_TRANSFER = "manual_transfer"
    GATEWAY = "gateway"


class ReceiptLifecycleStatus(StrEnum):
    OBSERVED = "observed"
    RECONCILED = "reconciled"
    CONFIRMED = "confirmed"
    REVERSED = "reversed"


class IssuerVerificationStatus(StrEnum):
    SYNTHETIC = "synthetic"
    VERIFIED = "verified"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    VOID = "void"


class FinancialAuthorityType(StrEnum):
    PREPAID_CASH = "prepaid_cash"
    APPROVED_CREDIT = "approved_credit"
    SUBSIDY = "subsidy"


class LiabilityReservationStatus(StrEnum):
    PENDING_FUNDING = "pending_funding"
    RESERVED = "reserved"


class ProductionAuthorityBasis(StrEnum):
    STANDARD_WINDOW_ELAPSED = "standard_window_elapsed"
    ADVERTISER_EXPEDITED_WAIVER = "advertiser_expedited_waiver"
    APPROVED_CREDIT = "approved_credit"


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


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"
    __table_args__ = (
        CheckConstraint(
            "method IN ('manual_transfer', 'gateway')", name="ck_payment_receipts_method"
        ),
        CheckConstraint("length(currency) = 3", name="ck_payment_receipts_currency"),
        CheckConstraint("amount > 0", name="ck_payment_receipts_amount_positive"),
        UniqueConstraint(
            "external_transaction_id", name="uq_payment_receipts_external_transaction"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReceiptReconciliation(Base):
    __tablename__ = "receipt_reconciliations"
    __table_args__ = (
        CheckConstraint(
            "length(expected_currency) = 3", name="ck_receipt_reconciliations_currency"
        ),
        CheckConstraint("expected_amount > 0", name="ck_receipt_reconciliations_amount_positive"),
        UniqueConstraint("receipt_id", name="uq_receipt_reconciliations_receipt"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_receipts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    expected_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    matched: Mapped[bool] = mapped_column(nullable=False)
    reconciled_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReceiptLifecycleEvent(Base):
    __tablename__ = "receipt_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('observed', 'reconciled', 'confirmed', 'reversed')",
            name="ck_receipt_lifecycle_events_status",
        ),
        CheckConstraint("sequence_number BETWEEN 1 AND 4", name="ck_receipt_lifecycle_sequence"),
        CheckConstraint(
            "(status = 'observed' AND sequence_number = 1) OR "
            "(status = 'reconciled' AND sequence_number = 2) OR "
            "(status = 'confirmed' AND sequence_number = 3) OR "
            "(status = 'reversed' AND sequence_number = 4)",
            name="ck_receipt_lifecycle_status_sequence",
        ),
        UniqueConstraint("receipt_id", "status", name="uq_receipt_lifecycle_status"),
        UniqueConstraint("receipt_id", "sequence_number", name="uq_receipt_lifecycle_sequence"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_receipts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReceiptAllocation(Base):
    __tablename__ = "receipt_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_receipt_allocations_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_receipt_allocations_currency"),
        UniqueConstraint("receipt_id", "commercial_terms_id", name="uq_receipt_allocations_terms"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_receipts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commercial_terms_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_terms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    allocated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceIssuerProfile(Base):
    __tablename__ = "invoice_issuer_profiles"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('synthetic', 'verified')",
            name="ck_invoice_issuer_profiles_verification",
        ),
        CheckConstraint("length(country_code) = 2", name="ck_invoice_issuer_profiles_country"),
        UniqueConstraint(
            "external_input_reference", name="uq_invoice_issuer_profiles_external_ref"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_identification_number: Mapped[str] = mapped_column(String(128), nullable=False)
    registered_address: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    invoice_wording: Mapped[str] = mapped_column(Text, nullable=False)
    numbering_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_input_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceNumberSequence(Base):
    __tablename__ = "invoice_number_sequences"
    __table_args__ = (
        CheckConstraint("calendar_year >= 2020", name="ck_invoice_number_sequences_year"),
        CheckConstraint("next_number > 0", name="ck_invoice_number_sequences_next"),
        UniqueConstraint(
            "issuer_profile_id",
            "calendar_year",
            name="uq_invoice_number_sequences_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    issuer_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoice_issuer_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    calendar_year: Mapped[int] = mapped_column(Integer, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'issued', 'void')", name="ck_invoices_status"),
        CheckConstraint("length(currency) = 3", name="ck_invoices_currency"),
        CheckConstraint(
            "net_amount >= 0 AND tax_rate >= 0 AND tax_rate <= 1 "
            "AND tax_amount >= 0 AND gross_amount >= 0",
            name="ck_invoices_amounts_non_negative",
        ),
        CheckConstraint(
            "gross_amount = net_amount + tax_amount", name="ck_invoices_total_conservation"
        ),
        CheckConstraint(
            "(status = 'draft' AND invoice_number IS NULL AND issued_at IS NULL AND "
            "issuer_profile_id IS NULL AND issuer_snapshot IS NULL AND "
            "issued_by_user_id IS NULL) OR "
            "(status IN ('issued', 'void') AND invoice_number IS NOT NULL AND "
            "issued_at IS NOT NULL AND issuer_profile_id IS NOT NULL AND "
            "issuer_snapshot IS NOT NULL AND issued_by_user_id IS NOT NULL)",
            name="ck_invoices_issuance_state",
        ),
        UniqueConstraint("commercial_terms_id", name="uq_invoices_commercial_terms"),
        UniqueConstraint("invoice_number", name="uq_invoices_number"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    commercial_terms_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_terms.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("advertiser_organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    issuer_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("invoice_issuer_profiles.id", ondelete="RESTRICT")
    )
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    issuer_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CampaignFinancialAuthorization(Base):
    __tablename__ = "campaign_financial_authorizations"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0", name="ck_campaign_financial_authorizations_revision"
        ),
        CheckConstraint(
            "authority_type IN ('prepaid_cash', 'approved_credit', 'subsidy')",
            name="ck_campaign_financial_authorizations_type",
        ),
        CheckConstraint(
            "length(currency) = 3", name="ck_campaign_financial_authorizations_currency"
        ),
        CheckConstraint(
            "authorized_amount > 0 AND max_driver_liability > 0 "
            "AND max_driver_liability <= authorized_amount",
            name="ck_campaign_financial_authorizations_amounts",
        ),
        CheckConstraint(
            "(authority_type = 'prepaid_cash' AND funded_cash_amount = authorized_amount "
            "AND credit_limit IS NULL AND credit_due_at IS NULL AND "
            "credit_approved_by_user_id IS NULL AND credit_terms IS NULL "
            "AND subsidy_reference IS NULL) OR "
            "(authority_type = 'approved_credit' AND funded_cash_amount = 0 "
            "AND credit_limit = authorized_amount AND credit_due_at IS NOT NULL AND "
            "credit_approved_by_user_id IS NOT NULL AND credit_terms IS NOT NULL "
            "AND subsidy_reference IS NULL) OR "
            "(authority_type = 'subsidy' AND funded_cash_amount = 0 "
            "AND credit_limit IS NULL AND credit_due_at IS NULL AND "
            "credit_approved_by_user_id IS NULL AND credit_terms IS NULL "
            "AND subsidy_reference IS NOT NULL)",
            name="ck_campaign_financial_authorizations_evidence",
        ),
        UniqueConstraint(
            "campaign_id", "revision_number", name="uq_campaign_financial_authorization_revision"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commercial_terms_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_terms.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    authority_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    authorized_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    funded_cash_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    max_driver_liability: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    credit_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credit_approved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    credit_terms: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    subsidy_reference: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinancialAuthorizationAllocation(Base):
    __tablename__ = "financial_authorization_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_financial_authorization_allocations_amount"),
        UniqueConstraint(
            "authorization_id",
            "receipt_allocation_id",
            name="uq_financial_authorization_allocation_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_financial_authorizations.id", ondelete="RESTRICT"), nullable=False
    )
    receipt_allocation_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_allocations.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class CampaignLiabilityReservation(Base):
    __tablename__ = "campaign_liability_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_funding', 'reserved')",
            name="ck_campaign_liability_reservations_status",
        ),
        CheckConstraint(
            "covered_vehicle_days > 0 AND hourly_rate >= 0 AND daily_hours_cap > 0 "
            "AND requested_amount > 0 AND formula_version <> ''",
            name="ck_campaign_liability_reservations_formula",
        ),
        CheckConstraint(
            "(status = 'pending_funding' AND authorization_id IS NULL "
            "AND reserved_amount IS NULL AND reserved_at IS NULL) OR "
            "(status = 'reserved' AND authorization_id IS NOT NULL "
            "AND reserved_amount = requested_amount AND reserved_at IS NOT NULL)",
            name="ck_campaign_liability_reservations_state",
        ),
        UniqueConstraint("assignment_id", name="uq_campaign_liability_reservations_assignment"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_rule_binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignment_rule_bindings.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaign_financial_authorizations.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    covered_vehicle_days: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    daily_hours_cap: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reserved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)


class ExpeditedProductionWaiver(Base):
    __tablename__ = "expedited_production_waivers"
    __table_args__ = (
        CheckConstraint(
            "accepted_at >= requested_at", name="ck_expedited_production_waivers_timeline"
        ),
        CheckConstraint(
            "length(accepted_wording_hash) = 64 AND wording_version <> ''",
            name="ck_expedited_production_waivers_wording",
        ),
        UniqueConstraint("campaign_id", name="uq_expedited_production_waivers_campaign"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    commercial_terms_id: Mapped[UUID] = mapped_column(
        ForeignKey("commercial_terms.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wording_version: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted_wording_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ProductionStart(Base):
    __tablename__ = "production_starts"
    __table_args__ = (
        CheckConstraint(
            "authority_basis IN ('standard_window_elapsed', "
            "'advertiser_expedited_waiver', 'approved_credit')",
            name="ck_production_starts_authority_basis",
        ),
        CheckConstraint(
            "(authority_basis = 'advertiser_expedited_waiver' AND waiver_id IS NOT NULL) OR "
            "(authority_basis <> 'advertiser_expedited_waiver' AND waiver_id IS NULL)",
            name="ck_production_starts_waiver_basis",
        ),
        CheckConstraint(
            "(authority_basis IN ('standard_window_elapsed', 'advertiser_expedited_waiver') "
            "AND fully_funded_at IS NOT NULL) OR "
            "(authority_basis = 'approved_credit' AND fully_funded_at IS NULL)",
            name="ck_production_starts_funding_basis",
        ),
        CheckConstraint(
            "fully_funded_at IS NULL OR started_at >= fully_funded_at",
            name="ck_production_starts_timeline",
        ),
        UniqueConstraint("campaign_id", name="uq_production_starts_campaign"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    authorization_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_financial_authorizations.id", ondelete="RESTRICT"), nullable=False
    )
    authority_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    waiver_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("expedited_production_waivers.id", ondelete="RESTRICT")
    )
    fully_funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
