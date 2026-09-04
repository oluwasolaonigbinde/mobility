from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from redis import Redis
from sqlalchemy import func, select, update
from worker_recovery_harness import (
    DurableStorageProvider,
    WorkerProcessHarness,
)

from app.adapters.disbursement import FakeDisbursementAdapter
from app.models.audit import AuditEvent
from app.models.disbursement import (
    PayoutBatchLine,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
    PayoutSubmissionObservation,
)
from app.models.notification import Notification
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.report_issuance import (
    ReportArtifact,
    ReportIssuance,
    ReportPublicationIntent,
)
from app.models.stored_file import StoredObjectDeletion
from app.services.fraud_holds import lock_fraud_hold_scope
from app.services.stored_object_deletions import ensure_stored_object_deletion
from app.services.trip_processing import AUDIT_ACTION_TRIP_PROCESSING
from tests.test_disbursement_worker import _prepare_batch
from tests.test_mny03a_earnings_release import (
    build_graph as build_release_graph,
)
from tests.test_mny03a_earnings_release import (
    create_ledger,
    seed_assessment_authority,
)
from tests.test_report_issuances import issue_run, request_issuance
from tests.test_trip_processing import (
    BASE_TIME,
    add_pings,
    create_test_payout_rule,
    moving_points,
)
from tests.test_trip_processing import (
    build_graph as build_trip_graph,
)

RECEIPT_FIELDS = {
    "scenario",
    "pid",
    "signal",
    "job",
    "idempotency_key",
    "queue_state",
    "db_state",
    "external_effect_state",
    "cursor_deadletter_state",
    "terminal_convergence",
}


@pytest.fixture
def r58_redis_url() -> str:
    redis_url = os.environ.get("ARQ_TEST_REDIS_URL")
    authority = os.environ.get("REQUIRE_REAL_INTEGRATIONS") == "1" or bool(os.environ.get("CI"))
    if not redis_url:
        if authority:
            pytest.fail("ARQ_TEST_REDIS_URL is required by the R58 CI recovery lane")
        pytest.skip("R58 real Redis is not configured")
    client = Redis.from_url(redis_url)
    try:
        client.ping()
    except Exception as exc:
        pytest.fail(f"R58 real Redis is unavailable: {type(exc).__name__}: {exc}")
    finally:
        client.close()
    return redis_url


def _database_coordinates(sessionmaker) -> tuple[str, str]:
    engine = sessionmaker.kw["bind"]
    database_url = engine.url.render_as_string(hide_password=False)
    schema_name = engine.get_execution_options()["schema_translate_map"][None]
    return database_url, schema_name


def _harness(*, tmp_path, redis_url, sessionmaker, settings, scenario) -> WorkerProcessHarness:
    database_url, schema_name = _database_coordinates(sessionmaker)
    return WorkerProcessHarness(
        tmp_path=tmp_path,
        redis_url=redis_url,
        database_url=database_url,
        schema_name=schema_name,
        settings=settings,
        scenario=scenario,
    )


def _assert_crashed_queue(queue_state: dict) -> None:
    assert queue_state["queued"] is True
    assert queue_state["in_progress"] is True
    assert queue_state["payload_present"] is True
    assert queue_state["retry_count"] >= 1
    assert queue_state["result_present"] is False


def _assert_terminal_queue(queue_state: dict) -> None:
    assert queue_state == {
        "queued": False,
        "in_progress": False,
        "payload_present": False,
        "retry_count": 0,
        "result_present": False,
    }


def _assert_receipt(receipt: dict, *, scenario: str) -> None:
    assert set(receipt) == RECEIPT_FIELDS
    assert receipt["scenario"] == scenario
    assert receipt["pid"] > 0
    assert receipt["signal"] == "SIGKILL"
    assert receipt["job"]
    assert receipt["idempotency_key"]
    assert receipt["terminal_convergence"]["converged"] is True


async def _earnings_state(sessionmaker, trip_ids: list[UUID]) -> dict:
    async with sessionmaker() as session:
        statuses = dict(
            (
                await session.execute(
                    select(
                        EarningsLedgerEntry.trip_session_id,
                        EarningsLedgerEntry.status,
                    ).where(EarningsLedgerEntry.trip_session_id.in_(trip_ids))
                )
            ).all()
        )
        audits = {
            trip_id: int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "worker.earnings.released",
                        AuditEvent.entity_id == str(trip_id),
                    )
                )
                or 0
            )
            for trip_id in trip_ids
        }
        notices = int(
            await session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.payload["trip_session_id"]
                    .as_string()
                    .in_([str(trip_id) for trip_id in trip_ids])
                )
            )
            or 0
        )
        return {
            "statuses": {str(key): value for key, value in statuses.items()},
            "release_audits": {str(key): value for key, value in audits.items()},
            "release_notices": notices,
        }


