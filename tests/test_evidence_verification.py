import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_fraud_assessments import build_graph

from app.core.errors import AppError
from app.jobs.evidence_verification import sweep_evidence_verifications
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.evidence_verification import (
    EvidenceVerification,
    EvidenceVerificationStatus,
)
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip import TripSession
from app.models.trip_analytics import FraudFlag
from app.services.evidence_verification import (
    evaluate_assignment_verification,
    list_driver_pending_verifications,
    parse_evidence_renewal_policy,
    queue_physical_spot_check,
    resolve_physical_spot_check,
)
from app.services.fraud_holds import acknowledge_fraud_flag, fraud_hold_counts, resolve_fraud_flag

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
PASSWORD = "long-secure-password"


def configured(settings):
    return settings.model_copy(
        update={
            "evidence_high_earner_threshold_ngn": "1000.00",
            "evidence_renewal_lookback_days": 30,
            "evidence_challenge_response_hours": 24,
        }
    )


def activate_and_add_earning(db_sessionmaker, graph, *, amount: str = "1200.00") -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            assignment.status = CampaignAssignmentStatus.ACTIVE.value
            assignment.activated_at = NOW - timedelta(days=1)
            trip = await session.get(TripSession, graph.trip.id)
            trip.started_at = NOW - timedelta(hours=2)
            trip.ended_at = NOW - timedelta(hours=1)
            trip.sealed_at = NOW - timedelta(minutes=50)
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
                    occurred_at=NOW - timedelta(minutes=45),
                    description="Synthetic verified earnings",
                    ledger_metadata={},
                )
            )
            await session.commit()

    asyncio.run(run())


def test_policy_has_no_invented_default_and_rejects_invalid_values(settings) -> None:
    policy, error = parse_evidence_renewal_policy(settings)
    assert policy is None
    assert error == "missing_configuration"

    blank = settings.model_copy(
        update={
            "evidence_high_earner_threshold_ngn": "",
            "evidence_renewal_lookback_days": 30,
            "evidence_challenge_response_hours": 24,
        }
    )
    policy, error = parse_evidence_renewal_policy(blank)
    assert policy is None
    assert error == "missing_configuration"

    invalid = settings.model_copy(
        update={
            "evidence_high_earner_threshold_ngn": "NaN",
            "evidence_renewal_lookback_days": 30,
            "evidence_challenge_response_hours": 24,
        }
    )
    policy, error = parse_evidence_renewal_policy(invalid)
    assert policy is None
    assert error == "invalid_configuration"


def test_high_earner_challenge_is_idempotent_then_missed_challenge_holds_money(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "high-earner")
    activate_and_add_earning(db_sessionmaker, graph)

    async def run():
        async with db_sessionmaker() as session:
            first = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            retry = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            missed = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW + timedelta(hours=25),
            )
            await session.commit()
        async with db_sessionmaker() as session:
            verification = await session.scalar(select(EvidenceVerification))
            flag = await session.get(FraudFlag, verification.fraud_flag_id)
            count = await session.scalar(select(func.count(EvidenceVerification.id)))
            return first, retry, missed, verification, flag, count

    first, retry, missed, verification, flag, count = asyncio.run(run())
    assert first.high_earner_issued == 1
    assert retry.high_earner_issued == 0
    assert missed.missed_challenges == 1
    assert count == 1
    assert verification.status == EvidenceVerificationStatus.MISSED.value
    assert flag.flag_type == "missed_display_challenge"
    assert flag.status == "open"
    assert verification.verification_metadata["gps_claim"] == "none"


def test_concurrent_sessions_create_one_authoritative_day_hold(db_sessionmaker, settings) -> None:
    graph = build_graph(db_sessionmaker, "concurrent")
    activate_and_add_earning(db_sessionmaker, graph, amount="1.00")

    async def run():
        async with db_sessionmaker() as session:
            source = await session.get(TripSession, graph.trip.id)
            overlap = TripSession(
                assignment_id=source.assignment_id,
                campaign_id=source.campaign_id,
                driver_profile_id=source.driver_profile_id,
                vehicle_id=source.vehicle_id,
                started_by_user_id=source.started_by_user_id,
                status="sealed",
                started_at=source.started_at + timedelta(minutes=30),
                ended_at=source.ended_at + timedelta(minutes=30),
                sealed_at=source.ended_at + timedelta(minutes=40),
                seal_reason="migration_backfill",
                trip_metadata={"synthetic_overlap": True},
            )
            session.add(overlap)
            await session.commit()
        async with db_sessionmaker() as session:
            first = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            second = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            flags = list(
                (
                    await session.scalars(
                        select(FraudFlag).where(FraudFlag.flag_type == "concurrent_session_day")
                    )
                ).all()
            )
            return first, second, flags

    first, second, flags = asyncio.run(run())
    assert first.concurrent_holds >= 1
    assert second.concurrent_holds == 0
    assert len(flags) >= 1
    assert all(flag.status == "open" for flag in flags)


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


