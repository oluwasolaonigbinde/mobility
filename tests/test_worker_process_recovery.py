from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
import redis
from arq.connections import RedisSettings, create_pool
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from test_measurement_runs import create_measurement_graph, issue_payload
from test_mny03a_earnings_release import (
    build_graph as build_release_graph,
)
from test_mny03a_earnings_release import (
    create_ledger,
    seed_assessment_authority,
)
from test_payout_batches import _seed_authority
from test_trip_processing import (
    add_pings,
    create_test_payout_rule,
    moving_points,
)
from test_trip_processing import (
    build_graph as build_trip_graph,
)
from worker_recovery_harness import (
    PersistentStorageProvider,
    RecoveryReceipt,
    read_provider_events,
)

from app.adapters.disbursement import FakeDisbursementAdapter
from app.core.config import Settings
from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.disbursement import (
    PayoutBatchLine,
    PayoutSubmissionIntent,
    PayoutSubmissionIntentState,
)
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.report_issuance import (
    ReportArtifact,
    ReportIssuance,
    ReportIssuanceStatus,
    ReportPublicationIntent,
)
from app.models.stored_file import StoredObjectDeletion
from app.models.trip import TripSession
from app.models.user import User, UserRole, UserStatus
from app.schemas.measurement import MeasurementRunCreate
from app.schemas.report_issuances import ReportIssuanceCreate
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    reserve_payout_batch,
    submit_payout_batch,
)
from app.services.measurement import issue_measurement_run
from app.services.report_issuances import (
    REPORT_MAX_ATTEMPTS,
    request_report_issuance,
)
from app.services.stored_object_deletions import ensure_stored_object_deletion

WORKER_SCRIPT = Path(__file__).with_name("worker_recovery_harness.py")
JOB_KEY_PREFIX = "arq:job:"
IN_PROGRESS_KEY_PREFIX = "arq:in-progress:"


def _integration_required() -> bool:
    return os.environ.get("CI") == "true" or os.environ.get("REQUIRE_REAL_INTEGRATIONS") == "1"


def _require_integration_url(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    message = f"{name} is required for real worker-process recovery evidence"
    if _integration_required():
        pytest.fail(message)
    pytest.skip(message)


def _redis_url_for_recovery(base_url: str) -> str:
    parsed = urlsplit(base_url)
    configured = os.environ.get("R58_REDIS_DB")
    database = int(configured) if configured is not None else 14
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment))


async def _create_database(base_url: str, database_name: str) -> str:
    parsed = make_url(base_url)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    database_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    maintenance = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with maintenance.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await maintenance.dispose()

    try:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                await connection.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()
    except Exception:
        await _drop_database(base_url, database_name)
        raise
    return database_url


async def _drop_database(base_url: str, database_name: str) -> None:
    parsed = make_url(base_url)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    maintenance = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with maintenance.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await maintenance.dispose()


