import asyncio
from uuid import uuid4

from conftest import auth_headers
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.models.audit import AuditEvent
from app.models.disbursement import PayoutBatch, PayoutBatchLine


def test_payout_projection_routes_are_exact_bounded_and_read_only(
    postgis_db_client, postgis_db_sessionmaker
):
    client, sessions = postgis_db_client, postgis_db_sessionmaker
    graph = build_graph(sessions, f"operations-api-{uuid4().hex[:8]}")

    async def seed():
        async with sessions() as session:
            first = await _seed_authority(session, graph, amount="100.07")
            second = await _seed_authority(session, graph, amount="25.03")
            await session.commit()
            return str(first.id), str(second.id)

    async def counts():
        async with sessions() as session:
            return tuple(
                [
                    await session.scalar(select(func.count(model.id)))
                    for model in (AuditEvent, PayoutBatch, PayoutBatchLine)
                ]
            )

    ids = asyncio.run(seed())
    headers = auth_headers(client, graph.admin.email)
    before = asyncio.run(counts())
    eligible = client.get("/api/v1/admin/payout-batches/eligible?limit=1", headers=headers)
    assert eligible.status_code == 200
    assert eligible.json()["total"] == 2
    assert len(eligible.json()["items"]) == 1
    assert eligible.json()["items"][0]["driver_name"] == graph.driver.full_name
    assert isinstance(eligible.json()["items"][0]["amount"], str)
    assert "account_number" not in eligible.text and "0123456789" not in eligible.text
    preview = client.post(
        "/api/v1/admin/payout-batches/selection-preview",
        headers=headers,
        json={"currency": "NGN", "ledger_entry_ids": ids},
    )
    assert preview.status_code == 200
    assert preview.json()["total_amount"] == "125.10"
    assert preview.json()["currency"] == "NGN"
    assert asyncio.run(counts()) == before
    assert (
        client.get("/api/v1/admin/payout-batches/eligible?limit=101", headers=headers).status_code
        == 422
    )
    assert (
        client.get("/api/v1/admin/payout-batches/summaries?offset=-1", headers=headers).status_code
        == 422
    )

    request_id = str(uuid4())
    for _ in range(2):
        created = client.post(
            "/api/v1/admin/payout-batches",
            headers=headers,
            json={"currency": "NGN", "request_id": request_id},
        )
        assert created.status_code == 201
        assert created.json()["id"] == request_id
        reserved = client.post(
            f"/api/v1/admin/payout-batches/{request_id}/reserve",
            headers=headers,
            json={"ledger_entry_ids": ids},
        )
        assert reserved.status_code == 200
    summary = client.get("/api/v1/admin/payout-batches/summaries?limit=1", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert "lines" not in summary.json()["items"][0]
    assert summary.json()["items"][0]["line_count"] == 2
    detail = client.get(
        f"/api/v1/admin/payout-batches/{request_id}/detail?limit=1", headers=headers
    )
    assert detail.status_code == 200
    assert detail.json()["total"] == 2 and len(detail.json()["lines"]) == 1
    assert detail.json()["summary"]["total_amount"] == "125.10"
    line_id = detail.json()["lines"][0]["id"]
    history = client.get(f"/api/v1/admin/payout-batches/lines/{line_id}/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"] == []
    assert history.json()["latest_submission_outcome"] is None
    position = client.get(
        f"/api/v1/admin/payout-batches/campaigns/{graph.campaign.id}/position", headers=headers
    )
    assert position.status_code == 200
    assert position.json()["items"][0]["reserved"] == "125.10"
    assert position.json()["items"][0]["cash_paid"] == "0.00"
    assert position.json()["items"][0]["provider_verified_paid"] == "0.00"
    assert position.json()["external_blockers"]

    driver_headers = auth_headers(client, graph.driver.email)
    for path in (
        "/eligible",
        "/summaries",
        f"/{request_id}/detail",
        f"/lines/{line_id}/history",
        f"/campaigns/{graph.campaign.id}/position",
    ):
        assert (
            client.get(f"/api/v1/admin/payout-batches{path}", headers=driver_headers).status_code
            == 403
        )
    assert (
        client.post(
            "/api/v1/admin/payout-batches/selection-preview",
            headers=driver_headers,
            json={"currency": "NGN", "ledger_entry_ids": ids},
        ).status_code
        == 403
    )
