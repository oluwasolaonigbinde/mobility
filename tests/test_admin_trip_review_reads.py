import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from authorization_matrix import _dependency_names
from conftest import (
    auth_headers,
    create_test_user,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
)
from sqlalchemy import select
from test_admin_hub_reads import bearer
from test_fraud_assessments import create_flag
from test_fraud_holds import build_review_graph
from test_mny03a_earnings_release import create_ledger
from test_trip_analytics import add_pings

from app.api.v1.trip_analytics import router
from app.models.payout import EarningsLedgerEntry
from app.models.trip import LocationPing, LocationPingBatch, QuarantinedPingBatch
from app.models.trip_analytics import FraudFlag
from app.models.user import UserRole, UserStatus
from app.services.admin_trip_review import read_held_trip_pay
from app.services.trips import point_value

PASSWORD = "long-secure-password"
NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)
ROUTE = "/api/v1/admin/fraud-flags/{flag_id}/route"


@pytest.fixture
def db_sessionmaker(postgis_db_sessionmaker):
    return postgis_db_sessionmaker


def test_held_money_is_trip_level_pending_net_without_writes(db_client, db_sessionmaker):
    graph = build_review_graph(db_sessionmaker, "held-read")
    first = create_flag(db_sessionmaker, graph)
    second = create_flag(db_sessionmaker, graph, flag_type="poor_accuracy")
    create_ledger(db_sessionmaker, graph, amount="100.00")
    create_ledger(db_sessionmaker, graph, status="available", amount="50.00")
    create_ledger(db_sessionmaker, graph, status="paid", amount="40.00")
    reversal = create_ledger(db_sessionmaker, graph, amount="20.00")

    async def reverse():
        async with db_sessionmaker() as session:
            entry = await session.get(EarningsLedgerEntry, reversal.id)
            entry.entry_type = "reversal"
            await session.commit()

    asyncio.run(reverse())
    before = [
        (entry.id, entry.status, entry.amount)
        for entry in fetch_earnings_ledger_entries(db_sessionmaker)
    ]
    audit_before = len(fetch_audit_events(db_sessionmaker))
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    response = db_client.get(
        "/api/v1/admin/fraud-flags", headers=headers, params={"trip_session_id": str(graph.trip.id)}
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    for item in response.json()["items"]:
        assert Decimal(item["money_effect"]["held_pending_net"]) == Decimal("80.00")
        assert item["money_effect"]["held_currency"] == "NGN"
        assert Decimal(item["money_effect"]["available_net"]) == Decimal("90.00")
    assert [
        (entry.id, entry.status, entry.amount)
        for entry in fetch_earnings_ledger_entries(db_sessionmaker)
    ] == before
    assert len(fetch_audit_events(db_sessionmaker)) == audit_before

    async def dismiss(flag_id):
        async with db_sessionmaker() as session:
            flag = await session.get(FraudFlag, flag_id)
            flag.status = "dismissed"
            flag.reviewed_by_user_id = graph.admin.id
            flag.reviewed_at = NOW
            flag.resolution_note = "Review cleared"
            await session.commit()

    asyncio.run(dismiss(first.id))

    async def held():
        async with db_sessionmaker() as session:
            return await read_held_trip_pay(session, trip_id=graph.trip.id)

    assert asyncio.run(held()).amount == Decimal("80.00")
    asyncio.run(dismiss(second.id))
    result = asyncio.run(held())
    assert result.amount == 0 and result.currency is None


def test_mixed_pending_currencies_fail_closed(db_sessionmaker):
    graph = build_review_graph(db_sessionmaker, "held-currencies")
    create_flag(db_sessionmaker, graph)
    create_ledger(db_sessionmaker, graph)
    other = create_ledger(db_sessionmaker, graph)

    async def read():
        async with db_sessionmaker() as session:
            entry = await session.get(EarningsLedgerEntry, other.id)
            entry.currency = "USD"
            await session.commit()
            return await read_held_trip_pay(session, trip_id=graph.trip.id)

    with pytest.raises(RuntimeError, match="multiple currencies"):
        asyncio.run(read())


def test_route_is_paged_ordered_trip_bound_and_audited(db_client, db_sessionmaker):
    graph = build_review_graph(db_sessionmaker, "route-read")
    other = build_review_graph(db_sessionmaker, "route-other")
    flag = create_flag(db_sessionmaker, graph)
    add_pings(
        db_sessionmaker,
        trip_id=graph.trip.id,
        points=[(NOW, 9.0 + i / 1000, 7.0, 5.0) for i in range(5)],
    )
    add_pings(db_sessionmaker, trip_id=other.trip.id, points=[(NOW, 50.0, 30.0, 5.0)])

    async def corrupt_and_order():
        async with db_sessionmaker() as session:
            other_batch = await session.scalar(
                select(LocationPingBatch).where(LocationPingBatch.trip_session_id == other.trip.id)
            )
            session.add(
                LocationPing(
                    trip_session_id=graph.trip.id,
                    batch_id=other_batch.id,
                    recorded_at=NOW,
                    received_at=NOW,
                    latitude=80.0,
                    longitude=60.0,
                    geom=point_value(session, lon=60.0, lat=80.0),
                )
            )
            session.add(
                QuarantinedPingBatch(
                    trip_session_id=graph.trip.id,
                    idempotency_key="not-applied",
                    payload_hash="a" * 64,
                    payload={"pings": [{"latitude": 75, "longitude": 55}]},
                    ping_count=1,
                    received_at=NOW,
                )
            )
            await session.commit()
            return list(
                (
                    await session.scalars(
                        select(LocationPing.id)
                        .where(
                            LocationPing.trip_session_id == graph.trip.id,
                            LocationPing.batch_id != other_batch.id,
                        )
                        .order_by(LocationPing.recorded_at, LocationPing.id)
                    )
                ).all()
            )

    expected = asyncio.run(corrupt_and_order())
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    path = ROUTE.format(flag_id=flag.id)
    first = db_client.get(path, headers=headers, params={"limit": 2})
    last = db_client.get(path, headers=headers, params={"limit": 2, "offset": 4})
    assert first.status_code == last.status_code == 200
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json()["total"] == last.json()["total"] == 5
    assert first.json()["flag_id"] == str(flag.id)
    assert first.json()["trip_session_id"] == str(graph.trip.id)
    assert [point["id"] for point in first.json()["items"]] == [str(i) for i in expected[:2]]
    assert [point["id"] for point in last.json()["items"]] == [str(expected[-1])]
    assert all(point["latitude"] < 10 for point in first.json()["items"])
    events = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.fraud_review.route_read"
    ]
    assert len(events) == 2
    assert all(
        event.actor_user_id == graph.admin.id and event.entity_id == str(flag.id)
        for event in events
    )
    assert all(
        "latitude" not in str(event.event_metadata) and "longitude" not in str(event.event_metadata)
        for event in events
    )
    for query in ({"limit": 0}, {"limit": 1001}, {"offset": -1}):
        assert db_client.get(path, headers=headers, params=query).status_code == 422
    assert db_client.get(ROUTE.format(flag_id=uuid4()), headers=headers).status_code == 404
    route = next(r for r in router.routes if r.path == ROUTE.removeprefix("/api/v1"))
    assert "require_admin_user" in _dependency_names(route)


