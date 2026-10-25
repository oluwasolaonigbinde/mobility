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
from app.jobs.payment_gateway import process_payment_gateway_event_job, sweep_payment_gateway_events
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
from app.services.billing.gateway import (
    ingest_payment_gateway_webhook,
    process_payment_gateway_event,
    record_payment_gateway_failure,
)
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
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
            "organization_id": "00000000-0000-4000-8000-000000000002",
            "amount": "100.00",
            "currency": "NGN",
            "payer_name": "Gateway Advertiser",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    ).encode()


def test_permanent_failure_redelivery_is_terminal_and_poison_page_cannot_starve(db_sessionmaker):
    fake = FakePaymentGatewayAdapter()

    async def scenario():
        poison_ids = []
        async with db_sessionmaker() as session:
            for index in range(100):
                payload = _payload(
                    uuid4(), event_id=f"poison-{index}", transaction_id=f"poison-{index}"
                )
                event, _ = await ingest_payment_gateway_webhook(
                    session, adapter=fake, payload=payload, signature=fake.sign_webhook(payload)
                )
                poison_ids.append(event.id)
                await record_payment_gateway_failure(
                    session, event_id=event.id, error_code="PAYMENT_EVENT_TERMS_MISMATCH"
                )
            payload = json.loads(
                _payload(uuid4(), event_id="eligible-later", transaction_id="eligible-later")
            )
            payload["event_type"] = "payment_failed"
            encoded = json.dumps(payload).encode()
            later, _ = await ingest_payment_gateway_webhook(
                session, adapter=fake, payload=encoded, signature=fake.sign_webhook(encoded)
            )
            await session.commit()
        ctx = {"sessionmaker": db_sessionmaker}
        # A deterministic duplicate job returns the existing terminal evidence.
        for _ in range(3):
            result = await process_payment_gateway_event_job(ctx, str(poison_ids[0]))
            assert result["outcome"] == "failed"
            assert result["attempt_number"] == 1
        result = await sweep_payment_gateway_events(ctx)
        assert result == {"selected": 1, "processed": 1, "failed": 0}
        assert await sweep_payment_gateway_events(ctx) == {
            "selected": 0,
            "processed": 0,
            "failed": 0,
        }
        async with db_sessionmaker() as session:
            assert (
                await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))) == 101
            )
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 0
            assert await session.scalar(select(func.count(ReceiptAllocation.id))) == 0
            assert (
                await session.scalar(
                    select(PaymentGatewayProcessingAttempt.outcome).where(
                        PaymentGatewayProcessingAttempt.gateway_event_id == later.id
                    )
                )
                == "ignored_failed"
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "code", ["PAYMENT_EVENT_TERMS_MISMATCH", "PAYMENT_CHECKOUT_BINDING_MISMATCH"]
)
def test_terminal_recording_serializes_duplicate_jobs_and_cannot_append_attempts(
    db_sessionmaker, code
):
    fake = FakePaymentGatewayAdapter()

    async def scenario():
        async with db_sessionmaker() as session:
            payload = _payload(uuid4(), event_id="terminal-race", transaction_id="terminal-race")
            event, _ = await ingest_payment_gateway_webhook(
                session, adapter=fake, payload=payload, signature=fake.sign_webhook(payload)
            )
            await session.commit()

        async def record():
            async with db_sessionmaker() as session:
                attempt = await record_payment_gateway_failure(
                    session, event_id=event.id, error_code=code
                )
                await session.commit()
                return attempt.id

        first, second = await asyncio.gather(record(), record())
        assert first == second
        assert await process_payment_gateway_event_job(
            {"sessionmaker": db_sessionmaker}, str(event.id)
        ) == {"event_id": str(event.id), "outcome": "failed", "attempt_number": 1}
        async with db_sessionmaker() as session:
            assert (
                await record_payment_gateway_failure(
                    session, event_id=event.id, error_code="TRANSIENT_UNAVAILABLE"
                )
            ).id == first
            assert await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))) == 1

    asyncio.run(scenario())


