from copy import deepcopy
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    CommercialQuotationRevision,
    CommercialQuoteRequest,
    CommercialTerms,
    PaymentClass,
    PaymentReceipt,
    QuoteRequestSource,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptMethod,
    ReceiptReconciliation,
)
from app.models.campaign import Campaign
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

MONEY_QUANTUM = Decimal("0.01")

RECEIPT_SEQUENCE = {
    ReceiptLifecycleStatus.OBSERVED: 1,
    ReceiptLifecycleStatus.RECONCILED: 2,
    ReceiptLifecycleStatus.CONFIRMED: 3,
    ReceiptLifecycleStatus.REVERSED: 4,
}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            "INVALID_ACCEPTED_AT",
            "accepted_at must include a timezone",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
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
    if not rate.is_finite() or rate < 0 or rate > 1:
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1",
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


async def _active_admin(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.role != UserRole.ADMIN or user.status != UserStatus.ACTIVE:
        raise AppError(
            "ADMIN_REQUIRED",
            "An active administrator is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


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
    campaign = await _campaign(session, campaign_id)
    if source == QuoteRequestSource.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != campaign.organization_id:
            raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    else:
        await _active_admin(session, actor_user_id)
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
    await _active_admin(session, actor_user_id)
    quote_request = await session.get(CommercialQuoteRequest, quote_request_id)
    if quote_request is None:
        raise AppError("QUOTE_REQUEST_NOT_FOUND", "Quote request was not found", status_code=404)
    await acquire_campaign_terms_lock(session, quote_request.campaign_id)
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
    revision = await session.get(CommercialQuotationRevision, quotation_revision_id)
    if revision is None:
        raise AppError("QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404)
    await acquire_campaign_terms_lock(session, revision.campaign_id)
    revision = (
        await session.execute(
            select(CommercialQuotationRevision)
            .where(CommercialQuotationRevision.id == quotation_revision_id)
            .with_for_update()
        )
    ).scalar_one()
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
        await _active_admin(session, actor_user_id)
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
    trusted_gateway: bool = False,
) -> PaymentReceipt:
    if actor_user_id is None:
        if method != ReceiptMethod.GATEWAY or not trusted_gateway:
            raise AppError(
                "RECEIPT_ACTOR_REQUIRED",
                "A trusted gateway or active administrator is required",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    else:
        await _active_admin(session, actor_user_id)
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
    existing = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.external_transaction_id == external_id)
    )
    if existing is not None:
        exact = (
            existing.organization_id == organization_id
            and existing.method == method
            and existing.provider == normalized_provider
            and existing.amount == receipt_amount
            and existing.currency == normalized_currency
            and existing.payer_name == normalized_payer
            and existing.evidence_reference == evidence
            and existing.observed_at == observed
        )
        if exact:
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
    await _active_admin(session, actor_user_id)
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
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
    await _active_admin(session, actor_user_id)
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
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
    actor_user_id: UUID,
    amount: Decimal | str,
) -> ReceiptAllocation:
    await _active_admin(session, actor_user_id)
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.id == commercial_terms_id).with_for_update()
    )
    if receipt is None or terms is None or receipt.organization_id != terms.organization_id:
        raise AppError(
            "BILLING_AUTHORITY_NOT_FOUND", "Billing authority was not found", status_code=404
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
    if Decimal(terms_allocated or 0) + allocation_amount > terms.gross_amount:
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
    return allocation


async def reverse_payment_receipt(
    session: AsyncSession, *, receipt_id: UUID, actor_user_id: UUID, reason: str
) -> PaymentReceipt:
    await _active_admin(session, actor_user_id)
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
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
