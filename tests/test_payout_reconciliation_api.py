import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from conftest import auth_headers, create_test_user
from sqlalchemy import select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.adapters.disbursement import FakeDisbursementAdapter
from app.api.v1.disbursements import get_disbursement_adapter
from app.models.disbursement import PayoutSubmissionIntent
from app.models.user import UserRole
from app.services.disbursements import process_payout_submission_intent


async def _run_submission_worker(db_sessionmaker, fake) -> None:
    async with db_sessionmaker() as session:
        intent_id = await session.scalar(select(PayoutSubmissionIntent.id))
    assert (
        await process_payout_submission_intent(
            db_sessionmaker, intent_id=intent_id, adapter=fake
        )
        == "resolved"
    )


def test_reconciliation_api_enforces_separation_and_verified_line_finality(
    db_client, db_sessionmaker
) -> None:
    graph = build_graph(db_sessionmaker, f"reconcile-api-{uuid4().hex[:8]}")
    checker = create_test_user(
        db_sessionmaker,
        email=f"reconcile-api-checker-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    reconciler = create_test_user(
        db_sessionmaker,
        email=f"reconcile-api-worker-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )

    async def seed():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            await session.commit()
            return entry.id

    entry_id = asyncio.run(seed())
    maker_headers = auth_headers(db_client, graph.admin.email)
    checker_headers = auth_headers(db_client, checker.email)
    reconciler_headers = auth_headers(db_client, reconciler.email)
    fake = FakeDisbursementAdapter()
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: fake

    batch_id = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=maker_headers,
        json={"currency": "NGN"},
    ).json()["id"]
    reserved = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/reserve",
        headers=maker_headers,
        json={"ledger_entry_ids": [str(entry_id)]},
    )
    assert reserved.status_code == 200
    assert (
        db_client.post(
            f"/api/v1/admin/payout-batches/{batch_id}/approve",
            headers=checker_headers,
        ).status_code
        == 200
    )
    submitted = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    )
    assert submitted.status_code == 200
    assert submitted.json()["lines"][0]["status"] == "reserved"
    assert fake.calls == []
    asyncio.run(_run_submission_worker(db_sessionmaker, fake))
    line = db_client.get(
        f"/api/v1/admin/payout-batches/{batch_id}", headers=maker_headers
    ).json()["lines"][0]
    assert line["status"] == "submitted"
    fake.set_poll_result(
        provider_transfer_reference=line["provider_transfer_reference"],
        provider_event_id="api-poll-success",
        outcome="succeeded",
        occurred_at=datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    maker_poll = db_client.post(
        f"/api/v1/admin/payout-batches/lines/{line['id']}/poll", headers=maker_headers
    )
    assert maker_poll.status_code == 403
    reconciled = db_client.post(
        f"/api/v1/admin/payout-batches/lines/{line['id']}/poll",
        headers=reconciler_headers,
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "completed"
    assert reconciled.json()["lines"][0]["status"] == "succeeded"
    earnings = db_client.get(
        "/api/v1/driver/earnings/summary",
        headers=auth_headers(db_client, graph.driver.email),
    )
    assert earnings.status_code == 200
    totals = earnings.json()["totals_by_currency"][0]
    assert totals["available_amount"] == "0.00"
    assert totals["paid_amount"] == "100.00"
    assert totals["lifetime_earned_amount"] == "100.00"


def test_webhook_api_rejects_forgery_and_accepts_signed_fake_evidence(
    db_client, db_sessionmaker
) -> None:
    graph = build_graph(db_sessionmaker, f"webhook-api-{uuid4().hex[:8]}")
    checker = create_test_user(
        db_sessionmaker,
        email=f"webhook-api-checker-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )

    async def seed():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            await session.commit()
            return entry.id

    entry_id = asyncio.run(seed())
    maker_headers = auth_headers(db_client, graph.admin.email)
    checker_headers = auth_headers(db_client, checker.email)
    fake = FakeDisbursementAdapter()
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: fake
    batch_id = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=maker_headers,
        json={"currency": "NGN"},
    ).json()["id"]
    db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/reserve",
        headers=maker_headers,
        json={"ledger_entry_ids": [str(entry_id)]},
    )
    db_client.post(f"/api/v1/admin/payout-batches/{batch_id}/approve", headers=checker_headers)
    queued_line = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    ).json()["lines"][0]
    assert queued_line["status"] == "reserved"
    asyncio.run(_run_submission_worker(db_sessionmaker, fake))
    line = db_client.get(
        f"/api/v1/admin/payout-batches/{batch_id}", headers=maker_headers
    ).json()["lines"][0]
    payload = json.dumps(
        {
            "provider_transfer_reference": line["provider_transfer_reference"],
            "provider_event_id": "api-webhook-success",
            "outcome": "succeeded",
            "occurred_at": "2026-08-23T12:30:00+00:00",
        },
        sort_keys=True,
    ).encode()
    forged = db_client.post(
        "/api/v1/admin/payout-batches/provider-webhook",
        content=payload,
        headers={"X-Provider-Signature": "forged"},
    )
    assert forged.status_code == 401
    accepted = db_client.post(
        "/api/v1/admin/payout-batches/provider-webhook",
        content=payload,
        headers={"X-Provider-Signature": fake.sign_webhook(payload)},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "completed"
