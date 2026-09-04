import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.adapters.disbursement import (
    FakeDisbursementAdapter,
    ProviderLookup,
    ProviderLookupStatus,
)
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatch,
    PayoutBatchLine,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
)
from app.models.fraud_assessment import FraudAssessment
from app.models.payout import EarningsLedgerEntry
from app.models.route_replay import RouteReplaySignature
from app.models.trip_analytics import FraudFlag
from app.services import disbursements
from app.services.disbursements import (
    approve_payout_batch,
    claim_payout_submission_intent,
    create_payout_batch_draft,
    process_payout_submission_intent,
    reserve_payout_batch,
    submit_payout_batch,
)
from app.services.fraud_holds import (
    acknowledge_fraud_flag,
    lock_fraud_hold_scope,
    resolve_fraud_flag,
)
from tests.test_disbursement_worker import _prepare_batch
from tests.test_mny03a_earnings_release import (
    NOW,
    build_graph,
    seed_assessment_authority,
)
from tests.test_payout_batches import _seed_authority


async def _prepare_cross_trip_batch(
    sessionmaker,
    graphs,
    adapter,
    *,
    reverse_ledger_trip_order: bool = False,
    distinct_requester: bool = False,
):
    checker = type(graphs[0].admin)(
        email=f"r21-checker-{uuid4().hex}@example.com",
        password_hash=graphs[0].admin.password_hash,
        full_name="R21 Checker",
        role="admin",
        status="active",
    )
    requester = graphs[0].admin
    if distinct_requester:
        requester = type(graphs[0].admin)(
            email=f"r21-requester-{uuid4().hex}@example.com",
            password_hash=graphs[0].admin.password_hash,
            full_name="R21 Requester",
            role="admin",
            status="active",
        )
    async with sessionmaker() as session:
        session.add(checker)
        if distinct_requester:
            session.add(requester)
        await session.flush()
        entries = [await _seed_authority(session, graph) for graph in graphs]
        if reverse_ledger_trip_order:
            low_trip_id, high_trip_id = sorted(
                (graph.trip.id for graph in graphs),
                key=str,
            )
            for entry in entries:
                entry.id = UUID(int=2 if entry.trip_session_id == low_trip_id else 1)
            assert {entry.trip_session_id for entry in entries} == {
                low_trip_id,
                high_trip_id,
            }
            await session.flush()
        batch = await create_payout_batch_draft(
            session,
            currency="NGN",
            actor_user_id=graphs[0].admin.id,
        )
        _, lines = await reserve_payout_batch(
            session,
            batch_id=batch.id,
            ledger_entry_ids=tuple(entry.id for entry in entries),
            actor_user_id=graphs[0].admin.id,
        )
        await approve_payout_batch(
            session,
            batch_id=batch.id,
            actor_user_id=checker.id,
        )
        await submit_payout_batch(
            session,
            batch_id=batch.id,
            actor_user_id=requester.id,
            adapter=adapter,
        )
        intent_ids = tuple(
            await session.scalars(
                select(PayoutSubmissionIntent.id)
                .where(PayoutSubmissionIntent.payout_batch_line_id.in_([line.id for line in lines]))
                .order_by(PayoutSubmissionIntent.payout_batch_line_id)
            )
        )
        await session.commit()
        return batch.id, intent_ids


def test_committed_hold_blocks_claim_and_all_provider_io(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r21-hold-{uuid4().hex[:8]}")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            adapter,
        )

        async with postgis_db_sessionmaker() as hold_session:
            await lock_fraud_hold_scope(hold_session, graph.trip.id)
            hold_session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=graph.analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status="open",
                    description="Concurrent authoritative hold.",
                    evidence={"test": True},
                    detected_at=NOW + timedelta(seconds=1),
                )
            )
            await hold_session.flush()
            worker = asyncio.create_task(
                process_payout_submission_intent(
                    postgis_db_sessionmaker,
                    intent_id=intent_ids[0],
                    adapter=adapter,
                )
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(worker), timeout=0.1)
            await hold_session.commit()
        with pytest.raises(AppError) as blocked:
            await worker
        async with postgis_db_sessionmaker() as session:
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id == intent_ids[0]
                    )
                )
                or 0
            )
        return blocked.value.code, attempts

    code, attempts = asyncio.run(exercise())
    assert code == "PAYOUT_ENTRY_HELD"
    assert attempts == 0
    assert adapter.calls == []


