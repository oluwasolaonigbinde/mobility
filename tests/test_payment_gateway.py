import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_receipt_allocations import _accepted_terms

from app.adapters.payments import DisabledPaymentGatewayAdapter, FakePaymentGatewayAdapter
from app.core.errors import AppError
from app.jobs.payment_gateway import process_payment_gateway_event_job
from app.models.billing import (
    PaymentGatewayEvent,
    PaymentGatewayProcessingAttempt,
    PaymentReceipt,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptMethod,
)
from app.models.user import UserRole
from app.services.billing import (
    ingest_payment_gateway_webhook,
    process_payment_gateway_event,
    record_payment_gateway_failure,
    record_payment_receipt,
)


def _fixture(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="gateway-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="gateway-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    return admin, owner, organization, campaign


def _payload(terms_id, *, event_id="gateway-event-1", transaction_id="gateway-txn-1"):
    return json.dumps(
        {
            "provider_event_id": event_id,
            "external_transaction_id": transaction_id,
            "event_type": "payment_confirmed",
            "commercial_terms_id": str(terms_id),
            "amount": "100.00",
            "currency": "NGN",
            "payer_name": "Gateway Advertiser",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    ).encode()


def test_signed_gateway_ingestion_is_thin_and_worker_retry_converges(db_sessionmaker) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker)
    fake = FakePaymentGatewayAdapter()

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="GATEWAY-Q1",
            )
            payload = _payload(terms.id)
            with pytest.raises(AppError) as invalid:
                await ingest_payment_gateway_webhook(
                    session,
                    adapter=fake,
                    payload=payload,
                    signature="forged",
                )
            assert invalid.value.code == "INVALID_PAYMENT_WEBHOOK_SIGNATURE"
            assert await session.scalar(select(func.count(PaymentGatewayEvent.id))) == 0

            event, created = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=payload,
                signature=fake.sign_webhook(payload),
            )
            duplicate, duplicate_created = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=payload,
                signature=fake.sign_webhook(payload),
            )
            assert created is True
            assert duplicate_created is False
            assert duplicate.id == event.id
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 0

            with pytest.raises(AppError) as forged_authority:
                await record_payment_receipt(
                    session,
                    organization_id=terms.organization_id,
                    actor_user_id=None,
                    method=ReceiptMethod.GATEWAY,
                    provider=fake.provider_name,
                    external_transaction_id=f"{fake.provider_name}:gateway-txn-1",
                    amount="99.00",
                    currency="NGN",
                    payer_name="Gateway Advertiser",
                    evidence_reference="tamper",
                    observed_at=event.occurred_at,
                    trusted_gateway_event_id=event.id,
                )
            assert forged_authority.value.code == "GATEWAY_RECEIPT_LINEAGE_MISMATCH"
            failed = await record_payment_gateway_failure(
                session, event_id=event.id, error_code="TRANSIENT_TEST_FAILURE"
            )
            assert failed.attempt_number == 1
            first = await process_payment_gateway_event(session, event_id=event.id)
            retry = await process_payment_gateway_event(session, event_id=event.id)
            assert retry.id == first.id
            assert first.outcome == "confirmed"
            assert first.attempt_number == 2
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 1
            assert await session.scalar(select(func.count(ReceiptAllocation.id))) == 1
            assert await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))) == 2
            statuses = list(
                await session.scalars(
                    select(ReceiptLifecycleEvent.status).order_by(
                        ReceiptLifecycleEvent.sequence_number
                    )
                )
            )
            assert statuses == [
                ReceiptLifecycleStatus.OBSERVED,
                ReceiptLifecycleStatus.RECONCILED,
                ReceiptLifecycleStatus.CONFIRMED,
            ]
            await session.commit()

    asyncio.run(scenario())