def test_failure_persistence_error_remains_retryable_and_racing_jobs_converge(
    db_sessionmaker, monkeypatch
):
    import app.jobs.payment_gateway as jobs

    fake = FakePaymentGatewayAdapter()
    original = jobs.record_payment_gateway_failure

    async def scenario():
        async with db_sessionmaker() as session:
            payload = _payload(uuid4(), event_id="retry-persist", transaction_id="retry-persist")
            event, _ = await ingest_payment_gateway_webhook(
                session, adapter=fake, payload=payload, signature=fake.sign_webhook(payload)
            )
            await session.commit()

        async def unavailable(*args, **kwargs):
            raise RuntimeError("synthetic failure-store outage")

        monkeypatch.setattr(jobs, "record_payment_gateway_failure", unavailable)
        ctx = {"sessionmaker": db_sessionmaker}
        with pytest.raises(RuntimeError, match="failure-store outage"):
            await jobs.process_payment_gateway_event_job(ctx, str(event.id))
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))) == 0
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 0
        monkeypatch.setattr(jobs, "record_payment_gateway_failure", original)
        first, second = await asyncio.gather(
            jobs.process_payment_gateway_event_job(ctx, str(event.id)),
            jobs.process_payment_gateway_event_job(ctx, str(event.id)),
        )
        assert (
            first == second == {"event_id": str(event.id), "outcome": "failed", "attempt_number": 1}
        )
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(PaymentGatewayProcessingAttempt.id))) == 1
            assert await session.scalar(select(func.count(ReceiptAllocation.id))) == 0

    asyncio.run(scenario())


def test_transient_processing_failure_is_swept_again_and_recovers(db_sessionmaker, monkeypatch):
    import app.jobs.payment_gateway as jobs

    fake = FakePaymentGatewayAdapter()
    original = jobs.process_payment_gateway_event

    async def scenario():
        payload = json.loads(_payload(uuid4(), event_id="transient", transaction_id="transient"))
        payload["event_type"] = "payment_failed"
        encoded = json.dumps(payload).encode()
        async with db_sessionmaker() as session:
            event, _ = await ingest_payment_gateway_webhook(
                session, adapter=fake, payload=encoded, signature=fake.sign_webhook(encoded)
            )
            await session.commit()

        async def temporarily_unavailable(*args, **kwargs):
            raise RuntimeError("synthetic recoverable processing outage")

        monkeypatch.setattr(jobs, "process_payment_gateway_event", temporarily_unavailable)
        ctx = {"sessionmaker": db_sessionmaker}
        with pytest.raises(RuntimeError, match="recoverable processing outage"):
            await jobs.process_payment_gateway_event_job(ctx, str(event.id))
        monkeypatch.setattr(jobs, "process_payment_gateway_event", original)
        assert await jobs.sweep_payment_gateway_events(ctx) == {
            "selected": 1,
            "processed": 1,
            "failed": 0,
        }
        async with db_sessionmaker() as session:
            attempts = list(
                await session.scalars(
                    select(PaymentGatewayProcessingAttempt)
                    .where(PaymentGatewayProcessingAttempt.gateway_event_id == event.id)
                    .order_by(PaymentGatewayProcessingAttempt.attempt_number)
                )
            )
            assert [(attempt.outcome, attempt.error_code) for attempt in attempts] == [
                ("failed", "RuntimeError"),
                ("ignored_failed", None),
            ]
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 0
            assert await session.scalar(select(func.count(ReceiptAllocation.id))) == 0

    asyncio.run(scenario())


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
                ReceiptLifecycleStatus.RECORDED,
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


def test_manual_payment_before_gateway_confirmation_preserves_unallocated_cash(
    db_sessionmaker,
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker)
    fake = FakePaymentGatewayAdapter()

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="GATEWAY-MANUAL-RACE",
            )
            manual = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="BANK-BEFORE-GATEWAY",
                amount="100.00",
                currency="NGN",
                payer_name="Gateway Advertiser",
                evidence_reference="statement-before-gateway",
                observed_at=datetime.now(UTC),
            )
            await confirm_payment_receipt(
                session,
                receipt_id=manual.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await allocate_payment_receipt(
                session,
                receipt_id=manual.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="100.00",
            )
            body = _payload(
                terms.id,
                event_id="gateway-after-manual",
                transaction_id="gateway-after-manual",
            )
            event, _ = await ingest_payment_gateway_webhook(
                session,
                adapter=fake,
                payload=body,
                signature=fake.sign_webhook(body),
            )
            attempt = await process_payment_gateway_event(session, event_id=event.id)
            assert attempt.outcome == "confirmed_unallocated"
            assert attempt.receipt_id is not None
            assert attempt.allocation_id is None
            assert await session.scalar(select(func.count(PaymentReceipt.id))) == 2
            assert await session.scalar(select(func.count(ReceiptAllocation.id))) == 1
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
    result = asyncio.run(
        process_payment_gateway_event_job({"sessionmaker": db_sessionmaker}, str(event_id))
    )
    assert result["outcome"] == "failed"
    assert result["attempt_number"] == 1

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
