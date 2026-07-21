import asyncio
import logging
import os
from datetime import timedelta

import pytest
import sentry_sdk
from arq.connections import RedisSettings, create_pool
from arq.cron import CronJob
from arq.worker import Function, Retry, Worker
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
from app.jobs import trip_processing as jobs
from app.jobs.worker import WorkerSettings, sweep_cron_minutes
from app.services.trip_processing import process_ended_trip


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

    assert len(WorkerSettings.cron_jobs) == 1
    cron_job = WorkerSettings.cron_jobs[0]
    assert isinstance(cron_job, CronJob)
    assert cron_job.coroutine is jobs.process_unprocessed_trips
    assert cron_job.unique is True
    assert cron_job.max_tries == 1
    assert cron_job.keep_result_s == 0
    assert cron_job.minute == sweep_cron_minutes(get_settings().worker_sweep_interval_minutes)


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

    with caplog.at_level(logging.ERROR, logger="app.jobs.trip_processing"):
        with pytest.raises(RuntimeError):
            asyncio.run(jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id)))

    assert "job=process_trip" in caplog.text
    assert "error_class=RuntimeError" in caplog.text
    counts = table_counts(db_sessionmaker)
    assert all(value == 0 for value in counts.values())


def test_process_trip_integrity_error_becomes_arq_retry(
    db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_graph(db_sessionmaker, "job-race")

    async def duplicate(session, *, trip_id, settings):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(jobs, "process_ended_trip", duplicate)

    with pytest.raises(Retry) as exc_info:
        asyncio.run(jobs.process_trip(make_ctx(db_sessionmaker, settings), str(graph.trip.id)))

    assert exc_info.value.defer_score == 5000


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


def test_burst_worker_runs_enqueued_trip_end_to_end(postgis_db_sessionmaker, settings) -> None:
    redis_url = os.environ.get("ARQ_TEST_REDIS_URL")
    if not redis_url:
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