def test_authenticated_events_are_durable_before_business_validation(db_sessionmaker) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker)
    fake = FakePaymentGatewayAdapter()

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="GATEWAY-DURABLE",
            )
            malformed = b"{}"
            with pytest.raises(AppError) as invalid:
                await ingest_payment_gateway_webhook(
                    session,
                    adapter=fake,
                    payload=malformed,
                    signature=fake.sign_webhook(malformed),
                )
            assert invalid.value.code == "INVALID_PAYMENT_WEBHOOK_PAYLOAD"
            with pytest.raises(AppError) as disabled:
                await ingest_payment_gateway_webhook(
                    session,
                    adapter=DisabledPaymentGatewayAdapter(),
                    payload=malformed,
                    signature="unused",
                )
            assert disabled.value.code == "PAYMENT_PROVIDER_NOT_CONFIGURED"

            unresolved = _payload(
                uuid4(), event_id="unresolved-event", transaction_id="unresolved-txn"
            )
            event, created = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=unresolved,
                signature=fake.sign_webhook(unresolved),
            )
            assert created is True
            with pytest.raises(AppError) as mismatch:
                await process_payment_gateway_event(session, event_id=event.id)
            assert mismatch.value.code == "PAYMENT_EVENT_TERMS_MISMATCH"
            assert await session.get(PaymentGatewayEvent, event.id) is not None

            payload = _payload(
                terms.id, event_id="shared-provider-event", transaction_id="shared-txn"
            )
            first, _ = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=payload,
                signature=fake.sign_webhook(payload),
            )
            replacement = FakePaymentGatewayAdapter()
            replacement.provider_name = "replacement-gateway"
            second, _ = await ingest_payment_gateway_webhook(
                session,
                adapter=replacement,
                payload=payload,
                signature=replacement.sign_webhook(payload),
            )
            assert first.provider_event_id == second.provider_event_id
            assert first.provider != second.provider
            await session.commit()

    asyncio.run(scenario())


def test_worker_job_persists_failure_attempt_after_business_rollback(db_sessionmaker) -> None:
    fake = FakePaymentGatewayAdapter()

    async def setup():
        async with db_sessionmaker() as session:
            payload = _payload(
                uuid4(), event_id="poison-event", transaction_id="poison-transaction"
            )
            event, _ = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=payload,
                signature=fake.sign_webhook(payload),
            )
            await session.commit()
            return event.id

    event_id = asyncio.run(setup())
    with pytest.raises(AppError) as processing_error:
        asyncio.run(
            process_payment_gateway_event_job({"sessionmaker": db_sessionmaker}, str(event_id))
        )
    assert processing_error.value.code == "PAYMENT_EVENT_TERMS_MISMATCH"

    async def assert_failure() -> None:
        async with db_sessionmaker() as session:
            attempt = await session.scalar(
                select(PaymentGatewayProcessingAttempt).where(
                    PaymentGatewayProcessingAttempt.gateway_event_id == event_id
                )
            )
            assert attempt is not None
            assert attempt.outcome == "failed"
            assert attempt.error_code == "PAYMENT_EVENT_TERMS_MISMATCH"

    asyncio.run(assert_failure())


def test_concurrent_gateway_workers_create_one_receipt_and_allocation(
    postgis_db_sessionmaker,
) -> None:
    admin, owner, _, campaign = _fixture(postgis_db_sessionmaker)
    fake = FakePaymentGatewayAdapter()

    async def setup():
        async with postgis_db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="GATEWAY-OVERLAP",
            )
            payload = _payload(terms.id, event_id="overlap-event", transaction_id="overlap-txn")
            event, _ = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=payload,
                signature=fake.sign_webhook(payload),
            )
            await session.commit()
            return event.id

    event_id = asyncio.run(setup())

    async def process():
        async with postgis_db_sessionmaker() as session:
            attempt = await process_payment_gateway_event(session, event_id=event_id)
            await session.commit()
            return attempt.id

    async def overlap():
        return await asyncio.gather(process(), process())

    first, second = asyncio.run(overlap())
    assert first == second

    async def counts():
        async with postgis_db_sessionmaker() as session:
            return (
                await session.scalar(select(func.count(PaymentReceipt.id))),
                await session.scalar(select(func.count(ReceiptAllocation.id))),
                await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))),
            )

    assert asyncio.run(counts()) == (1, 1, 1)
