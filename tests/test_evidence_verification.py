import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import auth_headers
from test_fraud_assessments import build_graph

from app.core.errors import AppError
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
from app.services.evidence_verification import (
    queue_physical_spot_check,
    resolve_physical_spot_check,
)
from app.services.fraud_holds import acknowledge_fraud_flag, fraud_hold_counts, resolve_fraud_flag

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


def test_physical_spot_check_exact_retry_failure_and_dismissal_release(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "spot-check")
    activate_and_add_earning(db_sessionmaker, graph, amount="1.00")
    request_id = uuid4()

    async def run():
        async with db_sessionmaker() as session:
            first = await queue_physical_spot_check(
                session,
                actor_user_id=graph.assignment.assigned_by_user_id,
                assignment_id=graph.assignment.id,
                trip_session_id=graph.trip.id,
                client_request_id=request_id,
                note="Inspect the installed display.",
                metadata={"fixture": "synthetic"},
                now=NOW,
            )
            await session.commit()
            verification_id = first.id
        async with db_sessionmaker() as session:
            retry = await queue_physical_spot_check(
                session,
                actor_user_id=graph.assignment.assigned_by_user_id,
                assignment_id=graph.assignment.id,
                trip_session_id=graph.trip.id,
                client_request_id=request_id,
                note="Inspect the installed display.",
                metadata={"fixture": "synthetic"},
                now=NOW,
            )
            assert retry.id == verification_id
            with pytest.raises(AppError, match="spot-check retry"):
                await queue_physical_spot_check(
                    session,
                    actor_user_id=graph.assignment.assigned_by_user_id,
                    assignment_id=graph.assignment.id,
                    trip_session_id=graph.trip.id,
                    client_request_id=request_id,
                    note="Changed request.",
                    metadata={"fixture": "synthetic"},
                    now=NOW,
                )
            await session.rollback()
        async with db_sessionmaker() as session:
            failed = await resolve_physical_spot_check(
                session,
                verification_id=verification_id,
                actor_user_id=graph.assignment.assigned_by_user_id,
                outcome="failed",
                note="Branding was not present.",
                evidence={"observation": "physical inspection"},
                now=NOW,
            )
            await session.commit()
            flag_id = failed.fraud_flag_id
        async with db_sessionmaker() as session:
            exact = await resolve_physical_spot_check(
                session,
                verification_id=verification_id,
                actor_user_id=graph.assignment.assigned_by_user_id,
                outcome="failed",
                note="Branding was not present.",
                evidence={"observation": "physical inspection"},
                now=NOW,
            )
            assert exact.fraud_flag_id == flag_id
            second = await queue_physical_spot_check(
                session,
                actor_user_id=graph.assignment.assigned_by_user_id,
                assignment_id=graph.assignment.id,
                trip_session_id=graph.trip.id,
                client_request_id=uuid4(),
                note="Repeat physical inspection.",
                metadata={"fixture": "synthetic-repeat"},
                now=NOW,
            )
            second_failed = await resolve_physical_spot_check(
                session,
                verification_id=second.id,
                actor_user_id=graph.assignment.assigned_by_user_id,
                outcome="failed",
                note="The repeat inspection also failed.",
                evidence={"observation": "second physical inspection"},
                now=NOW,
            )
            assert second_failed.fraud_flag_id == flag_id
            await acknowledge_fraud_flag(
                session,
                flag_id=flag_id,
                actor_user_id=graph.assignment.assigned_by_user_id,
                now=NOW,
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag_id,
                actor_user_id=graph.assignment.assigned_by_user_id,
                outcome="dismissed",
                resolution_note="False positive after evidence review.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
        async with db_sessionmaker() as session:
            return await fraud_hold_counts(session, graph.trip.id)

    assert asyncio.run(run()) == {"low": 0, "medium": 0, "high": 0}


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
                    status="pending",
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
    filters = {"status": "pending", "verification_type": "physical_spot_check"}
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
    empty = db_client.get(path, headers=headers, params={**filters, "status": "passed"})
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
    for invalid in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert db_client.get(path, headers=headers, params=invalid).status_code == 422
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    assert db_client.get(path, headers=driver_headers).status_code == 403
    assert db_client.get(path).status_code == 401
