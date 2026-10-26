import asyncio
from datetime import UTC, datetime

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import select

from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    PaymentClass,
    QuoteRequestSource,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptMethod,
)
from app.models.user import UserRole
from app.services.billing.quotes import (
    accept_quotation_revision,
    record_quotation_revision,
    request_custom_quote,
)
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    record_payment_receipt,
    reverse_payment_receipt,
)


async def _accepted_terms(
    session,
    *,
    campaign,
    admin,
    owner,
    reference,
    amount="100.00",
    tax_rate="0",
    payment_class=PaymentClass.STANDARD_PREPAID,
):
    request = await request_custom_quote(
        session,
        campaign_id=campaign.id,
        actor_user_id=owner.id,
        source=QuoteRequestSource.IN_PLATFORM,
        request_details={},
    )
    revision = await record_quotation_revision(
        session,
        quote_request_id=request.id,
        actor_user_id=admin.id,
        quote_reference=reference,
        currency="NGN",
        line_items=[{"code": "MEDIA", "description": "Media", "kind": "media", "amount": amount}],
        production_scope={"vehicle_count": 1},
        payment_class=payment_class,
        payment_terms={"net_days": 30}
        if payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT
        else {},
        tax_rate=tax_rate,
    )
    return await accept_quotation_revision(
        session,
        quotation_revision_id=revision.id,
        actor_user_id=owner.id,
        acceptance_method=AcceptanceMethod.IN_PLATFORM,
    )


def _fixture(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="receipt-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="receipt-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=admin.id
    )
    return admin, owner, organization, campaign


def test_receipt_lifecycle_and_allocation_are_canonical_and_idempotent(db_sessionmaker) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="R-Q1"
            )
            observed_at = datetime.now(UTC)
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-TXN-001",
                amount="100.00",
                currency="ngn",
                payer_name="Acme Ads",
                evidence_reference="statement-line-17",
                observed_at=observed_at,
            )
            duplicate = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-TXN-001",
                amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-line-17",
                observed_at=observed_at,
            )
            assert duplicate.id == receipt.id
            reconciliation = await confirm_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            assert reconciliation is True
            allocation = await allocate_payment_receipt(
                session,
                receipt_id=receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="100.00",
            )
            same = await allocate_payment_receipt(
                session,
                receipt_id=receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="100.00",
            )
            assert same.id == allocation.id
            await reverse_payment_receipt(
                session, receipt_id=receipt.id, actor_user_id=admin.id, reason="bank reversal"
            )
            await session.commit()
            statuses = list(
                await session.scalars(
                    select(ReceiptLifecycleEvent.status)
                    .where(ReceiptLifecycleEvent.receipt_id == receipt.id)
                    .order_by(ReceiptLifecycleEvent.sequence_number)
                )
            )
            assert statuses == [
                ReceiptLifecycleStatus.RECORDED,
                ReceiptLifecycleStatus.CONFIRMED,
                ReceiptLifecycleStatus.REVERSED,
            ]

    asyncio.run(scenario())


def test_mismatched_receipt_cannot_confirm_or_allocate(db_sessionmaker) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="R-Q2"
            )
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-TXN-002",
                amount="90.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-line-18",
                observed_at=datetime.now(UTC),
            )
            reconciliation = await confirm_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            assert reconciliation is False
            with pytest.raises(AppError) as allocation_error:
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms.id,
                    actor_user_id=admin.id,
                    amount="90.00",
                )
            assert allocation_error.value.code == "RECEIPT_NOT_CONFIRMED"

    asyncio.run(scenario())