@dataclass(slots=True)
class RecoveryEnvironment:
    database_url: str
    redis_url: str
    queue_name: str
    state_root: Path
    sessionmaker: async_sessionmaker[AsyncSession]
    engine: AsyncEngine
    processes: list[subprocess.Popen] = field(default_factory=list)

    @property
    def redis(self) -> redis.Redis:
        return redis.Redis.from_url(self.redis_url, decode_responses=True)

    def start_worker(self, cut_point: str = "") -> subprocess.Popen:
        environment = os.environ.copy()
        environment.update(
            {
                "R58_DATABASE_URL": self.database_url,
                "R58_REDIS_URL": self.redis_url,
                "R58_QUEUE_NAME": self.queue_name,
                "R58_STATE_ROOT": str(self.state_root),
                "R58_CUT_POINT": cut_point,
                "R58_IN_PROGRESS_SECONDS": "0.5",
                "PAYOUT_CRYPTO_KEYRING_B64": (
                    '{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}'
                ),
                "PYTHONPATH": os.pathsep.join(
                    filter(None, (str(WORKER_SCRIPT.parent.parent), environment.get("PYTHONPATH")))
                ),
            }
        )
        log_path = self.state_root / "worker-logs" / f"{cut_point or 'restart'}-{uuid4()}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as stream:
            process = subprocess.Popen(
                [sys.executable, str(WORKER_SCRIPT)],
                cwd=WORKER_SCRIPT.parent.parent,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        process.r58_log_path = log_path  # type: ignore[attr-defined]
        self.processes.append(process)
        return process

    def marker(self, cut_point: str) -> Path:
        return self.state_root / "markers" / f"{cut_point}.json"

    def wait_for_marker(self, process: subprocess.Popen, cut_point: str) -> dict:
        marker = self.marker(cut_point)
        self.wait_until(lambda: marker.exists(), process=process)
        return json.loads(marker.read_text(encoding="utf-8"))

    def wait_until(self, predicate, *, process: subprocess.Popen | None = None) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if predicate():
                return
            if process is not None and process.poll() is not None:
                log_path = process.r58_log_path  # type: ignore[attr-defined]
                pytest.fail(
                    f"worker {process.pid} exited {process.returncode} before the boundary:\n"
                    f"{log_path.read_text(encoding='utf-8')}"
                )
            time.sleep(0.02)
        detail = ""
        if process is not None:
            log_path = process.r58_log_path  # type: ignore[attr-defined]
            detail = f"\nworker log:\n{log_path.read_text(encoding='utf-8')}"
        pytest.fail(f"timed out waiting for worker recovery boundary{detail}")

    def kill(self, process: subprocess.Popen) -> int:
        os.kill(process.pid, signal.SIGKILL)
        return_code = process.wait(timeout=10)
        assert return_code == -signal.SIGKILL
        return -return_code

    def stop(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    def stop_all(self) -> None:
        for process in self.processes:
            self.stop(process)

    def queue_state(self, job_id: str) -> dict[str, object]:
        client = self.redis
        try:
            retry_count = client.get(f"arq:retry:{job_id}")
            return {
                "queued": client.zscore(self.queue_name, job_id) is not None,
                "in_progress": bool(client.exists(f"{IN_PROGRESS_KEY_PREFIX}{job_id}")),
                "job_definition": bool(client.exists(f"{JOB_KEY_PREFIX}{job_id}")),
                "retry_count": int(retry_count) if retry_count is not None else None,
            }
        finally:
            client.close()

    def wait_for_ack(self, process: subprocess.Popen, job_id: str) -> None:
        def acknowledged() -> bool:
            state = self.queue_state(job_id)
            return all(
                not state[field]
                for field in ("queued", "in_progress", "job_definition", "retry_count")
            )

        self.wait_until(
            acknowledged,
            process=process,
        )

    def cleanup_queue(self) -> None:
        client = self.redis
        try:
            job_ids = client.zrange(self.queue_name, 0, -1)
            if job_ids:
                client.zrem(self.queue_name, *job_ids)
                keys = [
                    key
                    for job_id in job_ids
                    for key in (
                        f"{JOB_KEY_PREFIX}{job_id}",
                        f"{IN_PROGRESS_KEY_PREFIX}{job_id}",
                        f"arq:retry:{job_id}",
                    )
                ]
                client.delete(*keys)
            client.delete(
                self.queue_name,
                f"{self.queue_name}:health-check",
                "worker:trip-processing:sweep-cursor:v1",
            )
        finally:
            client.close()


@pytest.fixture
def recovery_environment(tmp_path: Path):
    database_base = _require_integration_url("TEST_DATABASE_URL")
    redis_base = _require_integration_url("ARQ_TEST_REDIS_URL")
    database_name = f"r58_{uuid4().hex}"
    redis_url = _redis_url_for_recovery(redis_base)
    database_created = False
    try:
        database_url = asyncio.run(_create_database(database_base, database_name))
        database_created = True
        client = redis.Redis.from_url(redis_url)
        try:
            client.ping()
        finally:
            client.close()
    except Exception as exc:
        if database_created:
            asyncio.run(_drop_database(database_base, database_name))
        if _integration_required():
            pytest.fail(f"R58 requires reachable PostgreSQL and Redis: {exc!r}")
        pytest.skip(f"R58 PostgreSQL/Redis services are unavailable: {exc!r}")

    engine = create_async_engine(database_url, poolclass=NullPool)
    environment = RecoveryEnvironment(
        database_url=database_url,
        redis_url=redis_url,
        queue_name=f"arq:r58:{uuid4().hex}",
        state_root=tmp_path / "r58-state",
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
        engine=engine,
    )
    try:
        yield environment
    finally:
        try:
            environment.stop_all()
        finally:
            try:
                environment.cleanup_queue()
            finally:
                try:
                    asyncio.run(engine.dispose())
                finally:
                    asyncio.run(_drop_database(database_base, database_name))


def _runtime_settings(
    base: Settings,
    environment: RecoveryEnvironment,
    *,
    batch_size: int = 25,
) -> Settings:
    return base.model_copy(
        update={
            "database_url": environment.database_url,
            "redis_url": environment.redis_url,
            "privacy_disclosure_synthetic_test_mode": True,
            "privacy_collection_synthetic_test_mode": True,
            "privacy_min_vehicles_per_cell": 1,
            "privacy_min_trips_per_cell": 1,
            "privacy_min_days_per_cell": 1,
            "privacy_max_contributor_share": 1.0,
            "privacy_min_resolution_m": 50,
            "worker_sweep_batch_size": batch_size,
        }
    )


def _enqueue(
    environment: RecoveryEnvironment,
    function: str,
    job_id: str,
    *args: object,
) -> None:
    async def enqueue() -> None:
        pool = await create_pool(
            RedisSettings.from_dsn(environment.redis_url),
            default_queue_name=environment.queue_name,
        )
        try:
            job = await pool.enqueue_job(
                function,
                *args,
                _job_id=job_id,
                _queue_name=environment.queue_name,
            )
            assert job is not None
        finally:
            await pool.aclose()

    asyncio.run(enqueue())


def _enqueue_next_cron_occurrence(
    environment: RecoveryEnvironment,
    function: str,
    interrupted_job_id: str,
) -> str:
    recovery_job_id = f"{interrupted_job_id}:next:{uuid4()}"
    _enqueue(environment, function, recovery_job_id)
    return recovery_job_id


def _effect_count(environment: RecoveryEnvironment, event: str, **match: object) -> int:
    return sum(
        1
        for item in read_provider_events(environment.state_root)
        if item["event"] == event and all(item.get(key) == value for key, value in match.items())
    )


def _write_receipt(
    environment: RecoveryEnvironment,
    *,
    cut_point: str,
    process: subprocess.Popen,
    exit_signal: int,
    job_id: str,
    idempotency_key: str,
    queue_state: dict[str, object],
    database_state: dict[str, object],
    provider_effect_count: int,
    cursor_state: dict[str, object] | None = None,
    dead_letter_state: dict[str, object] | None = None,
    post_restart_convergence: dict[str, object],
) -> None:
    receipt = RecoveryReceipt(
        cut_point=cut_point,
        process_pid=process.pid,
        exit_signal=exit_signal,
        job_id=job_id,
        idempotency_key=idempotency_key,
        queue_state=queue_state,
        database_state=database_state,
        provider_effect_count=provider_effect_count,
        cursor_state=cursor_state or {},
        dead_letter_state=dead_letter_state or {},
        post_restart_convergence=post_restart_convergence,
    )
    receipt_path = environment.state_root / "receipts" / f"{cut_point}.json"
    receipt.write(receipt_path)
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == asdict(receipt)


def test_earnings_release_recovers_after_claim_and_between_committed_members(
    recovery_environment: RecoveryEnvironment,
    settings: Settings,
) -> None:
    runtime = _runtime_settings(settings, recovery_environment)
    claim_graph = build_release_graph(
        recovery_environment.sessionmaker, f"r58-claim-{uuid4().hex[:8]}"
    )
    seed_assessment_authority(recovery_environment.sessionmaker, claim_graph, runtime)
    claim_entry = create_ledger(recovery_environment.sessionmaker, claim_graph)
    claim_job_id = f"r58:earnings:claim:{claim_graph.trip.id}"
    _enqueue(
        recovery_environment,
        "cron:sweep_earnings_release_reviews",
        claim_job_id,
    )
    claimed_worker = recovery_environment.start_worker("earnings_after_claim")
    marker = recovery_environment.wait_for_marker(claimed_worker, "earnings_after_claim")
    claimed_queue = recovery_environment.queue_state(claim_job_id)

    async def claim_state() -> str:
        async with recovery_environment.sessionmaker() as session:
            return (await session.get(EarningsLedgerEntry, claim_entry.id)).status

    assert marker["pid"] == claimed_worker.pid
    assert claimed_queue == {
        "queued": True,
        "in_progress": True,
        "job_definition": True,
        "retry_count": 1,
    }
    assert asyncio.run(claim_state()) == "pending"
    exit_signal = recovery_environment.kill(claimed_worker)
    restarted = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restarted, claim_job_id)
    assert asyncio.run(claim_state()) == "pending"
    assert _effect_count(recovery_environment, "job_started", job_id=claim_job_id) == 1
    claim_recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:sweep_earnings_release_reviews",
        claim_job_id,
    )
    recovery_environment.wait_for_ack(restarted, claim_recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=claim_recovery_job_id) == 1
    assert asyncio.run(claim_state()) == "available"
    _write_receipt(
        recovery_environment,
        cut_point="earnings_after_claim",
        process=claimed_worker,
        exit_signal=exit_signal,
        job_id=claim_job_id,
        idempotency_key=claim_job_id,
        queue_state=claimed_queue,
        database_state={"ledger_status": "pending"},
        provider_effect_count=0,
        post_restart_convergence={
            "recovery_job_id": claim_recovery_job_id,
            "ledger_status": "available",
            "stranded": False,
        },
    )
    recovery_environment.stop(restarted)

    graphs = [
        build_release_graph(
            recovery_environment.sessionmaker,
            f"r58-member-{index}-{uuid4().hex[:8]}",
        )
        for index in range(2)
    ]
    entries = []
    for graph in graphs:
        seed_assessment_authority(recovery_environment.sessionmaker, graph, runtime)
        entries.append(create_ledger(recovery_environment.sessionmaker, graph))
    ordered = sorted(zip(graphs, entries, strict=True), key=lambda item: item[0].trip.id)
    first_graph, first_entry = ordered[0]
    second_graph, second_entry = ordered[1]
    lock_ready = threading.Event()
    release_lock = threading.Event()

    def hold_second_trip() -> None:
        async def hold() -> None:
            async with recovery_environment.sessionmaker() as session:
                async with session.begin():
                    await session.execute(
                        select(TripSession.id)
                        .where(TripSession.id == second_graph.trip.id)
                        .with_for_update()
                    )
                    lock_ready.set()
                    await asyncio.to_thread(release_lock.wait)

        asyncio.run(hold())

    lock_thread = threading.Thread(target=hold_second_trip, daemon=True)
    lock_thread.start()
    assert lock_ready.wait(timeout=10)
    member_job_id = f"r58:earnings:members:{uuid4()}"
    _enqueue(
        recovery_environment,
        "cron:sweep_earnings_release_reviews",
        member_job_id,
    )
    member_worker = recovery_environment.start_worker()

    async def member_states() -> tuple[str, str]:
        async with recovery_environment.sessionmaker() as session:
            first = await session.get(EarningsLedgerEntry, first_entry.id)
            second = await session.get(EarningsLedgerEntry, second_entry.id)
            return first.status, second.status

    recovery_environment.wait_until(
        lambda: asyncio.run(member_states()) == ("available", "pending"),
        process=member_worker,
    )
    member_queue = recovery_environment.queue_state(member_job_id)
    member_signal = recovery_environment.kill(member_worker)
    release_lock.set()
    lock_thread.join(timeout=10)
    assert not lock_thread.is_alive()
    member_restart = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(member_restart, member_job_id)
    assert asyncio.run(member_states()) == ("available", "pending")
    assert _effect_count(recovery_environment, "job_started", job_id=member_job_id) == 1
    member_recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:sweep_earnings_release_reviews",
        member_job_id,
    )
    recovery_environment.wait_for_ack(member_restart, member_recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=member_recovery_job_id) == 1
    assert asyncio.run(member_states()) == ("available", "available")

    async def release_audits() -> int:
        async with recovery_environment.sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "worker.earnings.released",
                        AuditEvent.entity_id.in_(
                            [str(first_graph.trip.id), str(second_graph.trip.id)]
                        ),
                    )
                )
                or 0
            )

    assert asyncio.run(release_audits()) == 2
    _write_receipt(
        recovery_environment,
        cut_point="earnings_after_one_committed_member",
        process=member_worker,
        exit_signal=member_signal,
        job_id=member_job_id,
        idempotency_key=member_job_id,
        queue_state=member_queue,
        database_state={"first": "available", "second": "pending"},
        provider_effect_count=0,
        post_restart_convergence={
            "recovery_job_id": member_recovery_job_id,
            "first": "available",
            "second": "available",
            "release_audits": 2,
            "duplicate_release": False,
        },
    )