def test_earnings_release_recovers_after_claim_and_after_one_committed_item(
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    claimed_graph = build_release_graph(postgis_db_sessionmaker, "r58-claimed")
    seed_assessment_authority(postgis_db_sessionmaker, claimed_graph, settings)
    claimed_entry = create_ledger(postgis_db_sessionmaker, claimed_graph)
    claimed = _harness(
        tmp_path=tmp_path / "after-claim",
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="earnings-after-claim",
    )
    try:
        claimed.enqueue(
            "r58_earnings_release",
            job_id=f"r58-earnings-claim-{uuid4().hex}",
        )
        claimed.start(barrier_point="earnings_after_claim")
        claimed.wait_for("earnings_after_claim")
        claimed_pid = claimed.kill()
        crashed_queue = asdict(claimed.queue_state())
        _assert_crashed_queue(crashed_queue)
        pending_state = asyncio.run(
            _earnings_state(postgis_db_sessionmaker, [claimed_graph.trip.id])
        )
        assert pending_state["statuses"] == {str(claimed_graph.trip.id): "pending"}
        claimed.unlock_dead_worker()
        claimed.finish()
        final_queue = asdict(claimed.queue_state())
        _assert_terminal_queue(final_queue)
        final_state = asyncio.run(_earnings_state(postgis_db_sessionmaker, [claimed_graph.trip.id]))
        assert final_state == {
            "statuses": {str(claimed_graph.trip.id): "available"},
            "release_audits": {str(claimed_graph.trip.id): 1},
            "release_notices": 1,
        }
        receipt = claimed.persist_receipt(
            name="earnings_after_claim",
            pid=claimed_pid,
            idempotency_key=str(claimed_entry.id),
            queue_state={"after_kill": crashed_queue, "terminal": final_queue},
            db_state={"after_kill": pending_state, "terminal": final_state},
            cursor_deadletter_state={"deadlettered": False, "cursor": None},
            terminal_convergence={"converged": True, "duplicate_releases": 0},
        )
        _assert_receipt(receipt, scenario="earnings_after_claim")
    finally:
        claimed.close()

    committed_graphs = sorted(
        [
            build_release_graph(postgis_db_sessionmaker, "r58-first-commit"),
            build_release_graph(postgis_db_sessionmaker, "r58-tail-commit"),
        ],
        key=lambda graph: graph.trip.id,
    )
    for graph in committed_graphs:
        seed_assessment_authority(postgis_db_sessionmaker, graph, settings)
        create_ledger(postgis_db_sessionmaker, graph)
    first, tail = committed_graphs
    committed = _harness(
        tmp_path=tmp_path / "after-one-commit",
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="earnings-after-one-commit",
    )
    committed.enqueue(
        "r58_earnings_release",
        job_id=f"r58-earnings-commit-{uuid4().hex}",
    )

    async def crash_between_commits() -> tuple[int, dict, dict]:
        async with postgis_db_sessionmaker() as lock_session:
            await lock_fraud_hold_scope(lock_session, tail.trip.id)
            committed.start(barrier_point=None)
            committed.wait_for("broker_claimed")
            async with asyncio.timeout(30):
                while True:
                    state = await _earnings_state(
                        postgis_db_sessionmaker,
                        [first.trip.id, tail.trip.id],
                    )
                    if state["statuses"].get(str(first.trip.id)) == "available":
                        break
            assert state["statuses"][str(tail.trip.id)] == "pending"
            pid = committed.kill()
            queue = asdict(committed.queue_state())
            await lock_session.rollback()
            return pid, queue, state

    try:
        committed_pid, committed_queue, one_committed_state = asyncio.run(crash_between_commits())
        _assert_crashed_queue(committed_queue)
        committed.unlock_dead_worker()
        committed.finish()
        committed_final_queue = asdict(committed.queue_state())
        _assert_terminal_queue(committed_final_queue)
        committed_final_state = asyncio.run(
            _earnings_state(
                postgis_db_sessionmaker,
                [first.trip.id, tail.trip.id],
            )
        )
        assert set(committed_final_state["statuses"].values()) == {"available"}
        assert set(committed_final_state["release_audits"].values()) == {1}
        assert committed_final_state["release_notices"] == 2
        receipt = committed.persist_receipt(
            name="earnings_after_one_commit",
            pid=committed_pid,
            idempotency_key=f"{first.trip.id}:{tail.trip.id}",
            queue_state={
                "after_kill": committed_queue,
                "terminal": committed_final_queue,
            },
            db_state={
                "after_kill": one_committed_state,
                "terminal": committed_final_state,
            },
            cursor_deadletter_state={"deadlettered": False, "cursor": None},
            terminal_convergence={"converged": True, "duplicate_releases": 0},
        )
        _assert_receipt(receipt, scenario="earnings_after_one_commit")
    finally:
        committed.close()


async def _payout_state(sessionmaker, intent_id: UUID, line_id: UUID) -> dict:
    async with sessionmaker() as session:
        intent = await session.get(PayoutSubmissionIntent, intent_id)
        line = await session.get(PayoutBatchLine, line_id)
        attempts = int(
            await session.scalar(
                select(func.count(PayoutSubmissionAttempt.id)).where(
                    PayoutSubmissionAttempt.intent_id == intent_id
                )
            )
            or 0
        )
        observations = int(
            await session.scalar(
                select(func.count(PayoutSubmissionObservation.id)).where(
                    PayoutSubmissionObservation.intent_id == intent_id
                )
            )
            or 0
        )
        return {
            "intent_state": intent.state,
            "intent_generation": intent.generation,
            "line_state": line.status,
            "attempts": attempts,
            "observations": observations,
            "idempotency_key": intent.idempotency_key,
        }


async def _expire_payout_claim(sessionmaker, intent_id: UUID) -> None:
    async with sessionmaker() as session:
        await session.execute(
            update(PayoutSubmissionIntent)
            .where(PayoutSubmissionIntent.id == intent_id)
            .values(claim_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()


def test_payout_recovers_provider_acceptance_and_post_commit_broker_orphan(
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    graph = build_release_graph(postgis_db_sessionmaker, f"r58-payout-{uuid4().hex[:8]}")
    _, line_ids, intent_ids = asyncio.run(
        _prepare_batch(
            postgis_db_sessionmaker,
            graph,
            FakeDisbursementAdapter(),
        )
    )
    intent_id, line_id = intent_ids[0], line_ids[0]
    before_commit = _harness(
        tmp_path=tmp_path / "provider-before-commit",
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="payout-provider-before-commit",
    )
    try:
        before_commit.enqueue(
            "r58_payout_submission",
            str(intent_id),
            job_id=f"r58-payout-provider-{uuid4().hex}",
        )
        before_commit.start(barrier_point="payout_after_provider_acceptance")
        before_commit.wait_for("payout_after_provider_acceptance")
        provider_pid = before_commit.kill()
        provider_queue = asdict(before_commit.queue_state())
        _assert_crashed_queue(provider_queue)
        provider_db = asyncio.run(_payout_state(postgis_db_sessionmaker, intent_id, line_id))
        assert provider_db["intent_state"] == "claimed"
        assert provider_db["line_state"] == "reserved"
        assert provider_db["attempts"] == 1
        assert provider_db["observations"] == 0
        assert len(before_commit.effects()["payout_effects"]) == 1

        asyncio.run(_expire_payout_claim(postgis_db_sessionmaker, intent_id))
        before_commit.unlock_dead_worker()
        before_commit.finish()
        provider_final_queue = asdict(before_commit.queue_state())
        _assert_terminal_queue(provider_final_queue)
        provider_final_db = asyncio.run(_payout_state(postgis_db_sessionmaker, intent_id, line_id))
        assert provider_final_db["intent_state"] == "resolved"
        assert provider_final_db["line_state"] == "submitted"
        effects = before_commit.effects()
        assert len(effects["payout_effects"]) == 1
        assert effects["payout_submit_requests"] == 1
        assert effects["payout_lookup_requests"] == 1
        receipt = before_commit.persist_receipt(
            name="payout_provider_before_commit",
            pid=provider_pid,
            idempotency_key=provider_db["idempotency_key"],
            queue_state={
                "after_kill": provider_queue,
                "terminal": provider_final_queue,
            },
            db_state={"after_kill": provider_db, "terminal": provider_final_db},
            cursor_deadletter_state={"deadlettered": False, "cursor": None},
            terminal_convergence={"converged": True, "cash_effect_count": 1},
        )
        _assert_receipt(receipt, scenario="payout_provider_before_commit")
    finally:
        before_commit.close()

    committed_graph = build_release_graph(
        postgis_db_sessionmaker, f"r58-payout-ack-{uuid4().hex[:8]}"
    )
    _, committed_lines, committed_intents = asyncio.run(
        _prepare_batch(
            postgis_db_sessionmaker,
            committed_graph,
            FakeDisbursementAdapter(),
        )
    )
    committed_intent, committed_line = committed_intents[0], committed_lines[0]
    before_ack = _harness(
        tmp_path=tmp_path / "commit-before-ack",
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="payout-commit-before-ack",
    )
    try:
        before_ack.enqueue(
            "r58_payout_submission",
            str(committed_intent),
            job_id=f"r58-payout-ack-{uuid4().hex}",
        )
        before_ack.start(barrier_point="payout_after_local_commit")
        before_ack.wait_for("payout_after_local_commit")
        ack_pid = before_ack.kill()
        ack_queue = asdict(before_ack.queue_state())
        _assert_crashed_queue(ack_queue)
        ack_db = asyncio.run(
            _payout_state(postgis_db_sessionmaker, committed_intent, committed_line)
        )
        assert ack_db["intent_state"] == "resolved"
        assert ack_db["line_state"] == "submitted"
        before_ack.unlock_dead_worker()
        before_ack.finish()
        ack_final_queue = asdict(before_ack.queue_state())
        _assert_terminal_queue(ack_final_queue)
        ack_final_db = asyncio.run(
            _payout_state(postgis_db_sessionmaker, committed_intent, committed_line)
        )
        assert ack_final_db == ack_db
        ack_effects = before_ack.effects()
        assert len(ack_effects["payout_effects"]) == 1
        assert ack_effects["payout_submit_requests"] == 1
        assert ack_effects["payout_lookup_requests"] == 0
        receipt = before_ack.persist_receipt(
            name="payout_commit_before_ack",
            pid=ack_pid,
            idempotency_key=ack_db["idempotency_key"],
            queue_state={"after_kill": ack_queue, "terminal": ack_final_queue},
            db_state={"after_kill": ack_db, "terminal": ack_final_db},
            cursor_deadletter_state={"deadlettered": False, "cursor": None},
            terminal_convergence={"converged": True, "cash_effect_count": 1},
        )
        _assert_receipt(receipt, scenario="payout_commit_before_ack")
    finally:
        before_ack.close()


async def _deletion_state(sessionmaker, intent_id: UUID) -> dict:
    async with sessionmaker() as session:
        intent = await session.get(StoredObjectDeletion, intent_id)
        return {
            "state": intent.state,
            "attempts": intent.attempts,
            "provider_deleted": intent.provider_deleted_at is not None,
            "completed": intent.completed_at is not None,
            "request_fingerprint": intent.request_fingerprint,
        }


def test_deletion_recovers_after_object_delete_before_metadata_finality(
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    harness = _harness(
        tmp_path=tmp_path,
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="deletion-object-before-finality",
    )
    storage_key = f"managed/r58/{uuid4().hex}/private-object"
    content = b"r58 private deletion evidence"
    checksum = hashlib.sha256(content).hexdigest()
    storage_config = {
        "effect_root": str(harness.effect_root),
        "redis_url": r58_redis_url,
        "event_key": harness.event_key,
        "release_key": harness.release_key,
        "barrier_point": None,
    }
    asyncio.run(
        DurableStorageProvider(storage_config).put(
            object_key=storage_key,
            content_type="application/octet-stream",
            data=content,
            checksum_sha256=checksum,
        )
    )

    async def seed() -> tuple[UUID, str]:
        async with postgis_db_sessionmaker() as session:
            intent = await ensure_stored_object_deletion(
                session,
                storage_key=storage_key,
                object_checksum_sha256=checksum,
                reason="r58_worker_recovery",
                owner_type="r58_synthetic_private_object",
                owner_id=uuid4(),
                organization_id=uuid4(),
                subject_user_id=None,
            )
            await session.commit()
            return intent.id, intent.request_fingerprint

    intent_id, request_fingerprint = asyncio.run(seed())
    try:
        harness.enqueue(
            "r58_object_deletion",
            job_id=f"r58-deletion-{uuid4().hex}",
        )
        harness.start(barrier_point="deletion_after_object_delete")
        harness.wait_for("deletion_after_object_delete")
        pid = harness.kill()
        queue = asdict(harness.queue_state())
        _assert_crashed_queue(queue)
        crashed_db = asyncio.run(_deletion_state(postgis_db_sessionmaker, intent_id))
        assert crashed_db["state"] == "pending"
        assert not harness.effects()["objects"]
        assert harness.effects()["delete_effects"] == 1

        harness.unlock_dead_worker()
        harness.finish()
        final_queue = asdict(harness.queue_state())
        _assert_terminal_queue(final_queue)
        final_db = asyncio.run(_deletion_state(postgis_db_sessionmaker, intent_id))
        assert final_db["state"] == "completed"
        assert final_db["provider_deleted"] is True
        assert final_db["completed"] is True
        effects = harness.effects()
        assert effects["objects"] == {}
        assert effects["delete_effects"] == 1
        assert effects["delete_requests"] == 2
        receipt = harness.persist_receipt(
            name="deletion_object_before_finality",
            pid=pid,
            idempotency_key=request_fingerprint,
            queue_state={"after_kill": queue, "terminal": final_queue},
            db_state={"after_kill": crashed_db, "terminal": final_db},
            cursor_deadletter_state={"deadlettered": False, "cursor": None},
            terminal_convergence={
                "converged": True,
                "object_leaked": False,
                "false_finality": False,
            },
        )
        _assert_receipt(receipt, scenario="deletion_object_before_finality")
    finally:
        harness.close()


async def _report_state(sessionmaker, issuance_id: UUID) -> dict:
    async with sessionmaker() as session:
        issuance = await session.get(ReportIssuance, issuance_id)
        intents = list(
            await session.scalars(
                select(ReportPublicationIntent)
                .where(ReportPublicationIntent.report_issuance_id == issuance_id)
                .order_by(ReportPublicationIntent.generation)
            )
        )
        artifact_count = int(
            await session.scalar(
                select(func.count(ReportArtifact.id)).where(
                    ReportArtifact.report_issuance_id == issuance_id
                )
            )
            or 0
        )
        return {
            "issuance_state": issuance.status,
            "worker_attempts": issuance.worker_attempts,
            "artifact_count": artifact_count,
            "publication_states": [intent.state for intent in intents],
            "publication_generations": [intent.generation for intent in intents],
        }


async def _expire_report_leases(sessionmaker, issuance_id: UUID) -> None:
    expired = datetime.now(UTC) - timedelta(seconds=1)
    async with sessionmaker() as session:
        issuance = await session.get(ReportIssuance, issuance_id)
        issuance.lease_expires_at = expired
        intents = list(
            await session.scalars(
                select(ReportPublicationIntent).where(
                    ReportPublicationIntent.report_issuance_id == issuance_id
                )
            )
        )
        for intent in intents:
            if intent.state in {"prepared", "publishing", "cleaning"}:
                intent.lease_expires_at = expired
        await session.commit()


def _queued_report(postgis_db_client, postgis_db_sessionmaker) -> UUID:
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    response = request_issuance(postgis_db_client, advertiser, run["id"])
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


def test_report_publication_recovers_first_artifact_and_cleanup_transition(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    issuance_id = _queued_report(postgis_db_client, postgis_db_sessionmaker)
    harness = _harness(
        tmp_path=tmp_path,
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="report-artifact-and-cleanup",
    )
    try:
        harness.enqueue(
            "r58_report_publication",
            job_id=f"r58-report-orphan-{uuid4().hex}",
        )
        harness.start(barrier_point="report_after_first_artifact")
        harness.wait_for("report_after_first_artifact")
        artifact_pid = harness.kill()
        artifact_queue = asdict(harness.queue_state())
        _assert_crashed_queue(artifact_queue)
        artifact_db = asyncio.run(_report_state(postgis_db_sessionmaker, issuance_id))
        assert artifact_db["issuance_state"] == "processing"
        assert artifact_db["artifact_count"] == 0
        assert artifact_db["publication_states"] == ["publishing"]
        assert len(harness.effects()["objects"]) == 1

        asyncio.run(_expire_report_leases(postgis_db_sessionmaker, issuance_id))
        harness.unlock_dead_worker()
        harness.start(barrier_point="report_during_cleanup")
        harness.wait_for("report_during_cleanup")
        cleanup_pid = harness.kill()
        cleanup_queue = asdict(harness.queue_state())
        _assert_crashed_queue(cleanup_queue)
        cleanup_db = asyncio.run(_report_state(postgis_db_sessionmaker, issuance_id))
        assert cleanup_db["issuance_state"] == "processing"
        assert cleanup_db["publication_states"] == ["cleaning"]
        assert harness.effects()["objects"] == {}

        asyncio.run(_expire_report_leases(postgis_db_sessionmaker, issuance_id))
        harness.unlock_dead_worker()
        harness.finish()
        final_queue = asdict(harness.queue_state())
        _assert_terminal_queue(final_queue)
        final_db = asyncio.run(_report_state(postgis_db_sessionmaker, issuance_id))
        assert final_db["issuance_state"] == "ready"
        assert final_db["artifact_count"] == 2
        assert final_db["publication_states"] == ["cleaned", "complete"]
        assert final_db["publication_generations"] == [1, 2]
        assert len(harness.effects()["objects"]) == 2

        artifact_receipt = harness.persist_receipt(
            name="report_after_first_artifact",
            pid=artifact_pid,
            idempotency_key=str(issuance_id),
            queue_state={"after_kill": artifact_queue, "terminal": final_queue},
            db_state={"after_kill": artifact_db, "terminal": final_db},
            cursor_deadletter_state={
                "after_kill": ["publishing"],
                "terminal": ["cleaned", "complete"],
            },
            terminal_convergence={"converged": True, "orphan_count": 0},
        )
        _assert_receipt(artifact_receipt, scenario="report_after_first_artifact")
        cleanup_receipt = harness.persist_receipt(
            name="report_during_cleanup",
            pid=cleanup_pid,
            idempotency_key=str(issuance_id),
            queue_state={"after_kill": cleanup_queue, "terminal": final_queue},
            db_state={"after_kill": cleanup_db, "terminal": final_db},
            cursor_deadletter_state={
                "after_kill": ["cleaning"],
                "terminal": ["cleaned", "complete"],
            },
            terminal_convergence={"converged": True, "orphan_count": 0},
        )
        _assert_receipt(cleanup_receipt, scenario="report_during_cleanup")
    finally:
        harness.close()


def test_report_publication_commit_survives_broker_ack_loss(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    issuance_id = _queued_report(postgis_db_client, postgis_db_sessionmaker)
    harness = _harness(
        tmp_path=tmp_path,
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=settings,
        scenario="report-commit-before-ack",
    )
    try:
        harness.enqueue(
            "r58_report_publication",
            job_id=f"r58-report-commit-{uuid4().hex}",
        )
        harness.start(barrier_point="report_after_publication_commit")
        harness.wait_for("report_after_publication_commit")
        pid = harness.kill()
        queue = asdict(harness.queue_state())
        _assert_crashed_queue(queue)
        committed_db = asyncio.run(_report_state(postgis_db_sessionmaker, issuance_id))
        assert committed_db["issuance_state"] == "ready"
        assert committed_db["artifact_count"] == 2
        assert committed_db["publication_states"] == ["complete"]
        committed_effects = harness.effects()
        assert len(committed_effects["objects"]) == 2

        harness.unlock_dead_worker()
        harness.finish()
        final_queue = asdict(harness.queue_state())
        _assert_terminal_queue(final_queue)
        final_db = asyncio.run(_report_state(postgis_db_sessionmaker, issuance_id))
        assert final_db == committed_db
        assert harness.effects()["objects"] == committed_effects["objects"]
        receipt = harness.persist_receipt(
            name="report_commit_before_ack",
            pid=pid,
            idempotency_key=str(issuance_id),
            queue_state={"after_kill": queue, "terminal": final_queue},
            db_state={"after_kill": committed_db, "terminal": final_db},
            cursor_deadletter_state={"deadlettered": False, "publications": ["complete"]},
            terminal_convergence={"converged": True, "duplicate_artifacts": 0},
        )
        _assert_receipt(receipt, scenario="report_commit_before_ack")
    finally:
        harness.close()


async def _cursor_state(redis_url: str) -> str | None:
    from redis.asyncio import Redis as AsyncRedis

    from app.jobs.trip_processing import SWEEP_CURSOR_KEY

    redis = AsyncRedis.from_url(redis_url, decode_responses=True)
    try:
        return await redis.get(SWEEP_CURSOR_KEY)
    finally:
        await redis.aclose()


async def _trip_processing_state(sessionmaker, trip_ids: list[UUID]) -> dict:
    async with sessionmaker() as session:
        calculation_counts = {
            trip_id: int(
                await session.scalar(
                    select(func.count(PayoutCalculation.id)).where(
                        PayoutCalculation.trip_session_id == trip_id
                    )
                )
                or 0
            )
            for trip_id in trip_ids
        }
        ledger_counts = {
            trip_id: int(
                await session.scalar(
                    select(func.count(EarningsLedgerEntry.id)).where(
                        EarningsLedgerEntry.trip_session_id == trip_id
                    )
                )
                or 0
            )
            for trip_id in trip_ids
        }
        audit_counts = {
            trip_id: int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == AUDIT_ACTION_TRIP_PROCESSING,
                        AuditEvent.entity_id == str(trip_id),
                    )
                )
                or 0
            )
            for trip_id in trip_ids
        }
        return {
            "calculations": {str(key): value for key, value in calculation_counts.items()},
            "ledger_entries": {str(key): value for key, value in ledger_counts.items()},
            "processing_audits": {str(key): value for key, value in audit_counts.items()},
        }


def test_cursor_persistence_restart_reaches_tail_without_skips(
    postgis_db_sessionmaker,
    settings,
    r58_redis_url,
    tmp_path,
) -> None:
    batch_settings = settings.model_copy(update={"worker_sweep_batch_size": 2})
    graphs = []
    for index in range(3):
        graph = build_trip_graph(
            postgis_db_sessionmaker,
            f"r58c{index}-{uuid4().hex[:6]}",
            ended_at=BASE_TIME + timedelta(minutes=30 + index),
        )
        create_test_payout_rule(
            postgis_db_sessionmaker,
            campaign_id=graph.campaign.id,
            created_by_user_id=graph.admin.id,
            base_rate_per_km=10,
        )
        add_pings(
            postgis_db_sessionmaker,
            trip_id=graph.trip.id,
            points=moving_points(),
            idempotency_key=f"r58-cursor-{index}",
        )
        graphs.append(graph)
    trip_ids = [graph.trip.id for graph in graphs]
    harness = _harness(
        tmp_path=tmp_path,
        redis_url=r58_redis_url,
        sessionmaker=postgis_db_sessionmaker,
        settings=batch_settings,
        scenario="cursor-persist-before-ack",
    )
    try:
        harness.enqueue(
            "r58_cursor_sweep",
            job_id=f"r58-cursor-{uuid4().hex}",
        )
        harness.start(barrier_point="cursor_after_persist")
        event = harness.wait_for("cursor_after_persist")
        assert event["detail"] == {"processed": 2, "selected": 2}
        pid = harness.kill()
        queue = asdict(harness.queue_state())
        _assert_crashed_queue(queue)
        cursor_after_kill = asyncio.run(_cursor_state(r58_redis_url))
        assert cursor_after_kill is not None
        partial_db = asyncio.run(_trip_processing_state(postgis_db_sessionmaker, trip_ids))
        assert sorted(partial_db["calculations"].values()) == [0, 1, 1]

        harness.unlock_dead_worker()
        harness.finish()
        final_queue = asdict(harness.queue_state())
        _assert_terminal_queue(final_queue)
        assert asyncio.run(_cursor_state(r58_redis_url)) is None
        final_db = asyncio.run(_trip_processing_state(postgis_db_sessionmaker, trip_ids))
        assert set(final_db["calculations"].values()) == {1}
        assert set(final_db["ledger_entries"].values()) == {1}
        assert set(final_db["processing_audits"].values()) == {1}
        receipt = harness.persist_receipt(
            name="cursor_persist_before_ack",
            pid=pid,
            idempotency_key=harness.job_id or "",
            queue_state={"after_kill": queue, "terminal": final_queue},
            db_state={"after_kill": partial_db, "terminal": final_db},
            cursor_deadletter_state={
                "after_kill": cursor_after_kill,
                "terminal": None,
                "deadlettered": False,
            },
            terminal_convergence={
                "converged": True,
                "tail_items": 1,
                "skipped_items": 0,
                "duplicate_money_rows": 0,
            },
        )
        _assert_receipt(receipt, scenario="cursor_persist_before_ack")
    finally:
        harness.close()
