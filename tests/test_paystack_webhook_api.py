"""Paystack webhook ingestion through the API test client (SYNTHETIC fixtures only)."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_user
from paystack_fixtures import (
    SYNTHETIC_TEST_KEY,
    RecordingTransport,
    charge_success,
    ok,
    payload,
    recipient,
    sign,
    transfer,
    transfer_event,
)
from sqlalchemy import func, select
from test_billing_api import _fixture
from test_invoices import _issuer
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.adapters.disbursement import DisbursementInstruction
from app.adapters.disbursement.paystack import (
    PaystackDisbursementAdapter,
    TransferDestination,
    paystack_transfer_reference,
)
from app.adapters.payments.paystack import PaystackClient, PaystackPaymentGatewayAdapter
from app.api.v1.dependencies import get_payment_event_enqueuer, get_payout_event_enqueuer
from app.api.v1.disbursements import get_disbursement_adapter
from app.api.v1.webhooks import (
    get_paystack_disbursement_adapter,
    get_paystack_payment_adapter,
)
from app.core.errors import AppError
from app.jobs.disbursements import (
    process_payout_provider_event_job,
    sweep_payout_provider_events,
)
from app.jobs.payment_gateway import sweep_payment_gateway_events
from app.models.billing import (
    IssuerVerificationStatus,
    PaymentCheckoutIntent,
    PaymentGatewayEvent,
    PaymentReceipt,
)
from app.models.data_subject_request import DataSubjectRequestType
from app.models.disbursement import (
    PayoutBatchLine,
    PayoutLineReconciliationEvent,
    PayoutProviderEventProcessingAttempt,
    PayoutSubmissionIntent,
)
from app.models.payout import EarningsLedgerEntry
from app.models.user import UserRole
from app.services.billing import create_invoice_draft, issue_invoice
from app.services.data_subject_requests import (
    create_data_subject_request,
    data_subject_inventory,
    verify_data_subject_identity,
)
from app.services.disbursements import process_payout_submission_intent

WEBHOOK = "/api/v1/webhooks/paystack"


class RecordingEnqueuer:
    def __init__(self) -> None:
        self.ids = []
        self.payout_ids = []

    async def enqueue_payment_event(self, event_id) -> None:
        self.ids.append(event_id)

    async def enqueue_payout_event(self, event_id) -> None:
        self.payout_ids.append(event_id)


class FailingEnqueuer:
    async def enqueue_payment_event(self, event_id) -> None:
        raise TimeoutError("synthetic enqueue timeout")

    async def enqueue_payout_event(self, event_id) -> None:
        raise TimeoutError("synthetic enqueue timeout")


def _count(db_sessionmaker, model, *where) -> int:
    async def run() -> int:
        async with db_sessionmaker() as session:
            query = select(func.count()).select_from(model)
            if where:
                query = query.where(*where)
            return int(await session.scalar(query) or 0)

    return asyncio.run(run())


def _accepted_terms(db_client, db_sessionmaker, suffix: str, settings) -> str:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, suffix)
    admin_headers = auth_headers(db_client, admin.email)
    owner_headers = auth_headers(db_client, owner.email)
    request = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/quote-request",
        headers=owner_headers,
        json={"request_details": {}},
    )
    revision = db_client.post(
        f"/api/v1/admin/quote-requests/{request.json()['id']}/revisions",
        headers=admin_headers,
        json={
            "quote_reference": f"PAYSTACK-{suffix}",
            "currency": "NGN",
            "line_items": [
                {"code": "MEDIA", "description": "Media", "kind": "media", "amount": "100.00"}
            ],
            "production_scope": {"vehicle_count": 1},
            "payment_class": "standard_prepaid",
            "payment_terms": {},
            "tax_rate": "0.00",
        },
    )
    terms_id = db_client.post(
        f"/api/v1/advertiser/quotations/{revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    ).json()["id"]

    async def bind_checkout() -> None:
        async with db_sessionmaker() as session:
            draft = await create_invoice_draft(
                session, commercial_terms_id=UUID(terms_id), actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                f"SYNTHETIC-{suffix}",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            session.add(
                PaymentCheckoutIntent(
                    reference="cv-synthetic-checkout-0001",
                    provider="paystack",
                    organization_id=organization.id,
                    commercial_terms_id=UUID(terms_id),
                    invoice_id=invoice.id,
                    requested_by_user_id=owner.id,
                    customer_email=owner.email,
                    amount=invoice.gross_amount,
                    currency=invoice.currency,
                    status="initialized",
                    checkout_url="https://checkout.paystack.test/synthetic",
                    provider_checkout_id="cv-synthetic-checkout-0001",
                    failure_code=None,
                    created_at=datetime.now(UTC),
                    initialized_at=datetime.now(UTC),
                    verified_at=None,
                )
            )
            await session.commit()

    asyncio.run(bind_checkout())
    return terms_id, str(organization.id)


def test_paystack_charge_webhook_records_once_and_converges_to_one_receipt(
    db_client, db_sessionmaker, settings
) -> None:
    terms_id, organization_id = _accepted_terms(
        db_client, db_sessionmaker, "paystack-charge", settings
    )
    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_paystack_disbursement_adapter] = lambda: (
        PaystackDisbursementAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = lambda: enqueuer
    db_client.app.dependency_overrides[get_payout_event_enqueuer] = lambda: enqueuer

    body = payload(
        charge_success(
            terms_id=terms_id,
            organization_id=organization_id,
            amount=10000,
        )
    )
    reserialized = json.dumps(json.loads(body), indent=2).encode()
    first = db_client.post(WEBHOOK, content=body, headers={"X-Paystack-Signature": sign(body)})
    replay = db_client.post(WEBHOOK, content=body, headers={"X-Paystack-Signature": sign(body)})
    resent = db_client.post(
        WEBHOOK, content=reserialized, headers={"X-Paystack-Signature": sign(reserialized)}
    )
    assert [r.status_code for r in (first, replay, resent)] == [200, 200, 200], first.text
    assert first.json() == {"event": "charge.success", "accepted": True, "duplicate": False}
    assert replay.json()["duplicate"] is True
    assert resent.json()["duplicate"] is True
    assert len(enqueuer.ids) == 3 and len(set(enqueuer.ids)) == 1

    async def stored_event() -> PaymentGatewayEvent:
        async with db_sessionmaker() as session:
            return await session.scalar(select(PaymentGatewayEvent))

    event = asyncio.run(stored_event())
    assert (event.provider, event.event_type, event.currency) == (
        "paystack",
        "payment_confirmed",
        "NGN",
    )
    assert str(event.amount) == "100.00"
    assert event.commercial_terms_reference == terms_id
    assert _count(db_sessionmaker, PaymentGatewayEvent) == 1

    result = asyncio.run(sweep_payment_gateway_events({"sessionmaker": db_sessionmaker}))
    assert result == {"selected": 1, "processed": 1, "failed": 0}
    assert (
        asyncio.run(sweep_payment_gateway_events({"sessionmaker": db_sessionmaker}))["selected"]
        == 0
    )
    assert _count(db_sessionmaker, PaymentReceipt, PaymentReceipt.provider == "paystack") == 1


def test_committed_payment_event_survives_request_path_enqueue_failure(
    db_client, db_sessionmaker, settings
) -> None:
    terms_id, organization_id = _accepted_terms(
        db_client, db_sessionmaker, "paystack-enqueue-recovery", settings
    )
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_paystack_disbursement_adapter] = lambda: (
        PaystackDisbursementAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = FailingEnqueuer
    db_client.app.dependency_overrides[get_payout_event_enqueuer] = FailingEnqueuer
    body = payload(
        charge_success(
            terms_id=terms_id,
            organization_id=organization_id,
            amount=10000,
        )
    )

    with pytest.raises(TimeoutError, match="enqueue timeout"):
        db_client.post(WEBHOOK, content=body, headers={"X-Paystack-Signature": sign(body)})

    assert _count(db_sessionmaker, PaymentGatewayEvent) == 1
    assert _count(db_sessionmaker, PaymentReceipt) == 0
    assert asyncio.run(sweep_payment_gateway_events({"sessionmaker": db_sessionmaker})) == {
        "selected": 1,
        "processed": 1,
        "failed": 0,
    }
    assert _count(db_sessionmaker, PaymentReceipt, PaymentReceipt.provider == "paystack") == 1


def test_paystack_webhook_acknowledges_foreign_events_and_rejects_forgery(
    db_client, db_sessionmaker
) -> None:
    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_paystack_disbursement_adapter] = lambda: (
        PaystackDisbursementAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = lambda: enqueuer
    db_client.app.dependency_overrides[get_payout_event_enqueuer] = lambda: enqueuer
    before = _count(db_sessionmaker, PaymentGatewayEvent)

    for body, event, accepted in (
        (charge_success(metadata={"source": "payment-page"}), "charge.success", False),
        (transfer_event("transfer.success", reference="cvp_synthetic"), "transfer.success", True),
        (
            {"event": "refund.processed", "data": {"status": "processed"}},
            "refund.processed",
            False,
        ),
    ):
        raw = payload(body)
        response = db_client.post(WEBHOOK, content=raw, headers={"X-Paystack-Signature": sign(raw)})
        assert response.status_code == 200, response.text
        assert response.json() == {
            "event": event,
            "accepted": accepted,
            "duplicate": False,
        }

    good = payload(charge_success())
    rejected = {
        "forged": db_client.post(
            WEBHOOK, content=good, headers={"X-Paystack-Signature": "0" * 128}
        ),
        "other-secret": db_client.post(
            WEBHOOK,
            content=good,
            headers={"X-Paystack-Signature": sign(good, "sk_test_someone_else")},
        ),
        "missing": db_client.post(WEBHOOK, content=good),
        "blank": db_client.post(WEBHOOK, content=good, headers={"X-Paystack-Signature": " "}),
    }
    assert {name: r.status_code for name, r in rejected.items()} == {
        "forged": 401,
        "other-secret": 401,
        "missing": 401,
        "blank": 401,
    }
    malformed = b"{not json"
    live_domain = payload(charge_success(domain="live"))
    for raw in (malformed, live_domain):
        response = db_client.post(WEBHOOK, content=raw, headers={"X-Paystack-Signature": sign(raw)})
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "INVALID_PAYMENT_WEBHOOK_PAYLOAD"
    assert _count(db_sessionmaker, PaymentGatewayEvent) == before
    assert enqueuer.ids == []


def test_paystack_webhook_is_disabled_without_a_key(db_client, settings) -> None:
    assert settings.paystack_secret_key is None
    raw = payload(charge_success())
    disabled = db_client.post(WEBHOOK, content=raw, headers={"X-Paystack-Signature": sign(raw)})
    assert disabled.status_code == 503
    assert disabled.json()["error"]["code"] == "PAYMENT_PROVIDER_NOT_CONFIGURED"
    assert db_client.post(WEBHOOK, content=raw).status_code == 401


def _submitted_paystack_line(db_client, db_sessionmaker, suffix: str):
    graph = build_graph(db_sessionmaker, f"paystack-{suffix}-{uuid4().hex[:8]}")
    checker = create_test_user(
        db_sessionmaker,
        email=f"paystack-checker-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )

    async def seed():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            await session.commit()
            return entry.id

    entry_id = asyncio.run(seed())
    maker_headers = auth_headers(db_client, graph.admin.email)
    resolved: list[DisbursementInstruction] = []

    async def resolver(item: DisbursementInstruction) -> TransferDestination:
        resolved.append(item)
        return TransferDestination(
            account_name="Synthetic Driver", account_number="0000000001", bank_code="999"
        )

    transport = RecordingTransport()
    adapter = PaystackDisbursementAdapter(
        PaystackClient(SYNTHETIC_TEST_KEY, transport=transport), destination_resolver=resolver
    )
    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: adapter
    db_client.app.dependency_overrides[get_paystack_disbursement_adapter] = lambda: adapter
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payout_event_enqueuer] = lambda: enqueuer
    batch_id = db_client.post(
        "/api/v1/admin/payout-batches", headers=maker_headers, json={"currency": "NGN"}
    ).json()["id"]
    db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/reserve",
        headers=maker_headers,
        json={"ledger_entry_ids": [str(entry_id)]},
    )
    db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/approve",
        headers=auth_headers(db_client, checker.email),
    )
    queued = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    )
    assert queued.status_code == 200, queued.text

    async def intent():
        async with db_sessionmaker() as session:
            return await session.scalar(select(PayoutSubmissionIntent))

    submission = asyncio.run(intent())
    reference = paystack_transfer_reference(submission.idempotency_key)
    transport.queue(ok(recipient()), ok(transfer(reference=reference)))
    assert (
        asyncio.run(
            process_payout_submission_intent(
                db_sessionmaker, intent_id=submission.id, adapter=adapter
            )
        )
        == "resolved"
    )
    line = db_client.get(f"/api/v1/admin/payout-batches/{batch_id}", headers=maker_headers).json()[
        "lines"
    ][0]
    assert line["status"] == "submitted"
    assert line["provider_transfer_reference"] == "TRF_synthetic0001"
    assert [item.instruction for item in resolved] == [submission.instruction]
    return adapter, transport, line, reference, entry_id, enqueuer


def _ledger_status(db_sessionmaker, entry_id) -> str:
    async def run() -> str:
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(EarningsLedgerEntry.status).where(EarningsLedgerEntry.id == entry_id)
            )

    return str(asyncio.run(run()))


def test_paystack_transfer_webhook_queues_before_reconciliation(
    db_client, db_sessionmaker
) -> None:
    _, transport, line, reference, entry_id, enqueuer = _submitted_paystack_line(
        db_client, db_sessionmaker, "success"
    )
    body = payload(transfer_event("transfer.success", reference=reference))
    signature = {"X-Paystack-Signature": sign(body)}
    forged = db_client.post(
        WEBHOOK, content=body, headers={"X-Paystack-Signature": sign(body, "sk_test_x")}
    )
    assert forged.status_code == 401
    first = db_client.post(WEBHOOK, content=body, headers=signature)
    replay = db_client.post(WEBHOOK, content=body, headers=signature)
    assert first.status_code == replay.status_code == 200, first.text
    assert first.json() == {
        "event": "transfer.success",
        "accepted": True,
        "duplicate": False,
    }
    assert replay.json()["duplicate"] is True
    assert len(set(enqueuer.payout_ids)) == 1
    assert "paid" not in _ledger_status(db_sessionmaker, entry_id).lower()
    assert _count(db_sessionmaker, PayoutLineReconciliationEvent) == 0

    processed = asyncio.run(
        process_payout_provider_event_job(
            {"sessionmaker": db_sessionmaker}, str(enqueuer.payout_ids[0])
        )
    )
    assert processed["outcome"] == "processed"
    assert "paid" in _ledger_status(db_sessionmaker, entry_id).lower()
    events = _count(
        db_sessionmaker,
        PayoutLineReconciliationEvent,
        PayoutLineReconciliationEvent.line_id == UUID(line["id"]),
    )
    assert events == 1

    reconciler = create_test_user(
        db_sessionmaker,
        email=f"paystack-reconciler-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    transport.queue(ok(transfer(reference=reference, status="success")))
    polled = db_client.post(
        f"/api/v1/admin/payout-batches/lines/{line['id']}/poll",
        headers=auth_headers(db_client, reconciler.email),
    )
    assert polled.status_code == 200, polled.text
    assert (
        _count(
            db_sessionmaker,
            PayoutLineReconciliationEvent,
            PayoutLineReconciliationEvent.line_id == UUID(line["id"]),
        )
        == 1
    )

    unknown = payload(
        transfer_event("transfer.success", reference="cvp_unknown", transfer_code="TRF_unknown")
    )
    missing = db_client.post(
        WEBHOOK, content=unknown, headers={"X-Paystack-Signature": sign(unknown)}
    )
    assert missing.status_code == 200
    unknown_event_id = enqueuer.payout_ids[-1]
    try:
        asyncio.run(
            process_payout_provider_event_job(
                {"sessionmaker": db_sessionmaker}, str(unknown_event_id)
            )
        )
    except Exception:
        pass
    assert _count(
        db_sessionmaker,
        PayoutProviderEventProcessingAttempt,
        PayoutProviderEventProcessingAttempt.provider_event_id == unknown_event_id,
        PayoutProviderEventProcessingAttempt.outcome == "failed",
    ) == 1
    assert asyncio.run(sweep_payout_provider_events({"sessionmaker": db_sessionmaker})) == {
        "selected": 1,
        "processed": 0,
        "failed": 1,
    }
    assert asyncio.run(sweep_payout_provider_events({"sessionmaker": db_sessionmaker})) == {
        "selected": 1,
        "processed": 0,
        "failed": 1,
    }
    assert asyncio.run(sweep_payout_provider_events({"sessionmaker": db_sessionmaker})) == {
        "selected": 0,
        "processed": 0,
        "failed": 0,
    }


def test_paystack_reversal_then_late_success_never_marks_the_ledger_paid(
    db_client, db_sessionmaker
) -> None:
    _, _, line, reference, entry_id, enqueuer = _submitted_paystack_line(
        db_client, db_sessionmaker, "reversed"
    )
    reversed_body = payload(
        transfer_event(
            "transfer.reversed", reference=reference, updated_at="2026-09-26T12:00:00.000Z"
        )
    )
    late_success = payload(
        transfer_event(
            "transfer.success", reference=reference, updated_at="2026-09-26T11:00:00.000Z"
        )
    )
    reversed_response = db_client.post(
        WEBHOOK,
        content=reversed_body,
        headers={"X-Paystack-Signature": sign(reversed_body)},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    late = db_client.post(
        WEBHOOK,
        content=late_success,
        headers={"X-Paystack-Signature": sign(late_success)},
    )
    assert late.status_code == 200, late.text
    for event_id in enqueuer.payout_ids:
        asyncio.run(
            process_payout_provider_event_job(
                {"sessionmaker": db_sessionmaker}, str(event_id)
            )
        )
    assert "paid" not in _ledger_status(db_sessionmaker, entry_id).lower()

    async def applied_flags() -> list[bool]:
        async with db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(PayoutLineReconciliationEvent.applied)
                    .where(PayoutLineReconciliationEvent.line_id == UUID(line["id"]))
                    .order_by(PayoutLineReconciliationEvent.provider_occurred_at.desc())
                )
            )

    assert asyncio.run(applied_flags()) == [True, False]


def test_paystack_newer_reversal_after_success_makes_earnings_available_again(
    db_client, db_sessionmaker
) -> None:
    _, _, line, reference, entry_id, enqueuer = _submitted_paystack_line(
        db_client, db_sessionmaker, "success-then-reversed"
    )
    success = payload(
        transfer_event(
            "transfer.success", reference=reference, updated_at="2026-09-26T11:00:00.000Z"
        )
    )
    reversed_body = payload(
        transfer_event(
            "transfer.reversed", reference=reference, updated_at="2026-09-26T12:00:00.000Z"
        )
    )
    for body in (success, reversed_body):
        response = db_client.post(
            WEBHOOK,
            content=body,
            headers={"X-Paystack-Signature": sign(body)},
        )
        assert response.status_code == 200, response.text
        asyncio.run(
            process_payout_provider_event_job(
                {"sessionmaker": db_sessionmaker}, str(enqueuer.payout_ids[-1])
            )
        )

    assert "available" in _ledger_status(db_sessionmaker, entry_id).lower()

    async def state() -> tuple[str, list[bool]]:
        async with db_sessionmaker() as session:
            line_status = await session.scalar(
                select(PayoutBatchLine.status).where(PayoutBatchLine.id == UUID(line["id"]))
            )
            applied = list(
                await session.scalars(
                    select(PayoutLineReconciliationEvent.applied)
                    .where(PayoutLineReconciliationEvent.line_id == UUID(line["id"]))
                    .order_by(PayoutLineReconciliationEvent.provider_occurred_at)
                )
            )
            return str(line_status), applied

    assert asyncio.run(state()) == ("failed", [True, True])


def test_paystack_transfer_evidence_must_match_the_frozen_amount(
    db_client, db_sessionmaker
) -> None:
    _, _, _, reference, entry_id, enqueuer = _submitted_paystack_line(
        db_client, db_sessionmaker, "amount-mismatch"
    )
    body = payload(transfer_event("transfer.success", reference=reference, amount=9999))
    response = db_client.post(
        WEBHOOK,
        content=body,
        headers={"X-Paystack-Signature": sign(body)},
    )
    assert response.status_code == 200, response.text
    event_id = enqueuer.payout_ids[-1]
    with pytest.raises(AppError) as rejected:
        asyncio.run(
            process_payout_provider_event_job(
                {"sessionmaker": db_sessionmaker}, str(event_id)
            )
        )
    assert rejected.value.code == "PAYOUT_PROVIDER_EVIDENCE_MISMATCH"
    assert "paid" not in _ledger_status(db_sessionmaker, entry_id).lower()


def test_provider_events_and_failed_attempts_are_in_driver_inventory(
    db_client, db_sessionmaker
) -> None:
    _, _, _, reference, entry_id, enqueuer = _submitted_paystack_line(
        db_client, db_sessionmaker, "dsr-provider-events"
    )
    success = payload(transfer_event("transfer.success", reference=reference))
    response = db_client.post(
        WEBHOOK, content=success, headers={"X-Paystack-Signature": sign(success)}
    )
    assert response.status_code == 200, response.text
    asyncio.run(
        process_payout_provider_event_job(
            {"sessionmaker": db_sessionmaker}, str(enqueuer.payout_ids[-1])
        )
    )

    mismatch = payload(
        transfer_event("transfer.failed", reference=reference, amount=9999)
    )
    response = db_client.post(
        WEBHOOK, content=mismatch, headers={"X-Paystack-Signature": sign(mismatch)}
    )
    assert response.status_code == 200, response.text
    with pytest.raises(AppError):
        asyncio.run(
            process_payout_provider_event_job(
                {"sessionmaker": db_sessionmaker}, str(enqueuer.payout_ids[-1])
            )
        )

    admin = create_test_user(
        db_sessionmaker,
        email=f"paystack-dsr-admin-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )

    async def inventory() -> int:
        async with db_sessionmaker() as session:
            subject_user_id = await session.scalar(
                select(EarningsLedgerEntry.driver_user_id).where(
                    EarningsLedgerEntry.id == entry_id
                )
            )
            assert subject_user_id is not None
            case = await create_data_subject_request(
                session,
                actor_user_id=admin.id,
                subject_user_id=subject_user_id,
                request_type=DataSubjectRequestType.ACCESS,
                client_request_id=uuid4(),
                requested_at=datetime.now(UTC),
            )
            await verify_data_subject_identity(
                session, actor_user_id=admin.id, request_id=case.id
            )
            result = await data_subject_inventory(
                session, actor_user_id=admin.id, request_id=case.id
            )
            return result["database"]["payout_provider_processing_evidence"]

    assert asyncio.run(inventory()) == 4
