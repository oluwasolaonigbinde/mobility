"""Paystack webhook ingestion through the API test client (SYNTHETIC fixtures only)."""

import asyncio
import json
from uuid import UUID, uuid4

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
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.adapters.disbursement import DisbursementInstruction
from app.adapters.disbursement.paystack import (
    PaystackDisbursementAdapter,
    TransferDestination,
    paystack_transfer_reference,
)
from app.adapters.payments.paystack import PaystackClient, PaystackPaymentGatewayAdapter
from app.api.v1.dependencies import get_payment_event_enqueuer
from app.api.v1.disbursements import get_disbursement_adapter
from app.api.v1.webhooks import get_paystack_payment_adapter
from app.jobs.payment_gateway import sweep_payment_gateway_events
from app.models.billing import PaymentGatewayEvent, PaymentReceipt
from app.models.disbursement import PayoutLineReconciliationEvent, PayoutSubmissionIntent
from app.models.payout import EarningsLedgerEntry
from app.models.user import UserRole
from app.services.disbursements import process_payout_submission_intent

WEBHOOK = "/api/v1/webhooks/paystack"
PROVIDER_WEBHOOK = "/api/v1/admin/payout-batches/provider-webhook"


class RecordingEnqueuer:
    def __init__(self) -> None:
        self.ids = []

    async def enqueue_payment_event(self, event_id) -> None:
        self.ids.append(event_id)


def _count(db_sessionmaker, model, *where) -> int:
    async def run() -> int:
        async with db_sessionmaker() as session:
            query = select(func.count()).select_from(model)
            if where:
                query = query.where(*where)
            return int(await session.scalar(query) or 0)

    return asyncio.run(run())


def _accepted_terms(db_client, db_sessionmaker, suffix: str) -> str:
    admin, owner, _, campaign = _fixture(db_sessionmaker, suffix)
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
    return db_client.post(
        f"/api/v1/advertiser/quotations/{revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    ).json()["id"]


def test_paystack_charge_webhook_records_once_and_converges_to_one_receipt(
    db_client, db_sessionmaker
) -> None:
    terms_id = _accepted_terms(db_client, db_sessionmaker, "paystack-charge")
    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = lambda: enqueuer

    body = payload(charge_success(terms_id=terms_id, amount=10000))
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


def test_paystack_webhook_acknowledges_foreign_events_and_rejects_forgery(
    db_client, db_sessionmaker
) -> None:
    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_paystack_payment_adapter] = lambda: (
        PaystackPaymentGatewayAdapter(PaystackClient(SYNTHETIC_TEST_KEY))
    )
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = lambda: enqueuer
    before = _count(db_sessionmaker, PaymentGatewayEvent)

    for body, event in (
        (charge_success(metadata={"source": "payment-page"}), "charge.success"),
        (transfer_event("transfer.success", reference="cvp_synthetic"), "transfer.success"),
        ({"event": "refund.processed", "data": {"status": "processed"}}, "refund.processed"),
    ):
        raw = payload(body)
        response = db_client.post(WEBHOOK, content=raw, headers={"X-Paystack-Signature": sign(raw)})
        assert response.status_code == 200, response.text
        assert response.json() == {"event": event, "accepted": False, "duplicate": False}

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
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: adapter
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
    return adapter, transport, line, reference, entry_id


def _ledger_status(db_sessionmaker, entry_id) -> str:
    async def run() -> str:
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(EarningsLedgerEntry.status).where(EarningsLedgerEntry.id == entry_id)
            )

    return str(asyncio.run(run()))


def test_paystack_transfer_webhook_reconciles_through_the_provider_webhook_route(
    db_client, db_sessionmaker
) -> None:
    _, transport, line, reference, entry_id = _submitted_paystack_line(
        db_client, db_sessionmaker, "success"
    )
    body = payload(transfer_event("transfer.success", reference=reference))
    signature = {"X-Provider-Signature": sign(body)}
    forged = db_client.post(
        PROVIDER_WEBHOOK, content=body, headers={"X-Provider-Signature": sign(body, "sk_test_x")}
    )
    assert forged.status_code == 401
    first = db_client.post(PROVIDER_WEBHOOK, content=body, headers=signature)
    replay = db_client.post(PROVIDER_WEBHOOK, content=body, headers=signature)
    assert first.status_code == replay.status_code == 200, first.text
    assert first.json()["status"] == "completed"
    assert first.json()["lines"][0]["status"] == "succeeded"
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
        PROVIDER_WEBHOOK, content=unknown, headers={"X-Provider-Signature": sign(unknown)}
    )
    assert missing.status_code == 404


def test_paystack_reversal_then_late_success_never_marks_the_ledger_paid(
    db_client, db_sessionmaker
) -> None:
    _, _, line, reference, entry_id = _submitted_paystack_line(
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
        PROVIDER_WEBHOOK,
        content=reversed_body,
        headers={"X-Provider-Signature": sign(reversed_body)},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    assert reversed_response.json()["lines"][0]["status"] == "failed"
    late = db_client.post(
        PROVIDER_WEBHOOK, content=late_success, headers={"X-Provider-Signature": sign(late_success)}
    )
    assert late.status_code == 200, late.text
    assert late.json()["lines"][0]["status"] == "failed"
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
