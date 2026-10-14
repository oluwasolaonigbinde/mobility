"""Billing: checkout domain operations."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from starlette import status

from app.adapters.payments import (
    CheckoutRequest,
    CheckoutSession,
    PaymentGatewayAdapter,
    PaymentGatewayUnavailableError,
)
from app.adapters.payments.paystack import (
    PaystackNotFoundError,
    PaystackOutcomeUnknownError,
    PaystackRejectedError,
)
from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    Invoice,
    InvoiceStatus,
    PaymentCheckoutIntent,
    PaymentCheckoutStatus,
    PaymentClass,
    PaymentGatewayEvent,
    PaymentGatewayProcessingAttempt,
)
from app.models.user import User
from app.services.audit import create_audit_event
from app.services.billing.common import MONEY_QUANTUM
from app.services.billing.invoices import invoice_payment_status
from app.services.billing.queries import adjusted_invoice_obligation
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import database_clock


async def prepare_invoice_payment_checkout(  # noqa: C901
    session: AsyncSession,
    *,
    invoice_id: UUID,
    actor_user_id: UUID,
    adapter: PaymentGatewayAdapter,
) -> PaymentCheckoutIntent:
    """Persist one exact, tenant-owned invoice balance before calling the provider."""

    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    if invoice is None or invoice.organization_id != organization.id:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    if invoice.status != InvoiceStatus.ISSUED.value:
        raise AppError(
            "INVOICE_NOT_PAYABLE",
            "Only an issued invoice can be paid online",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = await session.get(CommercialTerms, invoice.commercial_terms_id)
    if terms is None or terms.organization_id != organization.id:
        raise AppError(
            "INVOICE_TERMS_MISMATCH",
            "Invoice terms do not belong to this advertiser",
            status_code=status.HTTP_409_CONFLICT,
        )
    if terms.payment_class != PaymentClass.STANDARD_PREPAID.value:
        raise AppError(
            "INVOICE_NOT_PAYABLE_ONLINE",
            "Corporate credit invoices are settled under their agreed credit terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    _, funded = await invoice_payment_status(session, invoice)
    obligation = await adjusted_invoice_obligation(session, invoice.id)
    amount = (obligation - funded).quantize(MONEY_QUANTUM)
    if amount <= 0:
        raise AppError(
            "INVOICE_ALREADY_PAID",
            "This invoice has no remaining balance",
            status_code=status.HTTP_409_CONFLICT,
        )
    if invoice.currency != terms.currency or invoice.currency != "NGN":
        raise AppError(
            "PAYMENT_CURRENCY_UNSUPPORTED",
            "Online payment is currently available only for NGN invoices",
            status_code=status.HTTP_409_CONFLICT,
        )
    provider = adapter.provider_name.strip().lower()
    if not provider or provider == "disabled":
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED",
            "Online payment is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    existing = await session.scalar(
        select(PaymentCheckoutIntent)
        .where(
            PaymentCheckoutIntent.invoice_id == invoice.id,
            PaymentCheckoutIntent.provider == provider,
            PaymentCheckoutIntent.status.in_(
                (
                    PaymentCheckoutStatus.PENDING.value,
                    PaymentCheckoutStatus.INITIALIZED.value,
                    PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value,
                    PaymentCheckoutStatus.CONFIRMED.value,
                )
            ),
        )
        .order_by(PaymentCheckoutIntent.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        if existing.status == PaymentCheckoutStatus.CONFIRMED.value:
            confirmation_applied = bool(
                await session.scalar(
                    select(
                        exists().where(
                            PaymentGatewayEvent.provider == provider,
                            PaymentGatewayEvent.external_transaction_id == existing.reference,
                            PaymentGatewayEvent.event_type == "payment_confirmed",
                            PaymentGatewayProcessingAttempt.gateway_event_id
                            == PaymentGatewayEvent.id,
                            PaymentGatewayProcessingAttempt.outcome.in_(
                                ("confirmed", "confirmed_unallocated")
                            ),
                        )
                    )
                )
            )
            if not confirmation_applied:
                raise AppError(
                    "PAYMENT_CONFIRMATION_PROCESSING",
                    "A confirmed online payment is still being applied",
                    status_code=status.HTTP_409_CONFLICT,
                )
        elif Decimal(existing.amount) == amount and existing.currency == invoice.currency:
            return existing
        else:
            raise AppError(
                "PAYMENT_CHECKOUT_ALREADY_ACTIVE",
                "An earlier online checkout is still active for this invoice",
                status_code=status.HTTP_409_CONFLICT,
            )
    user = await session.get(User, actor_user_id)
    customer_email = (
        (organization.billing_email or (user.email if user is not None else "")).strip().lower()
    )
    if not customer_email:
        raise AppError(
            "PAYMENT_CUSTOMER_EMAIL_REQUIRED",
            "A valid billing or account email is required for online payment",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    checkout = PaymentCheckoutIntent(
        reference=f"cv-{uuid4().hex}",
        provider=provider,
        organization_id=organization.id,
        commercial_terms_id=terms.id,
        invoice_id=invoice.id,
        requested_by_user_id=actor_user_id,
        customer_email=customer_email,
        amount=amount,
        currency=invoice.currency,
        status=PaymentCheckoutStatus.PENDING.value,
        checkout_url=None,
        provider_checkout_id=None,
        failure_code=None,
        created_at=now,
        initialized_at=None,
        verified_at=None,
    )
    session.add(checkout)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser.payment_checkout.requested",
        entity_type="payment_checkout_intent",
        entity_id=str(checkout.id),
        metadata={
            "invoice_id": str(invoice.id),
            "reference": checkout.reference,
            "amount": f"{amount:.2f}",
            "currency": invoice.currency,
            "provider": provider,
        },
    )
    return checkout


async def lock_committed_checkout(
    session: AsyncSession, checkout_id: UUID
) -> PaymentCheckoutIntent:
    committed = await session.scalar(
        select(PaymentCheckoutIntent)
        .where(PaymentCheckoutIntent.id == checkout_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if committed is None:
        raise RuntimeError("A committed payment checkout disappeared")
    return committed


def require_initialization_unknown(committed: PaymentCheckoutIntent) -> None:
    if committed.status != PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value:
        raise AppError(
            "PAYMENT_CHECKOUT_STATE_CHANGED",
            "The payment checkout changed while Paystack was preparing it",
            status_code=status.HTTP_409_CONFLICT,
        )


@asynccontextmanager
async def checkout_reference_lock(
    session: AsyncSession, checkout_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Bind recovery to its owned connection across commits and provider I/O."""
    bind = session.bind
    if bind is None:
        raise RuntimeError("Checkout recovery requires a database connection")
    engine = bind.engine if isinstance(bind, AsyncConnection) else bind
    # Release the caller's read transaction before waiting. The lock owner uses
    # this same connection for its domain work, so waiters cannot exhaust the
    # pool while an owner needs a second connection to publish its result.
    await session.rollback()
    key = int.from_bytes(
        hashlib.sha256(f"payment-checkout:{checkout_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    async with engine.connect() as connection:
        try:
            await connection.execute(select(func.pg_advisory_lock(key)))
            await connection.rollback()  # session locks survive rollback
            async with AsyncSession(bind=connection, expire_on_commit=False) as locked_session:
                yield locked_session
        finally:
            try:
                await connection.execute(select(func.pg_advisory_unlock(key)))
                await connection.rollback()
            except BaseException:
                # Never return a connection carrying a session lock to its pool.
                await connection.invalidate()
                raise


async def _reconcile_unknown_checkout(
    session: AsyncSession,
    *,
    checkout: PaymentCheckoutIntent,
    adapter: PaymentGatewayAdapter,
    actor_user_id: UUID,
) -> bool:
    """Return True only for same-reference dispatch; never authorize replacement."""
    from app.services.billing.gateway import ingest_verified_payment_event

    verified = None
    error = None
    try:
        verified = await adapter.verify_transaction(checkout.reference)
        outcome = "verified"
    except PaystackNotFoundError:
        outcome = "not_found_same_reference_retry"
    except (PaystackOutcomeUnknownError, PaystackRejectedError, ValueError) as exc:
        outcome = "unknown"
        error = exc
    except PaymentGatewayUnavailableError as exc:
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED", "Online payment is not configured", status_code=503
        ) from exc
    if verified is not None:
        await ingest_verified_payment_event(session, adapter=adapter, verified=verified)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="advertiser.payment_checkout.reconciled",
        entity_type="payment_checkout_intent",
        entity_id=str(checkout.id),
        metadata={"reference": checkout.reference, "outcome": outcome},
    )
    if error is not None:
        raise AppError(
            "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN",
            "The saved payment reference is still uncertain. No replacement has been created.",
            status_code=502,
        ) from error
    return verified is None


