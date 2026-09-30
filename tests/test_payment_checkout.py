import asyncio
from uuid import UUID

import pytest
from conftest import auth_headers, create_test_campaign, create_test_organization, create_test_user
from paystack_fixtures import SYNTHETIC_TEST_KEY, RecordingTransport, ok, transaction
from sqlalchemy import func, select
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

from app.adapters.payments.paystack import PaystackClient, PaystackPaymentGatewayAdapter
from app.api.v1.billing import get_payment_gateway_adapter
from app.core.errors import AppError
from app.jobs.payment_gateway import sweep_payment_gateway_events
from app.models.billing import (
    InvoiceStatus,
    IssuerVerificationStatus,
    PaymentCheckoutIntent,
    PaymentGatewayEvent,
    PaymentReceipt,
)
from app.models.user import UserRole
from app.services.billing import (
    create_invoice_draft,
    initialize_invoice_payment_checkout,
    issue_invoice,
    prepare_invoice_payment_checkout,
    reverse_payment_receipt,
)


def test_issued_invoice_checkout_is_stable_and_verified_before_funding(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    settings.paystack_checkout_return_url = (
        "http://localhost:3000/advertiser/billing/paystack/return"
    )
    admin = create_test_user(db_sessionmaker, email="checkout-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="checkout-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=owner.id,
        billing_email="billing@example.com",
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def arrange():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="CHECKOUT-Q1",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-CHECKOUT-ISSUER",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            assert invoice.status == InvoiceStatus.ISSUED.value
            return terms.id, invoice.id, organization.id

    terms_id, invoice_id, organization_id = asyncio.run(arrange())
    fixed_id = UUID("11111111-2222-4333-8444-555555555555")
    reference = f"cv-{fixed_id.hex}"
    monkeypatch.setattr("app.services.billing.uuid4", lambda: fixed_id)
    transport = RecordingTransport(
        ok(
            {
                "reference": reference,
                "authorization_url": f"https://checkout.paystack.com/{reference}",
            }
        ),
        ok(
            transaction(
                reference=reference,
                terms_id=str(terms_id),
                organization_id=str(organization_id),
                amount=10000,
            )
        ),
    )
    adapter = PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY, transport=transport))
    db_client.app.dependency_overrides[get_payment_gateway_adapter] = lambda: adapter
    headers = auth_headers(db_client, owner.email)
    try:
        checkout = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert checkout.status_code == 201, checkout.text
        assert checkout.json() == {
            "reference": reference,
            "invoice_id": str(invoice_id),
            "amount": "100.00",
            "currency": "NGN",
            "status": "initialized",
            "checkout_url": f"https://checkout.paystack.com/{reference}",
        }
        assert transport.json_bodies()[0]["email"] == "billing@example.com"
        retry = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert retry.status_code == 201
        assert retry.json() == checkout.json()
        assert len(transport.requests) == 1

        verified = db_client.post(
            f"/api/v1/advertiser/payment-checkouts/{reference}/verify", headers=headers
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["status"] == "confirmed"
        assert len(transport.requests) == 2
        blocked = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "PAYMENT_CONFIRMATION_PROCESSING"
        assert len(transport.requests) == 2
        asyncio.run(sweep_payment_gateway_events({"sessionmaker": db_sessionmaker}))

        async def reverse_applied_payment() -> None:
            async with db_sessionmaker() as session:
                receipt_id = await session.scalar(select(PaymentReceipt.id))
                assert receipt_id is not None
                await reverse_payment_receipt(
                    session,
                    receipt_id=receipt_id,
                    actor_user_id=admin.id,
                    reason="synthetic gateway reversal",
                )
                await session.commit()

        asyncio.run(reverse_applied_payment())
        replacement_id = UUID("66666666-7777-4888-8999-000000000000")
        replacement_reference = f"cv-{replacement_id.hex}"
        monkeypatch.setattr("app.services.billing.uuid4", lambda: replacement_id)
        transport.queue(
            ok(
                {
                    "reference": replacement_reference,
                    "authorization_url": (
                        f"https://checkout.paystack.com/{replacement_reference}"
                    ),
                }
            )
        )
        replacement = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["reference"] == replacement_reference
        assert replacement.json()["amount"] == "100.00"
        assert len(transport.requests) == 3
    finally:
        db_client.app.dependency_overrides.pop(get_payment_gateway_adapter, None)

    async def assert_funded():
        async with db_sessionmaker() as session:
            intent = await session.scalar(
                select(PaymentCheckoutIntent).where(PaymentCheckoutIntent.reference == reference)
            )
            assert intent is not None and intent.status == "confirmed"
            assert await session.scalar(select(func.count(PaymentGatewayEvent.id))) == 1
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 1

    asyncio.run(assert_funded())


def test_paystack_verification_rejects_amount_outside_saved_checkout(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    settings.paystack_checkout_return_url = (
        "http://localhost:3000/advertiser/billing/paystack/return"
    )
    admin = create_test_user(db_sessionmaker, email="checkout-amount-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="checkout-amount-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def arrange():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="CHECKOUT-Q2",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-CHECKOUT-AMOUNT",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            return terms.id, invoice.id, organization.id

    terms_id, invoice_id, organization_id = asyncio.run(arrange())
    fixed_id = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
    reference = f"cv-{fixed_id.hex}"
    monkeypatch.setattr("app.services.billing.uuid4", lambda: fixed_id)
    transport = RecordingTransport(
        ok(
            {
                "reference": reference,
                "authorization_url": f"https://checkout.paystack.com/{reference}",
            }
        ),
        ok(
            transaction(
                reference=reference,
                terms_id=str(terms_id),
                organization_id=str(organization_id),
                amount=9999,
            )
        ),
    )
    adapter = PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY, transport=transport))
    db_client.app.dependency_overrides[get_payment_gateway_adapter] = lambda: adapter
    headers = auth_headers(db_client, owner.email)
    try:
        assert (
            db_client.post(
                f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
            ).status_code
            == 201
        )
        rejected = db_client.post(
            f"/api/v1/advertiser/payment-checkouts/{reference}/verify", headers=headers
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "PAYMENT_CHECKOUT_BINDING_MISMATCH"
    finally:
        db_client.app.dependency_overrides.pop(get_payment_gateway_adapter, None)

    async def assert_rejected():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(PaymentGatewayEvent.id))) == 0
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 0

    asyncio.run(assert_rejected())


