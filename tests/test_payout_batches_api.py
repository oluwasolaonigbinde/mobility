import asyncio
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


def test_admin_batch_api_runs_fake_provider_flow_and_default_fails_closed(
    db_client, db_sessionmaker
) -> None:
    graph = build_graph(db_sessionmaker, f"api-{uuid4().hex[:8]}")

    async def seed():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            await session.commit()
            return entry.id

    entry_id = asyncio.run(seed())
    maker_headers = auth_headers(db_client, graph.admin.email)

    created = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=maker_headers,
        json={"currency": "ngn", "reason": "Synthetic manual payout"},
    )
    assert created.status_code == 201
    batch_id = created.json()["id"]
    reserved = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/reserve",
        headers=maker_headers,
        json={"ledger_entry_ids": [str(entry_id)], "reason": "Reserve verified earnings"},
    )
    assert reserved.status_code == 200
    assert reserved.json()["status"] == "reserved"
    assert reserved.json()["total_amount"] == "100.00"

    maker_approval = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/approve",
        headers=maker_headers,
        json={"reason": "Synthetic verified payout action"},
    )
    assert maker_approval.status_code == 200
    approved = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/approve",
        headers=maker_headers,
        json={"reason": "Synthetic verified payout action"},
    )
    assert approved.status_code == 200

    unavailable = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit",
        headers=maker_headers,
        json={"reason": "Synthetic verified payout action"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "DISBURSEMENT_PROVIDER_UNAVAILABLE"

    fake = FakeDisbursementAdapter()
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: fake
    submitted = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit",
        headers=maker_headers,
        json={"reason": "Synthetic verified payout action"},
    )
    replayed = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit",
        headers=maker_headers,
        json={"reason": "Synthetic verified payout action"},
    )
    assert submitted.status_code == replayed.status_code == 200
    assert submitted.json()["status"] == "reserved"
    assert fake.calls == []

    async def run_worker():
        async with db_sessionmaker() as session:
            intent_id = await session.scalar(select(PayoutSubmissionIntent.id))
        return await process_payout_submission_intent(
            db_sessionmaker, intent_id=intent_id, adapter=fake
        )

    assert asyncio.run(run_worker()) == "resolved"
    stored = db_client.get(f"/api/v1/admin/payout-batches/{batch_id}", headers=maker_headers)
    assert stored.status_code == 200
    assert stored.json()["status"] == "submitted"
    assert len(fake.calls) == 1


def test_payout_batch_api_is_admin_only(db_client, db_sessionmaker) -> None:
    driver = create_test_user(
        db_sessionmaker,
        email=f"batch-api-driver-{uuid4().hex}@example.com",
        role=UserRole.DRIVER,
    )
    denied = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=auth_headers(db_client, driver.email),
        json={"currency": "NGN", "reason": "Synthetic manual payout"},
    )
    assert denied.status_code == 403