def test_one_stale_assessment_blocks_whole_unresolved_batch(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graphs = tuple(
        build_graph(postgis_db_sessionmaker, f"r21-batch-{index}-{uuid4().hex[:6]}")
        for index in range(2)
    )
    for graph in graphs:
        seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, intent_ids = await _prepare_cross_trip_batch(
            postgis_db_sessionmaker,
            graphs,
            adapter,
        )
        async with postgis_db_sessionmaker() as session:
            assessment = await session.scalar(
                select(FraudAssessment).where(FraudAssessment.trip_session_id == graphs[1].trip.id)
            )
            assert assessment is not None
            assessment.inputs_fingerprint = "f" * 64
            await session.commit()
        with pytest.raises(AppError) as stale:
            await process_payout_submission_intent(
                postgis_db_sessionmaker,
                intent_id=intent_ids[0],
                adapter=adapter,
            )
        async with postgis_db_sessionmaker() as session:
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id.in_(intent_ids)
                    )
                )
                or 0
            )
        return stale.value.code, attempts

    code, attempts = asyncio.run(exercise())
    assert code == "PAYOUT_ASSESSMENT_NOT_CURRENT"
    assert attempts == 0
    assert adapter.calls == []


def test_concurrent_assessment_drift_is_rechecked_after_trip_lock(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r21-assess-{uuid4().hex[:8]}")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            adapter,
        )
        async with postgis_db_sessionmaker() as assessment_session:
            await lock_fraud_hold_scope(assessment_session, graph.trip.id)
            assessment = await assessment_session.scalar(
                select(FraudAssessment)
                .where(FraudAssessment.trip_session_id == graph.trip.id)
                .with_for_update()
            )
            assert assessment is not None
            assessment.inputs_fingerprint = "e" * 64
            await assessment_session.flush()
            worker = asyncio.create_task(
                process_payout_submission_intent(
                    postgis_db_sessionmaker,
                    intent_id=intent_ids[0],
                    adapter=adapter,
                )
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(worker), timeout=0.1)
            await assessment_session.commit()
        with pytest.raises(AppError) as blocked:
            await worker
        return blocked.value.code

    assert asyncio.run(exercise()) == "PAYOUT_ASSESSMENT_NOT_CURRENT"
    assert adapter.calls == []


def test_multi_trip_claim_takes_trip_locks_in_stable_order(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graphs = tuple(
        build_graph(postgis_db_sessionmaker, f"r21-order-{index}-{uuid4().hex[:6]}")
        for index in range(2)
    )
    for graph in graphs:
        seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    low_trip_id, high_trip_id = sorted(
        (graph.trip.id for graph in graphs),
        key=str,
    )
    adapter = FakeDisbursementAdapter()
    entered_trip_locking = asyncio.Event()
    original_lock_scopes = disbursements.lock_fraud_hold_scopes

    async def observed_lock_scopes(session, trip_ids):
        entered_trip_locking.set()
        return await original_lock_scopes(session, trip_ids)

    monkeypatch.setattr(disbursements, "lock_fraud_hold_scopes", observed_lock_scopes)

    async def exercise():
        _, intent_ids = await _prepare_cross_trip_batch(
            postgis_db_sessionmaker,
            graphs,
            adapter,
            reverse_ledger_trip_order=True,
        )
        async with postgis_db_sessionmaker() as blocker:
            await lock_fraud_hold_scope(blocker, low_trip_id)
            claim_task = asyncio.create_task(
                claim_payout_submission_intent(
                    postgis_db_sessionmaker,
                    intent_id=intent_ids[0],
                    adapter=adapter,
                )
            )
            await asyncio.wait_for(entered_trip_locking.wait(), timeout=1)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(claim_task), timeout=0.1)

            async def lock_later_trip():
                async with postgis_db_sessionmaker() as probe:
                    await lock_fraud_hold_scope(probe, high_trip_id)
                    await probe.rollback()

            await asyncio.wait_for(lock_later_trip(), timeout=0.5)
            await blocker.commit()
        claim = await asyncio.wait_for(claim_task, timeout=2)
        return claim

    claim = asyncio.run(exercise())
    assert claim is not None
    assert adapter.calls == []


