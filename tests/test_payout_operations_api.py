import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.models.audit import AuditEvent
from app.models.disbursement import PayoutBatch, PayoutBatchLine


def test_fully_offset_selection_returns_nothing_to_send_and_no_batch(
    postgis_db_client,
    postgis_db_sessionmaker,
):
    from test_payout_recoveries import seed_debt

    from app.models.disbursement import PayoutRecoveryOffset
    from app.models.payout import EarningsLedgerEntry

    client, db = postgis_db_client, postgis_db_sessionmaker
    graph = build_graph(db, f"offset-api-{uuid4().hex[:8]}")

    async def seed():
        async with db() as session:
            funding, _ = await seed_debt(session, graph, payable="40.00")
            await session.commit()
            return str(funding.id)

    entry_id = asyncio.run(seed())
    headers = auth_headers(client, graph.admin.email)
    request_id = str(uuid4())
    preview = client.post(
        "/api/v1/admin/payout-batches/selection-preview",
        headers=headers,
        json={"currency": "NGN", "ledger_entry_ids": [entry_id]},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["earnings_amount"] == "40.00"
    assert preview.json()["deduction_amount"] == "40.00"
    assert preview.json()["total_amount"] == "0.00"
    for _ in range(2):
        created = client.post(
            "/api/v1/admin/payout-batches",
            headers=headers,
            json={"currency": "NGN", "request_id": request_id, "reason": "Settle next payout"},
        )
        assert created.status_code == 201, created.text
        settled = client.post(
            f"/api/v1/admin/payout-batches/{request_id}/reserve",
            headers=headers,
            json={"ledger_entry_ids": [entry_id], "reason": "Settle next payout"},
        )
        assert settled.status_code == 200, settled.text
        assert settled.json() == {"outcome": "nothing_to_send", "message": "Nothing needs sending."}

    async def check():
        async with db() as session:
            assert await session.get(PayoutBatch, UUID(request_id)) is None
            assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == 1
            credit = await session.get(EarningsLedgerEntry, UUID(entry_id))
            assert credit.status == "paid"
            assert (
                await session.scalar(select(func.count(PayoutBatchLine.id))) == 1
            )  # Original cash only.

    asyncio.run(check())


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
            json={"currency": "NGN", "request_id": request_id, "reason": "Synthetic manual payout"},
        )
        assert created.status_code == 201
        assert created.json()["id"] == request_id
        reserved = client.post(
            f"/api/v1/admin/payout-batches/{request_id}/reserve",
            headers=headers,
            json={"ledger_entry_ids": ids, "reason": "Reserve verified earnings"},
        )
        assert reserved.status_code == 200
    summary = client.get("/api/v1/admin/payout-batches/summaries?limit=1", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total"] == 1
    assert "lines" not in summary.json()["items"][0]
    assert summary.json()["items"][0]["line_count"] == 2
    attention = client.get(
        "/api/v1/admin/payout-batches/summaries?needs_attention=true", headers=headers
    )
    badges = client.get("/api/v1/admin/badge-summary", headers=headers)
    assert badges.status_code == 200
    assert badges.json()["source_counts"]["batches"] == attention.json()["total"] == 1
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


@pytest.mark.parametrize(
    "cash,reserved,in_flight,expected",
    [
        ("100.00", "0", "0", "Already paid"),
        ("0", "100.00", "0", "Already reserved or in flight"),
        ("0", "0", "100.00", "Already reserved or in flight"),
        ("0", "0", "0", "Nothing left to pay"),
    ],
)
def test_zero_payable_reason_distinguishes_paid_from_unpaid(
    db_sessionmaker, monkeypatch, cash, reserved, in_flight, expected
):
    from app.services import payout_operations
    from app.services.payout_balances import TripMoneyPosition

    graph = build_graph(db_sessionmaker, f"zero-label-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)

            async def position(*args, **kwargs):
                return TripMoneyPosition(
                    cash_paid=Decimal(cash),
                    reserved=Decimal(reserved),
                    in_flight=Decimal(in_flight),
                )

            monkeypatch.setattr(payout_operations, "trip_money_position", position)
            result = await payout_operations.eligible_payment_entries(session, limit=25, offset=0)
            row = next(item for item in result["items"] if item["ledger_entry_id"] == entry.id)
            assert row["amount"] == 0
            assert row["eligible"] is False
            assert expected in row["ineligibility_reasons"]
            if expected != "Already paid":
                assert "Already paid" not in row["ineligibility_reasons"]
            if expected == "Already reserved or in flight":
                assert "Nothing left to pay" not in row["ineligibility_reasons"]

    asyncio.run(exercise())