def _seed_payout_intent(
    environment: RecoveryEnvironment,
    tag: str,
) -> tuple[UUID, str, UUID]:
    graph = build_release_graph(environment.sessionmaker, tag)

    async def seed() -> tuple[UUID, str, UUID]:
        checker = User(
            email=f"r58-checker-{uuid4().hex}@example.com",
            password_hash=graph.admin.password_hash,
            full_name="R58 payout checker",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        async with environment.sessionmaker() as session:
            session.add(checker)
            await session.flush()
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=checker.id,
            )
            await submit_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=FakeDisbursementAdapter(),
            )
            intent = await session.scalar(
                select(PayoutSubmissionIntent).where(
                    PayoutSubmissionIntent.payout_batch_line_id == lines[0].id
                )
            )
            await session.commit()
            return intent.id, intent.idempotency_key, lines[0].id

    return asyncio.run(seed())


def test_payout_submission_recovers_provider_acceptance_and_committed_ack_boundary(
    recovery_environment: RecoveryEnvironment,
) -> None:
    async def payout_state(intent_id: UUID, line_id: UUID) -> dict[str, object]:
        async with recovery_environment.sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            line = await session.get(PayoutBatchLine, line_id)
            return {
                "intent": intent.state,
                "generation": intent.generation,
                "line": line.status,
                "provider_reference": line.provider_transfer_reference,
            }

    intent_id, idempotency_key, line_id = _seed_payout_intent(
        recovery_environment,
        f"r58-provider-{uuid4().hex[:8]}",
    )
    provider_job_id = f"r58:payout:provider:{intent_id}"
    _enqueue(
        recovery_environment,
        "process_disbursement_intent",
        provider_job_id,
        str(intent_id),
    )
    provider_worker = recovery_environment.start_worker("payout_after_provider_acceptance")
    recovery_environment.wait_for_marker(
        provider_worker,
        "payout_after_provider_acceptance",
    )
    before_restart = asyncio.run(payout_state(intent_id, line_id))
    provider_queue = recovery_environment.queue_state(provider_job_id)
    assert before_restart["intent"] == PayoutSubmissionIntentState.CLAIMED.value
    assert before_restart["line"] == "reserved"
    assert (
        _effect_count(
            recovery_environment,
            "disbursement_accepted",
            idempotency_key=idempotency_key,
        )
        == 1
    )
    provider_signal = recovery_environment.kill(provider_worker)

    async def expire_claim() -> None:
        async with recovery_environment.sessionmaker() as session:
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == intent_id)
                .values(claim_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()

    asyncio.run(expire_claim())
    provider_restart = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(provider_restart, provider_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=provider_job_id) == 2
    provider_final = asyncio.run(payout_state(intent_id, line_id))
    assert provider_final["intent"] == PayoutSubmissionIntentState.RESOLVED.value
    assert provider_final["line"] == "submitted"
    assert (
        _effect_count(
            recovery_environment,
            "disbursement_accepted",
            idempotency_key=idempotency_key,
        )
        == 1
    )
    assert (
        _effect_count(
            recovery_environment,
            "disbursement_lookup_found",
            idempotency_key=idempotency_key,
        )
        == 1
    )
    _write_receipt(
        recovery_environment,
        cut_point="payout_after_provider_acceptance",
        process=provider_worker,
        exit_signal=provider_signal,
        job_id=provider_job_id,
        idempotency_key=idempotency_key,
        queue_state=provider_queue,
        database_state=before_restart,
        provider_effect_count=1,
        post_restart_convergence={
            **provider_final,
            "job_start_count": 2,
            "duplicate_provider_effect": False,
        },
    )
    recovery_environment.stop(provider_restart)

    committed_intent, committed_key, committed_line = _seed_payout_intent(
        recovery_environment,
        f"r58-commit-{uuid4().hex[:8]}",
    )
    committed_job_id = f"r58:payout:commit:{committed_intent}"
    _enqueue(
        recovery_environment,
        "process_disbursement_intent",
        committed_job_id,
        str(committed_intent),
    )
    committed_worker = recovery_environment.start_worker("payout_after_commit")
    recovery_environment.wait_for_marker(committed_worker, "payout_after_commit")
    committed_before = asyncio.run(payout_state(committed_intent, committed_line))
    committed_queue = recovery_environment.queue_state(committed_job_id)
    assert committed_before["intent"] == PayoutSubmissionIntentState.RESOLVED.value
    assert committed_before["line"] == "submitted"
    committed_signal = recovery_environment.kill(committed_worker)
    committed_restart = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(committed_restart, committed_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=committed_job_id) == 2
    committed_final = asyncio.run(payout_state(committed_intent, committed_line))
    assert committed_final == committed_before
    assert (
        _effect_count(
            recovery_environment,
            "disbursement_accepted",
            idempotency_key=committed_key,
        )
        == 1
    )
    _write_receipt(
        recovery_environment,
        cut_point="payout_after_commit_before_broker_ack",
        process=committed_worker,
        exit_signal=committed_signal,
        job_id=committed_job_id,
        idempotency_key=committed_key,
        queue_state=committed_queue,
        database_state=committed_before,
        provider_effect_count=1,
        post_restart_convergence={
            **committed_final,
            "job_start_count": 2,
            "duplicate_provider_effect": False,
        },
    )


def test_external_deletion_recovers_from_provider_not_found_without_false_finality(
    recovery_environment: RecoveryEnvironment,
) -> None:
    storage = PersistentStorageProvider(recovery_environment.state_root / "storage")
    storage_key = f"r58/deletion/{uuid4()}"
    content = b"R58 private object"
    checksum = __import__("hashlib").sha256(content).hexdigest()
    asyncio.run(
        storage.put(
            object_key=storage_key,
            content_type="application/octet-stream",
            data=content,
            checksum_sha256=checksum,
        )
    )

    async def seed() -> UUID:
        async with recovery_environment.sessionmaker() as session:
            intent = await ensure_stored_object_deletion(
                session,
                storage_key=storage_key,
                object_checksum_sha256=checksum,
                reason="r58_recovery",
                owner_type="synthetic_test",
                owner_id=uuid4(),
                organization_id=uuid4(),
                subject_user_id=None,
            )
            await session.commit()
            return intent.id

    intent_id = asyncio.run(seed())
    job_id = f"r58:deletion:{intent_id}"
    _enqueue(
        recovery_environment,
        "cron:recover_stored_object_deletions",
        job_id,
    )
    worker = recovery_environment.start_worker("deletion_after_provider_delete")
    recovery_environment.wait_for_marker(worker, "deletion_after_provider_delete")
    queue_state = recovery_environment.queue_state(job_id)

    async def deletion_state() -> dict[str, object]:
        async with recovery_environment.sessionmaker() as session:
            intent = await session.get(StoredObjectDeletion, intent_id)
            return {
                "state": intent.state,
                "attempts": intent.attempts,
                "provider_deleted_at": (
                    intent.provider_deleted_at.isoformat() if intent.provider_deleted_at else None
                ),
                "completed_at": intent.completed_at.isoformat() if intent.completed_at else None,
            }

    assert storage_key not in storage.keys()
    before_restart = asyncio.run(deletion_state())
    assert before_restart["state"] == "pending"
    assert _effect_count(recovery_environment, "object_deleted", object_key=storage_key) == 1
    exit_signal = recovery_environment.kill(worker)
    restarted = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restarted, job_id)
    assert asyncio.run(deletion_state()) == before_restart
    assert _effect_count(recovery_environment, "job_started", job_id=job_id) == 1
    assert (
        _effect_count(recovery_environment, "object_delete_not_found", object_key=storage_key) == 0
    )
    recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:recover_stored_object_deletions",
        job_id,
    )
    recovery_environment.wait_for_ack(restarted, recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=recovery_job_id) == 1
    final = asyncio.run(deletion_state())
    assert final["state"] == "completed"
    assert final["provider_deleted_at"] is not None
    assert final["completed_at"] is not None
    assert _effect_count(recovery_environment, "object_deleted", object_key=storage_key) == 1
    assert (
        _effect_count(
            recovery_environment,
            "object_delete_not_found",
            object_key=storage_key,
        )
        == 1
    )
    _write_receipt(
        recovery_environment,
        cut_point="deletion_after_provider_delete",
        process=worker,
        exit_signal=exit_signal,
        job_id=job_id,
        idempotency_key=str(intent_id),
        queue_state=queue_state,
        database_state=before_restart,
        provider_effect_count=1,
        post_restart_convergence={
            "recovery_job_id": recovery_job_id,
            **final,
            "provider_not_found_observed": True,
            "false_success": False,
        },
    )


