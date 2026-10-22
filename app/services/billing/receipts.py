"""Billing: receipts domain operations."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    Invoice,
    PaymentGatewayEvent,
    PaymentReceipt,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptMethod,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import (
    RECEIPT_SEQUENCE,
    _aware_utc,
    _campaign,
    _money,
    _stored_aware_utc,
)
from app.services.billing.queries import _receipt_status, effective_invoice_obligation
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


async def _append_receipt_event(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    lifecycle_status: ReceiptLifecycleStatus,
    actor_user_id: UUID | None,
    occurred_at: datetime,
    reason: str | None = None,
    provider_event_id: UUID | None = None,
) -> ReceiptLifecycleEvent:
    event = ReceiptLifecycleEvent(
        receipt_id=receipt_id,
        status=lifecycle_status,
        sequence_number=RECEIPT_SEQUENCE[lifecycle_status],
        provider_event_id=provider_event_id,
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


async def record_payment_receipt(  # noqa: C901
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
                _stored_aware_utc(observed_at) == _stored_aware_utc(gateway_event.occurred_at),
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
        lifecycle_status=ReceiptLifecycleStatus.RECORDED,
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


async def confirm_payment_receipt(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    actor_user_id: UUID,
    expected_amount: Decimal | str,
    expected_currency: str,
) -> bool:
    await require_active_admin(session, actor_user_id)
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    if receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    if receipt.method != ReceiptMethod.MANUAL_TRANSFER:
        raise AppError(
            "VERIFIED_GATEWAY_EVENT_REQUIRED",
            "Gateway payments need verified provider confirmation",
            status_code=403,
        )
    amount = _money(expected_amount, "expected_amount")
    currency = expected_currency.strip().upper()
    if amount == 0 or len(currency) != 3:
        raise AppError(
            "INVALID_CONFIRMATION_EXPECTATION",
            "Expected amount and currency are required",
            status_code=400,
        )
    current = await _receipt_status(session, receipt.id)
    matched = receipt.amount == amount and receipt.currency == currency
    if current == ReceiptLifecycleStatus.CONFIRMED:
        if not matched:
            raise AppError(
                "RECEIPT_CONFIRMATION_CONFLICT",
                "Confirmed payment details cannot change",
                status_code=409,
            )
        return True
    if current != ReceiptLifecycleStatus.RECORDED:
        raise AppError(
            "RECEIPT_NOT_RECORDED", "Only a recorded receipt can be confirmed", status_code=409
        )
    now = await database_clock(session)
    if matched:
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
        action="billing.receipt.confirmation_checked",
        entity_type="payment_receipt",
        entity_id=str(receipt.id),
        metadata={
            "expected_amount": f"{amount:.2f}",
            "expected_currency": currency,
            "matched": matched,
        },
    )
    return matched


async def allocate_payment_receipt(  # noqa: C901
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
        or Decimal(gateway_event.amount) != Decimal(receipt.amount)
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
    effective_obligation = await effective_invoice_obligation(session, commercial_terms_id=terms.id)
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
) -> tuple[PaymentReceipt, bool, ReceiptAllocation | None]:
    """Record and conditionally confirm one manual bank statement line."""
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
    matched = await confirm_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=actor_user_id,
        expected_amount=expected_amount,
        expected_currency=currency,
    )
    if not matched:
        return receipt, False, None
    amount_to_allocate = allocation_amount if allocation_amount is not None else observed_amount
    allocation = await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=commercial_terms_id,
        actor_user_id=actor_user_id,
        amount=amount_to_allocate,
    )
    return receipt, True, allocation
