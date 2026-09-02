from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.billing import (
    AcceptanceMethod,
    FinancialAuthorityType,
    InvoiceCorrectionType,
    IssuerVerificationStatus,
    PaymentClass,
)


class ORMRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanyProfileRead(ORMRead):
    id: UUID
    name: str
    billing_email: str | None
    address_line_1: str | None
    address_line_2: str | None
    address_city: str | None
    address_region: str | None
    address_postal_code: str | None
    address_country_code: str | None
    industry: str | None
    operational_contact_name: str | None
    operational_contact_email: str | None
    operational_contact_phone: str | None
    billing_contact_name: str | None
    billing_contact_phone: str | None
    profile_notes: str | None
    country_code: str | None
    currency: str
    status: str


class CompanyProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    billing_email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    address_city: str | None = None
    address_region: str | None = None
    address_postal_code: str | None = None
    address_country_code: str | None = None
    industry: str | None = None
    operational_contact_name: str | None = None
    operational_contact_email: str | None = None
    operational_contact_phone: str | None = None
    billing_contact_name: str | None = None
    billing_contact_phone: str | None = None
    profile_notes: str | None = None
    country_code: str | None = None
    currency: str | None = None
    status: str | None = None


class QuoteRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_details: dict[str, Any] = Field(default_factory=dict)


class QuoteRequestRead(ORMRead):
    id: UUID
    campaign_id: UUID
    organization_id: UUID
    source: str
    request_details: dict[str, Any]
    requested_by_user_id: UUID
    requested_at: datetime


class QuoteRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_reference: str
    currency: str
    line_items: list[dict[str, Any]]
    production_scope: dict[str, Any]
    payment_class: PaymentClass
    payment_terms: dict[str, Any] = Field(default_factory=dict)
    tax_rate: Decimal


class QuoteRevisionRead(ORMRead):
    id: UUID
    quote_request_id: UUID
    campaign_id: UUID
    organization_id: UUID
    revision_number: int
    quote_reference: str
    currency: str
    line_items: list[dict[str, Any]]
    production_scope: dict[str, Any]
    production_cost_amount: Decimal
    payment_class: str
    payment_terms: dict[str, Any]
    net_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    created_at: datetime


class QuoteAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acceptance_method: AcceptanceMethod = AcceptanceMethod.IN_PLATFORM
    external_accepted_at: datetime | None = None
    external_acceptance_reference: str | None = None


class CommercialTermsRead(ORMRead):
    id: UUID
    campaign_id: UUID
    organization_id: UUID
    quotation_revision_id: UUID
    quote_reference: str
    quotation_revision_number: int
    currency: str
    line_items: list[dict[str, Any]]
    production_scope: dict[str, Any]
    production_cost_amount: Decimal
    payment_class: str
    payment_terms: dict[str, Any]
    standard_production_wait_hours: int
    net_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    acceptance_method: str
    accepted_at: datetime


class ReceiptRead(ORMRead):
    id: UUID
    organization_id: UUID
    method: str
    provider: str
    external_transaction_id: str
    amount: Decimal
    currency: str
    payer_name: str
    evidence_reference: str
    observed_at: datetime


class ReceiptEventRead(ORMRead):
    id: UUID
    receipt_id: UUID
    sequence_number: int
    status: str
    reason: str | None
    occurred_at: datetime


class ReceiptAllocationRead(ORMRead):
    id: UUID
    receipt_id: UUID
    commercial_terms_id: UUID
    amount: Decimal
    currency: str
    allocated_at: datetime


class BillingHistoryEntry(BaseModel):
    receipt: ReceiptRead
    events: list[ReceiptEventRead]
    allocations: list[ReceiptAllocationRead]
    current_status: str | None


class ManualTransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    commercial_terms_id: UUID
    external_transaction_id: str
    observed_amount: Decimal
    expected_amount: Decimal
    currency: str
    payer_name: str
    evidence_reference: str
    observed_at: datetime
    allocation_amount: Decimal | None = None


class ManualTransferResult(BaseModel):
    receipt: ReceiptRead
    matched: bool
    allocation: ReceiptAllocationRead | None


class IssuerProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_name: str
    tax_identification_number: str
    registered_address: str
    country_code: str
    invoice_wording: str
    numbering_prefix: str
    verification_status: IssuerVerificationStatus
    external_input_reference: str


class IssuerProfileRead(ORMRead):
    id: UUID
    legal_name: str
    tax_identification_number: str
    registered_address: str
    country_code: str
    invoice_wording: str
    numbering_prefix: str
    verification_status: str
    external_input_reference: str
    recorded_at: datetime


class InvoiceCorrectionRead(ORMRead):
    id: UUID
    invoice_id: UUID
    sequence_number: int
    correction_number: str
    correction_reference: str
    correction_type: str
    currency: str
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    reason: str
    created_at: datetime


