import asyncio
import logging
import os
import time
from uuid import UUID, uuid4

import pytest
from arq.connections import RedisSettings, create_pool
from arq.worker import Worker, func
from conftest import fetch_trip_sessions
from starlette import status as http_status
from test_trips import create_trip_ready_graph, driver_headers, start_trip

from app.api.v1.dependencies import get_trip_enqueuer
from app.core.trip_enqueue import (
    TRIP_PROCESSING_JOB_NAME,
    RedisTripProcessingEnqueuer,
    UnconfiguredTripProcessingEnqueuer,
    build_trip_enqueuer,
)
from app.models.trip import TripSession


@pytest.fixture(autouse=True)
def _reenable_worker_loggers():
    # In-process alembic upgrades (test_migration_slice7-9) run fileConfig with
    # disable_existing_loggers=True, which disables these module loggers for the
    # rest of the pytest session; caplog assertions need them re-enabled.
    for name in ("app.core.trip_enqueue", "app.jobs.trip_processing"):
        logging.getLogger(name).disabled = False


class SpyEnqueuer:
    def __init__(self, sessionmaker) -> None:
        self.sessionmaker = sessionmaker
        self.calls: list[UUID] = []
        self.observed: list[tuple[str, object]] = []

    async def enqueue_trip_processing(self, trip_id: UUID) -> None:
        self.calls.append(trip_id)
        # Independent session: only committed state is visible here.
        async with self.sessionmaker() as session:
            trip = await session.get(TripSession, trip_id)
            self.observed.append((trip.status, trip.ended_at))


def end_trip(db_client, trip_id: str):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={
            "end_reason": "driver_ended",
            "metadata": {},
        },
    )


def reconcile_trip_evidence(db_client, trip_id: str):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )


def start_ended_ready_trip(db_client, db_sessionmaker) -> str:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    response = start_trip(db_client, assignment.id)
    assert response.status_code == http_status.HTTP_201_CREATED
    return response.json()["id"]


def test_trip_reconcile_commits_before_enqueue_and_calls_once(db_client, db_sessionmaker) -> None:
    trip_id = start_ended_ready_trip(db_client, db_sessionmaker)
    spy = SpyEnqueuer(db_sessionmaker)
    db_client.app.dependency_overrides[get_trip_enqueuer] = lambda: spy
    try:
        ended = end_trip(db_client, trip_id)
        assert ended.status_code == http_status.HTTP_200_OK
        assert ended.json()["status"] == "ended"
        assert ended.json()["ended_at"] is not None
        assert spy.calls == []
        response = reconcile_trip_evidence(db_client, trip_id)
        replay = reconcile_trip_evidence(db_client, trip_id)
    finally:
        db_client.app.dependency_overrides.pop(get_trip_enqueuer, None)

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["trip_id"] == trip_id
    assert body["status"] == "sealed"
    assert body["duplicate"] is False
    assert spy.calls == [UUID(trip_id)]
    status_at_enqueue, ended_at_at_enqueue = spy.observed[0]
    assert status_at_enqueue == "sealed"
    assert ended_at_at_enqueue is not None
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json() == {**body, "duplicate": True}
    assert spy.calls == [UUID(trip_id)]


def test_trip_reconcile_fails_open_when_redis_unreachable(
    db_client, db_sessionmaker, caplog
) -> None:
    trip_id = start_ended_ready_trip(db_client, db_sessionmaker)
    assert end_trip(db_client, trip_id).json()["status"] == "ended"
    # Real implementation pointed at a closed port: the swallow lives in the
    # enqueuer itself, the router stays a bare await after a successful exact
    # reconciliation seals the trip.
    unreachable = RedisTripProcessingEnqueuer("redis://127.0.0.1:1/0")
    db_client.app.dependency_overrides[get_trip_enqueuer] = lambda: unreachable
    try:
        with caplog.at_level(logging.WARNING, logger="app.core.trip_enqueue"):
            started = time.monotonic()
            response = reconcile_trip_evidence(db_client, trip_id)
            elapsed = time.monotonic() - started
    finally:
        db_client.app.dependency_overrides.pop(get_trip_enqueuer, None)

    assert response.status_code == http_status.HTTP_200_OK
    assert elapsed < 3.0
    assert "event=trip_enqueue_failed" in caplog.text
    assert trip_id in caplog.text
    trips = fetch_trip_sessions(db_sessionmaker)
    assert trips[0].status == "sealed"
    assert trips[0].ended_at is not None


def test_trip_reconcile_warns_when_redis_url_unset(db_client, db_sessionmaker, caplog) -> None:
    # No override: the settings fixture has redis_url=None, so the default
    # dependency resolves to the unconfigured (warn-and-return) enqueuer after
    # exact reconciliation seals the v2 trip.
    trip_id = start_ended_ready_trip(db_client, db_sessionmaker)
    assert end_trip(db_client, trip_id).json()["status"] == "ended"

    with caplog.at_level(logging.WARNING, logger="app.core.trip_enqueue"):
        response = reconcile_trip_evidence(db_client, trip_id)

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["status"] == "sealed"
    assert "event=trip_enqueue_failed" in caplog.text
    assert "error_class=RedisUrlNotConfigured" in caplog.text
    assert trip_id in caplog.text


def test_build_trip_enqueuer_variants(settings) -> None:
    assert isinstance(build_trip_enqueuer(settings), UnconfiguredTripProcessingEnqueuer)
    configured = settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/5"})
    first = build_trip_enqueuer(configured)
    assert isinstance(first, RedisTripProcessingEnqueuer)
    assert build_trip_enqueuer(configured) is first


def test_real_redis_enqueue_dedupe_and_zero_retention() -> None:
    redis_url = os.environ.get("ARQ_TEST_REDIS_URL")
    if not redis_url:
        if os.environ.get("CI"):
            pytest.fail("ARQ_TEST_REDIS_URL missing in CI")
        pytest.skip("ARQ test Redis URL is not configured")

    trip_id = uuid4()
    job_id = f"trip-process:{trip_id}"

    async def exercise() -> None:
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
        await pool.flushdb()

        enqueuer = RedisTripProcessingEnqueuer(redis_url)
        await enqueuer.enqueue_trip_processing(trip_id)
        assert await pool.zscore("arq:queue", job_id) is not None

        # Same deterministic id while queued -> arq dedupes (returns None).
        duplicate = await pool.enqueue_job(TRIP_PROCESSING_JOB_NAME, str(trip_id), _job_id=job_id)
        assert duplicate is None

        async def fake_process_trip(ctx, raw_trip_id: str) -> dict:
            return {"trip_id": raw_trip_id}

        worker = Worker(
            functions=[func(fake_process_trip, name=TRIP_PROCESSING_JOB_NAME, keep_result=0)],
            redis_settings=RedisSettings.from_dsn(redis_url),
            burst=True,
            poll_delay=0,
        )
        assert await worker.run_check() == 1
        await worker.close()

        # keep_result=0: no result key survives, so retention can never
        # suppress a later re-enqueue of the same trip id (criterion 21).
        assert await pool.exists(f"arq:result:{job_id}") == 0
        re_enqueued = await pool.enqueue_job(TRIP_PROCESSING_JOB_NAME, str(trip_id), _job_id=job_id)
        assert re_enqueued is not None

        await pool.flushdb()
        if enqueuer._pool is not None:
            await enqueuer._pool.aclose()
        await pool.aclose()

    asyncio.run(exercise())
