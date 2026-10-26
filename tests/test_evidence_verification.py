import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from conftest import auth_headers
from sqlalchemy import func, select
from test_fraud_assessments import build_graph

from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.evidence_verification import (
    EvidenceVerification,
)
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip import TripSession
from app.services.fraud_holds import fraud_hold_counts, resolve_fraud_flag

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
PASSWORD = "long-secure-password"


def activate_and_add_earning(
    db_sessionmaker, graph, *, amount: str = "1200.00", now: datetime = NOW
) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            assignment.status = CampaignAssignmentStatus.ACTIVE.value
            assignment.activated_at = now - timedelta(days=1)
            trip = await session.get(TripSession, graph.trip.id)
            trip.started_at = now - timedelta(hours=2)
            trip.ended_at = now - timedelta(hours=1)
            trip.sealed_at = now - timedelta(minutes=50)
            session.add(
                EarningsLedgerEntry(
                    driver_profile_id=graph.profile.id,
                    driver_user_id=graph.driver.id,
                    campaign_id=graph.campaign.id,
                    trip_session_id=graph.trip.id,
                    vehicle_id=graph.vehicle.id,
                    entry_type=EarningsLedgerEntryType.TRIP_PAYOUT.value,
                    status=EarningsLedgerEntryStatus.AVAILABLE.value,
                    amount=Decimal(amount),
                    currency="NGN",
                    occurred_at=now - timedelta(minutes=45),
                    description="Synthetic verified earnings",
                    ledger_metadata={},
                )
            )
            await session.commit()

    asyncio.run(run())


def test_spot_result_retry_hold_and_explicit_dismissal(db_client, db_sessionmaker):
    graph = build_graph(db_sessionmaker, "spot-check")
    activate_and_add_earning(db_sessionmaker, graph, amount="1.00")
    headers = auth_headers(db_client, "admin-spot-check@example.com", PASSWORD)
    path = "/api/v1/admin/evidence-verifications/physical-spot-checks"
    payload = {
        "assignment_id": str(graph.assignment.id),
        "trip_session_id": str(graph.trip.id),
        "client_request_id": str(uuid4()),
        "outcome": "failed",
        "note": "Branding was absent during the physical inspection.",
    }
    failed = db_client.post(path, headers=headers, json=payload)
    assert failed.status_code == 201, failed.text
    assert failed.json()["status"] == "failed"
    flag_id = failed.json()["fraud_flag_id"]
    assert flag_id is not None
    retry = db_client.post(path, headers=headers, json=payload)
    assert retry.status_code == 201
    assert retry.json()["id"] == failed.json()["id"]
    conflict = db_client.post(path, headers=headers, json={**payload, "outcome": "passed"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "EVIDENCE_VERIFICATION_REPLAY_CONFLICT"
    passed = db_client.post(
        path,
        headers=headers,
        json={
            **payload,
            "client_request_id": str(uuid4()),
            "outcome": "passed",
            "note": "Branding is present on a later inspection.",
        },
    )
    assert passed.status_code == 201, passed.text
    assert passed.json()["fraud_flag_id"] is None

    async def inspect_and_dismiss():
        async with db_sessionmaker() as session:
            assert (await fraud_hold_counts(session, graph.trip.id))["high"] == 1
            assert await session.scalar(select(func.count()).select_from(EvidenceVerification)) == 2
            pass
            await resolve_fraud_flag(
                session,
                flag_id=UUID(flag_id),
                actor_user_id=graph.assignment.assigned_by_user_id,
                outcome="dismissed",
                resolution_note="Staff reviewed the failed observation.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
            assert (await fraud_hold_counts(session, graph.trip.id))["high"] == 0

    asyncio.run(inspect_and_dismiss())
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    assert db_client.post(path, headers=driver_headers, json=payload).status_code == 403
    assert db_client.post(path, json=payload).status_code == 401
    for change in ({"note": " "}, {"outcome": "pending"}):
        assert db_client.post(path, headers=headers, json={**payload, **change}).status_code == 422


def test_admin_physical_checks_have_complete_filtered_paging(db_client, db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, "physical-paging")
    headers = auth_headers(db_client, "admin-physical-paging@example.com", PASSWORD)
    identifiers = sorted((uuid4() for _ in range(103)), reverse=True)

    async def add_checks() -> None:
        async with db_sessionmaker() as session:
            session.add_all(
                EvidenceVerification(
                    id=identifier,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    source_trip_session_id=graph.trip.id,
                    verification_type="physical_spot_check",
                    status="passed",
                    resolved_by_user_id=graph.assignment.assigned_by_user_id,
                    resolved_at=NOW,
                    issued_by_user_id=graph.assignment.assigned_by_user_id,
                    client_request_id=uuid4(),
                    request_fingerprint="a" * 64,
                    issued_at=NOW,
                )
                for identifier in identifiers
            )
            await session.commit()

    asyncio.run(add_checks())
    path = "/api/v1/admin/evidence-verifications"
    filters = {"status": "passed", "verification_type": "physical_spot_check"}
    first = db_client.get(path, headers=headers, params=filters)
    assert first.status_code == 200
    assert first.json()["total"] == 103
    assert first.json()["limit"] == 100
    assert first.json()["offset"] == 0
    assert [row["id"] for row in first.json()["items"]] == [str(i) for i in identifiers[:100]]
    tail = db_client.get(path, headers=headers, params={**filters, "offset": 100, "limit": 10})
    assert tail.status_code == 200
    assert tail.json()["total"] == 103
    assert [row["id"] for row in tail.json()["items"]] == [str(i) for i in identifiers[100:]]
    empty = db_client.get(path, headers=headers, params={**filters, "status": "failed"})
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
    for invalid in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert db_client.get(path, headers=headers, params=invalid).status_code == 422
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    assert db_client.get(path, headers=driver_headers).status_code == 403
    assert db_client.get(path).status_code == 401
