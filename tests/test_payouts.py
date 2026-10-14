"""Current daily-rate payout API, evidence and tenant boundaries."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from payout_fixtures import PASSWORD, build_v4_graph, drive
from sqlalchemy import update

from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.models.user import UserRole


def test_tampered_manifest_receipt_cannot_originate_money(db_client, db_sessionmaker, settings):
    graph = build_v4_graph(db_sessionmaker, settings, "api-tampered")

    async def tamper():
        async with db_sessionmaker() as session:
            await session.execute(
                update(TripSession)
                .where(TripSession.id == graph.trip.id)
                .values(evidence_manifest_receipt_signature="tampered")
            )
            await session.commit()

    asyncio.run(tamper())
    response = db_client.post(
        f"/api/v1/admin/trips/{graph.trip.id}/calculate-payout",
        headers=auth_headers(db_client, graph.admin.email, PASSWORD),
        json={},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRIP_EVIDENCE_NOT_VERIFIED"
    assert fetch_payout_calculations(db_sessionmaker) == []
    assert fetch_earnings_ledger_entries(db_sessionmaker) == []


def test_admin_calculation_replay_is_idempotent_and_retains_frozen_rule(
    db_client, db_sessionmaker, settings
):
    graph = build_v4_graph(
        db_sessionmaker, settings, "api-replay", daily_rate_naira="600", daily_target_miles="1"
    )
    drive(db_sessionmaker, settings, graph.trip)
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    endpoint = f"/api/v1/admin/trips/{graph.trip.id}/calculate-payout"
    first = db_client.post(endpoint, headers=headers, json={})
    second = db_client.post(endpoint, headers=headers, json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["final_payout"] == "600.00"
    assert len(fetch_payout_calculations(db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(db_sessionmaker)) == 1
    wrong_rule = db_client.post(endpoint, headers=headers, json={"payout_rule_id": str(uuid4())})
    assert wrong_rule.status_code == 400
    assert len(fetch_earnings_ledger_entries(db_sessionmaker)) == 1


def test_payout_api_roles_and_driver_ownership(db_client, db_sessionmaker, settings):
    graph = build_v4_graph(
        db_sessionmaker, settings, "api-roles", daily_rate_naira="600", daily_target_miles="1"
    )
    drive(db_sessionmaker, settings, graph.trip)
    other = create_test_user(
        db_sessionmaker, email="other-earnings@example.com", role=UserRole.DRIVER, password=PASSWORD
    )
    create_test_driver_profile(db_sessionmaker, user_id=other.id)
    admin = auth_headers(db_client, graph.admin.email, PASSWORD)
    driver = auth_headers(db_client, graph.driver.email, PASSWORD)
    stranger = auth_headers(db_client, other.email, PASSWORD)
    calculate = f"/api/v1/admin/trips/{graph.trip.id}/calculate-payout"
    assert db_client.post(calculate, json={}).status_code == 401
    assert db_client.post(calculate, headers=driver, json={}).status_code == 403
    endpoint = f"/api/v1/driver/trips/{graph.trip.id}/earnings-breakdown"
    assert db_client.get(endpoint, headers=driver).json()["amount"] == "600.00"
    assert db_client.get(endpoint, headers=stranger).status_code == 404
    assert db_client.get("/api/v1/driver/earnings/ledger", headers=stranger).json()["total"] == 0
    ledger = db_client.get("/api/v1/driver/earnings/ledger", headers=driver)
    assert ledger.json()["total"] == 1
    listing = db_client.get(
        "/api/v1/admin/payout-calculations",
        headers=admin,
        params={"driver_profile_id": str(graph.profile.id)},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    empty = db_client.get(
        "/api/v1/admin/payout-calculations",
        headers=admin,
        params={"driver_profile_id": str(uuid4())},
    )
    assert empty.json()["total"] == 0


def test_driver_earnings_ledger_paginates_beyond_first_fifty(db_client, db_sessionmaker, settings):
    graph = build_v4_graph(db_sessionmaker, settings, "ledger-pagination")

    async def seed():
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    EarningsLedgerEntry(
                        driver_profile_id=graph.profile.id,
                        driver_user_id=graph.driver.id,
                        campaign_id=graph.campaign.id,
                        vehicle_id=graph.vehicle.id,
                        entry_type="adjustment",
                        status="available",
                        amount=Decimal("1.00"),
                        currency="NGN",
                        description=f"Pagination {index}",
                        occurred_at=graph.trip.started_at + timedelta(seconds=index),
                    )
                    for index in range(75)
                ]
            )
            await session.commit()

    asyncio.run(seed())
    response = db_client.get(
        "/api/v1/driver/earnings/ledger?limit=50&offset=50",
        headers=auth_headers(db_client, graph.driver.email, PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["total"] == 75
    assert response.json()["limit"] == 50
    assert response.json()["offset"] == 50
    assert len(response.json()["items"]) == 25