@pytest.mark.parametrize(
    "role,state",
    [
        (UserRole.DRIVER, UserStatus.ACTIVE),
        (UserRole.ADVERTISER, UserStatus.ACTIVE),
        (UserRole.ADMIN, UserStatus.DISABLED),
    ],
)
def test_route_and_held_reads_deny_nonstaff(db_client, db_sessionmaker, settings, role, state):
    user = create_test_user(
        db_sessionmaker, email="trip-read-denied@example.com", role=role, user_status=state
    )
    for path in [ROUTE.format(flag_id=uuid4()), "/api/v1/admin/fraud-flags"]:
        assert db_client.get(path, headers=bearer(user, settings)).status_code == 403
        assert db_client.get(path).status_code == 401
    assert not [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.fraud_review.route_read"
    ]


def test_route_audit_failure_never_returns_coordinates(db_client, db_sessionmaker, monkeypatch):
    graph = build_review_graph(db_sessionmaker, "route-audit-failure")
    flag = create_flag(db_sessionmaker, graph)
    add_pings(db_sessionmaker, trip_id=graph.trip.id, points=[(NOW, 9.0, 7.0, 5.0)])

    async def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("app.api.v1.trip_analytics.create_audit_event", fail)
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        db_client.get(ROUTE.format(flag_id=flag.id), headers=headers)


