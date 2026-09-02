import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

import app.jobs.evidence_verification as evidence_job
from app.jobs.evidence_verification import sweep_evidence_verifications
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.evidence_verification import (
    EvidenceVerification,
    EvidenceVerificationStatus,
)
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryStatus
from app.models.trip_analytics import FraudFlag
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from app.services import campaign_assignments as assignments_service
from app.services.earnings_release import release_pending_earnings_for_trip
from app.services.evidence_verification import evaluate_assignment_verification
from tests.test_mny03a_earnings_release import (
    build_graph,
    create_ledger,
    seed_assessment_authority,
)

CHALLENGE_NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _configured(settings):
    return settings.model_copy(
        update={
            "evidence_high_earner_threshold_ngn": "1000.00",
            "evidence_renewal_lookback_days": 30,
            "evidence_challenge_response_hours": 24,
        }
    )


def test_due_challenge_survives_deactivation_sweep_race_and_holds_release_once(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "r30-finality")

    async def activate() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(CampaignAssignment)
                .where(CampaignAssignment.id == graph.assignment.id)
                .values(
                    status=CampaignAssignmentStatus.ACTIVE.value,
                    activated_at=CHALLENGE_NOW - timedelta(days=1),
                )
            )
            await session.commit()

    asyncio.run(activate())
    entry = create_ledger(
        postgis_db_sessionmaker,
        graph,
        status=EarningsLedgerEntryStatus.PENDING.value,
        amount="1200.00",
    )
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)

    async def issue_and_make_due() -> None:
        async with postgis_db_sessionmaker() as session:
            result = await evaluate_assignment_verification(
                session,
                assignment_id=graph.assignment.id,
                settings=_configured(settings),
                now=CHALLENGE_NOW,
            )
            assert result.high_earner_issued == 1
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(EvidenceVerification)
                .where(EvidenceVerification.assignment_id == graph.assignment.id)
                .values(due_at=CHALLENGE_NOW - timedelta(seconds=1))
            )
            await session.commit()

    asyncio.run(issue_and_make_due())

    deactivated_uncommitted = asyncio.Event()
    allow_deactivation_commit = asyncio.Event()
    evaluation_started = asyncio.Event()
    real_evaluate = evidence_job.evaluate_assignment_verification

    async def observed_evaluate(*args, **kwargs):
        evaluation_started.set()
        return await real_evaluate(*args, **kwargs)

    monkeypatch.setattr(evidence_job, "evaluate_assignment_verification", observed_evaluate)

    async def deactivate() -> None:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.deactivate_driver_assignment(
                session,
                user_id=graph.driver.id,
                assignment_id=graph.assignment.id,
                payload=CampaignAssignmentTransition(metadata={}),
            )
            deactivated_uncommitted.set()
            await allow_deactivation_commit.wait()
            await session.commit()

    async def race():
        deactivation_task = asyncio.create_task(deactivate())
        await asyncio.wait_for(deactivated_uncommitted.wait(), timeout=2)
        sweep_task = asyncio.create_task(
            sweep_evidence_verifications(
                {
                    "settings": _configured(settings),
                    "sessionmaker": postgis_db_sessionmaker,
                }
            )
        )
        await asyncio.wait_for(evaluation_started.wait(), timeout=2)
        allow_deactivation_commit.set()
        _, sweep = await asyncio.wait_for(
            asyncio.gather(deactivation_task, sweep_task),
            timeout=10,
        )
        return sweep

    first_sweep = asyncio.run(race())
    assert first_sweep["processed"] == 1
    assert first_sweep["missed_challenges"] == 1

    async def release_and_read():
        async with postgis_db_sessionmaker() as session:
            released = await release_pending_earnings_for_trip(
                session,
                trip_id=graph.trip.id,
                settings=settings,
            )
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            verification = await session.scalar(
                select(EvidenceVerification).where(
                    EvidenceVerification.assignment_id == graph.assignment.id
                )
            )
            stored_entry = await session.get(EarningsLedgerEntry, entry.id)
            flags = await session.scalar(
                select(func.count(FraudFlag.id)).where(
                    FraudFlag.flag_type == "missed_display_challenge"
                )
            )
            audits = await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "evidence_verification.challenge_missed"
                )
            )
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            return released, verification, stored_entry, flags, audits, assignment

    released, verification, stored_entry, flags, audits, assignment = asyncio.run(
        release_and_read()
    )
    assert released.released_entry_ids == ()
    assert released.hold_active is True
    assert verification.status == EvidenceVerificationStatus.MISSED.value
    assert stored_entry.status == EarningsLedgerEntryStatus.PENDING.value
    assert assignment.status == CampaignAssignmentStatus.DEACTIVATED.value
    assert flags == 1
    assert audits == 1

    second_sweep = asyncio.run(
        sweep_evidence_verifications(
            {
                "settings": _configured(settings),
                "sessionmaker": postgis_db_sessionmaker,
            }
        )
    )
    assert second_sweep["missed_challenges"] == 0

    async def exact_once_counts() -> tuple[int, int]:
        async with postgis_db_sessionmaker() as session:
            return (
                await session.scalar(
                    select(func.count(FraudFlag.id)).where(
                        FraudFlag.flag_type == "missed_display_challenge"
                    )
                ),
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "evidence_verification.challenge_missed"
                    )
                ),
            )

    assert asyncio.run(exact_once_counts()) == (1, 1)