def test_allocation_cannot_exceed_receipt_or_accepted_obligation(db_sessionmaker) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker)
    second_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Second campaign",
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            first_terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="R-Q3",
                amount="80.00",
            )
            second_terms = await _accepted_terms(
                session,
                campaign=second_campaign,
                admin=admin,
                owner=owner,
                reference="R-Q4",
                amount="80.00",
            )
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-TXN-003",
                amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-line-19",
                observed_at=datetime.now(UTC),
            )
            await confirm_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await allocate_payment_receipt(
                session,
                receipt_id=receipt.id,
                commercial_terms_id=first_terms.id,
                actor_user_id=admin.id,
                amount="80.00",
            )
            with pytest.raises(AppError) as receipt_limit:
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=second_terms.id,
                    actor_user_id=admin.id,
                    amount="21.00",
                )
            assert receipt_limit.value.code == "RECEIPT_OVERALLOCATION"

            second_receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-TXN-004",
                amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-line-20",
                observed_at=datetime.now(UTC),
            )
            await confirm_payment_receipt(
                session,
                receipt_id=second_receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            with pytest.raises(AppError) as obligation_limit:
                await allocate_payment_receipt(
                    session,
                    receipt_id=second_receipt.id,
                    commercial_terms_id=first_terms.id,
                    actor_user_id=admin.id,
                    amount="1.00",
                )
            assert obligation_limit.value.code == "OBLIGATION_OVERFUNDING"

    asyncio.run(scenario())


def test_receipt_refusals_and_retries_preserve_canonical_authority(db_sessionmaker):
    from uuid import uuid4

    from sqlalchemy import func

    from app.models.audit import AuditEvent
    from app.models.billing import PaymentReceipt, ReceiptAllocation

    admin, owner, organization, campaign = _fixture(db_sessionmaker)

    async def run():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="BOUNDARY"
            )

            async def counts():
                await session.flush()
                return [
                    await session.scalar(select(func.count()).select_from(model))
                    for model in (
                        PaymentReceipt,
                        ReceiptAllocation,
                        ReceiptLifecycleEvent,
                        AuditEvent,
                    )
                ]

            async def refuses(operation, code):
                before = await counts()
                with pytest.raises(AppError) as caught:
                    await operation()
                assert caught.value.code == code
                assert await counts() == before

            for operation in (
                lambda: confirm_payment_receipt(
                    session,
                    receipt_id=uuid4(),
                    actor_user_id=admin.id,
                    expected_amount="100",
                    expected_currency="NGN",
                ),
                lambda: confirm_payment_receipt(
                    session,
                    receipt_id=uuid4(),
                    actor_user_id=admin.id,
                    expected_amount="100",
                    expected_currency="NGN",
                ),
                lambda: reverse_payment_receipt(
                    session, receipt_id=uuid4(), actor_user_id=admin.id, reason="missing"
                ),
            ):
                await refuses(operation, "RECEIPT_NOT_FOUND")
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="synthetic",
                external_transaction_id="BOUNDARY-RECEIPT",
                amount="100",
                currency="NGN",
                payer_name="Synthetic",
                evidence_reference="SYNTHETIC-ONLY",
                observed_at=datetime.now(UTC),
            )
            await refuses(
                lambda: reverse_payment_receipt(
                    session, receipt_id=receipt.id, actor_user_id=admin.id, reason="early"
                ),
                "RECEIPT_NOT_CONFIRMED",
            )
            for amount, currency in (("0", "NGN"), ("100", "N")):
                await refuses(
                    lambda amount=amount, currency=currency: confirm_payment_receipt(
                        session,
                        receipt_id=receipt.id,
                        actor_user_id=admin.id,
                        expected_amount=amount,
                        expected_currency=currency,
                    ),
                    "INVALID_CONFIRMATION_EXPECTATION",
                )
            args = dict(
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100",
                expected_currency="NGN",
            )
            reconciled = await confirm_payment_receipt(session, **args)
            before = await counts()
            assert (await confirm_payment_receipt(session, **args)) is reconciled is True
            assert await counts() == before
            await refuses(
                lambda: confirm_payment_receipt(session, **{**args, "expected_amount": "99"}),
                "RECEIPT_CONFIRMATION_CONFLICT",
            )
            allocation_args = dict(
                receipt_id=receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="50",
            )
            for changed, code in (
                ({"actor_user_id": None}, "ALLOCATION_ACTOR_REQUIRED"),
                ({"trusted_gateway_event_id": uuid4()}, "ALLOCATION_AUTHORITY_CONFLICT"),
                ({"commercial_terms_id": uuid4()}, "BILLING_AUTHORITY_NOT_FOUND"),
                ({"receipt_id": uuid4()}, "BILLING_AUTHORITY_NOT_FOUND"),
                ({"amount": "0"}, "INVALID_ALLOCATION_AMOUNT"),
            ):
                await refuses(
                    lambda changed=changed: allocate_payment_receipt(
                        session, **{**allocation_args, **changed}
                    ),
                    code,
                )
            allocation = await allocate_payment_receipt(session, **allocation_args)
            await refuses(
                lambda: allocate_payment_receipt(session, **{**allocation_args, "amount": "49"}),
                "ALLOCATION_ALREADY_RECORDED",
            )
            assert allocation.amount == 50
            await refuses(
                lambda: reverse_payment_receipt(
                    session, receipt_id=receipt.id, actor_user_id=admin.id, reason=" "
                ),
                "REVERSAL_REASON_REQUIRED",
            )
            await reverse_payment_receipt(
                session, receipt_id=receipt.id, actor_user_id=admin.id, reason="bank reversed"
            )
            before = await counts()
            assert (
                await reverse_payment_receipt(
                    session, receipt_id=receipt.id, actor_user_id=admin.id, reason="bank reversed"
                )
            ).id == receipt.id
            assert await counts() == before
            statuses = list(
                await session.scalars(
                    select(ReceiptLifecycleEvent.status)
                    .where(ReceiptLifecycleEvent.receipt_id == receipt.id)
                    .order_by(ReceiptLifecycleEvent.sequence_number)
                )
            )
            assert statuses == ["recorded", "confirmed", "reversed"]

    asyncio.run(run())


def test_receipt_missing_actor_invalid_facts_and_currency_cannot_grant_funding(db_sessionmaker):
    from uuid import uuid4

    from sqlalchemy import func

    from app.models.billing import PaymentReceipt, ReceiptAllocation

    admin, owner, organization, campaign = _fixture(db_sessionmaker)

    async def run():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="CURRENCY-BOUNDARY"
            )
            args = dict(
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="synthetic",
                external_transaction_id="USD-RECEIPT",
                amount="100",
                currency="USD",
                payer_name="Synthetic",
                evidence_reference="SYNTHETIC",
                observed_at=datetime.now(UTC),
            )
            for change, code in (
                ({"actor_user_id": None}, "RECEIPT_ACTOR_REQUIRED"),
                ({"organization_id": uuid4()}, "ORGANIZATION_NOT_FOUND"),
                ({"amount": "0"}, "INVALID_PAYMENT_RECEIPT"),
                ({"currency": "U"}, "INVALID_PAYMENT_RECEIPT"),
                ({"evidence_reference": " "}, "INVALID_PAYMENT_RECEIPT"),
            ):
                with pytest.raises(AppError) as caught:
                    await record_payment_receipt(session, **{**args, **change})
                assert caught.value.code == code
                assert await session.scalar(select(func.count()).select_from(PaymentReceipt)) == 0
            receipt = await record_payment_receipt(session, **args)
            await confirm_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100",
                expected_currency="USD",
            )
            with pytest.raises(AppError) as caught:
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms.id,
                    actor_user_id=admin.id,
                    amount="100",
                )
            assert caught.value.code == "ALLOCATION_CURRENCY_MISMATCH"
            assert await session.scalar(select(func.count()).select_from(ReceiptAllocation)) == 0

    asyncio.run(run())