def test_route_commit_failure_never_returns_coordinates(db_client, db_sessionmaker, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    graph = build_review_graph(db_sessionmaker, "route-commit-failure")
    flag = create_flag(db_sessionmaker, graph)
    add_pings(db_sessionmaker, trip_id=graph.trip.id, points=[(NOW, 9.0, 7.0, 5.0)])
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)

    async def fail(*args, **kwargs):
        raise RuntimeError("audit commit unavailable")

    monkeypatch.setattr(AsyncSession, "commit", fail)
    with pytest.raises(RuntimeError, match="audit commit unavailable"):
        db_client.get(ROUTE.format(flag_id=flag.id), headers=headers)
    assert not [
        e
        for e in fetch_audit_events(db_sessionmaker)
        if e.action == "admin.fraud_review.route_read"
    ]


@pytest.mark.parametrize("state", ["acknowledged", "confirmed"])
@pytest.mark.parametrize(
    "reversal_amount,expected", [("20.00", "80.00"), ("100.00", "0"), ("120.00", "0")]
)
def test_active_review_holds_and_nonpositive_net(db_sessionmaker, state, reversal_amount, expected):
    graph = build_review_graph(db_sessionmaker, "held-state")
    flag = create_flag(db_sessionmaker, graph)
    create_ledger(db_sessionmaker, graph, amount="100.00")
    reversal = create_ledger(db_sessionmaker, graph, amount=reversal_amount)

    async def read():
        async with db_sessionmaker() as session:
            current = await session.get(FraudFlag, flag.id)
            current.status = state
            current.reviewed_by_user_id = graph.admin.id
            current.reviewed_at = NOW
            current.resolution_note = "Problem confirmed" if state == "confirmed" else None
            entry = await session.get(EarningsLedgerEntry, reversal.id)
            entry.entry_type = "reversal"
            await session.commit()
            return await read_held_trip_pay(session, trip_id=graph.trip.id)

    result = asyncio.run(read())
    assert result.amount == Decimal(expected)
    assert result.currency == ("NGN" if result.amount else None)


def test_review_commands_do_not_use_held_read(db_client, db_sessionmaker, monkeypatch):
    graph = build_review_graph(db_sessionmaker, "held-command-separation")
    flag = create_flag(db_sessionmaker, graph)
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)

    async def fail(*args, **kwargs):
        raise RuntimeError("held read unavailable")

    monkeypatch.setattr("app.api.v1.trip_analytics.read_held_trip_pay", fail)
    base = f"/api/v1/admin/fraud-flags/{flag.id}/review"
    ack = db_client.post(base + "/acknowledge", headers=headers)
    assert ack.status_code == 200
    assert "held_pending_net" not in ack.json()["money_effect"]
    clear = db_client.post(
        base + "/resolve", headers=headers, json={"outcome": "dismissed", "note": "Verified review"}
    )
    assert clear.status_code == 200 and clear.json()["status"] == "dismissed"
