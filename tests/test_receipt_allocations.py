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
from app.services.billing import (
    accept_quotation_revision,
    allocate_payment_receipt,
    confirm_payment_receipt,
    reconcile_payment_receipt,
    record_payment_receipt,
    record_quotation_revision,
    request_custom_quote,
    reverse_payment_receipt,
)


async def _accepted_terms(session, *, campaign, admin, owner, reference, amount="100.00"):
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
        payment_class=PaymentClass.STANDARD_PREPAID,
        payment_terms={},
        tax_rate="0",
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
            reconciliation = await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            assert reconciliation.matched is True
            await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
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
                ReceiptLifecycleStatus.OBSERVED,
                ReceiptLifecycleStatus.RECONCILED,
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
            reconciliation = await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            assert reconciliation.matched is False
            with pytest.raises(AppError) as confirm_error:
                await confirm_payment_receipt(
                    session, receipt_id=receipt.id, actor_user_id=admin.id
                )
            assert confirm_error.value.code == "RECEIPT_NOT_RECONCILED"
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
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
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
            await reconcile_payment_receipt(
                session,
                receipt_id=second_receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(
                session, receipt_id=second_receipt.id, actor_user_id=admin.id
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
