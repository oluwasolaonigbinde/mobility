"""Billing: gateway domain operations."""

from copy import deepcopy
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.payments import (
    PaymentGatewayAdapter,
    PaymentGatewayUnavailableError,
    PaymentWebhookAuthenticationError,
    PaymentWebhookPayloadError,
    VerifiedPaymentEvent,
)
from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    PaymentCheckoutIntent,
    PaymentCheckoutStatus,
    PaymentGatewayEvent,
    PaymentGatewayProcessingAttempt,
    PaymentReceipt,
    ReceiptLifecycleStatus,
    ReceiptMethod,
)
from app.services.audit import create_audit_event
from app.services.billing.common import MONEY_QUANTUM, _money, _stored_aware_utc
from app.services.billing.queries import (
    _active_cash_allocations,
    _receipt_status,
    effective_invoice_obligation,
)
from app.services.billing.receipts import (
    _append_receipt_event,
    _trusted_confirmed_gateway_event,
    allocate_payment_receipt,
    record_payment_receipt,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

PERMANENT_PAYMENT_ERROR_CODES = frozenset(
    {"PAYMENT_EVENT_TERMS_MISMATCH", "PAYMENT_CHECKOUT_BINDING_MISMATCH"}
)


def payment_attempt_is_terminal():
    """One SQL predicate for processing, failure recording and catch-up selection."""
    return or_(
        PaymentGatewayProcessingAttempt.outcome.in_(
            ("confirmed", "confirmed_unallocated", "ignored_failed")
        ),
        and_(
            PaymentGatewayProcessingAttempt.outcome == "failed",
            PaymentGatewayProcessingAttempt.error_code.in_(PERMANENT_PAYMENT_ERROR_CODES),
        ),
    )


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
    return await ingest_verified_payment_event(session, adapter=adapter, verified=verified)


async def ingest_verified_payment_event(  # noqa: C901
    session: AsyncSession,
    *,
    adapter: PaymentGatewayAdapter,
    verified: VerifiedPaymentEvent,
) -> tuple[PaymentGatewayEvent, bool]:
    """Persist provider-verified evidence and enforce Cardvert checkout binding."""

    provider = adapter.provider_name.strip().lower()
    terms_reference = verified.commercial_terms_id.strip()
    organization_reference = verified.organization_id.strip()
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
        or not organization_reference
        or len(organization_reference) > 64
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
    checkout: PaymentCheckoutIntent | None = None
    if provider == "paystack":
        checkout = await session.scalar(
            select(PaymentCheckoutIntent)
            .where(PaymentCheckoutIntent.reference == verified.external_transaction_id)
            .with_for_update()
        )
        if (
            checkout is None
            or checkout.provider != provider
            or str(checkout.commercial_terms_id) != terms_reference
            or str(checkout.organization_id) != organization_reference
            or Decimal(checkout.amount) != amount
            or checkout.currency != verified.currency
        ):
            raise AppError(
                "PAYMENT_CHECKOUT_BINDING_MISMATCH",
                "Verified Paystack evidence does not match a Cardvert checkout",
                status_code=status.HTTP_409_CONFLICT,
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
            if checkout is not None:
                checkout.status = (
                    PaymentCheckoutStatus.CONFIRMED.value
                    if verified.event_type == "payment_confirmed"
                    else PaymentCheckoutStatus.FAILED.value
                )
                checkout.verified_at = checkout.verified_at or existing.received_at
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
    if checkout is not None:
        checkout.status = (
            PaymentCheckoutStatus.CONFIRMED.value
            if verified.event_type == "payment_confirmed"
            else PaymentCheckoutStatus.FAILED.value
        )
        checkout.verified_at = now
    return event, True


async def _confirm_verified_gateway_receipt(
    session: AsyncSession,
    *,
    receipt: PaymentReceipt,
    event: PaymentGatewayEvent,
) -> None:
    persisted, terms = await _trusted_confirmed_gateway_event(session, event.id)
    locked_receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt.id).with_for_update()
    )
    if locked_receipt is None:
        raise AppError("RECEIPT_NOT_FOUND", "Receipt was not found", status_code=404)
    receipt = locked_receipt
    if (
        receipt.method != ReceiptMethod.GATEWAY
        or receipt.organization_id != terms.organization_id
        or receipt.provider != persisted.provider
        or receipt.external_transaction_id
        != f"{persisted.provider}:{persisted.external_transaction_id}"
        or Decimal(receipt.amount) != Decimal(persisted.amount)
        or receipt.currency != persisted.currency
    ):
        raise AppError(
            "GATEWAY_CONFIRMATION_CONFLICT",
            "Receipt facts conflict with verified provider evidence",
            status_code=409,
        )
    current = await _receipt_status(session, receipt.id)
    if current == ReceiptLifecycleStatus.CONFIRMED:
        return
    if current != ReceiptLifecycleStatus.RECORDED:
        raise AppError(
            "GATEWAY_RECEIPT_NOT_CONFIRMABLE",
            "Verified gateway receipt is not in a confirmable state",
            status_code=409,
        )
    await _append_receipt_event(
        session,
        receipt_id=receipt.id,
        lifecycle_status=ReceiptLifecycleStatus.CONFIRMED,
        actor_user_id=None,
        occurred_at=await database_clock(session),
        reason=f"verified provider event {persisted.provider_event_id}",
        provider_event_id=persisted.id,
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
            payment_attempt_is_terminal(),
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
    if event.provider == "paystack":
        checkout = await session.scalar(
            select(PaymentCheckoutIntent)
            .where(PaymentCheckoutIntent.reference == event.external_transaction_id)
            .with_for_update()
        )
        if (
            checkout is None
            or checkout.provider != event.provider
            or checkout.commercial_terms_id != terms.id
            or checkout.organization_id != terms.organization_id
            or Decimal(checkout.amount) != Decimal(event.amount)
            or checkout.currency != event.currency
        ):
            raise AppError(
                "PAYMENT_CHECKOUT_BINDING_MISMATCH",
                "Verified Paystack evidence does not match its invoice checkout",
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
    await _confirm_verified_gateway_receipt(session, receipt=receipt, event=event)
    await acquire_campaign_terms_lock(session, terms.campaign_id)
    obligation = await effective_invoice_obligation(session, commercial_terms_id=terms.id)
    allocated = sum(
        (Decimal(item.amount) for item in await _active_cash_allocations(session, terms.id)),
        Decimal("0.00"),
    )
    remaining = max(Decimal("0.00"), obligation - allocated).quantize(MONEY_QUANTUM)
    allocation_amount = min(Decimal(event.amount), remaining).quantize(MONEY_QUANTUM)
    allocation = None
    if allocation_amount > 0:
        allocation = await allocate_payment_receipt(
            session,
            receipt_id=receipt.id,
            commercial_terms_id=terms.id,
            actor_user_id=None,
            amount=allocation_amount,
            trusted_gateway_event_id=event.id,
        )
    unallocated = (Decimal(event.amount) - allocation_amount).quantize(MONEY_QUANTUM)
    if unallocated > 0:
        await create_audit_event(
            session,
            actor_user_id=None,
            action="billing.gateway_overpayment.recorded",
            entity_type="payment_receipt",
            entity_id=str(receipt.id),
            metadata={
                "commercial_terms_id": str(terms.id),
                "unallocated_amount": f"{unallocated:.2f}",
                "currency": event.currency,
            },
        )
    attempt = PaymentGatewayProcessingAttempt(
        gateway_event_id=event.id,
        attempt_number=attempt_number,
        outcome="confirmed" if allocation is not None else "confirmed_unallocated",
        error_code=None,
        receipt_id=receipt.id,
        allocation_id=allocation.id if allocation is not None else None,
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
            payment_attempt_is_terminal(),
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