def _seed_report_issuance(
    environment: RecoveryEnvironment,
    settings: Settings,
    tag: str,
) -> UUID:
    admin, advertiser, campaign = create_measurement_graph(
        environment.sessionmaker,
        identity_tag=tag,
        identity_domain="example.com",
    )

    async def seed() -> UUID:
        async with environment.sessionmaker() as session:
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=MeasurementRunCreate.model_validate(issue_payload(campaign.id)),
                settings=settings,
            )
            issuance = await request_report_issuance(
                session,
                actor_user_id=advertiser.id,
                measurement_run_id=run.id,
                payload=ReportIssuanceCreate(client_request_id=uuid4()),
                settings=settings,
                admin=False,
            )
            await session.commit()
            return issuance.id

    return asyncio.run(seed())


async def _report_state(
    environment: RecoveryEnvironment,
    issuance_id: UUID,
) -> dict[str, object]:
    async with environment.sessionmaker() as session:
        issuance = await session.get(ReportIssuance, issuance_id)
        publications = list(
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
        failed_audit_count = int(
            await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.action == "report_issuance.failed",
                    AuditEvent.entity_type == "report_issuance",
                    AuditEvent.entity_id == str(issuance_id),
                )
            )
            or 0
        )
        return {
            "status": issuance.status,
            "attempts": issuance.worker_attempts,
            "last_error_code": issuance.last_error_code,
            "publication_states": [row.state for row in publications],
            "artifact_count": artifact_count,
            "failed_audit_count": failed_audit_count,
        }


