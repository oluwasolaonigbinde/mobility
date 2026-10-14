import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.services.disbursements as disbursement_service
from app.adapters.disbursement import FakeDisbursementAdapter
from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.disbursement import (
    PayoutBatchLine,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
    PayoutSubmissionObservation,
    PayoutSubmissionObservationOutcome,
)
from app.models.user import User
from app.services.disbursements import (
    DISBURSEMENT_CLAIM_LEASE,
    DisbursementClaimObservation,
    _resolve_payout_submission_claim,
    claim_payout_submission_intent,
    process_payout_submission_intent,
)
from tests.database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from tests.test_disbursement_worker import _prepare_batch
from tests.test_mny03a_earnings_release import build_graph


def test_concurrent_claim_commits_before_provider_io_and_submits_once(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r20-claim-{uuid4().hex[:8]}")
    losing_claim_finished = asyncio.Event()

    class LockProbeAdapter(FakeDisbursementAdapter):
        def __init__(self):
            super().__init__()
            self.committed_attempts_seen: list[int] = []

        async def submit_batch(self, *, batch_id, instructions):
            await losing_claim_finished.wait()
            async with postgis_db_sessionmaker() as probe:
                intent = await probe.scalar(
                    select(PayoutSubmissionIntent)
                    .where(
                        PayoutSubmissionIntent.idempotency_key == instructions[0].idempotency_key
                    )
                    .with_for_update(nowait=True)
                )
                self.committed_attempts_seen.append(
                    int(
                        await probe.scalar(
                            select(func.count(PayoutSubmissionAttempt.id)).where(
                                PayoutSubmissionAttempt.intent_id == intent.id
                            )
                        )
                        or 0
                    )
                )
            return await super().submit_batch(batch_id=batch_id, instructions=instructions)

    adapter = LockProbeAdapter()

    async def exercise():
        _, line_ids, intent_ids = await _prepare_batch(postgis_db_sessionmaker, graph, adapter)

        async def process_one() -> str:
            result = await process_payout_submission_intent(
                postgis_db_sessionmaker,
                intent_id=intent_ids[0],
                adapter=adapter,
            )
            if result == "skipped":
                losing_claim_finished.set()
            return result

        results = await asyncio.wait_for(asyncio.gather(process_one(), process_one()), timeout=10)
        async with postgis_db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_ids[0])
            line = await session.get(PayoutBatchLine, line_ids[0])
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id == intent.id
                    )
                )
                or 0
            )
            observations = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionObservation.id)).where(
                        PayoutSubmissionObservation.intent_id == intent.id
                    )
                )
                or 0
            )
            return results, intent, line, attempts, observations

    results, intent, line, attempts, observations = asyncio.run(exercise())
    assert sorted(results) == ["resolved", "skipped"]
    assert adapter.committed_attempts_seen == [1]
    assert len(adapter.calls) == 1
    assert intent.state == "resolved"
    assert line.status == "submitted"
    assert attempts == observations == 1