@pytest.mark.parametrize(
    "drift",
    (
        "assessment_formula",
        "analytics_formula",
        "replay_signature",
        "replay_config",
        "dismissed_flag",
        "ledger_state",
        "debt",
        "instruction",
    ),
)
def test_any_final_authority_drift_blocks_before_adapter(
    postgis_db_sessionmaker,
    settings,
    drift,
) -> None:
    graph = build_graph(
        postgis_db_sessionmaker,
        f"r21-drift-{uuid4().hex[:8]}",
    )
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            adapter,
            line_count=2 if drift == "debt" else 1,
        )
        async with postgis_db_sessionmaker() as session:
            assessment = await session.scalar(
                select(FraudAssessment).where(FraudAssessment.trip_session_id == graph.trip.id)
            )
            analytics = await session.get(type(graph.analytics), graph.analytics.id)
            signature = await session.scalar(
                select(RouteReplaySignature).where(
                    RouteReplaySignature.trip_session_id == graph.trip.id
                )
            )
            if drift == "assessment_formula":
                assessment.formula_version = "fraud_assessment_stale"
            elif drift == "analytics_formula":
                analytics.formula_version = "route_analytics_stale"
            elif drift == "replay_signature":
                signature.detector_version = "route_replay_stale"
            elif drift == "replay_config":
                signature.detector_config_fingerprint = "c" * 64
            elif drift == "ledger_state":
                entry = await session.scalar(
                    select(EarningsLedgerEntry)
                    .join(
                        PayoutBatchLine,
                        PayoutBatchLine.ledger_entry_id == EarningsLedgerEntry.id,
                    )
                    .join(
                        PayoutSubmissionIntent,
                        PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                    )
                    .where(PayoutSubmissionIntent.id == intent_ids[0])
                    .limit(1)
                )
                assert entry is not None
                entry.status = "pending"
            elif drift == "debt":
                entry = await session.scalar(
                    select(EarningsLedgerEntry)
                    .join(
                        PayoutBatchLine,
                        PayoutBatchLine.ledger_entry_id == EarningsLedgerEntry.id,
                    )
                    .join(
                        PayoutSubmissionIntent,
                        PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                    )
                    .where(PayoutSubmissionIntent.id == intent_ids[0])
                    .limit(1)
                )
                assert entry is not None
                session.add(
                    DriverCurrencyDebtAccount(
                        driver_profile_id=entry.driver_profile_id,
                        driver_user_id=entry.driver_user_id,
                        currency=entry.currency,
                        outstanding_amount=Decimal("10.00"),
                        lifetime_incurred_amount=Decimal("10.00"),
                        lifetime_allocated_amount=Decimal("0.00"),
                    )
                )
            elif drift == "instruction":
                line = await session.scalar(
                    select(PayoutBatchLine)
                    .join(
                        PayoutSubmissionIntent,
                        PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                    )
                    .where(PayoutSubmissionIntent.id == intent_ids[0])
                )
                assert line is not None
                line.instruction = {**line.instruction, "amount": "999.00"}
            else:
                flag = FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=graph.analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="stationary_trip",
                    severity="medium",
                    status="open",
                    description="Later dismissed review.",
                    evidence={"test": True},
                    detected_at=graph.analytics.computed_at,
                )
                session.add(flag)
                await session.flush()
                await acknowledge_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    now=NOW + timedelta(seconds=3),
                )
                await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    outcome="dismissed",
                    resolution_note="Dismissed after reservation.",
                    now=NOW + timedelta(seconds=4),
                )
            await session.commit()
        with pytest.raises(AppError) as blocked:
            await process_payout_submission_intent(
                postgis_db_sessionmaker,
                intent_id=intent_ids[0],
                adapter=adapter,
            )
        async with postgis_db_sessionmaker() as session:
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id.in_(intent_ids)
                    )
                )
                or 0
            )
        return blocked.value.code, attempts

    code, attempts = asyncio.run(exercise())
    assert code in {
        "PAYOUT_ASSESSMENT_NOT_CURRENT",
        "PAYOUT_LEDGER_NOT_AVAILABLE",
        "PAYOUT_DEBT_ALLOCATION_REQUIRED",
        "PAYOUT_INSTRUCTION_CHANGED",
    }
    assert attempts == 0
    assert adapter.calls == []