async def _expire_report_leases(
    environment: RecoveryEnvironment,
    issuance_id: UUID,
) -> None:
    expired = datetime.now(UTC) - timedelta(seconds=1)
    async with environment.sessionmaker() as session:
        await session.execute(
            update(ReportIssuance)
            .where(ReportIssuance.id == issuance_id)
            .values(lease_expires_at=expired)
        )
        await session.execute(
            update(ReportPublicationIntent)
            .where(ReportPublicationIntent.report_issuance_id == issuance_id)
            .values(lease_expires_at=expired)
        )
        await session.commit()


def test_report_publication_recovers_partial_artifact_and_cleans_abandoned_generation(
    recovery_environment: RecoveryEnvironment,
    settings: Settings,
) -> None:
    runtime = _runtime_settings(settings, recovery_environment)
    issuance_id = _seed_report_issuance(
        recovery_environment,
        runtime,
        f"r58-report-partial-{uuid4().hex[:8]}",
    )
    job_id = f"r58:report:partial:{issuance_id}"
    _enqueue(recovery_environment, "cron:sweep_report_issuances", job_id)
    worker = recovery_environment.start_worker("report_after_first_artifact")
    recovery_environment.wait_for_marker(worker, "report_after_first_artifact")
    queue_state = recovery_environment.queue_state(job_id)
    before_restart = asyncio.run(_report_state(recovery_environment, issuance_id))
    storage = PersistentStorageProvider(recovery_environment.state_root / "storage")
    assert before_restart["status"] == "processing"
    assert before_restart["publication_states"] == ["publishing"]
    assert len(storage.keys()) == 1
    exit_signal = recovery_environment.kill(worker)
    asyncio.run(_expire_report_leases(recovery_environment, issuance_id))
    restarted = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restarted, job_id)
    assert asyncio.run(_report_state(recovery_environment, issuance_id)) == before_restart
    assert _effect_count(recovery_environment, "job_started", job_id=job_id) == 1
    recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:sweep_report_issuances",
        job_id,
    )
    recovery_environment.wait_for_ack(restarted, recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=recovery_job_id) == 1
    final = asyncio.run(_report_state(recovery_environment, issuance_id))
    assert final["status"] == "ready"
    assert final["publication_states"] == ["cleaned", "complete"]
    assert final["artifact_count"] == 2
    assert len(storage.keys()) == 2
    report_puts = [
        event
        for event in read_provider_events(recovery_environment.state_root)
        if event["event"] == "object_put" and "/reports/" in event["object_key"]
    ]
    assert len(report_puts) == 3
    assert len({event["object_key"] for event in report_puts}) == 3
    _write_receipt(
        recovery_environment,
        cut_point="report_after_first_artifact",
        process=worker,
        exit_signal=exit_signal,
        job_id=job_id,
        idempotency_key=str(issuance_id),
        queue_state=queue_state,
        database_state=before_restart,
        provider_effect_count=3,
        dead_letter_state={"abandoned_generation": "cleaned"},
        post_restart_convergence={
            "recovery_job_id": recovery_job_id,
            **final,
            "live_objects": len(storage.keys()),
            "orphaned_objects": 0,
            "duplicate_object_keys": False,
        },
    )


