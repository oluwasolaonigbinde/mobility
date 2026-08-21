import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sentry_sdk
from arq.connections import RedisSettings, create_pool
from arq.cron import CronJob
from arq.worker import Function, Worker
from sqlalchemy.exc import IntegrityError
from test_trip_processing import (
    BASE_TIME,
    add_pings,
    build_graph,
    create_test_payout_rule,
    moving_points,
    seed_analytics,
    table_counts,
)

from app.core.config import get_settings
from app.core.trip_enqueue import RedisTripProcessingEnqueuer
from app.jobs import data_lifecycle as data_lifecycle_jobs
from app.jobs import trip_processing as jobs
from app.jobs.worker import WorkerSettings, sweep_cron_minutes
from app.services.trip_processing import DueTrip, process_ended_trip


@pytest.fixture(autouse=True)
def _reenable_worker_loggers():
    # In-process alembic upgrades (test_migration_slice7-9) run fileConfig with
    # disable_existing_loggers=True, which disables these module loggers for the
    # rest of the pytest session; caplog assertions need them re-enabled.
    for name in ("app.core.trip_enqueue", "app.jobs.trip_processing"):
        logging.getLogger(name).disabled = False


def make_ctx(sessionmaker, settings) -> dict:
    return {"settings": settings, "sessionmaker": sessionmaker}


def test_worker_settings_registers_process_trip_and_sweep_cron() -> None:
    assert len(WorkerSettings.functions) == 1
    registered = WorkerSettings.functions[0]
    assert isinstance(registered, Function)
    assert registered.name == "process_trip"
    assert registered.keep_result_s == 0
    assert registered.coroutine is jobs.process_trip

    assert len(WorkerSettings.cron_jobs) == 5
    cron_job = WorkerSettings.cron_jobs[0]
    assert isinstance(cron_job, CronJob)
    assert cron_job.coroutine is jobs.process_unprocessed_trips
    assert cron_job.unique is True
    assert cron_job.max_tries == 1
    assert cron_job.keep_result_s == 0
    assert cron_job.minute == sweep_cron_minutes(get_settings().worker_sweep_interval_minutes)

    seal_cron = WorkerSettings.cron_jobs[1]
    assert isinstance(seal_cron, CronJob)
    assert seal_cron.coroutine is jobs.seal_ended_trips_job
    assert seal_cron.unique is True
    assert seal_cron.minute == sweep_cron_minutes(get_settings().worker_sweep_interval_minutes)

    lifecycle_crons = {
        cron_job.coroutine: cron_job for cron_job in WorkerSettings.cron_jobs[2:]
    }
    assert set(lifecycle_crons) == {
        data_lifecycle_jobs.premake_ping_partitions,
        data_lifecycle_jobs.check_ping_partition_coverage,
        data_lifecycle_jobs.purge_expired_ping_partitions,
    }
    for cron_job in lifecycle_crons.values():
        assert isinstance(cron_job, CronJob)
        assert cron_job.unique is True
        # Daily, staggered hours so lifecycle DDL never stacks.
        assert len(cron_job.hour) == 1
    assert (
        len({next(iter(job.hour)) for job in lifecycle_crons.values()}) == 3
    )


def test_process_trip_malformed_id_fails_before_any_write(db_sessionmaker, settings) -> None:
    with pytest.raises(ValueError):
        asyncio.run(jobs.process_trip(make_ctx(db_sessionmaker, settings), "not-a-uuid"))

    counts = table_counts(db_sessionmaker)
    assert all(value == 0 for value in counts.values())


def test_process_trip_unexpected_error_rolls_back_and_reraises(
    db_sessionmaker,
    settings,
    monkeypatch,
    caplog,
) -> None:
    graph = build_graph(db_sessionmaker, "job-err")

    async def boom(session, *, trip_id, settings):
        raise RuntimeError("kaput")

    monkeypatch.setattr(jobs, "process_ended_trip", boom)
    captured: list[Exception] = []
    monkeypatch.setattr(jobs, "capture_exception", captured.append)

    with caplog.at_level(logging.ERROR, logger="app.jobs.trip_processing"):
        with pytest.raises(RuntimeError):
            asyncio.run(jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id)))

    assert "job=process_trip" in caplog.text
    assert "error_class=RuntimeError" in caplog.text
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)
    assert any(record.exc_info is not None for record in caplog.records)
    counts = table_counts(db_sessionmaker)
    assert all(value == 0 for value in counts.values())


