import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.budget import (
    BudgetPolicyAdapter,
    BudgetPolicyContext,
    DisabledBudgetPolicyAdapter,
)
from app.adapters.budget.provider import (
    BLOCKED_BUDGET_POLICY_STATE,
    MISSING_BUDGET_POLICY_GATE,
)
from app.adapters.payments import (
    PaymentGatewayAdapter,
    PaymentGatewayUnavailableError,
    PaymentWebhookAuthenticationError,
    PaymentWebhookPayloadError,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    BudgetCampaignTransition,
    BudgetCampaignTransitionAction,
    BudgetPolicyEvaluation,
    BudgetPolicyEvaluationState,
    CampaignFinancialAuthorization,
    CampaignLiabilityReservation,
    CommercialQuotationRevision,
    CommercialQuoteRequest,
    CommercialTerms,
    ExpeditedProductionWaiver,
    FinancialAuthorityType,
    FinancialAuthorizationAllocation,
    Invoice,
    InvoiceCorrection,
    InvoiceCorrectionType,
    InvoiceIssuerProfile,
    InvoiceNumberSequence,
    InvoiceStatus,
    IssuerVerificationStatus,
    PaymentClass,
    PaymentGatewayEvent,
    PaymentGatewayProcessingAttempt,
    PaymentReceipt,
    ProductionAuthorityBasis,
    ProductionStart,
    QuoteRequestSource,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptMethod,
    ReceiptReconciliation,
    RefundSettlement,
    SettlementDisposition,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationDisposition,
)
from app.models.organization import AdvertiserOrganization
from app.models.payout import AssignmentRuleBinding
from app.models.user import User, UserRole, UserStatus
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

MONEY_QUANTUM = Decimal("0.01")

EXPEDITED_WAIVER_WORDING_VERSION = "advertiser-expedited-v1"
EXPEDITED_WAIVER_WORDING = (
    "I request expedited production and understand refund eligibility ends only when "
    "expedited production actually starts."
)
EXPEDITED_WAIVER_WORDING_HASH = hashlib.sha256(EXPEDITED_WAIVER_WORDING.encode()).hexdigest()

RECEIPT_SEQUENCE = {
    ReceiptLifecycleStatus.OBSERVED: 1,
    ReceiptLifecycleStatus.RECONCILED: 2,
    ReceiptLifecycleStatus.CONFIRMED: 3,
    ReceiptLifecycleStatus.REVERSED: 4,
}

LIABILITY_FORMULA_VERSION = "rate-cap-vehicle-days-v1"
LAGOS_TZ = ZoneInfo("Africa/Lagos")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            "INVALID_ACCEPTED_AT",
            "accepted_at must include a timezone",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return value.astimezone(UTC)