def test_report_publication_commit_replays_before_broker_ack_without_duplicate_objects(
    recovery_environment: RecoveryEnvironment,
    settings: Settings,
) -> None:
    runtime = _runtime_settings(settings, recovery_environment)
    issuance_id = _seed_report_issuance(
        recovery_environment,
        runtime,
        f"r58-report-commit-{uuid4().hex[:8]}",
    )
    job_id = f"r58:report:commit:{issuance_id}"
    _enqueue(recovery_environment, "cron:sweep_report_issuances", job_id)
    worker = recovery_environment.start_worker("report_after_publication_commit")
    recovery_environment.wait_for_marker(worker, "report_after_publication_commit")
    queue_state = recovery_environment.queue_state(job_id)
    before_restart = asyncio.run(_report_state(recovery_environment, issuance_id))
    storage = PersistentStorageProvider(recovery_environment.state_root / "storage")
    assert before_restart["status"] == "ready"
    assert before_restart["artifact_count"] == 2
    assert len(storage.keys()) == 2
    exit_signal = recovery_environment.kill(worker)
    restarted = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restarted, job_id)
    assert asyncio.run(_report_state(recovery_environment, issuance_id)) == before_restart
    assert _effect_count(recovery_environment, "job_started", job_id=job_id) == 1
    recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:sweep_report_issuances",
        job_id,
    )
    recovery_environment.wait_for_ack(restarted, recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=recovery_job_id) == 1
    final = asyncio.run(_report_state(recovery_environment, issuance_id))
    assert final == before_restart
    assert len(storage.keys()) == 2
    assert _effect_count(recovery_environment, "object_put") == 2
    _write_receipt(
        recovery_environment,
        cut_point="report_after_publication_commit_before_broker_ack",
        process=worker,
        exit_signal=exit_signal,
        job_id=job_id,
        idempotency_key=str(issuance_id),
        queue_state=queue_state,
        database_state=before_restart,
        provider_effect_count=2,
        post_restart_convergence={
            "recovery_job_id": recovery_job_id,
            **final,
            "live_objects": len(storage.keys()),
            "duplicate_objects": False,
        },
    )