def test_process_trip_escaped_unique_integrity_error_is_captured_and_reraised(
    db_sessionmaker,
    settings,
    monkeypatch,
    caplog,
) -> None:
    graph = build_graph(db_sessionmaker, "job-race")

    async def duplicate(session, *, trip_id, settings):
        raise IntegrityError(
            "INSERT",
            {},
            Exception(
                'duplicate key value violates unique constraint '
                '"uq_trip_analytics_trip_session_id"'
            ),
        )

    captured: list[Exception] = []
    monkeypatch.setattr(jobs, "process_ended_trip", duplicate)
    monkeypatch.setattr(jobs, "capture_exception", captured.append)

    with caplog.at_level(logging.ERROR, logger="app.jobs.trip_processing"):
        with pytest.raises(IntegrityError) as exc_info:
            asyncio.run(
                jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id))
            )

    assert captured == [exc_info.value]
    assert "constraint=uq_trip_analytics_trip_session_id" in caplog.text
    assert any(record.exc_info is not None for record in caplog.records)


def test_process_trip_unexpected_integrity_error_is_captured_and_reraised(
    db_sessionmaker,
    settings,
    monkeypatch,
    caplog,
) -> None:
    graph = build_graph(db_sessionmaker, "job-integrity")
    failure = IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))

    async def invalid_write(session, *, trip_id, settings):
        raise failure

    captured: list[Exception] = []
    monkeypatch.setattr(jobs, "process_ended_trip", invalid_write)
    monkeypatch.setattr(jobs, "capture_exception", captured.append)

    with caplog.at_level(logging.ERROR, logger="app.jobs.trip_processing"):
        with pytest.raises(IntegrityError) as exc_info:
            asyncio.run(jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id)))

    assert exc_info.value is failure
    assert captured == [failure]
    assert any(record.exc_info is not None for record in caplog.records)
    assert "lost_write_race" not in caplog.text


def test_process_trip_logs_outcome_and_never_secrets(db_sessionmaker, settings, caplog) -> None:
    graph = build_graph(db_sessionmaker, "job-log")
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    seed_analytics(db_sessionmaker, graph)

    with caplog.at_level(logging.INFO, logger="app.jobs.trip_processing"):
        summary = asyncio.run(
            jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id))
        )

    assert summary["overall"] == "completed"
    assert summary["stages"]["payout"] == "created"
    assert summary["duration_ms"] >= 0
    assert "job=process_trip" in caplog.text
    assert str(graph.trip.id) in caplog.text
    assert "overall=completed" in caplog.text
    for secret in ("sqlite", "postgresql", "redis://", settings.jwt_secret_key, "password"):
        assert secret not in caplog.text


def test_sweep_recovers_lost_queue_and_second_pass_is_empty(
    postgis_db_sessionmaker,
    settings,
    caplog,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "sweep")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    # Trip ended but never enqueued (Redis flush / enqueue failure): the
    # Postgres-derived sweep must complete it without any queue state.
    ctx = make_ctx(postgis_db_sessionmaker, settings)
    with caplog.at_level(logging.INFO, logger="app.jobs.trip_processing"):
        first = asyncio.run(jobs.process_unprocessed_trips(ctx))

    assert first["selected"] == 1
    assert first["processed"] == 1
    assert first["partial"] == 0
    assert first["failed"] == 0
    assert first["skipped"] == 0
    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
    assert "job=process_unprocessed_trips" in caplog.text
    for secret in ("sqlite", "postgresql", "redis://", settings.jwt_secret_key, "password"):
        assert secret not in caplog.text

    second = asyncio.run(jobs.process_unprocessed_trips(ctx))
    assert second["selected"] == 0
    assert second["processed"] == 0


def test_sweep_isolates_per_trip_failures_and_continues(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph_bad = build_graph(
        db_sessionmaker,
        "iso-bad",
        ended_at=BASE_TIME + timedelta(minutes=20),
    )
    graph_good = build_graph(
        db_sessionmaker,
        "iso-good",
        ended_at=BASE_TIME + timedelta(minutes=40),
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph_good.campaign.id,
        created_by_user_id=graph_good.admin.id,
        base_rate_per_km=10,
    )
    seed_analytics(db_sessionmaker, graph_good)

    async def selective(session, *, trip_id, settings):
        if trip_id == graph_bad.trip.id:
            raise RuntimeError("corrupt trip data")
        return await process_ended_trip(session, trip_id=trip_id, settings=settings)

    monkeypatch.setattr(jobs, "process_ended_trip", selective)
    captured: list[Exception] = []
    monkeypatch.setattr(sentry_sdk, "capture_exception", captured.append)

    counts = asyncio.run(jobs.process_unprocessed_trips(make_ctx(db_sessionmaker, settings)))

    assert counts["selected"] == 2
    assert counts["processed"] == 1
    assert counts["failed"] == 1
    assert counts["skipped"] == 0
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)
    rows = table_counts(db_sessionmaker)
    assert rows["calculations"] == 1
    assert rows["ledger"] == 1


