"""Checkout failure and retry boundaries that protect invoice and payment state."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.adapters.payments import CheckoutSession, PaymentGatewayUnavailableError
from app.adapters.payments.paystack import (
    PaystackNotFoundError,
    PaystackOutcomeUnknownError,
    PaystackRejectedError,
)
from app.api.v1 import billing as billing_api
from app.core.errors import AppError
from app.models.billing import InvoiceStatus, PaymentCheckoutStatus, PaymentClass
from app.services import billing


class Session:
    def __init__(self, *, scalars=(), gets=()) -> None:
        self.scalars = list(scalars)
        self.gets = list(gets)
        self.flushes = 0
        self.commits = 0
        self.added = []

    async def scalar(self, _statement):
        return self.scalars.pop(0)

    async def get(self, _model, _identity):
        return self.gets.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1


class Adapter:
    provider_name = "paystack"

    def __init__(self, *, validate_error=None, create_result=None) -> None:
        self.validate_error = validate_error
        self.create_result = create_result or CheckoutSession(
            provider_checkout_id="checkout-1",
            checkout_url="https://checkout.paystack.com/synthetic",
        )
        self.create_calls = 0

    def validate_checkout(self, _request):
        if self.validate_error is not None:
            raise self.validate_error

    async def create_checkout(self, _request):
        self.create_calls += 1
        if isinstance(self.create_result, Exception):
            raise self.create_result
        return self.create_result


def payable_graph(*, invoice_status=InvoiceStatus.ISSUED.value, payment_class=None, currency="NGN"):
    organization = SimpleNamespace(id=uuid4(), billing_email="billing@example.test")
    terms = SimpleNamespace(
        id=uuid4(),
        organization_id=organization.id,
        payment_class=payment_class or PaymentClass.STANDARD_PREPAID.value,
        currency=currency,
    )
    invoice = SimpleNamespace(
        id=uuid4(),
        organization_id=organization.id,
        commercial_terms_id=terms.id,
        status=invoice_status,
        currency=currency,
    )
    actor = SimpleNamespace(id=uuid4(), email="owner@example.test")
    return organization, terms, invoice, actor


async def install_prepare_dependencies(
    monkeypatch, organization, *, funded="0.00", obligation="100.00"
):
    async def context(*_args, **_kwargs):
        return organization, object()

    async def payment_status(*_args, **_kwargs):
        return None, Decimal(funded)

    async def adjusted(*_args, **_kwargs):
        return Decimal(obligation)

    async def clock(_session):
        return datetime(2026, 9, 30, tzinfo=UTC)

    async def audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(billing, "get_required_advertiser_context", context)
    monkeypatch.setattr(billing, "invoice_payment_status", payment_status)
    monkeypatch.setattr(billing, "adjusted_invoice_obligation", adjusted)
    monkeypatch.setattr(billing, "database_clock", clock)
    monkeypatch.setattr(billing, "create_audit_event", audit)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing_invoice", "INVOICE_NOT_FOUND"),
        ("wrong_tenant", "INVOICE_NOT_FOUND"),
        ("draft_invoice", "INVOICE_NOT_PAYABLE"),
        ("missing_terms", "INVOICE_TERMS_MISMATCH"),
        ("wrong_terms_tenant", "INVOICE_TERMS_MISMATCH"),
        ("credit_terms", "INVOICE_NOT_PAYABLE_ONLINE"),
        ("already_paid", "INVOICE_ALREADY_PAID"),
        ("unsupported_currency", "PAYMENT_CURRENCY_UNSUPPORTED"),
        ("disabled_provider", "PAYMENT_PROVIDER_NOT_CONFIGURED"),
        ("active_different_amount", "PAYMENT_CHECKOUT_ALREADY_ACTIVE"),
        ("confirmed_processing", "PAYMENT_CONFIRMATION_PROCESSING"),
        ("missing_email", "PAYMENT_CUSTOMER_EMAIL_REQUIRED"),
    ],
)
def test_prepare_checkout_fails_closed_without_contacting_paystack(monkeypatch, case, expected):
    organization, terms, invoice, actor = payable_graph()
    adapter = Adapter()
    scalars = [invoice, None]
    gets = [terms, actor]
    funded, obligation = "0.00", "100.00"

    if case == "missing_invoice":
        scalars, gets = [None], []
    elif case == "wrong_tenant":
        invoice.organization_id = uuid4()
        scalars, gets = [invoice], []
    elif case == "draft_invoice":
        invoice.status = InvoiceStatus.DRAFT.value
        scalars, gets = [invoice], []
    elif case == "missing_terms":
        scalars, gets = [invoice], [None]
    elif case == "wrong_terms_tenant":
        terms.organization_id = uuid4()
        scalars, gets = [invoice], [terms]
    elif case == "credit_terms":
        terms.payment_class = PaymentClass.APPROVED_CORPORATE_CREDIT.value
        scalars, gets = [invoice], [terms]
    elif case == "already_paid":
        funded = obligation = "100.00"
        scalars, gets = [invoice], [terms]
    elif case == "unsupported_currency":
        invoice.currency = terms.currency = "USD"
        scalars, gets = [invoice], [terms]
    elif case == "disabled_provider":
        adapter.provider_name = "disabled"
        scalars, gets = [invoice], [terms]
    elif case == "active_different_amount":
        active = SimpleNamespace(
            status=PaymentCheckoutStatus.INITIALIZED.value,
            amount=Decimal("50.00"),
            currency="NGN",
        )
        scalars, gets = [invoice, active], [terms]
    elif case == "confirmed_processing":
        active = SimpleNamespace(
            status=PaymentCheckoutStatus.CONFIRMED.value,
            amount=Decimal("100.00"),
            currency="NGN",
            reference="cv-confirmed",
        )
        scalars, gets = [invoice, active, False], [terms]
    elif case == "missing_email":
        organization.billing_email = ""
        actor.email = ""

    asyncio.run(
        install_prepare_dependencies(
            monkeypatch, organization, funded=funded, obligation=obligation
        )
    )
    session = Session(scalars=scalars, gets=gets)

    with pytest.raises(AppError) as error:
        asyncio.run(
            billing.prepare_invoice_payment_checkout(
                session,
                invoice_id=invoice.id,
                actor_user_id=actor.id,
                adapter=adapter,
            )
        )

    assert error.value.code == expected
    assert adapter.create_calls == 0


def checkout(status=PaymentCheckoutStatus.PENDING.value):
    return SimpleNamespace(
        id=uuid4(),
        reference="cv-synthetic-checkout",
        provider="paystack",
        commercial_terms_id=uuid4(),
        organization_id=uuid4(),
        invoice_id=uuid4(),
        amount=Decimal("100.00"),
        currency="NGN",
        customer_email="owner@example.test",
        status=status,
        failure_code=None,
        checkout_url=None,
        provider_checkout_id=None,
        initialized_at=None,
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("blank_return", "PAYMENT_RETURN_URL_NOT_CONFIGURED"),
        ("missing", "PAYMENT_CHECKOUT_NOT_FOUND"),
        ("provider_mismatch", "PAYMENT_CHECKOUT_PROVIDER_MISMATCH"),
        ("initialization_unknown", "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN"),
        ("not_initializable", "PAYMENT_CHECKOUT_NOT_INITIALIZABLE"),
        ("disabled_validation", "PAYMENT_PROVIDER_NOT_CONFIGURED"),
        ("invalid_saved_details", "PAYMENT_CHECKOUT_INVALID"),
        ("provider_disabled", "PAYMENT_PROVIDER_NOT_CONFIGURED"),
        ("provider_rejected", "PAYMENT_CHECKOUT_REJECTED"),
        ("provider_unknown", "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN"),
        ("provider_malformed", "PAYMENT_CHECKOUT_INITIALIZATION_FAILED"),
        ("state_changed", "PAYMENT_CHECKOUT_STATE_CHANGED"),
    ],
)
def test_initialize_checkout_preserves_retry_and_uncertainty_state(monkeypatch, case, expected):
    saved = checkout()
    committed = saved
    adapter = Adapter()
    scalars = [saved]
    return_url = "https://cardvert.example/billing/paystack/return"

    if case == "blank_return":
        return_url, scalars = " ", []
    elif case == "missing":
        scalars = [None]
    elif case == "provider_mismatch":
        saved.provider = "other"
    elif case == "initialization_unknown":
        saved.status = PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value
    elif case == "not_initializable":
        saved.status = PaymentCheckoutStatus.FAILED.value
    elif case == "disabled_validation":
        adapter.validate_error = PaymentGatewayUnavailableError("disabled")
    elif case == "invalid_saved_details":
        adapter.validate_error = ValueError("invalid")
    elif case == "provider_disabled":
        adapter.create_result = PaymentGatewayUnavailableError("disabled")
    elif case == "provider_rejected":
        adapter.create_result = PaystackRejectedError("rejected")
        committed = checkout(PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value)
        scalars.append(committed)
    elif case == "provider_unknown":
        adapter.create_result = PaystackOutcomeUnknownError("unknown")
        committed = checkout(PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value)
        scalars.append(committed)
    elif case == "provider_malformed":
        adapter.create_result = ValueError("malformed")
        committed = checkout(PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value)
        scalars.append(committed)
    elif case == "state_changed":
        adapter.create_result = PaystackRejectedError("rejected")
        committed = checkout(PaymentCheckoutStatus.PENDING.value)
        scalars.append(committed)

    session = Session(scalars=scalars)

    with pytest.raises(AppError) as error:
        asyncio.run(
            billing.initialize_invoice_payment_checkout(
                session,
                checkout_id=saved.id,
                adapter=adapter,
                return_url=return_url,
            )
        )

    assert error.value.code == expected
    if case in {"invalid_saved_details", "provider_rejected"}:
        assert committed.status == PaymentCheckoutStatus.FAILED.value
    if case in {"provider_unknown", "provider_malformed"}:
        assert committed.status == PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value


def test_initialize_checkout_returns_existing_initialized_intent_without_provider_call():
    saved = checkout(PaymentCheckoutStatus.INITIALIZED.value)
    adapter = Adapter()

    result, provider_session = asyncio.run(
        billing.initialize_invoice_payment_checkout(
            Session(scalars=[saved]),
            checkout_id=saved.id,
            adapter=adapter,
            return_url="https://cardvert.example/billing/paystack/return",
        )
    )

    assert result is saved
    assert provider_session is None
    assert adapter.create_calls == 0


def test_prepare_checkout_reuses_the_same_active_amount(monkeypatch):
    organization, terms, invoice, actor = payable_graph()
    existing = checkout(PaymentCheckoutStatus.INITIALIZED.value)
    existing.amount = Decimal("100.00")
    existing.currency = "NGN"
    asyncio.run(install_prepare_dependencies(monkeypatch, organization))

    result = asyncio.run(
        billing.prepare_invoice_payment_checkout(
            Session(scalars=[invoice, existing], gets=[terms]),
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            adapter=Adapter(),
        )
    )

    assert result is existing


def test_initialize_checkout_records_the_returned_provider_session(monkeypatch):
    saved = checkout()
    committed = checkout(PaymentCheckoutStatus.INITIALIZATION_UNKNOWN.value)
    committed.id = saved.id

    async def clock(_session):
        return datetime(2026, 9, 30, tzinfo=UTC)

    monkeypatch.setattr(billing, "database_clock", clock)
    result, provider_session = asyncio.run(
        billing.initialize_invoice_payment_checkout(
            Session(scalars=[saved, committed]),
            checkout_id=saved.id,
            adapter=Adapter(),
            return_url="https://cardvert.example/billing/paystack/return",
        )
    )

    assert result is committed
    assert result.status == PaymentCheckoutStatus.INITIALIZED.value
    assert result.checkout_url == "https://checkout.paystack.com/synthetic"
    assert result.provider_checkout_id == "checkout-1"
    assert provider_session is not None


def test_get_checkout_hides_missing_advertiser_reference(monkeypatch):
    organization = SimpleNamespace(id=uuid4())

    async def context(*_args, **_kwargs):
        return organization, object()

    monkeypatch.setattr(billing, "get_required_advertiser_context", context)
    with pytest.raises(AppError) as error:
        asyncio.run(
            billing.get_advertiser_payment_checkout(
                Session(scalars=[None]), reference="cv-missing", actor_user_id=uuid4()
            )
        )
    assert error.value.code == "PAYMENT_CHECKOUT_NOT_FOUND"


class RouteSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class Verifier:
    def __init__(self, outcome) -> None:
        self.outcome = outcome

    async def verify_transaction(self, _reference):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class Enqueuer:
    def __init__(self) -> None:
        self.ids = []

    async def enqueue_payment_event(self, event_id):
        self.ids.append(event_id)


@pytest.mark.parametrize(
    ("provider_error", "expected"),
    [
        (PaymentGatewayUnavailableError("disabled"), "PAYMENT_PROVIDER_NOT_CONFIGURED"),
        (PaystackNotFoundError("not final"), "PAYMENT_NOT_FINAL"),
        (PaystackOutcomeUnknownError("unknown"), "PAYMENT_VERIFICATION_UNAVAILABLE"),
        (ValueError("malformed"), "PAYMENT_VERIFICATION_FAILED"),
    ],
)
def test_verify_checkout_maps_provider_uncertainty_without_applying_money(
    monkeypatch, provider_error, expected
):
    saved = checkout()

    async def get_checkout(*_args, **_kwargs):
        return saved

    monkeypatch.setattr(billing_api, "get_advertiser_payment_checkout", get_checkout)
    session = RouteSession()
    enqueuer = Enqueuer()

    with pytest.raises(AppError) as error:
        asyncio.run(
            billing_api.advertiser_verify_payment_checkout(
                saved.reference,
                SimpleNamespace(id=uuid4()),
                session,
                Verifier(provider_error),
                enqueuer,
            )
        )

    assert error.value.code == expected
    assert session.rollbacks == 1
    assert session.commits == 0
    assert enqueuer.ids == []


def test_checkout_routes_commit_failed_initialization_and_enqueue_verified_evidence(
    monkeypatch,
):
    saved = checkout()
    settings = SimpleNamespace(
        paystack_checkout_return_url="https://cardvert.example/billing/paystack/return"
    )
    session = RouteSession()

    async def prepare(*_args, **_kwargs):
        return saved

    async def fail_initialize(*_args, **_kwargs):
        raise AppError("PAYMENT_CHECKOUT_REJECTED", "rejected", status_code=502)

    monkeypatch.setattr(billing_api, "prepare_invoice_payment_checkout", prepare)
    monkeypatch.setattr(billing_api, "initialize_invoice_payment_checkout", fail_initialize)
    with pytest.raises(AppError):
        asyncio.run(
            billing_api.advertiser_create_invoice_checkout(
                saved.invoice_id,
                SimpleNamespace(id=uuid4()),
                session,
                settings,
                Adapter(),
            )
        )
    assert session.commits == 2

    pending = checkout()
    confirmed = checkout(PaymentCheckoutStatus.CONFIRMED.value)
    event = SimpleNamespace(id=uuid4())
    reads = iter((pending, confirmed))
    verified = object()

    async def get_checkout(*_args, **_kwargs):
        return next(reads)

    async def ingest(*_args, **_kwargs):
        return event, True

    monkeypatch.setattr(billing_api, "get_advertiser_payment_checkout", get_checkout)
    monkeypatch.setattr(billing_api, "ingest_verified_payment_event", ingest)
    session = RouteSession()
    enqueuer = Enqueuer()
    result = asyncio.run(
        billing_api.advertiser_verify_payment_checkout(
            pending.reference,
            SimpleNamespace(id=uuid4()),
            session,
            Verifier(verified),
            enqueuer,
        )
    )

    assert result.status == PaymentCheckoutStatus.CONFIRMED.value
    assert session.commits == 1
    assert enqueuer.ids == [event.id]