def test_provider_acceptance_before_local_save_keeps_one_recoverable_reference(
    db_sessionmaker, settings, monkeypatch
) -> None:
    settings.paystack_checkout_return_url = (
        "http://localhost:3000/advertiser/billing/paystack/return"
    )
    admin = create_test_user(db_sessionmaker, email="checkout-crash-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="checkout-crash-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="CHECKOUT-CRASH-Q1",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-CHECKOUT-CRASH",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            checkout = await prepare_invoice_payment_checkout(
                session,
                invoice_id=invoice.id,
                actor_user_id=owner.id,
                adapter=PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY)),
            )
            await session.commit()
            checkout_id = checkout.id

            transport = RecordingTransport(
                ok(
                    {
                        "reference": checkout.reference,
                        "authorization_url": (
                            f"https://checkout.paystack.com/{checkout.reference}"
                        ),
                    }
                )
            )
            adapter = PaystackPaymentGatewayAdapter(
                PaystackClient(SYNTHETIC_TEST_KEY, transport=transport)
            )

            async def local_save_failed(_session):
                raise RuntimeError("synthetic local persistence failure")

            monkeypatch.setattr("app.services.billing.database_clock", local_save_failed)
            with pytest.raises(RuntimeError, match="local persistence failure"):
                await initialize_invoice_payment_checkout(
                    session,
                    checkout_id=checkout_id,
                    adapter=adapter,
                    return_url=settings.paystack_checkout_return_url,
                )
            await session.rollback()

        async with db_sessionmaker() as recovery_session:
            saved = await recovery_session.get(PaymentCheckoutIntent, checkout_id)
            assert saved is not None
            assert saved.status == "initialization_unknown"
            with pytest.raises(AppError) as blocked:
                await initialize_invoice_payment_checkout(
                    recovery_session,
                    checkout_id=saved.id,
                    adapter=adapter,
                    return_url=settings.paystack_checkout_return_url,
                )
            assert blocked.value.code == "PAYMENT_CHECKOUT_INITIALIZATION_UNKNOWN"
            assert len(transport.requests) == 1

    asyncio.run(scenario())


def test_invalid_billing_email_fails_before_provider_and_can_be_corrected(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    settings.paystack_checkout_return_url = (
        "http://localhost:3000/advertiser/billing/paystack/return"
    )
    admin = create_test_user(db_sessionmaker, email="checkout-email-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="checkout-email-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=owner.id,
        billing_email="billing@invalid",
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def arrange() -> UUID:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="CHECKOUT-EMAIL-Q1",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-CHECKOUT-EMAIL",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            return invoice.id

    invoice_id = asyncio.run(arrange())
    first_id = UUID("10101010-2020-4030-8040-505050505050")
    replacement_id = UUID("60606060-7070-4080-8090-a0a0a0a0a0a0")
    monkeypatch.setattr("app.services.billing.uuid4", lambda: first_id)
    replacement_reference = f"cv-{replacement_id.hex}"
    transport = RecordingTransport(
        ok(
            {
                "reference": replacement_reference,
                "authorization_url": f"https://checkout.paystack.com/{replacement_reference}",
            }
        )
    )
    adapter = PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY, transport=transport))
    db_client.app.dependency_overrides[get_payment_gateway_adapter] = lambda: adapter
    headers = auth_headers(db_client, owner.email)
    try:
        rejected = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["error"]["code"] == "PAYMENT_CHECKOUT_INVALID"
        assert transport.requests == []

        async def correct_email() -> None:
            async with db_sessionmaker() as session:
                saved_organization = await session.get(type(organization), organization.id)
                assert saved_organization is not None
                saved_organization.billing_email = "billing@example.com"
                await session.commit()

        asyncio.run(correct_email())
        monkeypatch.setattr("app.services.billing.uuid4", lambda: replacement_id)
        created = db_client.post(
            f"/api/v1/advertiser/invoices/{invoice_id}/checkout", headers=headers
        )
        assert created.status_code == 201, created.text
        assert created.json()["reference"] == replacement_reference
        assert len(transport.requests) == 1
    finally:
        db_client.app.dependency_overrides.pop(get_payment_gateway_adapter, None)

    async def assert_states() -> None:
        async with db_sessionmaker() as session:
            states = list(
                await session.scalars(
                    select(PaymentCheckoutIntent.status).order_by(
                        PaymentCheckoutIntent.created_at, PaymentCheckoutIntent.id
                    )
                )
            )
            assert states == ["failed", "initialized"]

    asyncio.run(assert_states())