@pytest.mark.parametrize("inactive_authority", ("maker", "checker", "requester"))
def test_inactive_admin_authority_blocks_final_claim_before_adapter(
    postgis_db_sessionmaker,
    settings,
    inactive_authority,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r21-admin-{uuid4().hex[:8]}")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
    adapter = FakeDisbursementAdapter()

    async def exercise():
        batch_id, intent_ids = await _prepare_cross_trip_batch(
            postgis_db_sessionmaker,
            (graph,),
            adapter,
            distinct_requester=True,
        )
        async with postgis_db_sessionmaker() as session:
            batch = await session.get(PayoutBatch, batch_id)
            assert batch is not None and batch.approved_by_user_id is not None
            intent = await session.get(PayoutSubmissionIntent, intent_ids[0])
            assert intent is not None
            authority_ids = {
                "maker": batch.created_by_user_id,
                "checker": batch.approved_by_user_id,
                "requester": intent.requested_by_user_id,
            }
            assert len(set(authority_ids.values())) == 3
            authority = await session.get(
                type(graph.admin),
                authority_ids[inactive_authority],
            )
            assert authority is not None
            authority.status = "suspended"
            await session.commit()
        with pytest.raises(AppError) as blocked:
            await process_payout_submission_intent(
                postgis_db_sessionmaker,
                intent_id=intent_ids[0],
                adapter=adapter,
            )
        async with postgis_db_sessionmaker() as session:
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id.in_(intent_ids)
                    )
                )
                or 0
            )
        return blocked.value.code, attempts

    code, attempts = asyncio.run(exercise())
    assert code == "FORBIDDEN_ROLE"
    assert attempts == 0
    assert adapter.calls == []


def test_expired_pre_invocation_claim_repeats_gate_before_lookup(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r21-renew-{uuid4().hex[:8]}")
    seed_assessment_authority(postgis_db_sessionmaker, graph, settings)

    class LookupProbeAdapter(FakeDisbursementAdapter):
        def __init__(self):
            super().__init__()
            self.lookup_calls = 0

        async def lookup_line(self, *, idempotency_key, instruction_fingerprint):
            self.lookup_calls += 1
            return ProviderLookup(status=ProviderLookupStatus.NOT_FOUND)

    adapter = LookupProbeAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            adapter,
        )
        claim = await claim_payout_submission_intent(
            postgis_db_sessionmaker,
            intent_id=intent_ids[0],
            adapter=adapter,
        )
        assert claim is not None and claim.action == "submit"
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == intent_ids[0])
                .values(claim_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            await lock_fraud_hold_scope(session, graph.trip.id)
            session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=graph.analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status="open",
                    description="Hold before renewed claim.",
                    evidence={"test": True},
                    detected_at=NOW + timedelta(seconds=1),
                )
            )
            await session.commit()
        with pytest.raises(AppError) as blocked:
            await process_payout_submission_intent(
                postgis_db_sessionmaker,
                intent_id=intent_ids[0],
                adapter=adapter,
            )
        return blocked.value.code

    assert asyncio.run(exercise()) == "PAYOUT_ENTRY_HELD"
    assert adapter.calls == []
    assert adapter.lookup_calls == 0


def test_clean_claim_persists_complete_final_authority(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r21-audit-{uuid4().hex[:8]}")
    assessment_id = seed_assessment_authority(
        postgis_db_sessionmaker,
        graph,
        settings,
    )
    adapter = FakeDisbursementAdapter()

    async def exercise():
        batch_id, _, intent_ids = await _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            adapter,
        )
        outcome = await process_payout_submission_intent(
            postgis_db_sessionmaker,
            intent_id=intent_ids[0],
            adapter=adapter,
        )
        async with postgis_db_sessionmaker() as session:
            attempt = await session.scalar(
                select(PayoutSubmissionAttempt).where(
                    PayoutSubmissionAttempt.intent_id == intent_ids[0]
                )
            )
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "worker.payout_submission.authorized",
                    AuditEvent.entity_id == str(intent_ids[0]),
                )
            )
            return outcome, batch_id, attempt, event

    outcome, batch_id, attempt, event = asyncio.run(exercise())
    assert outcome == "resolved"
    assert len(adapter.calls) == 1
    assert attempt is not None and attempt.claim_token is not None
    assert event is not None
    metadata = event.event_metadata
    assert metadata["batch_id"] == str(batch_id)
    assert metadata["claim_generation"] == attempt.generation
    serialized_metadata = json.dumps(metadata, sort_keys=True)
    assert '"claim_token"' not in serialized_metadata
    assert str(attempt.claim_token) not in serialized_metadata
    assert metadata["claim_expires_at"]
    assert metadata["authorized_at"]
    assert metadata["final_gate_config_fingerprint"]
    assert metadata["candidate_line_ids"]
    assert metadata["trip_authorities"][0]["assessment_id"] == str(assessment_id)
    assert metadata["trip_authorities"][0]["assessment_current"] is True
    assert metadata["trip_authorities"][0]["fraud_hold_active"] is False
    assert metadata["trip_authorities"][0]["route_replay_signature_id"]
    assert metadata["ledger_authorities"][0]["status"] == "available"
