"""REQ-317: a lock held by the report sweep is "busy", never an error.

A Holder takes the same locks as ``sweep_scheduled_reports`` (the campaign
terms key and the trip row FOR SHARE) and parks. Every worker session uses a
short lock_timeout, so waiting on the holder surfaces as a real 55P03.
"""

import asyncio
import inspect
import logging
from datetime import timedelta

import pytest
from arq import Retry
from sqlalchemy import event, select, update
from test_req252_lock_scopes import Holder
from test_trip_processing import (
    add_pings,
    build_graph,
    create_test_daily_payout_authority,
    moving_points,
)

from app.jobs import assignment_activity as activity_job
from app.jobs import earnings_release as earnings_job
from app.jobs import trip_processing as trip_job
from app.jobs.worker import WorkerSettings, sweep_cron_minutes
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.services.assignment_activity import sweep_activity_flags
from app.services.payout_rule_serialization import acquire_campaign_terms_lock
from app.services.report_scheduling import sweep_scheduled_reports

WORKER_LOCK_TIMEOUT = "300ms"


@pytest.fixture
def short_wait(postgis_db_sessionmaker):
    """Every new connection gives up a lock wait quickly, like the 10 s worker setting."""
    engine = postgis_db_sessionmaker.kw["bind"].sync_engine

    def set_timeout(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET lock_timeout = '{WORKER_LOCK_TIMEOUT}'")
        cursor.close()

    event.listen(engine, "connect", set_timeout)
    yield postgis_db_sessionmaker
    event.remove(engine, "connect", set_timeout)


def report_sweep_locks(graph):
    async def body(session, pause):
        await acquire_campaign_terms_lock(session, graph.campaign.id)
        await session.execute(
            select(TripSession.id).where(TripSession.id == graph.trip.id).with_for_update(read=True)
        )
        await pause(session)

    return body


@pytest.fixture
def captured(monkeypatch):
    seen = []
    for module in (trip_job, earnings_job, activity_job):
        monkeypatch.setattr(module, "capture_exception", seen.append)
    return seen


def errors(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR and r.name.startswith("app.")]


def test_lock_busy_items_are_counted_busy_then_processed_after_release(
    short_wait, settings, captured, caplog
):
    db = short_wait
    graph = build_graph(db, "req317-busy")
    create_test_daily_payout_authority(
        db, campaign_id=graph.campaign.id, created_by_user_id=graph.admin.id
    )
    add_pings(db, trip_id=graph.trip.id, points=moving_points())
    ctx = {"settings": settings, "sessionmaker": db}
    caplog.set_level(logging.INFO)

    with Holder(db, report_sweep_locks(graph)):
        trips = asyncio.run(trip_job.process_unprocessed_trips(ctx))
        activity = asyncio.run(
            sweep_activity_flags(db, assignment_ids=[graph.assignment.id], settings=settings)
        )
        with pytest.raises(Retry) as retry:
            asyncio.run(trip_job.process_trip(ctx, str(graph.trip.id)))
    assert (trips["busy"], trips["failed"], trips["processed"]) == (1, 0, 0), trips
    assert (activity["busy"], activity["errors"], activity["evaluated"]) == (1, 0, 0), activity
    # The job comes back after the report sweep's hold, not straight into the same lock.
    assert retry.value.defer_score == trip_job.LOCK_BUSY_RETRY_SECONDS * 1000
    assert trip_job.LOCK_BUSY_RETRY_SECONDS > 90
    assert captured == [] and errors(caplog) == []

    trips = asyncio.run(trip_job.process_unprocessed_trips(ctx))
    activity = asyncio.run(
        sweep_activity_flags(db, assignment_ids=[graph.assignment.id], settings=settings)
    )
    assert (trips["busy"], trips["failed"], trips["processed"]) == (0, 0, 1), trips
    assert (activity["busy"], activity["errors"], activity["evaluated"]) == (0, 0, 1), activity

    async def make_releasable():
        async with db() as session:
            await session.execute(
                update(EarningsLedgerEntry)
                .where(EarningsLedgerEntry.trip_session_id == graph.trip.id)
                .values(release_at=graph.trip.ended_at - timedelta(minutes=1))
            )
            await session.commit()

    asyncio.run(make_releasable())
    with Holder(db, report_sweep_locks(graph)):
        held = asyncio.run(earnings_job.sweep_earnings_release_reviews(ctx))
    assert (held["busy"], held["release_failed"], held["released_entries"]) == (1, 0, 0), held
    assert captured == [] and errors(caplog) == []
    released = asyncio.run(earnings_job.sweep_earnings_release_reviews(ctx))
    assert (released["busy"], released["release_failed"]) == (0, 0), released
    assert released["released_entries"] == 1, released


def test_report_sweep_minutes_never_coincide_with_the_money_sweeps():
    money_sweeps = {
        trip_job.process_unprocessed_trips,
        trip_job.seal_ended_trips_job,
        earnings_job.sweep_earnings_release_reviews,
        activity_job.sweep_assignment_activity_flags,
    }
    minutes = {inspect.unwrap(job.coroutine): set(job.minute) for job in WorkerSettings.cron_jobs}
    report = minutes[sweep_scheduled_reports]
    assert report == {2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57}
    for name in money_sweeps:
        assert minutes[name] and not report & minutes[name], name
    assert sweep_cron_minutes(5, offset=2) == report