async def initialize_invoice_payment_checkout(
    session: AsyncSession,
    *,
    checkout_id: UUID,
    adapter: PaymentGatewayAdapter,
    return_url: str,
    actor_user_id: UUID | None = None,
) -> tuple[PaymentCheckoutIntent, CheckoutSession | None]:
    async with checkout_reference_lock(session, checkout_id) as locked_session:
        try:
            result = await _initialize_invoice_payment_checkout(
                locked_session,
                checkout_id=checkout_id,
                adapter=adapter,
                return_url=return_url,
                actor_user_id=actor_user_id,
            )
        except AppError:
            await locked_session.commit()
            raise
        # Publish the final state before another initializer/verifier owns the lock.
        await locked_session.commit()
        return result


async def _initialize_invoice_payment_checkout(  # noqa: C901
    session: AsyncSession,
    *,
    checkout_id: UUID,
    adapter: PaymentGatewayAdapter,
    return_url: str,
    actor_user_id: UUID | None,
) -> tuple[PaymentCheckoutIntent, CheckoutSession | None]:
    """Initialize a previously committed intent and retain the provider URL."""

    if not return_url.strip():
        raise AppError(
            "PAYMENT_RETURN_URL_NOT_CONFIGURED",
            "Online payment return is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    checkout = await session.scalar(
        select(PaymentCheckoutIntent)
        .where(PaymentCheckoutIntent.id == checkout_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if checkout is None:
        raise AppError(
            "PAYMENT_CHECKOUT_NOT_FOUND", "Payment checkout was not found", status_code=404
        )
    if checkout.provider != adapter.provider_name.strip().lower():
        raise AppError(
            "PAYMENT_CHECKOUT_PROVIDER_MISMATCH",
            "Payment checkout provider configuration changed",
            status_code=status.HTTP_409_CONFLICT,
        )
    if checkout.status in {
        PaymentCheckoutStatus.INITIALIZED.value,
        PaymentCheckoutStatus.CONFIRMED.value,
    }:
        return checkout, None
    recovering = checkout.status == PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value
    if recovering:
        dispatch = await _reconcile_unknown_checkout(
            session,
            checkout=checkout,
            adapter=adapter,
            actor_user_id=actor_user_id or checkout.requested_by_user_id,
        )
        if not dispatch:
            return checkout, None
    elif checkout.status != PaymentCheckoutStatus.PENDING.value:
        raise AppError(
            "PAYMENT_CHECKOUT_NOT_INITIALIZABLE",
            "This payment checkout cannot be initialized",
            status_code=status.HTTP_409_CONFLICT,
        )
    request = CheckoutRequest(
        idempotency_key=checkout.reference,
        commercial_terms_id=str(checkout.commercial_terms_id),
        organization_id=str(checkout.organization_id),
        amount=Decimal(checkout.amount),
        currency=checkout.currency,
        customer_reference=checkout.customer_email,
        return_url=return_url,
    )
    try:
        adapter.validate_checkout(request)
    except PaymentGatewayUnavailableError as exc:
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED",
            "Online payment is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except ValueError as exc:
        if not recovering:
            checkout.status = PaymentCheckoutStatus.FAILED.value
        checkout.failure_code = type(exc).__name__
        await session.flush()
        raise AppError(
            "PAYMENT_CHECKOUT_INVALID",
            "The saved billing details cannot be used for online payment.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    # Commit the uncertain state before external I/O. If Paystack accepts the
    # reference and this process dies before saving its URL, later requests
    # must verify this same reference rather than minting a second checkout.
    checkout.status = PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value
    checkout.failure_code = "provider_initialization_pending"
    await session.flush()
    await session.commit()

    try:
        provider_session = await adapter.create_checkout(request)
    except PaymentGatewayUnavailableError as exc:
        raise AppError(
            "PAYMENT_PROVIDER_NOT_CONFIGURED",
            "Online payment is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except (PaystackRejectedError, PaystackOutcomeUnknownError, ValueError) as exc:
        checkout = await lock_committed_checkout(session, checkout_id)
        if checkout.status == PaymentCheckoutStatus.CONFIRMED.value:
            return checkout, None
        require_initialization_unknown(checkout)
        if recovering:
            code = "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN"
            message = "The saved payment reference is still uncertain. Please verify it again."
        elif isinstance(exc, PaystackRejectedError):
            checkout.status = PaymentCheckoutStatus.FAILED.value
            code = "PAYMENT_CHECKOUT_REJECTED"
            message = "Paystack rejected this checkout. Please start a new payment attempt."
        elif isinstance(exc, PaystackOutcomeUnknownError):
            code = "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN"
            message = "Paystack may still be preparing this checkout. Please try again."
        else:
            code = "PAYMENT_CHECKOUT_INITIALIZATION_FAILED"
            message = "Paystack could not open the checkout. No payment has been confirmed."
        checkout.failure_code = type(exc).__name__
        await session.flush()
        raise AppError(code, message, status_code=status.HTTP_502_BAD_GATEWAY) from exc
    checkout = await lock_committed_checkout(session, checkout_id)
    if checkout.status == PaymentCheckoutStatus.CONFIRMED.value:
        return checkout, None
    require_initialization_unknown(checkout)
    now = await database_clock(session)
    checkout.status = PaymentCheckoutStatus.INITIALIZED.value
    checkout.checkout_url = provider_session.checkout_url
    checkout.provider_checkout_id = provider_session.provider_checkout_id
    checkout.failure_code = None
    checkout.initialized_at = now
    await session.flush()
    return checkout, provider_session


async def get_advertiser_payment_checkout(
    session: AsyncSession,
    *,
    reference: str,
    actor_user_id: UUID,
) -> PaymentCheckoutIntent:
    organization, _ = await get_required_advertiser_context(session, actor_user_id)
    checkout = await session.scalar(
        select(PaymentCheckoutIntent)
        .where(
            PaymentCheckoutIntent.reference == reference,
            PaymentCheckoutIntent.organization_id == organization.id,
        )
        .execution_options(populate_existing=True)
    )
    if checkout is None:
        raise AppError(
            "PAYMENT_CHECKOUT_NOT_FOUND", "Payment checkout was not found", status_code=404
        )
    return checkout