class InvoiceRead(ORMRead):
    id: UUID
    commercial_terms_id: UUID
    campaign_id: UUID
    organization_id: UUID
    issuer_profile_id: UUID | None
    invoice_number: str | None
    status: str
    customer_snapshot: dict[str, Any]
    issuer_snapshot: dict[str, Any] | None
    line_items: list[dict[str, Any]]
    currency: str
    net_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    effective_obligation_amount: Decimal = Decimal("0.00")
    funded_amount: Decimal = Decimal("0.00")
    payment_status: str = "unpaid"
    corrections: list[InvoiceCorrectionRead] = Field(default_factory=list)
    created_at: datetime
    issued_at: datetime | None


class InvoiceDraftCreate(BaseModel):
    commercial_terms_id: UUID


class InvoiceIssue(BaseModel):
    issuer_profile_id: UUID


class FinancialAuthorityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authority_type: FinancialAuthorityType
    max_driver_liability: Decimal
    reason: str
    credit_limit: Decimal | None = None
    due_at: datetime | None = None
    approved_by_user_id: UUID | None = None
    credit_terms: dict[str, Any] | None = None
    subsidy_amount: Decimal | None = None
    subsidy_reference: str | None = None


class FinancialAuthorityRead(ORMRead):
    id: UUID
    campaign_id: UUID
    commercial_terms_id: UUID
    revision_number: int
    authority_type: str
    currency: str
    authorized_amount: Decimal
    funded_cash_amount: Decimal
    max_driver_liability: Decimal
    credit_limit: Decimal | None
    credit_due_at: datetime | None
    subsidy_reference: str | None
    effective_from: datetime
    reason: str


class WaiverCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wording_version: str
    accepted_wording: str
    accepted_wording_hash: str = Field(min_length=64, max_length=64)


class WaiverCopyRead(BaseModel):
    wording_version: str
    accepted_wording: str
    accepted_wording_hash: str


class WaiverRead(ORMRead):
    id: UUID
    campaign_id: UUID
    commercial_terms_id: UUID
    wording_version: str
    accepted_wording_hash: str
    accepted_at: datetime


class ProductionStartCreate(BaseModel):
    waiver_id: UUID | None = None


class ProductionStartRead(ORMRead):
    id: UUID
    campaign_id: UUID
    authorization_id: UUID
    authority_basis: str
    waiver_id: UUID | None
    fully_funded_at: datetime | None
    started_at: datetime


class ReceiptReverse(BaseModel):
    reason: str


class InvoiceCorrectionCreate(BaseModel):
    correction_reference: str = Field(min_length=8, max_length=128)
    correction_type: InvoiceCorrectionType
    net_amount: Decimal
    tax_amount: Decimal
    reason: str

    @field_validator("correction_reference")
    @classmethod
    def validate_correction_reference(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.lower().startswith("legacy:"):
            raise ValueError("correction_reference uses a reserved namespace")
        return normalized


class RefundCreate(BaseModel):
    commercial_terms_id: UUID
    receipt_id: UUID
    amount: Decimal
    settlement_provider: str
    external_reference: str
    reason: str


class CreditSettlementCreate(BaseModel):
    commercial_terms_id: UUID
    settlement_provider: str
    external_reference: str
    reason: str


class SettlementRead(ORMRead):
    id: UUID
    commercial_terms_id: UUID
    campaign_id: UUID
    receipt_id: UUID | None
    cancellation_id: UUID | None
    disposition: str
    amount: Decimal
    currency: str
    funding_authorized_at: datetime | None
    eligibility_ends_at: datetime | None
    eligibility_evaluated_at: datetime | None
    settlement_provider: str
    external_reference: str
    reason: str
    recorded_at: datetime


class BudgetEvaluationRead(ORMRead):
    id: UUID
    campaign_id: UUID
    state: str
    external_gate: str | None
    campaign_budget_amount: Decimal | None
    campaign_daily_budget_amount: Decimal | None
    currency: str
    policy_id: str | None
    policy_revision: str | None
    policy_source: str | None
    budget_basis: str | None
    billing_fact_source: str | None
    billing_spend_amount: Decimal | None
    alert_threshold_amount: Decimal | None
    pause_threshold_amount: Decimal | None
    resume_threshold_amount: Decimal | None
    alert_applied: bool
    pause_applied: bool
    resume_allowed: bool
    evaluated_at: datetime


class BudgetResumeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class BudgetTransitionRead(ORMRead):
    id: UUID
    campaign_id: UUID
    evaluation_id: UUID
    action: str
    prior_status: str
    new_status: str
    actor_user_id: UUID | None
    reason: str | None
    created_at: datetime


class CampaignCommercialRead(BaseModel):
    quote_request: QuoteRequestRead | None
    revisions: list[QuoteRevisionRead]
    terms: CommercialTermsRead | None
    invoices: list[InvoiceRead]
    financial_authority: FinancialAuthorityRead | None
    expedited_waiver_copy: WaiverCopyRead
    waiver: WaiverRead | None
    production_start: ProductionStartRead | None
    settlements: list[SettlementRead]
    budget_evaluations: list[BudgetEvaluationRead]


class PaymentWebhookReceipt(BaseModel):
    event_id: UUID
    accepted: bool
    duplicate: bool