def test_report_expired_lease_dead_letter_survives_worker_kill_before_ack(
    recovery_environment: RecoveryEnvironment,
    settings: Settings,
) -> None:
    runtime = _runtime_settings(settings, recovery_environment)
    issuance_id = _seed_report_issuance(
        recovery_environment,
        runtime,
        f"r58-report-dead-{uuid4().hex[:8]}",
    )

    async def exhaust() -> None:
        async with recovery_environment.sessionmaker() as session:
            issuance = await session.get(ReportIssuance, issuance_id)
            issuance.status = ReportIssuanceStatus.PROCESSING.value
            issuance.worker_attempts = REPORT_MAX_ATTEMPTS
            issuance.processing_token = uuid4()
            issuance.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            issuance.next_attempt_at = None
            issuance.last_error_code = None
            issuance.ready_at = None
            await session.commit()

    asyncio.run(exhaust())
    job_id = f"r58:report:dead-letter:{issuance_id}"
    _enqueue(recovery_environment, "cron:sweep_report_issuances", job_id)
    worker = recovery_environment.start_worker("report_after_dead_letter")
    recovery_environment.wait_for_marker(worker, "report_after_dead_letter")
    queue_state = recovery_environment.queue_state(job_id)
    before_restart = asyncio.run(_report_state(recovery_environment, issuance_id))
    assert before_restart["status"] == "failed"
    assert before_restart["last_error_code"] == "worker_lease_expired"
    assert before_restart["failed_audit_count"] == 1
    exit_signal = recovery_environment.kill(worker)
    restarted = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restarted, job_id)
    assert asyncio.run(_report_state(recovery_environment, issuance_id)) == before_restart
    assert _effect_count(recovery_environment, "job_started", job_id=job_id) == 1
    recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:sweep_report_issuances",
        job_id,
    )
    recovery_environment.wait_for_ack(restarted, recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=recovery_job_id) == 1
    final = asyncio.run(_report_state(recovery_environment, issuance_id))
    assert final == before_restart
    assert final["failed_audit_count"] == 1
    _write_receipt(
        recovery_environment,
        cut_point="report_dead_letter_after_expired_lease_before_broker_ack",
        process=worker,
        exit_signal=exit_signal,
        job_id=job_id,
        idempotency_key=str(issuance_id),
        queue_state=queue_state,
        database_state={"status": "processing", "attempts": REPORT_MAX_ATTEMPTS},
        provider_effect_count=0,
        dead_letter_state=before_restart,
        post_restart_convergence={
            "recovery_job_id": recovery_job_id,
            **final,
            "duplicate_transition": False,
        },
    )