def test_crash_before_provider_call_queries_not_found_before_same_key_resend(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r20-pre-call-{uuid4().hex[:8]}")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(postgis_db_sessionmaker, graph, adapter)
        intent_id = intent_ids[0]
        monkeypatch.setattr(
            disbursement_service, "DISBURSEMENT_CLAIM_LEASE", timedelta(microseconds=-1)
        )
        crashed_claim = await claim_payout_submission_intent(
            postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
        )
        monkeypatch.setattr(
            disbursement_service, "DISBURSEMENT_CLAIM_LEASE", DISBURSEMENT_CLAIM_LEASE
        )
        after_lookup = await process_payout_submission_intent(
            postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
        )
        resubmits = await asyncio.gather(
            *(
                process_payout_submission_intent(
                    postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
                )
                for _ in range(2)
            )
        )
        async with postgis_db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            actions = tuple(
                await session.scalars(
                    select(PayoutSubmissionAttempt.action)
                    .where(PayoutSubmissionAttempt.intent_id == intent_id)
                    .order_by(PayoutSubmissionAttempt.generation)
                )
            )
            outcomes = tuple(
                await session.scalars(
                    select(PayoutSubmissionObservation.outcome)
                    .where(PayoutSubmissionObservation.intent_id == intent_id)
                    .order_by(PayoutSubmissionObservation.generation)
                )
            )
            return crashed_claim, after_lookup, resubmits, intent, actions, outcomes

    crashed_claim, after_lookup, resubmits, intent, actions, outcomes = asyncio.run(exercise())
    assert crashed_claim is not None and crashed_claim.action == "submit"
    assert after_lookup == "pending"
    assert sorted(resubmits) == ["resolved", "skipped"]
    assert len(adapter.calls) == 1
    assert intent.state == "resolved"
    assert actions == ("submit", "query", "submit")
    assert outcomes == ("not_found", "submitted")


@pytest.mark.parametrize("actor_change", ({}, {"status": "disabled"}, {"role": "driver"}))
def test_provider_response_lost_before_db_commit_recovers_by_query_without_resubmit(
    postgis_db_sessionmaker,
    monkeypatch,
    actor_change,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r20-post-call-{uuid4().hex[:8]}")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(postgis_db_sessionmaker, graph, adapter)
        intent_id = intent_ids[0]
        monkeypatch.setattr(
            disbursement_service, "DISBURSEMENT_CLAIM_LEASE", timedelta(microseconds=-1)
        )
        abandoned_claim = await claim_payout_submission_intent(
            postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
        )
        assert abandoned_claim is not None
        receipt = await adapter.submit_batch(
            batch_id=str(abandoned_claim.batch_id),
            instructions=(
                disbursement_service.DisbursementInstruction(
                    line_id=str(abandoned_claim.line_id),
                    idempotency_key=abandoned_claim.idempotency_key,
                    instruction=abandoned_claim.instruction,
                    instruction_fingerprint=abandoned_claim.instruction_fingerprint,
                ),
            ),
        )
        monkeypatch.setattr(
            disbursement_service, "DISBURSEMENT_CLAIM_LEASE", DISBURSEMENT_CLAIM_LEASE
        )
        if actor_change:
            async with postgis_db_sessionmaker() as session:
                await session.execute(
                    update(User).where(User.id == graph.admin.id).values(**actor_change)
                )
                await session.commit()
        resolver_holds_batch = asyncio.Event()
        release_resolver = asyncio.Event()
        contender_pid_ready = asyncio.Event()
        contender_pid: list[int] = []
        first_batch_locks = 0
        original_lock_batch = disbursement_service._locked_batch_with_lines
        original_require_admin = disbursement_service.require_active_admin

        async def controlled_batch_lock(session, batch_id):
            nonlocal first_batch_locks
            result = await original_lock_batch(session, batch_id)
            task = asyncio.current_task()
            if task is not None and task.get_name() == "r20-first-recovery":
                first_batch_locks += 1
                if first_batch_locks == 2:
                    # The query claim committed; resolution now holds the batch.
                    resolver_holds_batch.set()
                    await release_resolver.wait()
            return result

        async def capture_contender_pid(session, actor_user_id):
            task = asyncio.current_task()
            if (
                task is not None
                and task.get_name() == "r20-contending-recovery"
                and not contender_pid
            ):
                contender_pid.append(await session.scalar(select(func.pg_backend_pid())))
                contender_pid_ready.set()
            return await original_require_admin(session, actor_user_id)

        async def observe_contender_lock_wait():
            await contender_pid_ready.wait()
            async with postgis_db_sessionmaker() as probe:
                while not await probe.scalar(
                    select(func.cardinality(func.pg_blocking_pids(contender_pid[0])))
                ):
                    # Each real catalog query yields to the competing transaction.
                    pass

        monkeypatch.setattr(disbursement_service, "_locked_batch_with_lines", controlled_batch_lock)
        monkeypatch.setattr(disbursement_service, "require_active_admin", capture_contender_pid)
        first = asyncio.create_task(
            process_payout_submission_intent(
                postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
            ),
            name="r20-first-recovery",
        )
        workers = [first]
        try:
            await asyncio.wait_for(resolver_holds_batch.wait(), timeout=10)
            workers.append(
                asyncio.create_task(
                    process_payout_submission_intent(
                        postgis_db_sessionmaker, intent_id=intent_id, adapter=adapter
                    ),
                    name="r20-contending-recovery",
                )
            )
            await asyncio.wait_for(observe_contender_lock_wait(), timeout=10)
            release_resolver.set()
            recoveries = await asyncio.wait_for(asyncio.gather(*workers), timeout=10)
        finally:
            release_resolver.set()
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        stale_result = await _resolve_payout_submission_claim(
            postgis_db_sessionmaker,
            claim=abandoned_claim,
            observation=DisbursementClaimObservation(
                outcome=PayoutSubmissionObservationOutcome.SUBMITTED,
                provider_submission_reference=receipt.provider_reference,
                provider_transfer_reference=receipt.line_references[str(abandoned_claim.line_id)],
            ),
        )
        async with postgis_db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            actions = tuple(
                await session.scalars(
                    select(PayoutSubmissionAttempt.action)
                    .where(PayoutSubmissionAttempt.intent_id == intent_id)
                    .order_by(PayoutSubmissionAttempt.generation)
                )
            )
            outcomes = tuple(
                await session.scalars(
                    select(PayoutSubmissionObservation.outcome)
                    .where(PayoutSubmissionObservation.intent_id == intent_id)
                    .order_by(PayoutSubmissionObservation.generation)
                )
            )
            audits = tuple(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "admin.payout_batch.submitted",
                        AuditEvent.entity_id == str(abandoned_claim.batch_id),
                    )
                )
            )
            assert len(audits) == 1
            assert audits[0].actor_user_id == graph.admin.id
            assert audits[0].entity_type == "payout_batch"
            assert audits[0].event_metadata == {"line_count": 1}
            return recoveries, stale_result, intent, actions, outcomes

    recoveries, stale_result, intent, actions, outcomes = asyncio.run(exercise())
    assert sorted(recoveries) == ["resolved", "skipped"]
    assert stale_result == "stale"
    assert len(adapter.calls) == 1
    assert intent.state == "resolved"
    assert actions == ("submit", "query")
    assert outcomes == ("found",)