def test_driver_pending_list_is_tenant_scoped(db_sessionmaker, settings) -> None:
    first = build_graph(db_sessionmaker, "driver-scope-a")
    second = build_graph(db_sessionmaker, "driver-scope-b")
    activate_and_add_earning(db_sessionmaker, first)
    activate_and_add_earning(db_sessionmaker, second)

    async def run():
        for graph in (first, second):
            async with db_sessionmaker() as session:
                await evaluate_assignment_verification(
                    session,
                    assignment_id=graph.assignment.id,
                    settings=configured(settings),
                    now=NOW,
                )
                await session.commit()
        async with db_sessionmaker() as session:
            first_rows = await list_driver_pending_verifications(session, user_id=first.driver.id)
            second_rows = await list_driver_pending_verifications(session, user_id=second.driver.id)
            return first_rows, second_rows

    first_rows, second_rows = asyncio.run(run())
    assert {row.assignment_id for row in first_rows} == {first.assignment.id}
    assert {row.assignment_id for row in second_rows} == {second.assignment.id}


def test_postgres_worker_and_spot_check_retries_serialize(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "verification-race")
    activate_and_add_earning(postgis_db_sessionmaker, graph)
    request_id = uuid4()

    async def evaluate_once():
        async with postgis_db_sessionmaker() as session:
            result = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()
            return result.high_earner_issued

    async def queue_once():
        async with postgis_db_sessionmaker() as session:
            row = await queue_physical_spot_check(
                session,
                actor_user_id=graph.assignment.assigned_by_user_id,
                assignment_id=graph.assignment.id,
                trip_session_id=graph.trip.id,
                client_request_id=request_id,
                note="Concurrent exact retry.",
                metadata={"fixture": "race"},
                now=NOW,
            )
            await session.commit()
            return row.id

    async def run():
        issued = await asyncio.gather(evaluate_once(), evaluate_once())
        queued = await asyncio.gather(queue_once(), queue_once())
        async with postgis_db_sessionmaker() as session:
            automatic_count = await session.scalar(
                select(func.count(EvidenceVerification.id)).where(
                    EvidenceVerification.verification_type == "high_earner_renewal"
                )
            )
            spot_count = await session.scalar(
                select(func.count(EvidenceVerification.id)).where(
                    EvidenceVerification.verification_type == "physical_spot_check"
                )
            )
        return issued, queued, automatic_count, spot_count

    issued, queued, automatic_count, spot_count = asyncio.run(run())
    assert sorted(issued) == [0, 1]
    assert queued[0] == queued[1]
    assert automatic_count == 1
    assert spot_count == 1


def test_admin_spot_check_api_and_driver_pending_api_are_role_scoped(
    db_client, db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "verification-api")
    activate_and_add_earning(db_sessionmaker, graph)
    admin_headers = auth_headers(
        db_client, "admin-verification-api@example.com", PASSWORD
    )
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    request_id = uuid4()

    queued = db_client.post(
        "/api/v1/admin/evidence-verifications/physical-spot-checks",
        headers=admin_headers,
        json={
            "assignment_id": str(graph.assignment.id),
            "trip_session_id": str(graph.trip.id),
            "client_request_id": str(request_id),
            "note": "Synthetic operations check.",
            "metadata": {"source": "test"},
        },
    )
    assert queued.status_code == 201
    assert queued.json()["status"] == "pending"

    driver_forbidden = db_client.get(
        "/api/v1/admin/evidence-verifications", headers=driver_headers
    )
    assert driver_forbidden.status_code == 403

    async def issue_high_earner() -> None:
        async with db_sessionmaker() as session:
            await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=configured(settings),
                now=NOW,
            )
            await session.commit()

    asyncio.run(issue_high_earner())
    pending = db_client.get(
        "/api/v1/driver/evidence-verifications/pending", headers=driver_headers
    )
    assert pending.status_code == 200
    assert {item["assignment_id"] for item in pending.json()["items"]} == {
        str(graph.assignment.id)
    }
    assert {item["verification_type"] for item in pending.json()["items"]} == {
        "high_earner_renewal"
    }

    resolved = db_client.post(
        "/api/v1/admin/evidence-verifications/"
        f"{queued.json()['id']}/physical-spot-check-result",
        headers=admin_headers,
        json={
            "outcome": "passed",
            "note": "Display confirmed by physical inspection.",
            "evidence": {"method": "in_person"},
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "passed"


def test_worker_reports_unconfigured_high_earner_policy_without_inventing_work(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "worker-unconfigured")
    activate_and_add_earning(db_sessionmaker, graph)

    async def run():
        result = await sweep_evidence_verifications(
            {"settings": settings, "sessionmaker": db_sessionmaker}
        )
        async with db_sessionmaker() as session:
            count = await session.scalar(select(func.count(EvidenceVerification.id)))
        return result, count

    result, count = asyncio.run(run())
    assert result["processed"] == 1
    assert result["policy_unconfigured"] == 1
    assert result["high_earner_issued"] == 0
    assert count == 0