def test_cursor_persists_across_kill_and_reaches_every_tail_item_once(
    recovery_environment: RecoveryEnvironment,
) -> None:
    graphs = []
    for index in range(5):
        graph = build_trip_graph(
            recovery_environment.sessionmaker,
            f"c{index}-{uuid4().hex[:7]}",
            ended_at=datetime(2026, 8, 1, 12, index, tzinfo=UTC),
        )
        create_test_payout_rule(
            recovery_environment.sessionmaker,
            campaign_id=graph.campaign.id,
            created_by_user_id=graph.admin.id,
            base_rate_per_km=10,
        )
        add_pings(
            recovery_environment.sessionmaker,
            trip_id=graph.trip.id,
            points=moving_points(),
            idempotency_key=f"r58-cursor-{index}",
        )
        graphs.append(graph)

    first_job_id = f"r58:cursor:first:{uuid4()}"
    _enqueue(recovery_environment, "cron:process_unprocessed_trips", first_job_id)
    environment = os.environ
    previous_batch_size = environment.get("R58_SWEEP_BATCH_SIZE")
    environment["R58_SWEEP_BATCH_SIZE"] = "2"
    try:
        worker = recovery_environment.start_worker("cursor_after_write")
    finally:
        if previous_batch_size is None:
            environment.pop("R58_SWEEP_BATCH_SIZE", None)
        else:
            environment["R58_SWEEP_BATCH_SIZE"] = previous_batch_size
    recovery_environment.wait_for_marker(worker, "cursor_after_write")
    queue_state = recovery_environment.queue_state(first_job_id)
    redis_client = recovery_environment.redis
    try:
        cursor_before = redis_client.get("worker:trip-processing:sweep-cursor:v1")
    finally:
        redis_client.close()
    assert cursor_before is not None

    async def calculation_counts() -> dict[str, int]:
        async with recovery_environment.sessionmaker() as session:
            rows = await session.execute(
                select(PayoutCalculation.trip_session_id, func.count(PayoutCalculation.id))
                .where(PayoutCalculation.trip_session_id.in_([graph.trip.id for graph in graphs]))
                .group_by(PayoutCalculation.trip_session_id)
            )
            return {str(trip_id): int(count) for trip_id, count in rows}

    first_counts = asyncio.run(calculation_counts())
    assert sum(first_counts.values()) == 2
    exit_signal = recovery_environment.kill(worker)
    restart = recovery_environment.start_worker()
    recovery_environment.wait_for_ack(restart, first_job_id)
    assert asyncio.run(calculation_counts()) == first_counts
    assert _effect_count(recovery_environment, "job_started", job_id=first_job_id) == 1
    redis_client = recovery_environment.redis
    try:
        assert redis_client.get("worker:trip-processing:sweep-cursor:v1") == cursor_before
    finally:
        redis_client.close()
    recovery_job_id = _enqueue_next_cron_occurrence(
        recovery_environment,
        "cron:process_unprocessed_trips",
        first_job_id,
    )
    recovery_environment.wait_for_ack(restart, recovery_job_id)
    assert _effect_count(recovery_environment, "job_started", job_id=recovery_job_id) == 1
    recovery_environment.stop(restart)

    for index in range(1):
        tail_job_id = f"r58:cursor:tail:{index}:{uuid4()}"
        _enqueue(recovery_environment, "cron:process_unprocessed_trips", tail_job_id)
        tail_worker = recovery_environment.start_worker()
        recovery_environment.wait_for_ack(tail_worker, tail_job_id)
        recovery_environment.stop(tail_worker)

    final_counts = asyncio.run(calculation_counts())
    assert final_counts == {str(graph.trip.id): 1 for graph in graphs}
    redis_client = recovery_environment.redis
    try:
        cursor_after = redis_client.get("worker:trip-processing:sweep-cursor:v1")
    finally:
        redis_client.close()
    assert cursor_after is None
    _write_receipt(
        recovery_environment,
        cut_point="cursor_after_write_before_broker_ack",
        process=worker,
        exit_signal=exit_signal,
        job_id=first_job_id,
        idempotency_key=first_job_id,
        queue_state=queue_state,
        database_state={"processed_once": sorted(first_counts)},
        provider_effect_count=0,
        cursor_state={"before_kill": cursor_before, "after_convergence": cursor_after},
        post_restart_convergence={
            "recovery_job_id": recovery_job_id,
            "trip_calculation_counts": final_counts,
            "tail_reached": True,
            "duplicates": False,
        },
    )