def _stored_aware_utc(value: datetime) -> datetime:
    """Normalize a trusted DB timestamp (SQLite reflection drops tzinfo)."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _money(value: Decimal | str, field: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(MONEY_QUANTUM):
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a non-negative two-decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return amount


def _tax_rate(value: Decimal | str) -> Decimal:
    try:
        rate = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not rate.is_finite() or rate < 0 or rate > 1 or rate != rate.quantize(Decimal("0.000001")):
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1 with at most six decimal places",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return rate


def _canonical_line_items(
    line_items: list[dict],
) -> tuple[list[dict], Decimal, Decimal]:
    if not line_items:
        raise AppError(
            "COMMERCIAL_LINE_ITEMS_REQUIRED",
            "At least one structured quotation line item is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    canonical: list[dict] = []
    net = Decimal("0.00")
    production = Decimal("0.00")
    for index, item in enumerate(line_items):
        if not isinstance(item, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                "Each quotation line item must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        code = str(item.get("code", "")).strip()
        description = str(item.get("description", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not code or not description or kind not in {"media", "production", "other"}:
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} requires code, description and a supported kind",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        amount = _money(item.get("amount", ""), f"line_items[{index}].amount")
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        canonical.append(
            {
                "code": code,
                "description": description,
                "kind": kind,
                "amount": f"{amount:.2f}",
                "metadata": deepcopy(metadata),
            }
        )
        net += amount
        if kind == "production":
            production += amount
    return canonical, net, production


async def _campaign(session: AsyncSession, campaign_id: UUID, *, lock: bool = False) -> Campaign:
    statement = select(Campaign).where(Campaign.id == campaign_id)
    if lock:
        statement = statement.with_for_update()
    campaign = (await session.execute(statement)).scalar_one_or_none()
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    return campaign


async def request_custom_quote(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    source: QuoteRequestSource,
    request_details: dict,
) -> CommercialQuoteRequest:
    if source != QuoteRequestSource.IN_PLATFORM:
        await require_active_admin(session, actor_user_id)
    campaign = await _campaign(session, campaign_id)
    if source == QuoteRequestSource.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != campaign.organization_id:
            raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    if not isinstance(request_details, dict):
        raise AppError(
            "INVALID_QUOTE_REQUEST",
            "request_details must be a structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    quote_request = CommercialQuoteRequest(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        source=source,
        request_details=deepcopy(request_details),
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(quote_request)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "QUOTE_REQUEST_ALREADY_EXISTS",
            "This campaign already has a custom quotation request",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.quote_request.created",
        entity_type="commercial_quote_request",
        entity_id=str(quote_request.id),
        metadata={"campaign_id": str(campaign.id), "source": source.value},
    )
    return quote_request


async def record_quotation_revision(
    session: AsyncSession,
    *,
    quote_request_id: UUID,
    actor_user_id: UUID,
    quote_reference: str,
    currency: str,
    line_items: list[dict],
    production_scope: dict,
    payment_class: PaymentClass,
    payment_terms: dict,
    tax_rate: Decimal | str,
) -> CommercialQuotationRevision:
    campaign_id = await session.scalar(
        select(CommercialQuoteRequest.campaign_id).where(
            CommercialQuoteRequest.id == quote_request_id
        )
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    quote_request = await session.get(CommercialQuoteRequest, quote_request_id)
    if quote_request is None:
        raise AppError("QUOTE_REQUEST_NOT_FOUND", "Quote request was not found", status_code=404)
    assert campaign_id == quote_request.campaign_id
    campaign = await _campaign(session, quote_request.campaign_id, lock=True)
    reference = quote_reference.strip()
    normalized_currency = currency.strip().upper()
    if not reference or len(normalized_currency) != 3 or normalized_currency != campaign.currency:
        raise AppError(
            "INVALID_QUOTATION_IDENTITY",
            "Quote reference and campaign currency are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(production_scope, dict) or not production_scope:
        raise AppError(
            "PRODUCTION_SCOPE_REQUIRED",
            "production_scope must be a non-empty structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(payment_terms, dict):
        raise AppError(
            "INVALID_PAYMENT_TERMS",
            "payment_terms must be a structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    canonical_lines, net_amount, production_cost = _canonical_line_items(line_items)
    rate = _tax_rate(tax_rate)
    tax_amount = (net_amount * rate).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    revision_number = (
        int(
            await session.scalar(
                select(
                    func.coalesce(func.max(CommercialQuotationRevision.revision_number), 0)
                ).where(CommercialQuotationRevision.quote_request_id == quote_request.id)
            )
            or 0
        )
        + 1
    )
    revision = CommercialQuotationRevision(
        quote_request_id=quote_request.id,
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        revision_number=revision_number,
        quote_reference=reference,
        currency=normalized_currency,
        line_items=canonical_lines,
        production_scope=deepcopy(production_scope),
        production_cost_amount=production_cost,
        payment_class=payment_class,
        payment_terms=deepcopy(payment_terms),
        net_amount=net_amount,
        tax_rate=rate,
        tax_amount=tax_amount,
        gross_amount=net_amount + tax_amount,
        created_by_user_id=actor_user_id,
    )
    session.add(revision)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.quotation_revision.recorded",
        entity_type="commercial_quotation_revision",
        entity_id=str(revision.id),
        metadata={
            "campaign_id": str(campaign.id),
            "quote_reference": reference,
            "revision_number": revision_number,
            "currency": normalized_currency,
            "net_amount": f"{net_amount:.2f}",
            "tax_rate": str(rate),
            "tax_amount": f"{tax_amount:.2f}",
            "gross_amount": f"{revision.gross_amount:.2f}",
        },
    )
    return revision


async def accept_quotation_revision(
    session: AsyncSession,
    *,
    quotation_revision_id: UUID,
    actor_user_id: UUID,
    acceptance_method: AcceptanceMethod,
    external_accepted_at: datetime | None = None,
    external_acceptance_reference: str | None = None,
) -> CommercialTerms:
    campaign_id = await session.scalar(
        select(CommercialQuotationRevision.campaign_id).where(
            CommercialQuotationRevision.id == quotation_revision_id
        )
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    if acceptance_method != AcceptanceMethod.IN_PLATFORM:
        await require_active_admin(session, actor_user_id)
    revision = await session.get(CommercialQuotationRevision, quotation_revision_id)
    if revision is None:
        raise AppError("QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404)
    assert campaign_id == revision.campaign_id
    revision = (
        await session.execute(
            select(CommercialQuotationRevision)
            .where(CommercialQuotationRevision.id == quotation_revision_id)
            .with_for_update()
        )
    ).scalar_one()
    campaign = await _campaign(session, revision.campaign_id, lock=True)
    if campaign.currency != revision.currency:
        raise AppError(
            "QUOTATION_CURRENCY_MISMATCH",
            "Quotation currency must match the campaign currency at acceptance",
            status_code=status.HTTP_409_CONFLICT,
        )
    quote_request = await session.get(CommercialQuoteRequest, revision.quote_request_id)
    expected_source = (
        QuoteRequestSource.IN_PLATFORM
        if acceptance_method == AcceptanceMethod.IN_PLATFORM
        else QuoteRequestSource.EXTERNAL_RECORDED
    )
    if quote_request is None or quote_request.source != expected_source:
        raise AppError(
            "ACCEPTANCE_PROVENANCE_MISMATCH",
            "Acceptance method must match the recorded quotation provenance",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if acceptance_method == AcceptanceMethod.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != revision.organization_id:
            raise AppError(
                "QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404
            )
        accepted_by_user_id = actor_user_id
        accepted_at = now
        external_reference = None
    else:
        external_reference = (external_acceptance_reference or "").strip()
        if not external_reference or external_accepted_at is None:
            raise AppError(
                "EXTERNAL_ACCEPTANCE_EVIDENCE_REQUIRED",
                "External acceptance requires its reference and accepted_at",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        accepted_at = _aware_utc(external_accepted_at)
        if accepted_at > now:
            raise AppError(
                "INVALID_ACCEPTED_AT",
                "External acceptance cannot be recorded in the future",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        accepted_by_user_id = None
    existing_terms = await _commercial_terms_for_campaign(session, revision.campaign_id, lock=True)
    if existing_terms is not None:
        same_acceptance = (
            existing_terms.quotation_revision_id == revision.id
            and existing_terms.acceptance_method == acceptance_method
            and existing_terms.recorded_by_user_id == actor_user_id
            and existing_terms.accepted_by_user_id == accepted_by_user_id
            and existing_terms.external_acceptance_reference == external_reference
            and (
                acceptance_method == AcceptanceMethod.IN_PLATFORM
                or _stored_aware_utc(existing_terms.accepted_at) == accepted_at
            )
        )
        if same_acceptance:
            return existing_terms
        raise AppError(
            "COMMERCIAL_TERMS_ALREADY_ACCEPTED",
            "This campaign already has immutable accepted commercial terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    latest_revision_number = await session.scalar(
        select(func.max(CommercialQuotationRevision.revision_number)).where(
            CommercialQuotationRevision.quote_request_id == revision.quote_request_id
        )
    )
    if latest_revision_number != revision.revision_number:
        raise AppError(
            "QUOTATION_REVISION_SUPERSEDED",
            "Only the latest quotation revision can be accepted",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = CommercialTerms(
        campaign_id=revision.campaign_id,
        organization_id=revision.organization_id,
        quotation_revision_id=revision.id,
        quote_reference=revision.quote_reference,
        quotation_revision_number=revision.revision_number,
        currency=revision.currency,
        line_items=deepcopy(revision.line_items),
        production_scope=deepcopy(revision.production_scope),
        production_cost_amount=revision.production_cost_amount,
        payment_class=revision.payment_class,
        payment_terms=deepcopy(revision.payment_terms),
        standard_production_wait_hours=revision.standard_production_wait_hours,
        net_amount=revision.net_amount,
        tax_rate=revision.tax_rate,
        tax_amount=revision.tax_amount,
        gross_amount=revision.gross_amount,
        acceptance_method=acceptance_method,
        accepted_by_user_id=accepted_by_user_id,
        recorded_by_user_id=actor_user_id,
        external_acceptance_reference=external_reference,
        accepted_at=accepted_at,
    )
    try:
        async with session.begin_nested():
            session.add(terms)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "COMMERCIAL_TERMS_ALREADY_ACCEPTED",
            "This campaign already has immutable accepted commercial terms",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.terms.accepted",
        entity_type="commercial_terms",
        entity_id=str(terms.id),
        metadata={
            "campaign_id": str(terms.campaign_id),
            "quotation_revision_id": str(revision.id),
            "quote_reference": terms.quote_reference,
            "revision_number": terms.quotation_revision_number,
            "acceptance_method": acceptance_method.value,
            "accepted_at": accepted_at.isoformat(),
            "currency": terms.currency,
            "net_amount": f"{terms.net_amount:.2f}",
            "tax_amount": f"{terms.tax_amount:.2f}",
            "gross_amount": f"{terms.gross_amount:.2f}",
        },
    )
    return terms


async def _receipt_status(session: AsyncSession, receipt_id: UUID) -> str | None:
    return await session.scalar(
        select(ReceiptLifecycleEvent.status)
        .where(ReceiptLifecycleEvent.receipt_id == receipt_id)
        .order_by(ReceiptLifecycleEvent.sequence_number.desc())
        .limit(1)
    )


async def _append_receipt_event(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    lifecycle_status: ReceiptLifecycleStatus,
    actor_user_id: UUID | None,
    occurred_at: datetime,
    reason: str | None = None,
) -> ReceiptLifecycleEvent:
    event = ReceiptLifecycleEvent(
        receipt_id=receipt_id,
        status=lifecycle_status,
        sequence_number=RECEIPT_SEQUENCE[lifecycle_status],
        actor_user_id=actor_user_id,
        reason=reason,
        occurred_at=occurred_at,
    )
    session.add(event)
    await session.flush()
    return event


async def _trusted_confirmed_gateway_event(
    session: AsyncSession, event_id: UUID
) -> tuple[PaymentGatewayEvent, CommercialTerms]:
    event = await session.scalar(
        select(PaymentGatewayEvent).where(PaymentGatewayEvent.id == event_id).with_for_update()
    )
    if event is None or event.event_type != "payment_confirmed":
        raise AppError(
            "CONFIRMED_GATEWAY_EVENT_REQUIRED",
            "A persisted confirmed provider event is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    try:
        terms_id = UUID(event.commercial_terms_reference)
    except ValueError as exc:
        raise AppError(
            "PAYMENT_EVENT_TERMS_MISMATCH",
            "Provider event contains an invalid commercial terms reference",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    terms = await session.get(CommercialTerms, terms_id)
    if terms is None:
        raise AppError(
            "PAYMENT_EVENT_TERMS_MISMATCH",
            "Provider event does not resolve to accepted commercial terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    return event, terms


async def record_payment_receipt(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID | None,
    method: ReceiptMethod,
    provider: str,
    external_transaction_id: str,
    amount: Decimal | str,
    currency: str,
    payer_name: str,
    evidence_reference: str,
    observed_at: datetime,
    trusted_gateway_event_id: UUID | None = None,
) -> PaymentReceipt:
    if actor_user_id is None:
        if method != ReceiptMethod.GATEWAY or trusted_gateway_event_id is None:
            raise AppError(
                "RECEIPT_ACTOR_REQUIRED",
                "A trusted gateway or active administrator is required",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        gateway_event, gateway_terms = await _trusted_confirmed_gateway_event(
            session, trusted_gateway_event_id
        )
        if not all(
            (
                organization_id == gateway_terms.organization_id,
                provider.strip().lower() == gateway_event.provider,
                external_transaction_id.strip()
                == f"{gateway_event.provider}:{gateway_event.external_transaction_id}",
                Decimal(str(amount)) == Decimal(gateway_event.amount),
                currency.strip().upper() == gateway_event.currency,
                payer_name.strip() == gateway_event.payer_name,
                _stored_aware_utc(observed_at)
                == _stored_aware_utc(gateway_event.occurred_at),
            )
        ):
            raise AppError(
                "GATEWAY_RECEIPT_LINEAGE_MISMATCH",
                "Receipt facts must exactly match persisted provider evidence",
                status_code=status.HTTP_409_CONFLICT,
            )
    else:
        await require_active_admin(session, actor_user_id)
    organization_exists = await session.scalar(
        select(exists().where(CommercialTerms.organization_id == organization_id))
    )
    if not organization_exists:
        raise AppError("ORGANIZATION_NOT_FOUND", "Organization was not found", status_code=404)
    normalized_provider = provider.strip().lower()
    external_id = external_transaction_id.strip()
    normalized_currency = currency.strip().upper()
    normalized_payer = payer_name.strip()
    evidence = evidence_reference.strip()
    receipt_amount = _money(amount, "amount")
    if (
        receipt_amount == 0
        or len(normalized_currency) != 3
        or not all((normalized_provider, external_id, normalized_payer, evidence))
    ):
        raise AppError(
            "INVALID_PAYMENT_RECEIPT",
            "Receipt identity, positive amount, currency, payer and evidence are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    observed = _aware_utc(observed_at)

    def exact_match(candidate: PaymentReceipt) -> bool:
        return (
            candidate.organization_id == organization_id
            and candidate.method == method
            and candidate.provider == normalized_provider
            and candidate.amount == receipt_amount
            and candidate.currency == normalized_currency
            and candidate.payer_name == normalized_payer
            and candidate.evidence_reference == evidence
            and candidate.observed_at == observed
        )

    existing = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.external_transaction_id == external_id)
    )
    if existing is not None:
        if exact_match(existing):
            return existing
        raise AppError(
            "RECEIPT_IDENTITY_CONFLICT",
            "External transaction identity already belongs to different evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt = PaymentReceipt(
        organization_id=organization_id,
        method=method,
        provider=normalized_provider,
        external_transaction_id=external_id,
        amount=receipt_amount,
        currency=normalized_currency,
        payer_name=normalized_payer,
        evidence_reference=evidence,
        observed_by_user_id=actor_user_id,
        observed_at=observed,
    )
    try:
        async with session.begin_nested():
            session.add(receipt)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.external_transaction_id == external_id)
        )
        if concurrent is not None and exact_match(concurrent):
            return concurrent
        raise AppError(
            "RECEIPT_IDENTITY_CONFLICT",
            "External transaction identity is already recorded",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await _append_receipt_event(
        session,
        receipt_id=receipt.id,
        lifecycle_status=ReceiptLifecycleStatus.OBSERVED,
        actor_user_id=actor_user_id,
        occurred_at=observed,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.receipt.observed",
        entity_type="payment_receipt",
        entity_id=str(receipt.id),
        metadata={
            "organization_id": str(organization_id),
            "method": method.value,
            "provider": normalized_provider,
            "external_transaction_id": external_id,
            "amount": f"{receipt_amount:.2f}",
            "currency": normalized_currency,
        },
    )
    return receipt


async def reconcile_payment_receipt(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    actor_user_id: UUID,
    expected_amount: Decimal | str,
    expected_currency: str,
) -> ReceiptReconciliation:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    await require_active_admin(session, actor_user_id)
    if receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    existing = await session.scalar(
        select(ReceiptReconciliation).where(ReceiptReconciliation.receipt_id == receipt.id)
    )
    amount = _money(expected_amount, "expected_amount")
    currency = expected_currency.strip().upper()
    if amount == 0 or len(currency) != 3:
        raise AppError(
            "INVALID_RECONCILIATION_EXPECTATION",
            "Expected amount and currency are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if existing is not None:
        if existing.expected_amount == amount and existing.expected_currency == currency:
            return existing
        raise AppError(
            "RECONCILIATION_ALREADY_RECORDED",
            "Receipt reconciliation evidence is immutable",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    matched = receipt.amount == amount and receipt.currency == currency
    reconciliation = ReceiptReconciliation(
        receipt_id=receipt.id,
        expected_amount=amount,
        expected_currency=currency,
        matched=matched,
        reconciled_by_user_id=actor_user_id,
        reconciled_at=now,
    )
    session.add(reconciliation)
    await session.flush()
    if matched:
        await _append_receipt_event(
            session,
            receipt_id=receipt.id,
            lifecycle_status=ReceiptLifecycleStatus.RECONCILED,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.receipt.reconciled",
        entity_type="payment_receipt",
        entity_id=str(receipt.id),
        metadata={
            "expected_amount": f"{amount:.2f}",
            "expected_currency": currency,
            "matched": matched,
        },
    )
    return reconciliation


async def confirm_payment_receipt(
    session: AsyncSession, *, receipt_id: UUID, actor_user_id: UUID
) -> PaymentReceipt:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    await require_active_admin(session, actor_user_id)
    if receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    current = await _receipt_status(session, receipt.id)
    if current == ReceiptLifecycleStatus.CONFIRMED:
        return receipt
    if current != ReceiptLifecycleStatus.RECONCILED:
        raise AppError(
            "RECEIPT_NOT_RECONCILED",
            "Only an exactly matched reconciled receipt can be confirmed",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    await _append_receipt_event(
        session,
        receipt_id=receipt.id,
        lifecycle_status=ReceiptLifecycleStatus.CONFIRMED,
        actor_user_id=actor_user_id,
        occurred_at=now,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.receipt.confirmed",
        entity_type="payment_receipt",
        entity_id=str(receipt.id),
    )
    return receipt


async def allocate_payment_receipt(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    commercial_terms_id: UUID,
    actor_user_id: UUID | None,
    amount: Decimal | str,
    trusted_gateway_event_id: UUID | None = None,
) -> ReceiptAllocation:
    if actor_user_id is None:
        if trusted_gateway_event_id is None:
            raise AppError(
                "ALLOCATION_ACTOR_REQUIRED",
                "A trusted provider event or active administrator is required",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        gateway_event, gateway_terms = await _trusted_confirmed_gateway_event(
            session, trusted_gateway_event_id
        )
    else:
        if trusted_gateway_event_id is not None:
            raise AppError(
                "ALLOCATION_AUTHORITY_CONFLICT",
                "Manual and provider allocation authority cannot be combined",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    campaign_id = await session.scalar(
        select(CommercialTerms.campaign_id).where(CommercialTerms.id == commercial_terms_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    if actor_user_id is not None:
        await require_active_admin(session, actor_user_id)
    if campaign_id is None:
        raise AppError(
            "BILLING_AUTHORITY_NOT_FOUND", "Billing authority was not found", status_code=404
        )
    # Receipt-first ordering is shared with reversal. The campaign advisory,
    # campaign, terms and invoice order then matches correction and budget
    # transitions while serializing the obligation and its new funding fact.
    await _campaign(session, campaign_id, lock=True)
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.id == commercial_terms_id).with_for_update()
    )
    if receipt is None or terms is None or receipt.organization_id != terms.organization_id:
        raise AppError(
            "BILLING_AUTHORITY_NOT_FOUND", "Billing authority was not found", status_code=404
        )
    await session.scalar(
        select(Invoice.id).where(Invoice.commercial_terms_id == terms.id).with_for_update()
    )
    if actor_user_id is None and (
        gateway_terms.id != terms.id
        or gateway_event.provider != receipt.provider
        or f"{gateway_event.provider}:{gateway_event.external_transaction_id}"
        != receipt.external_transaction_id
        or Decimal(gateway_event.amount) != Decimal(str(amount))
        or gateway_event.currency != receipt.currency
    ):
        raise AppError(
            "GATEWAY_ALLOCATION_LINEAGE_MISMATCH",
            "Allocation facts must exactly match persisted provider evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    if await _receipt_status(session, receipt.id) != ReceiptLifecycleStatus.CONFIRMED:
        raise AppError(
            "RECEIPT_NOT_CONFIRMED",
            "Only a confirmed receipt can grant funding authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if receipt.currency != terms.currency:
        raise AppError(
            "ALLOCATION_CURRENCY_MISMATCH",
            "Receipt and commercial terms currencies must match",
            status_code=status.HTTP_409_CONFLICT,
        )
    allocation_amount = _money(amount, "allocation_amount")
    if allocation_amount == 0:
        raise AppError(
            "INVALID_ALLOCATION_AMOUNT",
            "Allocation amount must be positive",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    existing = await session.scalar(
        select(ReceiptAllocation).where(
            ReceiptAllocation.receipt_id == receipt.id,
            ReceiptAllocation.commercial_terms_id == terms.id,
        )
    )
    if existing is not None:
        if existing.amount == allocation_amount:
            return existing
        raise AppError(
            "ALLOCATION_ALREADY_RECORDED",
            "Receipt allocation is immutable",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt_allocated = await session.scalar(
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0)).where(
            ReceiptAllocation.receipt_id == receipt.id
        )
    )
    active_receipt = PaymentReceipt.__table__.alias("active_receipt")
    terms_allocated = await session.scalar(
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
        .join(active_receipt, active_receipt.c.id == ReceiptAllocation.receipt_id)
        .where(
            ReceiptAllocation.commercial_terms_id == terms.id,
            exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.CONFIRMED,
            ),
            ~exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
            ),
        )
    )
    if Decimal(receipt_allocated or 0) + allocation_amount > receipt.amount:
        raise AppError(
            "RECEIPT_OVERALLOCATION",
            "Allocation would exceed the receipt amount",
            status_code=status.HTTP_409_CONFLICT,
        )
    effective_obligation = await effective_invoice_obligation(
        session, commercial_terms_id=terms.id
    )
    if Decimal(terms_allocated or 0) + allocation_amount > effective_obligation:
        raise AppError(
            "OBLIGATION_OVERFUNDING",
            "Allocation would exceed the accepted commercial obligation",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    allocation = ReceiptAllocation(
        receipt_id=receipt.id,
        commercial_terms_id=terms.id,
        amount=allocation_amount,
        currency=receipt.currency,
        allocated_by_user_id=actor_user_id,
        allocation_source="provider" if trusted_gateway_event_id is not None else "manual",
        provider_event_id=trusted_gateway_event_id,
        allocated_at=now,
    )
    session.add(allocation)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.receipt.allocated",
        entity_type="receipt_allocation",
        entity_id=str(allocation.id),
        metadata={
            "receipt_id": str(receipt.id),
            "commercial_terms_id": str(terms.id),
            "amount": f"{allocation_amount:.2f}",
            "currency": receipt.currency,
        },
    )
    from app.models.notification import NotificationType
    from app.services.notifications import create_advertiser_business_notifications

    await create_advertiser_business_notifications(
        session,
        advertiser_organization_id=terms.organization_id,
        type_key=NotificationType.FUNDING_CONFIRMED,
        event_key=f"funding:allocation:v1:{allocation.id}",
        payload={
            "campaign_id": str(terms.campaign_id),
            "receipt_allocation_id": str(allocation.id),
            "currency": allocation.currency,
        },
    )
    return allocation


async def reverse_payment_receipt(
    session: AsyncSession, *, receipt_id: UUID, actor_user_id: UUID, reason: str
) -> PaymentReceipt:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    campaign_ids = sorted(
        set(
            await session.scalars(
                select(CommercialTerms.campaign_id)
                .join(
                    ReceiptAllocation,
                    ReceiptAllocation.commercial_terms_id == CommercialTerms.id,
                )
                .where(ReceiptAllocation.receipt_id == receipt_id)
            )
        ),
        key=str,
    )
    for campaign_id in campaign_ids:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    if receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    current = await _receipt_status(session, receipt.id)
    if current == ReceiptLifecycleStatus.REVERSED:
        return receipt
    if current != ReceiptLifecycleStatus.CONFIRMED:
        raise AppError(
            "RECEIPT_NOT_CONFIRMED",
            "Only a confirmed receipt can be reversed",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError(
            "REVERSAL_REASON_REQUIRED",
            "A reversal reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    now = await database_clock(session)
    await _append_receipt_event(
        session,
        receipt_id=receipt.id,
        lifecycle_status=ReceiptLifecycleStatus.REVERSED,
        actor_user_id=actor_user_id,
        occurred_at=now,
        reason=normalized_reason,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.receipt.reversed",
        entity_type="payment_receipt",
        entity_id=str(receipt.id),
        metadata={"reason": normalized_reason, "reversal_cutoff": now.isoformat()},
    )
    return receipt


async def record_invoice_issuer_profile(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    legal_name: str,
    tax_identification_number: str,
    registered_address: str,
    country_code: str,
    invoice_wording: str,
    numbering_prefix: str,
    verification_status: IssuerVerificationStatus,
    external_input_reference: str,
    settings: Settings,
) -> InvoiceIssuerProfile:
    await require_active_admin(session, actor_user_id)
    values = {
        "legal_name": legal_name.strip(),
        "tax_identification_number": tax_identification_number.strip(),
        "registered_address": registered_address.strip(),
        "country_code": country_code.strip().upper(),
        "invoice_wording": invoice_wording.strip(),
        "numbering_prefix": numbering_prefix.strip().upper(),
        "external_input_reference": external_input_reference.strip(),
    }
    if not all(values.values()) or len(values["country_code"]) != 2:
        raise AppError(
            "INCOMPLETE_ISSUER_FACTS",
            "Complete issuer facts and their external provenance are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if verification_status == IssuerVerificationStatus.VERIFIED and (
        not settings.invoice_issuer_external_input_reference
        or values["external_input_reference"] != settings.invoice_issuer_external_input_reference
    ):
        raise AppError(
            "VERIFIED_ISSUER_GATE_REQUIRED",
            "Verified issuer facts require the registered external Q28 gate",
            status_code=status.HTTP_409_CONFLICT,
        )
    existing = await session.scalar(
        select(InvoiceIssuerProfile).where(
            InvoiceIssuerProfile.external_input_reference == values["external_input_reference"]
        )
    )
    if existing is not None:
        exact = all(getattr(existing, field) == value for field, value in values.items()) and (
            existing.verification_status == verification_status
        )
        if exact:
            return existing
        raise AppError(
            "ISSUER_PROVENANCE_CONFLICT",
            "Issuer provenance reference conflicts with existing immutable facts",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    profile = InvoiceIssuerProfile(
        **values,
        verification_status=verification_status,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(profile)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(InvoiceIssuerProfile).where(
                InvoiceIssuerProfile.external_input_reference == values["external_input_reference"]
            )
        )
        if concurrent is not None:
            exact = (
                all(getattr(concurrent, field) == value for field, value in values.items())
                and concurrent.verification_status == verification_status
            )
            if exact:
                return concurrent
        raise AppError(
            "ISSUER_PROVENANCE_CONFLICT",
            "Issuer provenance reference conflicts with existing immutable facts",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice_issuer_profile.recorded",
        entity_type="invoice_issuer_profile",
        entity_id=str(profile.id),
        metadata={
            "legal_name": profile.legal_name,
            "country_code": profile.country_code,
            "verification_status": verification_status.value,
            "external_input_reference": profile.external_input_reference,
        },
    )
    return profile


def _customer_snapshot(organization: AdvertiserOrganization) -> dict:
    return {
        "organization_id": str(organization.id),
        "name": organization.name,
        "billing_email": organization.billing_email,
        "billing_contact_name": organization.billing_contact_name,
        "billing_contact_phone": organization.billing_contact_phone,
        "address": {
            "line_1": organization.address_line_1,
            "line_2": organization.address_line_2,
            "city": organization.address_city,
            "region": organization.address_region,
            "postal_code": organization.address_postal_code,
            "country_code": organization.address_country_code,
        },
    }


async def create_invoice_draft(
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    actor_user_id: UUID,
) -> Invoice:
    await require_active_admin(session, actor_user_id)
    terms = await session.get(CommercialTerms, commercial_terms_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", status_code=404
        )
    existing = await session.scalar(select(Invoice).where(Invoice.commercial_terms_id == terms.id))
    if existing is not None:
        return existing
    organization = await session.get(AdvertiserOrganization, terms.organization_id)
    if organization is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "Organization was not found", status_code=404)
    now = await database_clock(session)
    invoice = Invoice(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        organization_id=terms.organization_id,
        status=InvoiceStatus.DRAFT,
        customer_snapshot=_customer_snapshot(organization),
        issuer_snapshot=None,
        line_items=deepcopy(terms.line_items),
        currency=terms.currency,
        net_amount=terms.net_amount,
        tax_rate=terms.tax_rate,
        tax_amount=terms.tax_amount,
        gross_amount=terms.gross_amount,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(invoice)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "INVOICE_ALREADY_EXISTS",
            "An invoice already exists for these accepted terms",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice_draft.created",
        entity_type="invoice",
        entity_id=str(invoice.id),
        metadata={"commercial_terms_id": str(terms.id), "campaign_id": str(terms.campaign_id)},
    )
    return invoice


async def _acquire_invoice_number_lock(
    session: AsyncSession, number_prefix: str, calendar_year: int
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"invoice:{number_prefix}:{calendar_year}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def issue_invoice(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    issuer_profile_id: UUID,
    actor_user_id: UUID,
    settings: Settings,
) -> Invoice:
    await require_active_admin(session, actor_user_id)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    if invoice.status == InvoiceStatus.ISSUED:
        return invoice
    if invoice.status != InvoiceStatus.DRAFT:
        raise AppError(
            "INVOICE_NOT_ISSUABLE",
            "Only a draft invoice can be issued",
            status_code=status.HTTP_409_CONFLICT,
        )
    issuer = await session.get(InvoiceIssuerProfile, issuer_profile_id)
    synthetic_test_authority = (
        issuer is not None
        and settings.environment == "test"
        and issuer.verification_status == IssuerVerificationStatus.SYNTHETIC
    )
    configured_verified_authority = (
        issuer is not None
        and issuer.verification_status == IssuerVerificationStatus.VERIFIED
        and bool(settings.invoice_issuer_external_input_reference)
        and issuer.external_input_reference == settings.invoice_issuer_external_input_reference
    )
    if not synthetic_test_authority and not configured_verified_authority:
        raise AppError(
            "VERIFIED_ISSUER_FACTS_REQUIRED",
            "Real invoice issuance requires externally verified statutory issuer facts",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    organization = await session.get(AdvertiserOrganization, invoice.organization_id)
    if organization is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "Organization was not found", status_code=404)
    year = now.astimezone(LAGOS_TZ).year
    number_prefix = (
        f"TEST-{issuer.numbering_prefix}" if synthetic_test_authority else issuer.numbering_prefix
    )
    await _acquire_invoice_number_lock(session, number_prefix, year)
    sequence = await session.scalar(
        select(InvoiceNumberSequence)
        .where(
            InvoiceNumberSequence.number_prefix == number_prefix,
            InvoiceNumberSequence.calendar_year == year,
        )
        .with_for_update()
    )
    if sequence is None:
        sequence = InvoiceNumberSequence(
            number_prefix=number_prefix, calendar_year=year, next_number=1
        )
        session.add(sequence)
        await session.flush()
    number = sequence.next_number
    sequence.next_number += 1
    invoice.issuer_profile_id = issuer.id
    invoice.invoice_number = f"{number_prefix}-{year}-{number:06d}"
    invoice.status = InvoiceStatus.ISSUED
    invoice.customer_snapshot = _customer_snapshot(organization)
    invoice.issuer_snapshot = {
        "legal_name": issuer.legal_name,
        "tax_identification_number": issuer.tax_identification_number,
        "registered_address": issuer.registered_address,
        "country_code": issuer.country_code,
        "invoice_wording": issuer.invoice_wording,
        "external_input_reference": issuer.external_input_reference,
        "synthetic_test_authority": synthetic_test_authority,
    }
    invoice.issued_by_user_id = actor_user_id
    invoice.issued_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice.issued",
        entity_type="invoice",
        entity_id=str(invoice.id),
        metadata={
            "invoice_number": invoice.invoice_number,
            "organization_id": str(invoice.organization_id),
            "currency": invoice.currency,
            "net_amount": f"{invoice.net_amount:.2f}",
            "tax_rate": str(invoice.tax_rate),
            "tax_amount": f"{invoice.tax_amount:.2f}",
            "gross_amount": f"{invoice.gross_amount:.2f}",
        },
    )
    return invoice


async def invoice_payment_status(session: AsyncSession, invoice: Invoice) -> tuple[str, Decimal]:
    active_receipt = PaymentReceipt.__table__.alias("invoice_active_receipt")
    allocated = await session.scalar(
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
        .join(active_receipt, active_receipt.c.id == ReceiptAllocation.receipt_id)
        .where(
            ReceiptAllocation.commercial_terms_id == invoice.commercial_terms_id,
            exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.CONFIRMED,
            ),
            ~exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
            ),
        )
    )
    funded = Decimal(allocated or 0).quantize(MONEY_QUANTUM)
    obligation = await effective_invoice_obligation(
        session, commercial_terms_id=invoice.commercial_terms_id
    )
    if obligation == 0:
        return "paid", funded
    if funded <= 0:
        return "unpaid", funded
    if funded < obligation:
        return "partially_paid", funded
    return "paid", funded


async def process_manual_bank_transfer(
    session: AsyncSession,
    *,
    organization_id: UUID,
    commercial_terms_id: UUID,
    actor_user_id: UUID,
    external_transaction_id: str,
    observed_amount: Decimal | str,
    expected_amount: Decimal | str,
    currency: str,
    payer_name: str,
    evidence_reference: str,
    observed_at: datetime,
    allocation_amount: Decimal | str | None = None,
) -> tuple[PaymentReceipt, ReceiptReconciliation, ReceiptAllocation | None]:
    """Record, reconcile and conditionally confirm one manual bank statement line."""
    receipt = await record_payment_receipt(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        method=ReceiptMethod.MANUAL_TRANSFER,
        provider="manual-bank-transfer",
        external_transaction_id=external_transaction_id,
        amount=observed_amount,
        currency=currency,
        payer_name=payer_name,
        evidence_reference=evidence_reference,
        observed_at=observed_at,
    )
    reconciliation = await reconcile_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=actor_user_id,
        expected_amount=expected_amount,
        expected_currency=currency,
    )
    if not reconciliation.matched:
        return receipt, reconciliation, None
    await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=actor_user_id)
    amount_to_allocate = allocation_amount if allocation_amount is not None else observed_amount
    allocation = await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=commercial_terms_id,
        actor_user_id=actor_user_id,
        amount=amount_to_allocate,
    )
    return receipt, reconciliation, allocation


async def billing_history(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID | None = None,
) -> list[dict]:
    actor = await session.get(User, actor_user_id)
    if actor is None or actor.status != UserStatus.ACTIVE:
        raise AppError(
            "BILLING_HISTORY_NOT_FOUND", "Billing history was not found", status_code=404
        )
    if actor.role == UserRole.ADMIN:
        if organization_id is None:
            raise AppError(
                "ORGANIZATION_REQUIRED",
                "organization_id is required for an administrator",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        scoped_organization_id = organization_id
    else:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=False
        )
        if organization_id is not None and organization.id != organization_id:
            raise AppError(
                "BILLING_HISTORY_NOT_FOUND", "Billing history was not found", status_code=404
            )
        scoped_organization_id = organization.id
    receipts = list(
        await session.scalars(
            select(PaymentReceipt)
            .where(PaymentReceipt.organization_id == scoped_organization_id)
            .order_by(PaymentReceipt.observed_at.desc(), PaymentReceipt.id.desc())
        )
    )
    history: list[dict] = []
    for receipt in receipts:
        events = list(
            await session.scalars(
                select(ReceiptLifecycleEvent)
                .where(ReceiptLifecycleEvent.receipt_id == receipt.id)
                .order_by(ReceiptLifecycleEvent.sequence_number)
            )
        )
        allocations = list(
            await session.scalars(
                select(ReceiptAllocation).where(ReceiptAllocation.receipt_id == receipt.id)
            )
        )
        history.append(
            {
                "receipt": receipt,
                "events": events,
                "allocations": allocations,
                "current_status": events[-1].status if events else None,
            }
        )
    return history


async def _commercial_terms_for_campaign(
    session: AsyncSession, campaign_id: UUID, *, lock: bool = False
) -> CommercialTerms | None:
    statement = select(CommercialTerms).where(CommercialTerms.campaign_id == campaign_id)
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def _active_receipt_predicate(receipt_table):
    return (
        exists().where(
            ReceiptLifecycleEvent.receipt_id == receipt_table.c.id,
            ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.CONFIRMED,
        ),
        ~exists().where(
            ReceiptLifecycleEvent.receipt_id == receipt_table.c.id,
            ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
        ),
    )


async def _active_cash_allocations(
    session: AsyncSession, commercial_terms_id: UUID
) -> list[ReceiptAllocation]:
    receipt = PaymentReceipt.__table__.alias("financial_authority_receipt")
    confirmed, not_reversed = _active_receipt_predicate(receipt)
    return list(
        await session.scalars(
            select(ReceiptAllocation)
            .join(receipt, receipt.c.id == ReceiptAllocation.receipt_id)
            .where(
                ReceiptAllocation.commercial_terms_id == commercial_terms_id,
                confirmed,
                not_reversed,
            )
            .order_by(ReceiptAllocation.allocated_at, ReceiptAllocation.id)
        )
    )


async def effective_financial_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    effective_at: datetime | None = None,
) -> CampaignFinancialAuthorization | None:
    at = effective_at or await database_clock(session)
    return await session.scalar(
        select(CampaignFinancialAuthorization)
        .where(
            CampaignFinancialAuthorization.campaign_id == campaign_id,
            CampaignFinancialAuthorization.effective_from <= at,
        )
        .order_by(
            CampaignFinancialAuthorization.effective_from.desc(),
            CampaignFinancialAuthorization.revision_number.desc(),
        )
        .limit(1)
    )


async def _latest_financial_authorization(
    session: AsyncSession, campaign_id: UUID
) -> CampaignFinancialAuthorization | None:
    return await session.scalar(
        select(CampaignFinancialAuthorization)
        .where(CampaignFinancialAuthorization.campaign_id == campaign_id)
        .order_by(CampaignFinancialAuthorization.revision_number.desc())
        .limit(1)
        .with_for_update()
    )


async def _append_financial_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    authority_type: FinancialAuthorityType,
    authorized_amount: Decimal,
    max_driver_liability: Decimal,
    reason: str,
    cash_allocations: list[ReceiptAllocation] | None = None,
    credit_due_at: datetime | None = None,
    credit_approved_by_user_id: UUID | None = None,
    credit_terms: dict | None = None,
    subsidy_reference: str | None = None,
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED",
            "Accepted commercial terms are required before financial authorization",
            status_code=status.HTTP_409_CONFLICT,
        )
    if terms.currency != campaign.currency:
        raise AppError(
            "FINANCIAL_AUTHORITY_CURRENCY_MISMATCH",
            "Campaign and accepted commercial terms currency must match",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED",
            "Accepted commercial terms are required before financial authorization",
            status_code=status.HTTP_409_CONFLICT,
        )
    if authority_type == FinancialAuthorityType.PREPAID_CASH:
        current_allocations = await _active_cash_allocations(session, terms.id)
        authorized_amount = sum(
            (Decimal(row.amount) for row in current_allocations), Decimal("0.00")
        )
        cash_allocations = current_allocations
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError(
            "FINANCIAL_AUTHORITY_REASON_REQUIRED",
            "A financial authorization reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if authorized_amount <= 0 or max_driver_liability <= 0:
        raise AppError(
            "INVALID_FINANCIAL_AUTHORITY_AMOUNT",
            "Authorized amount and maximum driver liability must be positive",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if max_driver_liability > authorized_amount:
        raise AppError(
            "DRIVER_LIABILITY_EXCEEDS_AUTHORITY",
            "Maximum driver liability cannot exceed financial authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    latest = await _latest_financial_authorization(session, campaign_id)
    if latest is not None and (
        authorized_amount < Decimal(latest.authorized_amount)
        or max_driver_liability < Decimal(latest.max_driver_liability)
    ):
        raise AppError(
            "FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE",
            "Package 3 permits funded expansions only; reductions require governed revision",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_credit_terms = deepcopy(credit_terms) if credit_terms is not None else None
    if latest is not None and all(
        (
            latest.authority_type == authority_type,
            Decimal(latest.authorized_amount) == authorized_amount,
            Decimal(latest.max_driver_liability) == max_driver_liability,
            latest.credit_due_at == credit_due_at,
            latest.credit_approved_by_user_id == credit_approved_by_user_id,
            latest.credit_terms == normalized_credit_terms,
            latest.subsidy_reference == subsidy_reference,
        )
    ):
        return latest
    now = await database_clock(session)
    authorization = CampaignFinancialAuthorization(
        campaign_id=campaign_id,
        commercial_terms_id=terms.id,
        revision_number=1 if latest is None else latest.revision_number + 1,
        authority_type=authority_type,
        currency=terms.currency,
        authorized_amount=authorized_amount,
        funded_cash_amount=(
            authorized_amount
            if authority_type == FinancialAuthorityType.PREPAID_CASH
            else Decimal("0.00")
        ),
        max_driver_liability=max_driver_liability,
        credit_limit=(
            authorized_amount if authority_type == FinancialAuthorityType.APPROVED_CREDIT else None
        ),
        credit_due_at=credit_due_at,
        credit_approved_by_user_id=credit_approved_by_user_id,
        credit_terms=normalized_credit_terms,
        subsidy_reference=subsidy_reference,
        effective_from=now,
        created_by_user_id=actor_user_id,
        reason=normalized_reason,
        created_at=now,
    )
    session.add(authorization)
    await session.flush()
    for allocation in cash_allocations or []:
        session.add(
            FinancialAuthorizationAllocation(
                authorization_id=authorization.id,
                receipt_allocation_id=allocation.id,
                amount=allocation.amount,
            )
        )
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.financial_authority.recorded",
        entity_type="campaign_financial_authorization",
        entity_id=str(authorization.id),
        metadata={
            "campaign_id": str(campaign_id),
            "revision_number": authorization.revision_number,
            "authority_type": authority_type.value,
            "authorized_amount": f"{authorized_amount:.2f}",
            "max_driver_liability": f"{max_driver_liability:.2f}",
            "currency": terms.currency,
        },
    )
    return authorization


async def record_prepaid_cash_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    max_driver_liability: Decimal | str,
    reason: str,
) -> CampaignFinancialAuthorization:
    if await session.scalar(select(Campaign.id).where(Campaign.id == campaign_id)) is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_REQUIRED", "Accepted commercial terms are required", status_code=409
        )
    if terms.payment_class != PaymentClass.STANDARD_PREPAID:
        raise AppError(
            "PREPAID_AUTHORITY_NOT_PERMITTED",
            "The accepted terms do not permit prepaid-cash authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    allocations = await _active_cash_allocations(session, terms.id)
    funded = sum((Decimal(row.amount) for row in allocations), Decimal("0.00"))
    if funded <= 0:
        raise AppError(
            "CONFIRMED_FUNDING_REQUIRED",
            "Confirmed active allocations are required for prepaid authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    liability = _money(max_driver_liability, "max_driver_liability")
    return await _append_financial_authorization(
        session,
        campaign_id=campaign_id,
        actor_user_id=actor_user_id,
        authority_type=FinancialAuthorityType.PREPAID_CASH,
        authorized_amount=funded,
        max_driver_liability=liability,
        reason=reason,
        cash_allocations=allocations,
    )


async def record_approved_credit_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    credit_limit: Decimal | str,
    max_driver_liability: Decimal | str,
    due_at: datetime,
    approved_by_user_id: UUID,
    credit_terms: dict,
    reason: str,
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    for admin_user_id in sorted(
        {actor_user_id, approved_by_user_id}, key=lambda user_id: user_id.int
    ):
        await require_active_admin(session, admin_user_id)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    if terms is None or terms.payment_class != PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "APPROVED_CREDIT_TERMS_REQUIRED",
            "Accepted approved-corporate-credit terms are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_due_at = _aware_utc(due_at)
    now = await database_clock(session)
    if normalized_due_at <= now or not isinstance(credit_terms, dict) or not credit_terms:
        raise AppError(
            "INVALID_CREDIT_APPROVAL",
            "Credit approval requires a future due date and a non-empty terms snapshot",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await _append_financial_authorization(
        session,
        campaign_id=campaign_id,
        actor_user_id=actor_user_id,
        authority_type=FinancialAuthorityType.APPROVED_CREDIT,
        authorized_amount=_money(credit_limit, "credit_limit"),
        max_driver_liability=_money(max_driver_liability, "max_driver_liability"),
        reason=reason,
        credit_due_at=normalized_due_at,
        credit_approved_by_user_id=approved_by_user_id,
        credit_terms=credit_terms,
    )


async def record_subsidy_authorization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    subsidy_amount: Decimal | str,
    max_driver_liability: Decimal | str,
    subsidy_reference: str,
    reason: str,
) -> CampaignFinancialAuthorization:
    reference = subsidy_reference.strip()
    if not reference:
        raise AppError(
            "SUBSIDY_REFERENCE_REQUIRED",
            "Subsidy authority requires an evidence reference",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await _append_financial_authorization(
        session,
        campaign_id=campaign_id,
        actor_user_id=actor_user_id,
        authority_type=FinancialAuthorityType.SUBSIDY,
        authorized_amount=_money(subsidy_amount, "subsidy_amount"),
        max_driver_liability=_money(max_driver_liability, "max_driver_liability"),
        reason=reason,
        subsidy_reference=reference,
    )


async def _authorization_usable_liability(
    session: AsyncSession,
    authorization: CampaignFinancialAuthorization,
    *,
    effective_at: datetime | None = None,
) -> Decimal:
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        at = effective_at or await database_clock(session)
        if (
            authorization.credit_due_at is None
            or _stored_aware_utc(authorization.credit_due_at) <= at
        ):
            return Decimal("0.00")
    if authorization.authority_type != FinancialAuthorityType.PREPAID_CASH:
        return Decimal(authorization.max_driver_liability)
    receipt = PaymentReceipt.__table__.alias("active_authority_receipt")
    confirmed, not_reversed = _active_receipt_predicate(receipt)
    active_sources = await session.scalar(
        select(func.coalesce(func.sum(FinancialAuthorizationAllocation.amount), 0))
        .join(
            ReceiptAllocation,
            ReceiptAllocation.id == FinancialAuthorizationAllocation.receipt_allocation_id,
        )
        .join(receipt, receipt.c.id == ReceiptAllocation.receipt_id)
        .where(
            FinancialAuthorizationAllocation.authorization_id == authorization.id,
            confirmed,
            not_reversed,
        )
    )
    return min(Decimal(authorization.max_driver_liability), Decimal(active_sources or 0))


async def reserved_campaign_liability_total(
    session: AsyncSession,
    *,
    campaign_id: UUID,
) -> Decimal:
    from app.models.campaign_cancellation import CampaignCancellation
    from app.models.campaign_change import CampaignChangeRequest

    cancelled = await session.scalar(
        select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
    )
    if cancelled is not None:
        return Decimal("0.00")

    assignment_total = await session.scalar(
        select(func.coalesce(func.sum(CampaignLiabilityReservation.reserved_amount), 0)).where(
            CampaignLiabilityReservation.campaign_id == campaign_id,
            CampaignLiabilityReservation.status == "reserved",
        )
    )
    change_total = await session.scalar(
        select(func.coalesce(func.sum(CampaignChangeRequest.reserved_liability_amount), 0)).where(
            CampaignChangeRequest.campaign_id == campaign_id,
            CampaignChangeRequest.status == "applied",
        )
    )
    return Decimal(assignment_total or 0) + Decimal(change_total or 0)


async def reserve_assignment_liability(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    actor_user_id: UUID,
    require_admin: bool = True,
) -> CampaignLiabilityReservation:
    if not require_admin:
        actor = await session.get(User, actor_user_id)
        if actor is None or actor.status != UserStatus.ACTIVE:
            raise AppError(
                "ACTIVE_ACTOR_REQUIRED",
                "An active user is required to reserve assignment liability",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    campaign_id = await session.scalar(
        select(CampaignAssignment.campaign_id).where(CampaignAssignment.id == assignment_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    if require_admin:
        await require_active_admin(session, actor_user_id)
    assignment = await session.get(CampaignAssignment, assignment_id)
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "Assignment was not found", status_code=404)
    assert campaign_id == assignment.campaign_id
    await _campaign(session, assignment.campaign_id, lock=True)
    from app.models.campaign_cancellation import CampaignCancellation

    if await session.scalar(
        select(CampaignCancellation.id).where(
            CampaignCancellation.campaign_id == assignment.campaign_id
        )
    ) is not None:
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "Cancelled campaign liability cannot be reserved",
            status_code=status.HTTP_409_CONFLICT,
        )
    binding = await session.scalar(
        select(AssignmentRuleBinding).where(AssignmentRuleBinding.assignment_id == assignment.id)
    )
    if binding is None or binding.daily_payable_hours_cap is None:
        raise AppError(
            "FROZEN_PAYOUT_BINDING_REQUIRED",
            "A frozen rate and daily cap are required before reserving liability",
            status_code=status.HTTP_409_CONFLICT,
        )
    start_date = _stored_aware_utc(binding.campaign_window_start_at).astimezone(LAGOS_TZ).date()
    end_date = _stored_aware_utc(binding.campaign_window_end_at).astimezone(LAGOS_TZ).date()
    covered_days = max(1, (end_date - start_date).days + 1)
    rate = max(
        Decimal(binding.hourly_rate_naira),
        Decimal(binding.premium_hourly_rate_naira or binding.hourly_rate_naira),
    )
    cap = Decimal(binding.daily_payable_hours_cap)
    requested = (rate * cap * covered_days).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if requested <= 0:
        raise AppError(
            "ZERO_LIABILITY_RESERVE",
            "The frozen payout contract does not create positive liability",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=assignment.campaign_id, effective_at=now
    )
    reserved_total = await reserved_campaign_liability_total(
        session,
        campaign_id=assignment.campaign_id,
    )
    usable = (
        await _authorization_usable_liability(session, authorization, effective_at=now)
        if authorization is not None
        else Decimal("0.00")
    )
    can_reserve = authorization is not None and usable - reserved_total >= requested
    assignment = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )
    if assignment is None:
        raise AppError("ASSIGNMENT_NOT_FOUND", "Assignment was not found", status_code=404)
    existing = await session.scalar(
        select(CampaignLiabilityReservation)
        .where(CampaignLiabilityReservation.assignment_id == assignment.id)
        .with_for_update()
    )
    if existing is not None and Decimal(existing.requested_amount) != requested:
        raise AppError(
            "LIABILITY_RESERVATION_IMMUTABLE",
            "The assignment liability request is already frozen",
            status_code=status.HTTP_409_CONFLICT,
        )
    if existing is None:
        existing = CampaignLiabilityReservation(
            campaign_id=assignment.campaign_id,
            assignment_id=assignment.id,
            assignment_rule_binding_id=binding.id,
            authorization_id=authorization.id if can_reserve else None,
            status="reserved" if can_reserve else "pending_funding",
            covered_vehicle_days=covered_days,
            hourly_rate=rate,
            daily_hours_cap=cap,
            requested_amount=requested,
            reserved_amount=requested if can_reserve else None,
            requested_at=now,
            reserved_at=now if can_reserve else None,
            formula_version=LIABILITY_FORMULA_VERSION,
        )
        session.add(existing)
    elif existing.status == "pending_funding" and can_reserve:
        existing.authorization_id = authorization.id
        existing.status = "reserved"
        existing.reserved_amount = requested
        existing.reserved_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.liability_reservation.recorded",
        entity_type="campaign_liability_reservation",
        entity_id=str(existing.id),
        metadata={
            "campaign_id": str(assignment.campaign_id),
            "assignment_id": str(assignment.id),
            "status": existing.status,
            "requested_amount": f"{requested:.2f}",
            "formula_version": LIABILITY_FORMULA_VERSION,
        },
    )
    return existing


async def record_expedited_production_waiver(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    wording_version: str,
    accepted_wording: str,
    accepted_wording_hash: str,
) -> ExpeditedProductionWaiver:
    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    if campaign.organization_id != organization.id:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None or not wording_version or not accepted_wording or not accepted_wording_hash:
        raise AppError(
            "EXPEDITED_WAIVER_EVIDENCE_REQUIRED",
            "Accepted terms, wording version, wording and wording hash are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if (
        wording_version != EXPEDITED_WAIVER_WORDING_VERSION
        or accepted_wording != EXPEDITED_WAIVER_WORDING
        or accepted_wording_hash != EXPEDITED_WAIVER_WORDING_HASH
    ):
        raise AppError(
            "EXPEDITED_WAIVER_COPY_MISMATCH",
            "The expedited-production waiver copy is not the approved canonical version",
            status_code=status.HTTP_409_CONFLICT,
        )
    existing = await session.scalar(
        select(ExpeditedProductionWaiver).where(
            ExpeditedProductionWaiver.campaign_id == campaign_id
        )
    )
    if existing is not None:
        if (
            existing.accepted_by_user_id == actor_user_id
            and existing.commercial_terms_id == terms.id
            and existing.wording_version == EXPEDITED_WAIVER_WORDING_VERSION
            and existing.accepted_wording_hash == EXPEDITED_WAIVER_WORDING_HASH
        ):
            return existing
        raise AppError(
            "EXPEDITED_WAIVER_IMMUTABLE",
            "An immutable expedited-production waiver already exists",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    waiver = ExpeditedProductionWaiver(
        campaign_id=campaign_id,
        commercial_terms_id=terms.id,
        requested_by_user_id=actor_user_id,
        requested_at=now,
        accepted_by_user_id=actor_user_id,
        accepted_at=now,
        wording_version=EXPEDITED_WAIVER_WORDING_VERSION,
        accepted_wording_hash=EXPEDITED_WAIVER_WORDING_HASH,
    )
    session.add(waiver)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.expedited_waiver.accepted",
        entity_type="expedited_production_waiver",
        entity_id=str(waiver.id),
        metadata={
            "campaign_id": str(campaign_id),
            "wording_version": EXPEDITED_WAIVER_WORDING_VERSION,
            "accepted_wording_hash": EXPEDITED_WAIVER_WORDING_HASH,
        },
    )
    return waiver


async def _fully_funded_at(session: AsyncSession, terms: CommercialTerms) -> datetime | None:
    obligation = await effective_invoice_obligation(
        session, commercial_terms_id=terms.id
    )
    if obligation == 0:
        return await database_clock(session)
    cumulative = Decimal("0.00")
    for allocation in await _active_cash_allocations(session, terms.id):
        cumulative += Decimal(allocation.amount)
        if cumulative >= obligation:
            return allocation.allocated_at
    return None


async def record_production_start(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    waiver_id: UUID | None = None,
) -> ProductionStart:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    await _campaign(session, campaign_id, lock=True)
    from app.models.campaign_cancellation import CampaignCancellation

    if await session.scalar(
        select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
    ) is not None:
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "Cancelled campaign production cannot start",
            status_code=status.HTTP_409_CONFLICT,
        )
    existing = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    if existing is not None:
        return existing
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=campaign_id, effective_at=now
    )
    if terms is None or authorization is None:
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "Production requires accepted terms and effective financial authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    fully_funded_at: datetime | None = None
    waiver: ExpeditedProductionWaiver | None = None
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        if (
            authorization.credit_due_at is None
            or _stored_aware_utc(authorization.credit_due_at) <= now
        ):
            raise AppError(
                "CREDIT_AUTHORITY_EXPIRED",
                "Approved credit is no longer valid for production start",
                status_code=status.HTTP_409_CONFLICT,
            )
        basis = ProductionAuthorityBasis.APPROVED_CREDIT
        if waiver_id is not None:
            raise AppError(
                "WAIVER_NOT_APPLICABLE",
                "Expedited waiver is not applicable to approved-credit production",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif authorization.authority_type == FinancialAuthorityType.PREPAID_CASH:
        fully_funded_at = await _fully_funded_at(session, terms)
        if fully_funded_at is None:
            raise AppError(
                "FULL_FUNDING_REQUIRED",
                "Standard production requires confirmed allocations covering the full amount",
                status_code=status.HTTP_409_CONFLICT,
            )
        if waiver_id is None:
            boundary = fully_funded_at + timedelta(hours=terms.standard_production_wait_hours)
            if now < boundary:
                raise AppError(
                    "PRODUCTION_WAIT_ACTIVE",
                    "The exact 24-hour standard production wait has not elapsed",
                    status_code=status.HTTP_409_CONFLICT,
                )
            basis = ProductionAuthorityBasis.STANDARD_WINDOW_ELAPSED
        else:
            waiver = await session.get(ExpeditedProductionWaiver, waiver_id)
            if (
                waiver is None
                or waiver.campaign_id != campaign_id
                or _stored_aware_utc(waiver.accepted_at) > now
            ):
                raise AppError(
                    "VALID_EXPEDITED_WAIVER_REQUIRED",
                    "A valid immutable advertiser waiver is required",
                    status_code=status.HTTP_409_CONFLICT,
                )
            basis = ProductionAuthorityBasis.ADVERTISER_EXPEDITED_WAIVER
    else:
        raise AppError(
            "SUBSIDY_NOT_PRODUCTION_AUTHORITY",
            "Subsidy liability authority does not by itself authorize advertiser production",
            status_code=status.HTTP_409_CONFLICT,
        )
    production_start = ProductionStart(
        campaign_id=campaign_id,
        authorization_id=authorization.id,
        authority_basis=basis,
        waiver_id=waiver.id if waiver is not None else None,
        fully_funded_at=fully_funded_at,
        started_by_user_id=actor_user_id,
        started_at=now,
    )
    session.add(production_start)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.production.started",
        entity_type="production_start",
        entity_id=str(production_start.id),
        metadata={"campaign_id": str(campaign_id), "authority_basis": basis.value},
    )
    return production_start


async def assert_new_work_authorized(
    session: AsyncSession, *, campaign_id: UUID, assignment_id: UUID
) -> None:
    from app.models.campaign_cancellation import CampaignCancellation

    if await session.scalar(
        select(CampaignCancellation.id).where(CampaignCancellation.campaign_id == campaign_id)
    ) is not None:
        raise AppError(
            "CAMPAIGN_FINANCIAL_CUTOFF",
            "The campaign cancellation cutoff blocks new work",
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        authorization = await assert_campaign_production_authorized(
            session, campaign_id=campaign_id
        )
    except AppError as exc:
        if exc.code == "CREDIT_AUTHORITY_EXPIRED":
            raise
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Current campaign funding does not authorize new work",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    reservation = await session.scalar(
        select(CampaignLiabilityReservation).where(
            CampaignLiabilityReservation.campaign_id == campaign_id,
            CampaignLiabilityReservation.assignment_id == assignment_id,
            CampaignLiabilityReservation.status == "reserved",
        )
    )
    if reservation is None:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Production start and a funded assignment liability reserve are required",
            status_code=status.HTTP_409_CONFLICT,
        )
    usable = await _authorization_usable_liability(session, authorization)
    reserved_total = await reserved_campaign_liability_total(
        session,
        campaign_id=campaign_id,
    )
    if usable < reserved_total:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Current financial authority no longer covers reserved driver liability",
            status_code=status.HTTP_409_CONFLICT,
        )


async def assert_campaign_production_authorized(
    session: AsyncSession, *, campaign_id: UUID
) -> CampaignFinancialAuthorization:
    await acquire_campaign_terms_lock(session, campaign_id)
    terms = await _commercial_terms_for_campaign(session, campaign_id)
    production_start = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    now = await database_clock(session)
    authorization = await effective_financial_authorization(
        session, campaign_id=campaign_id, effective_at=now
    )
    if terms is None or production_start is None or authorization is None:
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "Campaign activation requires accepted terms and current production authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    usable = await _authorization_usable_liability(
        session, authorization, effective_at=now
    )
    if authorization.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        if usable <= 0:
            raise AppError(
                "CREDIT_AUTHORITY_EXPIRED",
                "Approved credit is no longer valid for new work",
                status_code=status.HTTP_409_CONFLICT,
            )
    elif authorization.authority_type == FinancialAuthorityType.PREPAID_CASH:
        if await _fully_funded_at(session, terms) is None or usable <= 0:
            raise AppError(
                "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
                "Confirmed cash authority no longer covers new work",
                status_code=status.HTTP_409_CONFLICT,
            )
    else:
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "Subsidy authority does not authorize advertiser production",
            status_code=status.HTTP_409_CONFLICT,
        )
    return authorization


async def ingest_payment_gateway_webhook(
    session: AsyncSession,
    *,
    adapter: PaymentGatewayAdapter,
    payload: bytes,
    signature: str | None,
) -> tuple[PaymentGatewayEvent, bool]:
    if signature is None or not signature.strip():
        raise AppError(
            "PAYMENT_WEBHOOK_UNAUTHORIZED",
            "Payment webhook authentication failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    try:
        verified = await adapter.parse_webhook(payload, signature)
    except PaymentGatewayUnavailableError as exc:
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED",
            "Payment webhook verification is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except PaymentWebhookAuthenticationError as exc:
        raise AppError(
            "INVALID_PAYMENT_WEBHOOK_SIGNATURE",
            "Payment webhook authentication or payload verification failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except PaymentWebhookPayloadError as exc:
        raise AppError(
            "INVALID_PAYMENT_WEBHOOK_PAYLOAD",
            "Authenticated payment webhook payload is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    provider = adapter.provider_name.strip().lower()
    terms_reference = verified.commercial_terms_id.strip()
    amount = _money(verified.amount, "gateway_event.amount")
    try:
        fingerprint_is_hex = len(verified.evidence_fingerprint) == 64 and bool(
            int(verified.evidence_fingerprint, 16) >= 0
        )
    except ValueError:
        fingerprint_is_hex = False
    if (
        not provider
        or not verified.provider_event_id.strip()
        or len(verified.provider_event_id) > 255
        or not verified.external_transaction_id.strip()
        or len(verified.external_transaction_id) > 255
        or not terms_reference
        or len(terms_reference) > 64
        or verified.event_type not in {"payment_confirmed", "payment_failed"}
        or amount == 0
        or len(verified.currency) != 3
        or not verified.currency.isalpha()
        or not verified.payer_name.strip()
        or verified.occurred_at.tzinfo is None
        or verified.occurred_at.utcoffset() is None
        or not fingerprint_is_hex
    ):
        raise AppError(
            "INVALID_PAYMENT_WEBHOOK_PAYLOAD",
            "Verified payment event is incomplete or malformed",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    existing = await session.scalar(
        select(PaymentGatewayEvent).where(
            PaymentGatewayEvent.provider == provider,
            PaymentGatewayEvent.provider_event_id == verified.provider_event_id,
        )
    )

    def exact_match(candidate: PaymentGatewayEvent) -> bool:
        return (
            candidate.provider == provider
            and candidate.external_transaction_id == verified.external_transaction_id
            and candidate.event_type == verified.event_type
            and candidate.commercial_terms_reference == terms_reference
            and Decimal(candidate.amount) == verified.amount
            and candidate.currency == verified.currency
            and candidate.payload == verified.canonical_payload
        )

    if existing is not None:
        if exact_match(existing):
            return existing, False
        raise AppError(
            "PAYMENT_EVENT_IDENTITY_CONFLICT",
            "Provider event identity belongs to different verified evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    event = PaymentGatewayEvent(
        provider=provider,
        provider_event_id=verified.provider_event_id,
        external_transaction_id=verified.external_transaction_id,
        event_type=verified.event_type,
        commercial_terms_reference=terms_reference,
        amount=amount,
        currency=verified.currency,
        payer_name=verified.payer_name.strip(),
        occurred_at=verified.occurred_at,
        evidence_fingerprint=verified.evidence_fingerprint,
        payload=deepcopy(verified.canonical_payload),
        received_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(PaymentGatewayEvent).where(
                PaymentGatewayEvent.provider == provider,
                PaymentGatewayEvent.provider_event_id == verified.provider_event_id,
            )
        )
        if concurrent is not None and exact_match(concurrent):
            return concurrent, False
        raise AppError(
            "PAYMENT_EVENT_IDENTITY_CONFLICT",
            "Provider event identity is already recorded",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    return event, True


async def _reconcile_verified_gateway_receipt(
    session: AsyncSession,
    *,
    receipt: PaymentReceipt,
    event: PaymentGatewayEvent,
) -> None:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt.id).with_for_update()
    )
    if receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    reconciliation = await session.scalar(
        select(ReceiptReconciliation).where(ReceiptReconciliation.receipt_id == receipt.id)
    )
    now = await database_clock(session)
    if reconciliation is None:
        reconciliation = ReceiptReconciliation(
            receipt_id=receipt.id,
            expected_amount=event.amount,
            expected_currency=event.currency,
            matched=True,
            verification_source="provider",
            provider_event_id=event.id,
            reconciled_by_user_id=None,
            reconciled_at=now,
        )
        session.add(reconciliation)
        await session.flush()
    elif (
        Decimal(reconciliation.expected_amount) != Decimal(event.amount)
        or reconciliation.expected_currency != event.currency
        or not reconciliation.matched
    ):
        raise AppError(
            "GATEWAY_RECONCILIATION_CONFLICT",
            "Existing receipt reconciliation conflicts with verified provider evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    current = await _receipt_status(session, receipt.id)
    if current == ReceiptLifecycleStatus.OBSERVED:
        await _append_receipt_event(
            session,
            receipt_id=receipt.id,
            lifecycle_status=ReceiptLifecycleStatus.RECONCILED,
            actor_user_id=None,
            occurred_at=now,
            reason=f"verified provider event {event.provider_event_id}",
        )
        current = ReceiptLifecycleStatus.RECONCILED
    if current == ReceiptLifecycleStatus.RECONCILED:
        await _append_receipt_event(
            session,
            receipt_id=receipt.id,
            lifecycle_status=ReceiptLifecycleStatus.CONFIRMED,
            actor_user_id=None,
            occurred_at=now,
            reason=f"verified provider event {event.provider_event_id}",
        )
    elif current != ReceiptLifecycleStatus.CONFIRMED:
        raise AppError(
            "GATEWAY_RECEIPT_NOT_CONFIRMABLE",
            "Verified gateway receipt is not in a confirmable state",
            status_code=status.HTTP_409_CONFLICT,
        )


async def process_payment_gateway_event(
    session: AsyncSession, *, event_id: UUID
) -> PaymentGatewayProcessingAttempt:
    event = await session.scalar(
        select(PaymentGatewayEvent).where(PaymentGatewayEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise AppError("PAYMENT_EVENT_NOT_FOUND", "Payment event was not found", status_code=404)
    completed = await session.scalar(
        select(PaymentGatewayProcessingAttempt)
        .where(
            PaymentGatewayProcessingAttempt.gateway_event_id == event.id,
            PaymentGatewayProcessingAttempt.outcome.in_(("confirmed", "ignored_failed")),
        )
        .order_by(PaymentGatewayProcessingAttempt.attempt_number.desc())
        .limit(1)
    )
    if completed is not None:
        return completed
    attempt_number = (
        int(
            await session.scalar(
                select(
                    func.coalesce(func.max(PaymentGatewayProcessingAttempt.attempt_number), 0)
                ).where(PaymentGatewayProcessingAttempt.gateway_event_id == event.id)
            )
            or 0
        )
        + 1
    )
    now = await database_clock(session)
    if event.event_type == "payment_failed":
        attempt = PaymentGatewayProcessingAttempt(
            gateway_event_id=event.id,
            attempt_number=attempt_number,
            outcome="ignored_failed",
            error_code=None,
            receipt_id=None,
            allocation_id=None,
            processed_at=now,
        )
        session.add(attempt)
        await session.flush()
        return attempt
    try:
        terms_id = UUID(event.commercial_terms_reference)
    except ValueError as exc:
        raise AppError(
            "PAYMENT_EVENT_TERMS_MISMATCH",
            "Provider event contains an invalid commercial terms reference",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    terms = await session.get(CommercialTerms, terms_id)
    if terms is None or terms.currency != event.currency:
        raise AppError(
            "PAYMENT_EVENT_TERMS_MISMATCH",
            "Verified payment event no longer matches accepted terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt = await record_payment_receipt(
        session,
        organization_id=terms.organization_id,
        actor_user_id=None,
        method=ReceiptMethod.GATEWAY,
        provider=event.provider,
        external_transaction_id=f"{event.provider}:{event.external_transaction_id}",
        amount=event.amount,
        currency=event.currency,
        payer_name=event.payer_name,
        evidence_reference=f"gateway:{event.provider}:{event.external_transaction_id}",
        observed_at=_stored_aware_utc(event.occurred_at),
        trusted_gateway_event_id=event.id,
    )
    await _reconcile_verified_gateway_receipt(session, receipt=receipt, event=event)
    allocation = await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=terms.id,
        actor_user_id=None,
        amount=event.amount,
        trusted_gateway_event_id=event.id,
    )
    attempt = PaymentGatewayProcessingAttempt(
        gateway_event_id=event.id,
        attempt_number=attempt_number,
        outcome="confirmed",
        error_code=None,
        receipt_id=receipt.id,
        allocation_id=allocation.id,
        processed_at=now,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def record_payment_gateway_failure(
    session: AsyncSession, *, event_id: UUID, error_code: str
) -> PaymentGatewayProcessingAttempt:
    event = await session.scalar(
        select(PaymentGatewayEvent).where(PaymentGatewayEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise AppError("PAYMENT_EVENT_NOT_FOUND", "Payment event was not found", status_code=404)
    completed = await session.scalar(
        select(PaymentGatewayProcessingAttempt)
        .where(
            PaymentGatewayProcessingAttempt.gateway_event_id == event.id,
            PaymentGatewayProcessingAttempt.outcome.in_(("confirmed", "ignored_failed")),
        )
        .order_by(PaymentGatewayProcessingAttempt.attempt_number.desc())
        .limit(1)
    )
    if completed is not None:
        return completed
    normalized_code = error_code.strip()[:128]
    if not normalized_code:
        normalized_code = "PAYMENT_GATEWAY_PROCESSING_ERROR"
    attempt_number = (
        int(
            await session.scalar(
                select(
                    func.coalesce(func.max(PaymentGatewayProcessingAttempt.attempt_number), 0)
                ).where(PaymentGatewayProcessingAttempt.gateway_event_id == event.id)
            )
            or 0
        )
        + 1
    )
    attempt = PaymentGatewayProcessingAttempt(
        gateway_event_id=event.id,
        attempt_number=attempt_number,
        outcome="failed",
        error_code=normalized_code,
        receipt_id=None,
        allocation_id=None,
        processed_at=await database_clock(session),
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def record_invoice_correction(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    actor_user_id: UUID,
    correction_reference: str,
    correction_type: InvoiceCorrectionType,
    net_amount: Decimal | str,
    tax_amount: Decimal | str,
    reason: str,
) -> InvoiceCorrection:
    campaign_id = await session.scalar(select(Invoice.campaign_id).where(Invoice.id == invoice_id))
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    if campaign_id is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    await _campaign(session, campaign_id, lock=True)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    reference = correction_reference.strip()
    if not reference or reference.lower().startswith("legacy:"):
        raise AppError(
            "INVALID_CORRECTION_REFERENCE",
            "A caller-supplied correction reference is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    normalized_reason = reason.strip()
    net = _money(net_amount, "correction.net_amount")
    tax = _money(tax_amount, "correction.tax_amount")
    gross = net + tax
    if gross <= 0 or not normalized_reason:
        raise AppError(
            "INVALID_INVOICE_CORRECTION",
            "A positive itemised correction and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "correction_type": correction_type.value,
                "net_amount": f"{net:.2f}",
                "tax_amount": f"{tax:.2f}",
                "reason": normalized_reason,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing = await session.scalar(
        select(InvoiceCorrection).where(
            InvoiceCorrection.invoice_id == invoice.id,
            InvoiceCorrection.correction_reference == reference,
        )
    )
    if existing is not None:
        if existing.request_fingerprint == fingerprint:
            return existing
        raise AppError(
            "INVOICE_CORRECTION_REFERENCE_CONFLICT",
            "Correction reference belongs to different immutable correction evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    if invoice.status not in {InvoiceStatus.ISSUED, InvoiceStatus.VOID}:
        raise AppError(
            "ISSUED_INVOICE_REQUIRED",
            "Only an issued invoice can receive an immutable correction",
            status_code=status.HTTP_409_CONFLICT,
        )
    rows = list(
        await session.scalars(
            select(InvoiceCorrection)
            .where(InvoiceCorrection.invoice_id == invoice.id)
            .order_by(InvoiceCorrection.sequence_number)
        )
    )
    credits = sum(
        (
            Decimal(row.gross_amount)
            for row in rows
            if row.correction_type == InvoiceCorrectionType.CREDIT_NOTE
        ),
        Decimal("0.00"),
    )
    debits = sum(
        (
            Decimal(row.gross_amount)
            for row in rows
            if row.correction_type == InvoiceCorrectionType.DEBIT_NOTE
        ),
        Decimal("0.00"),
    )
    if (
        correction_type == InvoiceCorrectionType.CREDIT_NOTE
        and credits + gross > Decimal(invoice.gross_amount) + debits
    ):
        raise AppError(
            "INVOICE_CREDIT_EXCEEDS_OBLIGATION",
            "Credit corrections cannot reduce the invoice obligation below zero",
            status_code=status.HTTP_409_CONFLICT,
        )
    sequence = len(rows) + 1
    now = await database_clock(session)
    correction = InvoiceCorrection(
        invoice_id=invoice.id,
        sequence_number=sequence,
        correction_number=f"COR-{invoice.invoice_number}-{sequence:03d}",
        correction_reference=reference,
        request_fingerprint=fingerprint,
        correction_type=correction_type,
        currency=invoice.currency,
        net_amount=net,
        tax_amount=tax,
        gross_amount=gross,
        reason=normalized_reason,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    session.add(correction)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice.corrected",
        entity_type="invoice_correction",
        entity_id=str(correction.id),
        metadata={
            "invoice_id": str(invoice.id),
            "correction_type": correction_type.value,
            "gross_amount": f"{gross:.2f}",
            "currency": invoice.currency,
        },
    )
    return correction


async def adjusted_invoice_obligation(session: AsyncSession, invoice_id: UUID) -> Decimal:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    return await effective_invoice_obligation(
        session, commercial_terms_id=invoice.commercial_terms_id
    )


async def effective_invoice_obligation(
    session: AsyncSession, *, commercial_terms_id: UUID
) -> Decimal:
    terms = await session.get(CommercialTerms, commercial_terms_id)
    if terms is None:
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.commercial_terms_id == commercial_terms_id)
    )
    if invoice is None:
        return Decimal(terms.gross_amount)
    rows = list(
        await session.scalars(
            select(InvoiceCorrection).where(InvoiceCorrection.invoice_id == invoice.id)
        )
    )
    adjusted = Decimal(invoice.gross_amount)
    for row in rows:
        if row.correction_type == InvoiceCorrectionType.CREDIT_NOTE:
            adjusted -= Decimal(row.gross_amount)
        else:
            adjusted += Decimal(row.gross_amount)
    return adjusted


async def _historical_fully_funded_at(
    session: AsyncSession, terms: CommercialTerms
) -> datetime | None:
    obligation = await effective_invoice_obligation(
        session, commercial_terms_id=terms.id
    )
    if obligation == 0:
        return terms.accepted_at
    cumulative = Decimal("0.00")
    allocations = list(
        await session.scalars(
            select(ReceiptAllocation)
            .where(ReceiptAllocation.commercial_terms_id == terms.id)
            .order_by(ReceiptAllocation.allocated_at, ReceiptAllocation.id)
        )
    )
    for allocation in allocations:
        cumulative += Decimal(allocation.amount)
        if cumulative >= obligation:
            return allocation.allocated_at
    return None


async def _refund_window(
    session: AsyncSession, terms: CommercialTerms
) -> tuple[datetime | None, datetime | None, ProductionStart | None]:
    if terms.payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT:
        return None, None, None
    production = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == terms.campaign_id)
    )
    funded_at = (
        production.fully_funded_at
        if production is not None and production.fully_funded_at is not None
        else await _historical_fully_funded_at(session, terms)
    )
    if funded_at is None:
        return None, None, None
    funded_at = _stored_aware_utc(funded_at)
    standard_end = funded_at + timedelta(hours=terms.standard_production_wait_hours)
    eligibility_ends_at = (
        min(standard_end, _stored_aware_utc(production.started_at))
        if production is not None
        else standard_end
    )
    return funded_at, eligibility_ends_at, production


async def record_refund_settlement(
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
    amount: Decimal | str,
    settlement_provider: str,
    external_reference: str,
    reason: str,
) -> RefundSettlement:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    campaign_id = await session.scalar(
        select(CommercialTerms.campaign_id).where(CommercialTerms.id == commercial_terms_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    if campaign_id is None:
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
    await _campaign(session, campaign_id, lock=True)
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.id == commercial_terms_id).with_for_update()
    )
    if terms is None:
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
    cancellation = await session.scalar(
        select(CampaignCancellation)
        .where(CampaignCancellation.campaign_id == terms.campaign_id)
        .with_for_update()
    )
    if receipt is None or receipt.organization_id != terms.organization_id:
        raise AppError("REFUND_AUTHORITY_NOT_FOUND", "Refund authority was not found", 404)
    if terms.payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "CASH_REFUND_NOT_APPLICABLE",
            "Corporate credit without cash uses contract settlement, not a refund",
            status_code=status.HTTP_409_CONFLICT,
        )
    provider = settlement_provider.strip().lower()
    reference = external_reference.strip()
    normalized_reason = reason.strip()
    refund_amount = _money(amount, "refund.amount")
    if refund_amount == 0 or not all((provider, reference, normalized_reason)):
        raise AppError(
            "INVALID_REFUND_SETTLEMENT",
            "Refund amount, provider, reference and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def exact_match(candidate: RefundSettlement) -> bool:
        return (
            candidate.commercial_terms_id == terms.id
            and candidate.receipt_id == receipt.id
            and candidate.cancellation_id == (
                cancellation.id if cancellation is not None else None
            )
            and Decimal(candidate.amount) == refund_amount
            and candidate.settlement_provider == provider
            and candidate.external_reference == reference
            and candidate.reason == normalized_reason
        )

    existing = await session.scalar(
        select(RefundSettlement).where(
            RefundSettlement.settlement_provider == provider,
            RefundSettlement.external_reference == reference,
        )
    )
    if existing is not None:
        if exact_match(existing):
            return existing
        raise AppError(
            "REFUND_REFERENCE_CONFLICT",
            "External refund reference belongs to different settlement evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    if cancellation is None:
        raise AppError(
            "REFUND_CANCELLATION_REQUIRED",
            "Cash refund recording requires an immutable campaign cancellation",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.commercial_terms_id != terms.id
        or cancellation.campaign_id != terms.campaign_id
        or cancellation.organization_id != terms.organization_id
        or cancellation.currency != terms.currency
    ):
        raise AppError(
            "REFUND_CANCELLATION_MISMATCH",
            "Campaign cancellation does not match the frozen cash-refund authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.disposition != CampaignCancellationDisposition.CASH_REFUND_DUE.value
        or Decimal(cancellation.refundable_amount) <= 0
    ):
        raise AppError(
            "REFUND_CANCELLATION_NOT_DUE",
            "The immutable campaign cancellation records no cash refund due",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.funding_authorized_at is None
        or cancellation.refund_eligibility_ends_at is None
        or _stored_aware_utc(cancellation.cutoff_at)
        >= _stored_aware_utc(cancellation.refund_eligibility_ends_at)
    ):
        raise AppError(
            "REFUND_CANCELLATION_MISMATCH",
            "Campaign cancellation does not match the frozen cash-refund authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if await _receipt_status(session, receipt.id) != ReceiptLifecycleStatus.REVERSED:
        raise AppError(
            "REVERSED_RECEIPT_REQUIRED",
            "Refund recording requires an append-only receipt reversal first",
            status_code=status.HTTP_409_CONFLICT,
        )
    allocation = await session.scalar(
        select(ReceiptAllocation).where(
            ReceiptAllocation.receipt_id == receipt.id,
            ReceiptAllocation.commercial_terms_id == terms.id,
        )
    )
    if allocation is None:
        raise AppError(
            "REFUND_ALLOCATION_REQUIRED",
            "Only allocated cash can be refunded",
            status_code=status.HTTP_409_CONFLICT,
        )
    prior = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.receipt_id == receipt.id,
                RefundSettlement.commercial_terms_id == terms.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if prior + refund_amount > Decimal(allocation.amount):
        raise AppError(
            "REFUND_EXCEEDS_CASH_AUTHORITY",
            "Refund cannot exceed the receipt's allocated cash authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt_refunded = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.receipt_id == receipt.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if receipt_refunded + refund_amount > Decimal(receipt.amount):
        raise AppError(
            "REFUND_EXCEEDS_RECEIPT_TOTAL",
            "Refund cannot exceed the receipt total",
            status_code=status.HTTP_409_CONFLICT,
        )
    cancellation_refunded = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.cancellation_id == cancellation.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if cancellation_refunded + refund_amount > Decimal(cancellation.refundable_amount):
        raise AppError(
            "REFUND_EXCEEDS_CANCELLATION_AUTHORITY",
            "Refund cannot exceed the cancellation's frozen refundable amount",
            status_code=status.HTTP_409_CONFLICT,
        )
    production = (
        await session.get(ProductionStart, cancellation.production_start_id)
        if cancellation.production_start_id is not None
        else None
    )
    funded_at = _stored_aware_utc(cancellation.funding_authorized_at)
    eligibility_ends_at = _stored_aware_utc(cancellation.refund_eligibility_ends_at)
    eligibility_evaluated_at = _stored_aware_utc(cancellation.cutoff_at)
    now = await database_clock(session)
    settlement = RefundSettlement(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        receipt_id=receipt.id,
        cancellation_id=cancellation.id,
        production_start_id=production.id if production is not None else None,
        waiver_id=production.waiver_id if production is not None else None,
        disposition=SettlementDisposition.REFUND_RECORDED,
        amount=refund_amount,
        currency=terms.currency,
        funding_authorized_at=funded_at,
        eligibility_ends_at=eligibility_ends_at,
        eligibility_evaluated_at=eligibility_evaluated_at,
        settlement_provider=provider,
        external_reference=reference,
        reason=normalized_reason,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(settlement)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(RefundSettlement).where(
                RefundSettlement.settlement_provider == provider,
                RefundSettlement.external_reference == reference,
            )
        )
        if concurrent is not None and exact_match(concurrent):
            return concurrent
        if concurrent is not None:
            raise AppError(
                "REFUND_REFERENCE_CONFLICT",
                "External refund reference belongs to different settlement evidence",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.refund.recorded",
        entity_type="refund_settlement",
        entity_id=str(settlement.id),
        metadata={
            "commercial_terms_id": str(terms.id),
            "receipt_id": str(receipt.id),
            "amount": f"{refund_amount:.2f}",
            "currency": terms.currency,
            "cancellation_id": str(cancellation.id),
            "eligibility_evaluated_at": eligibility_evaluated_at.isoformat(),
            "eligibility_ends_at": eligibility_ends_at.isoformat(),
        },
    )
    return settlement


async def record_credit_contract_settlement(
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    actor_user_id: UUID,
    settlement_provider: str,
    external_reference: str,
    reason: str,
) -> RefundSettlement:
    campaign_id = await session.scalar(
        select(CommercialTerms.campaign_id).where(CommercialTerms.id == commercial_terms_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    terms = None
    if campaign_id is not None:
        await _campaign(session, campaign_id, lock=True)
        terms = await session.scalar(
            select(CommercialTerms)
            .where(CommercialTerms.id == commercial_terms_id)
            .with_for_update()
        )
    if terms is None or terms.payment_class != PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "APPROVED_CREDIT_TERMS_REQUIRED",
            "Contract settlement requires approved corporate-credit terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    provider = settlement_provider.strip().lower()
    reference = external_reference.strip()
    normalized_reason = reason.strip()
    if not all((provider, reference, normalized_reason)):
        raise AppError(
            "INVALID_CREDIT_SETTLEMENT",
            "Settlement provider, reference and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    existing = await session.scalar(
        select(RefundSettlement).where(
            RefundSettlement.settlement_provider == provider,
            RefundSettlement.external_reference == reference,
        )
    )
    if existing is not None:
        if existing.commercial_terms_id == terms.id and existing.disposition == (
            SettlementDisposition.CREDIT_SETTLEMENT_RECORDED
        ):
            return existing
        raise AppError(
            "SETTLEMENT_REFERENCE_CONFLICT",
            "External settlement reference belongs to different evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    settlement = RefundSettlement(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        receipt_id=None,
        production_start_id=None,
        waiver_id=None,
        disposition=SettlementDisposition.CREDIT_SETTLEMENT_RECORDED,
        amount=Decimal("0.00"),
        currency=terms.currency,
        funding_authorized_at=None,
        eligibility_ends_at=None,
        settlement_provider=provider,
        external_reference=reference,
        reason=normalized_reason,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    session.add(settlement)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.credit_settlement.recorded",
        entity_type="refund_settlement",
        entity_id=str(settlement.id),
        metadata={
            "commercial_terms_id": str(terms.id),
            "external_reference": reference,
        },
    )
    return settlement


def _blocked_budget_evaluation_key(campaign: Campaign, *, evaluation_epoch_id: UUID | None) -> str:
    source = "|".join(
        (
            str(campaign.id),
            str(evaluation_epoch_id or "initial"),
            str(campaign.budget_amount),
            str(campaign.daily_budget_amount),
            campaign.currency,
            MISSING_BUDGET_POLICY_GATE,
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()


async def _campaign_billing_spend(
    session: AsyncSession, *, campaign_id: UUID, now: datetime
) -> tuple[Decimal, Decimal, str]:
    """Return advertiser billing authority only; driver payout rows are intentionally absent."""
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None:
        return Decimal("0.00"), Decimal("0.00"), "confirmed_funding"
    production = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    if production is not None:
        obligation = (
            await effective_invoice_obligation(session, commercial_terms_id=terms.id)
        ).quantize(MONEY_QUANTUM)
        daily = (
            obligation
            if _stored_aware_utc(production.started_at).astimezone(LAGOS_TZ).date()
            == now.astimezone(LAGOS_TZ).date()
            else Decimal("0.00")
        )
        return obligation, daily, "production_obligation"
    allocations = await _active_cash_allocations(session, terms.id)
    total = sum((Decimal(row.amount) for row in allocations), Decimal("0.00")).quantize(
        MONEY_QUANTUM
    )
    today = now.astimezone(LAGOS_TZ).date()
    daily = sum(
        (
            Decimal(row.amount)
            for row in allocations
            if _stored_aware_utc(row.allocated_at).astimezone(LAGOS_TZ).date() == today
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANTUM)
    return total, daily, "confirmed_funding"


def _budget_evaluation_key(
    campaign: Campaign,
    *,
    evaluation_epoch_id: UUID | None,
    decision,
    billing_fact_source: str,
) -> str:
    source = "|".join(
        (
            str(campaign.id),
            str(evaluation_epoch_id or "initial"),
            str(campaign.budget_amount),
            str(campaign.daily_budget_amount),
            campaign.currency,
            str(decision.policy_id),
            str(decision.policy_revision),
            str(decision.policy_source),
            str(decision.budget_basis),
            billing_fact_source,
            str(decision.billing_spend_amount),
            str(decision.alert_threshold_amount),
            str(decision.pause_threshold_amount),
            str(decision.resume_threshold_amount),
            decision.state,
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()


def _validate_budget_decision(decision, *, synthetic_test_authority: bool) -> None:
    if decision.policy_source == "synthetic_test" and not synthetic_test_authority:
        raise AppError(
            "SYNTHETIC_BUDGET_POLICY_FORBIDDEN",
            "Synthetic budget policy values are allowed only by explicit test authority",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if decision.policy_source not in {"external_approved", "synthetic_test"}:
        raise AppError(
            "BUDGET_POLICY_NOT_AUTHORIZED",
            "Budget policy does not carry approved revision authority",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    required = (
        decision.policy_id,
        decision.policy_revision,
        decision.budget_basis,
        decision.billing_spend_amount,
        decision.alert_threshold_amount,
        decision.pause_threshold_amount,
        decision.resume_threshold_amount,
    )
    missing = any(value is None for value in required)
    expected_state = None
    thresholds_valid = False
    expected_resume_allowed = False
    if not missing:
        spend = Decimal(decision.billing_spend_amount)
        alert = Decimal(decision.alert_threshold_amount)
        pause = Decimal(decision.pause_threshold_amount)
        resume = Decimal(decision.resume_threshold_amount)
        thresholds_valid = Decimal("0") <= resume <= alert < pause and spend >= 0
        expected_state = (
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value
            if spend >= pause
            else BudgetPolicyEvaluationState.ALERT_THRESHOLD.value
            if spend >= alert
            else BudgetPolicyEvaluationState.WITHIN_BUDGET.value
        )
        expected_resume_allowed = spend <= resume
    if (
        decision.state
        not in {
            BudgetPolicyEvaluationState.WITHIN_BUDGET.value,
            BudgetPolicyEvaluationState.ALERT_THRESHOLD.value,
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value,
        }
        or missing
        or not str(decision.policy_id).strip()
        or not str(decision.policy_revision).strip()
        or decision.budget_basis not in {"total", "daily"}
        or not thresholds_valid
        or decision.state != expected_state
        or decision.external_gate
        or decision.should_pause
        != (decision.state == BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value)
        or decision.resume_allowed != expected_resume_allowed
    ):
        raise AppError(
            "INVALID_BUDGET_POLICY_DECISION",
            "Budget policy decision is internally inconsistent",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def evaluate_campaign_budget_policy(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    adapter: BudgetPolicyAdapter | None = None,
    synthetic_test_authority: bool = False,
) -> BudgetPolicyEvaluation:
    """Persist one serialized advertiser-spend decision and any campaign pause."""
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    configured_budgets = [
        Decimal(value)
        for value in (campaign.budget_amount, campaign.daily_budget_amount)
        if value is not None
    ]
    if not configured_budgets:
        raise AppError(
            "CAMPAIGN_BUDGET_REQUIRED",
            "Budget policy evaluation requires a configured total or daily campaign budget",
            status_code=status.HTTP_409_CONFLICT,
        )
    selected_adapter = adapter or DisabledBudgetPolicyAdapter()
    if any(value <= 0 for value in configured_budgets) and not isinstance(
        selected_adapter, DisabledBudgetPolicyAdapter
    ):
        raise AppError(
            "CAMPAIGN_BUDGET_REQUIRED",
            "Authorized threshold evaluation requires positive configured budgets",
            status_code=status.HTTP_409_CONFLICT,
        )
    evaluation_epoch_id = await session.scalar(
        select(BudgetCampaignTransition.id)
        .where(
            BudgetCampaignTransition.campaign_id == campaign.id,
            BudgetCampaignTransition.action == BudgetCampaignTransitionAction.RESUME.value,
        )
        .order_by(BudgetCampaignTransition.created_at.desc())
        .limit(1)
    )
    now = await database_clock(session)
    total_spend, daily_spend, billing_fact_source = await _campaign_billing_spend(
        session, campaign_id=campaign.id, now=now
    )
    decision = await selected_adapter.evaluate(
        BudgetPolicyContext(
            campaign_id=campaign.id,
            currency=campaign.currency,
            configured_budget_amount=(
                Decimal(campaign.budget_amount) if campaign.budget_amount is not None else None
            ),
            configured_daily_budget_amount=(
                Decimal(campaign.daily_budget_amount)
                if campaign.daily_budget_amount is not None
                else None
            ),
            total_billing_spend_amount=total_spend,
            daily_billing_spend_amount=daily_spend,
        )
    )
    blocked = decision.state == BLOCKED_BUDGET_POLICY_STATE
    if blocked:
        if any(
            (
                decision.external_gate != MISSING_BUDGET_POLICY_GATE,
                decision.policy_id is not None,
                decision.policy_revision is not None,
                decision.policy_source is not None,
                decision.budget_basis is not None,
                decision.billing_spend_amount is not None,
                decision.alert_threshold_amount is not None,
                decision.pause_threshold_amount is not None,
                decision.resume_threshold_amount is not None,
                decision.should_pause,
                decision.resume_allowed,
            )
        ):
            raise AppError(
                "BUDGET_POLICY_NOT_AUTHORIZED",
                "EXT-BUDGET-POLICY is missing; threshold and pause decisions are disabled",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        evaluation_key = _blocked_budget_evaluation_key(
            campaign, evaluation_epoch_id=evaluation_epoch_id
        )
    else:
        _validate_budget_decision(decision, synthetic_test_authority=synthetic_test_authority)
        evaluation_key = _budget_evaluation_key(
            campaign,
            evaluation_epoch_id=evaluation_epoch_id,
            decision=decision,
            billing_fact_source=billing_fact_source,
        )
    existing = await session.scalar(
        select(BudgetPolicyEvaluation).where(
            BudgetPolicyEvaluation.campaign_id == campaign.id,
            BudgetPolicyEvaluation.evaluation_key == evaluation_key,
        )
    )
    if existing is not None:
        return existing

    pause_will_apply = decision.should_pause and campaign.status in {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.ACTIVE.value,
    }
    evaluation = BudgetPolicyEvaluation(
        campaign_id=campaign.id,
        evaluation_key=evaluation_key,
        state=decision.state,
        external_gate=decision.external_gate,
        campaign_budget_amount=campaign.budget_amount,
        campaign_daily_budget_amount=campaign.daily_budget_amount,
        currency=campaign.currency,
        policy_id=decision.policy_id,
        policy_revision=decision.policy_revision,
        policy_source=decision.policy_source,
        budget_basis=decision.budget_basis,
        billing_fact_source=None if blocked else billing_fact_source,
        billing_spend_amount=decision.billing_spend_amount,
        alert_threshold_amount=decision.alert_threshold_amount,
        pause_threshold_amount=decision.pause_threshold_amount,
        resume_threshold_amount=decision.resume_threshold_amount,
        alert_applied=decision.state
        in {
            BudgetPolicyEvaluationState.ALERT_THRESHOLD.value,
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value,
        },
        pause_applied=pause_will_apply,
        resume_allowed=decision.resume_allowed,
        evaluated_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(evaluation)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(BudgetPolicyEvaluation).where(
                BudgetPolicyEvaluation.campaign_id == campaign.id,
                BudgetPolicyEvaluation.evaluation_key == evaluation_key,
            )
        )
        if existing is None:
            raise
        return existing
    transition = None
    if pause_will_apply:
        prior_status = campaign.status
        campaign.status = CampaignStatus.PAUSED.value
        transition = BudgetCampaignTransition(
            campaign_id=campaign.id,
            evaluation_id=evaluation.id,
            action=BudgetCampaignTransitionAction.PAUSE.value,
            prior_status=prior_status,
            new_status=CampaignStatus.PAUSED.value,
            actor_user_id=None,
            reason="configured advertiser-spend pause threshold reached",
            created_at=now,
        )
        session.add(transition)
        await session.flush()
    await create_audit_event(
        session,
        actor_user_id=None,
        action=("billing.budget_policy.blocked" if blocked else "billing.budget_policy.evaluated"),
        entity_type="budget_policy_evaluation",
        entity_id=str(evaluation.id),
        metadata={
            "campaign_id": str(campaign.id),
            "external_gate": decision.external_gate or None,
            "policy_id": decision.policy_id,
            "policy_revision": decision.policy_revision,
            "policy_source": decision.policy_source,
            "budget_basis": decision.budget_basis,
            "billing_fact_source": None if blocked else billing_fact_source,
            "billing_spend_amount": (
                f"{decision.billing_spend_amount:.2f}"
                if decision.billing_spend_amount is not None
                else None
            ),
            "state": decision.state,
            "campaign_status": campaign.status,
            "pause_transition_id": str(transition.id) if transition is not None else None,
        },
    )
    if not blocked:
        from app.services.notifications import create_budget_policy_notices

        await create_budget_policy_notices(session, campaign=campaign, evaluation=evaluation)
    return evaluation


async def resume_campaign_after_budget_pause(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> BudgetCampaignTransition:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError(
            "BUDGET_RESUME_REASON_REQUIRED",
            "A budget-resume reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    campaign = await _campaign(session, campaign_id, lock=True)
    evaluation = await session.scalar(
        select(BudgetPolicyEvaluation)
        .where(BudgetPolicyEvaluation.campaign_id == campaign_id)
        .order_by(BudgetPolicyEvaluation.evaluated_at.desc(), BudgetPolicyEvaluation.id.desc())
        .limit(1)
        .with_for_update()
    )
    existing_resume = (
        await session.scalar(
            select(BudgetCampaignTransition).where(
                BudgetCampaignTransition.evaluation_id == evaluation.id,
                BudgetCampaignTransition.action == BudgetCampaignTransitionAction.RESUME.value,
            )
        )
        if evaluation is not None
        else None
    )
    if existing_resume is not None:
        if (
            existing_resume.actor_user_id == actor_user_id
            and existing_resume.reason == normalized_reason
        ):
            return existing_resume
        raise AppError(
            "BUDGET_RESUME_ALREADY_RECORDED",
            "This budget evaluation already has resume authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if campaign.status != CampaignStatus.PAUSED.value:
        raise AppError(
            "CAMPAIGN_NOT_BUDGET_PAUSED",
            "Campaign is not paused",
            status_code=status.HTTP_409_CONFLICT,
        )
    if evaluation is None or not evaluation.resume_allowed:
        raise AppError(
            "BUDGET_RESUME_NOT_AUTHORIZED",
            "The latest authoritative budget evaluation does not permit resume",
            status_code=status.HTTP_409_CONFLICT,
        )
    pause = await session.scalar(
        select(BudgetCampaignTransition)
        .where(
            BudgetCampaignTransition.campaign_id == campaign_id,
            BudgetCampaignTransition.action == BudgetCampaignTransitionAction.PAUSE.value,
        )
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    if pause is None:
        raise AppError(
            "BUDGET_PAUSE_AUTHORITY_MISSING",
            "Campaign pause is not owned by budget enforcement",
            status_code=status.HTTP_409_CONFLICT,
        )
    target = pause.prior_status
    now = await database_clock(session)
    latest_transition_at = await session.scalar(
        select(func.max(BudgetCampaignTransition.created_at)).where(
            BudgetCampaignTransition.campaign_id == campaign_id
        )
    )
    if latest_transition_at is not None:
        now = max(
            now,
            _stored_aware_utc(latest_transition_at) + timedelta(microseconds=1),
        )
    transition = BudgetCampaignTransition(
        campaign_id=campaign.id,
        evaluation_id=evaluation.id,
        action=BudgetCampaignTransitionAction.RESUME.value,
        prior_status=campaign.status,
        new_status=target,
        actor_user_id=actor_user_id,
        reason=normalized_reason,
        created_at=now,
    )
    campaign.status = target
    session.add(transition)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.budget_policy.resumed",
        entity_type="budget_campaign_transition",
        entity_id=str(transition.id),
        metadata={
            "campaign_id": str(campaign.id),
            "evaluation_id": str(evaluation.id),
            "policy_id": evaluation.policy_id,
            "policy_revision": evaluation.policy_revision,
            "status_before": CampaignStatus.PAUSED.value,
            "status_after": target,
            "reason": normalized_reason,
        },
    )
    from app.services.notifications import create_budget_resume_notices

    await create_budget_resume_notices(session, campaign=campaign, transition=transition)
    return transition


async def sweep_budget_policy_evaluations(
    session: AsyncSession,
    *,
    adapter: BudgetPolicyAdapter | None = None,
    synthetic_test_authority: bool = False,
) -> list[BudgetPolicyEvaluation]:
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id)
            .where(
                (Campaign.budget_amount.is_not(None)) | (Campaign.daily_budget_amount.is_not(None))
            )
            .order_by(Campaign.id)
        )
    )
    return [
        await evaluate_campaign_budget_policy(
            session,
            campaign_id=campaign_id,
            adapter=adapter,
            synthetic_test_authority=synthetic_test_authority,
        )
        for campaign_id in campaign_ids
    ]
