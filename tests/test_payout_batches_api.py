import asyncio
from uuid import uuid4

from conftest import auth_headers, create_test_user
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.adapters.disbursement import FakeDisbursementAdapter
from app.api.v1.disbursements import get_disbursement_adapter
from app.models.user import UserRole


def test_admin_batch_api_runs_fake_provider_flow_and_default_fails_closed(
    db_client, db_sessionmaker
) -> None:
    graph = build_graph(db_sessionmaker, f"api-{uuid4().hex[:8]}")
    checker = create_test_user(
        db_sessionmaker,
        email=f"api-checker-{uuid4().hex}@example.com",
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

    created = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=maker_headers,
        json={"currency": "ngn"},
    )
    assert created.status_code == 201
    batch_id = created.json()["id"]
    reserved = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/reserve",
        headers=maker_headers,
        json={"ledger_entry_ids": [str(entry_id)]},
    )
    assert reserved.status_code == 200
    assert reserved.json()["status"] == "reserved"
    assert reserved.json()["total_amount"] == "100.00"

    maker_approval = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/approve", headers=maker_headers
    )
    assert maker_approval.status_code == 403
    approved = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/approve", headers=checker_headers
    )
    assert approved.status_code == 200

    unavailable = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "DISBURSEMENT_PROVIDER_UNAVAILABLE"

    fake = FakeDisbursementAdapter()
    db_client.app.dependency_overrides[get_disbursement_adapter] = lambda: fake
    submitted = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    )
    replayed = db_client.post(
        f"/api/v1/admin/payout-batches/{batch_id}/submit", headers=maker_headers
    )
    assert submitted.status_code == replayed.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == fake.calls[1][1]


def test_payout_batch_api_is_admin_only(db_client, db_sessionmaker) -> None:
    driver = create_test_user(
        db_sessionmaker,
        email=f"batch-api-driver-{uuid4().hex}@example.com",
        role=UserRole.DRIVER,
    )
    denied = db_client.post(
        "/api/v1/admin/payout-batches",
        headers=auth_headers(db_client, driver.email),
        json={"currency": "NGN"},
    )
    assert denied.status_code == 403