@pytest.mark.parametrize("change", ("missing_intent", "requester_changed"))
def test_resolution_revalidates_prelocked_requester_before_mutation(
    postgis_db_sessionmaker, monkeypatch, change
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r20-actor-guard-{uuid4().hex[:8]}")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        batch_id, _, intent_ids = await _prepare_batch(postgis_db_sessionmaker, graph, adapter)
        claim = await claim_payout_submission_intent(
            postgis_db_sessionmaker, intent_id=intent_ids[0], adapter=adapter
        )
        assert claim is not None
        original_lock_batch = disbursement_service._locked_batch_with_lines

        async def change_requester_after_prelock(session, locked_batch_id):
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == intent_ids[0])
                .values(requested_by_user_id=graph.driver.id)
            )
            return await original_lock_batch(session, locked_batch_id)

        if change == "missing_intent":
            claim = replace(claim, intent_id=uuid4())
        else:
            monkeypatch.setattr(
                disbursement_service, "_locked_batch_with_lines", change_requester_after_prelock
            )
        result = await _resolve_payout_submission_claim(
            postgis_db_sessionmaker,
            claim=claim,
            observation=DisbursementClaimObservation(
                outcome=PayoutSubmissionObservationOutcome.UNKNOWN,
            ),
        )
        async with postgis_db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_ids[0])
            assert intent.state == "claimed"
            assert intent.requested_by_user_id == graph.admin.id
            assert (
                await session.scalar(
                    select(func.count(PayoutSubmissionObservation.id)).where(
                        PayoutSubmissionObservation.intent_id == intent.id
                    )
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.payout_batch.submitted",
                        AuditEvent.entity_id == str(batch_id),
                    )
                )
                == 0
            )
        return result

    assert asyncio.run(exercise()) == "stale"
    assert adapter.calls == []


def test_current_database_guards_and_model_have_no_owned_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def exercise() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO payout_submission_intents "
                        "(id, payout_batch_line_id, provider_name, idempotency_key, instruction, "
                        "instruction_fingerprint, requested_by_user_id, state, generation) VALUES "
                        "('83000000-0000-0000-0000-000000000001', "
                        "'83000000-0000-0000-0000-000000000002', 'fake', repeat('a', 64), "
                        "'{}'::jsonb, repeat('b', 64), "
                        "'83000000-0000-0000-0000-000000000003', 'pending', 0)"
                    )
                )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE payout_submission_intents SET state = 'claimed', generation = 1, "
                        "claim_token = '83000000-0000-0000-0000-000000000004', "
                        "claim_action = 'submit', claim_expires_at = now() + interval '2 minutes' "
                        "WHERE id = '83000000-0000-0000-0000-000000000001'"
                    )
                )
            with pytest.raises(DBAPIError, match="state transition is invalid"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payout_submission_intents SET "
                            "claim_token = '83000000-0000-0000-0000-000000000005' "
                            "WHERE id = '83000000-0000-0000-0000-000000000001'"
                        )
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO payout_submission_attempts "
                        "(id, intent_id, generation, claim_token, action, idempotency_key, "
                        "instruction_fingerprint) VALUES "
                        "('83000000-0000-0000-0000-000000000006', "
                        "'83000000-0000-0000-0000-000000000001', 1, "
                        "'83000000-0000-0000-0000-000000000004', 'submit', "
                        "repeat('a', 64), repeat('b', 64))"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO payout_submission_observations "
                        "(attempt_id, intent_id, generation, idempotency_key, "
                        "instruction_fingerprint, outcome, evidence_fingerprint, observed_at) "
                        "VALUES ('83000000-0000-0000-0000-000000000006', "
                        "'83000000-0000-0000-0000-000000000001', 1, repeat('a', 64), "
                        "repeat('b', 64), 'unknown', repeat('c', 64), now())"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payout_submission_attempts SET action = 'query' "
                            "WHERE id = '83000000-0000-0000-0000-000000000006'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM payout_submission_observations "
                            "WHERE attempt_id = '83000000-0000-0000-0000-000000000006'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM payout_submission_intents "
                            "WHERE id = '83000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    async def compare_owned() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                diffs = await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={"compare_type": False, "compare_server_default": False},
                        ),
                        Base.metadata,
                    )
                )
            return [
                diff
                for diff in diffs
                if any(
                    name in repr(diff)
                    for name in (
                        "payout_submission_intents",
                        "payout_submission_attempts",
                        "payout_submission_observations",
                    )
                )
            ]
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0106_development_baseline", monkeypatch)
        asyncio.run(exercise())
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(compare_owned()) == []
    finally:
        asyncio.run(drop_database(migration_url))