def test_sweep_counts_unexpected_integrity_error_as_failed(
    db_sessionmaker,
    settings,
    monkeypatch,
    caplog,
) -> None:
    graph = build_graph(db_sessionmaker, "sweep-integrity")
    failure = IntegrityError("INSERT", {}, Exception("CHECK constraint failed: broken"))

    async def invalid_write(session, *, trip_id, settings):
        raise failure

    captured: list[Exception] = []
    monkeypatch.setattr(jobs, "process_ended_trip", invalid_write)
    monkeypatch.setattr(jobs, "capture_exception", captured.append)

    with caplog.at_level(logging.ERROR, logger="app.jobs.trip_processing"):
        summary = asyncio.run(
            jobs.process_unprocessed_trips(make_ctx(db_sessionmaker, settings))
        )

    assert summary["selected"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 0
    assert captured == [failure]
    assert any(record.exc_info is not None for record in caplog.records)
    assert str(graph.trip.id) in caplog.text


def test_sweep_cursor_resumes_next_occurrence_and_reaches_healthy_tail(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    batch_settings = settings.model_copy(update={"worker_sweep_batch_size": 8})
    candidates = [
        DueTrip(id=uuid4(), ended_at=datetime(2026, 1, 1, index, tzinfo=UTC))
        for index in range(10)
    ]
    poison_ids = {candidate.id for candidate in candidates[:8]}
    attempted: list = []

    async def find_page(session, *, limit, settings, after=None):
        start = 0
        if after is not None:
            start = next(
                index + 1
                for index, candidate in enumerate(candidates)
                if (candidate.ended_at, candidate.id) == after
            )
        return candidates[start : start + limit]

    async def process(session, *, trip_id, settings):
        attempted.append(trip_id)
        if trip_id in poison_ids:
            raise RuntimeError("poison trip")
        return SimpleNamespace(overall="completed", stages=[])

    monkeypatch.setattr(jobs, "find_unprocessed_trip_page", find_page)
    monkeypatch.setattr(jobs, "process_ended_trip", process)
    monkeypatch.setattr(jobs, "capture_exception", lambda exc: None)

    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def get(self, key: str):
            return self.values.get(key)

        async def set(self, key: str, value: str):
            self.values[key] = value

        async def delete(self, key: str):
            self.values.pop(key, None)

    redis = FakeRedis()
    first_ctx = {**make_ctx(db_sessionmaker, batch_settings), "redis": redis}
    second_ctx = {**make_ctx(db_sessionmaker, batch_settings), "redis": redis}

    first = asyncio.run(jobs.process_unprocessed_trips(first_ctx))
    second = asyncio.run(jobs.process_unprocessed_trips(second_ctx))

    assert first["selected"] == 8
    assert first["processed"] == 0
    assert first["failed"] == 8
    assert first["skipped"] == 0
    assert second["selected"] == 2
    assert second["processed"] == 2
    assert second["failed"] == 0
    assert attempted[-2:] == [candidate.id for candidate in candidates[-2:]]
    assert jobs.SWEEP_CURSOR_KEY not in redis.values


def test_burst_worker_runs_enqueued_trip_end_to_end(postgis_db_sessionmaker, settings) -> None:
    redis_url = os.environ.get("ARQ_TEST_REDIS_URL")
    if not redis_url:
        if os.environ.get("CI"):
            pytest.fail("ARQ_TEST_REDIS_URL missing in CI")
        pytest.skip("ARQ test Redis URL is not configured")

    graph = build_graph(postgis_db_sessionmaker, "burst")
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())

    async def exercise() -> None:
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
        await pool.flushdb()

        enqueuer = RedisTripProcessingEnqueuer(redis_url)
        await enqueuer.enqueue_trip_processing(graph.trip.id)
        assert await pool.zscore("arq:queue", f"trip-process:{graph.trip.id}") is not None

        async def startup(ctx: dict) -> None:
            ctx["settings"] = settings
            ctx["sessionmaker"] = postgis_db_sessionmaker

        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=RedisSettings.from_dsn(redis_url),
            burst=True,
            poll_delay=0,
            on_startup=startup,
        )
        assert await worker.run_check() == 1
        await worker.close()

        await pool.flushdb()
        if enqueuer._pool is not None:
            await enqueuer._pool.aclose()
        await pool.aclose()

    asyncio.run(exercise())

    counts = table_counts(postgis_db_sessionmaker)
    assert counts["analytics"] == 1
    assert counts["estimates"] == 1
    assert counts["calculations"] == 1
    assert counts["ledger"] == 1
