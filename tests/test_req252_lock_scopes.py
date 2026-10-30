"""REQ-252: per-campaign, per-driver and per-trip locks replace the global gate.

Every test uses real PostgreSQL sessions. A holder runs in its own thread and
event loop and keeps its transaction open while the main thread reads. API
reads use a short lock_timeout, so a read that would wait shows up as 503.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import auth_headers
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_heatmaps import PASSWORD, create_heatmap_graph
from test_route_replay import BASE_TIME as REPLAY_TIME
from test_route_replay import create_graph as replay_graph
from test_route_replay import ping, run_detection
from test_trip_processing import build_graph

from app.db.integrity import database_sqlstate
from app.db.session import get_session
from app.main import create_app
from app.models.campaign import Campaign
from app.models.route_replay import RouteReplaySignature
from app.services import route_replay, trip_processing
from app.services.disclosure import lock_trip_disclosure_snapshot
from app.services.fraud_holds import (
    FraudScopeBusy,
    lock_driver_fraud_scopes,
    lock_fraud_hold_scope,
    lock_fraud_hold_scopes,
)
from app.services.trip_processing import process_ended_trip

READ_LOCK_TIMEOUT = "500ms"


class Holder:
    """Run ``body(session, pause)`` in another thread; ``pause`` parks it open."""

    def __init__(self, sessionmaker, body):
        self._sessionmaker = sessionmaker
        self._body = body
        self.ready = threading.Event()
        self.release = threading.Event()
        self.pid = None
        self.error = None
        self.result = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    async def pause(self, session):
        self.pid = await session.scalar(text("SELECT pg_backend_pid()"))
        self.ready.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)

    def _run(self):
        async def main():
            async with self._sessionmaker() as session:
                self.result = await self._body(session, self.pause)
                await session.commit()

        try:
            asyncio.run(main())
        except BaseException as exc:  # surfaced by stop()
            self.error = exc
        finally:
            self.ready.set()

    def __enter__(self):
        self._thread.start()
        assert self.ready.wait(20), "holder never took its locks"
        if self.error is not None:
            raise self.error
        return self

    def __exit__(self, *exc_info):
        self.release.set()
        self._thread.join(30)
        assert not self._thread.is_alive(), "holder did not finish"
        if self.error is not None and exc_info[0] is None:
            raise self.error


@pytest.fixture
def read_client(settings, postgis_db_sessionmaker):
    app = create_app(settings)

    async def short_wait_session():
        async with postgis_db_sessionmaker() as session:
            await session.execute(text(f"SET lock_timeout = '{READ_LOCK_TIMEOUT}'"))
            yield session

    app.dependency_overrides[get_session] = short_wait_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def paused_trip_processing(monkeypatch, settings, trip_id):
    """Holder body: real trip processing, parked right after it took its locks."""
    original = trip_processing.repair_missing_ledger_entries
    parked = {}

    async def repair(session, *, trip_id: object):
        if trip_id == parked["trip_id"]:
            await parked["pause"](session)
        return await original(session, trip_id=trip_id)

    monkeypatch.setattr(trip_processing, "repair_missing_ledger_entries", repair)

    async def body(session, pause):
        parked.update(trip_id=trip_id, pause=pause)
        result = await process_ended_trip(session, trip_id=trip_id, settings=settings)
        return result.overall

    return body


def advertiser_reads(client, headers, campaign_id):
    root = f"/api/v1/advertiser/campaigns/{campaign_id}"
    return {
        "daily_metrics": client.get(f"{root}/daily-metrics", headers=headers),
        "report": client.get(f"{root}/report", headers=headers),
        "dashboard": client.get("/api/v1/advertiser/dashboard/summary", headers=headers),
    }


def statuses(responses):
    return {name: response.status_code for name, response in responses.items()}


async def _with_timeout(sessionmaker, action):
    async with sessionmaker() as session:
        await session.execute(text(f"SET LOCAL lock_timeout = '{READ_LOCK_TIMEOUT}'"))
        result = await action(session)
        await session.commit()
        return result


def run_short(sessionmaker, action):
    return asyncio.run(_with_timeout(sessionmaker, action))


def heatmap_tenant(db, tag):
    graph = create_heatmap_graph(
        db,
        advertiser_email=f"adv-{tag}@example.com",
        driver_email=f"drv-{tag}@example.com",
        plate_number=f"RQ-{uuid4().hex[:6]}".upper(),
        organization_name=f"Org {tag}",
    )
    admin, advertiser, organization, campaign, driver, profile, vehicle, trip, _ = graph
    return SimpleNamespace(
        advertiser=advertiser,
        organization=organization,
        campaign=campaign,
        profile=profile,
        trip=trip,
    )


def test_unrelated_campaigns_and_drivers_do_not_wait_for_trip_processing(
    postgis_db_sessionmaker, read_client, settings, monkeypatch
):
    db = postgis_db_sessionmaker
    processing = build_graph(db, "rq-held")
    other_processing = build_graph(db, "rq-free")
    tenant = heatmap_tenant(db, "rq-other-org")
    headers = auth_headers(read_client, tenant.advertiser.email, PASSWORD)

    body = paused_trip_processing(monkeypatch, settings, processing.trip.id)
    with Holder(db, body):
        # The live-test 500s: another organisation's report pages.
        assert statuses(advertiser_reads(read_client, headers, tenant.campaign.id)) == {
            "daily_metrics": 200,
            "report": 200,
            "dashboard": 200,
        }
        # Another driver's trip and driver scopes are free.
        run_short(db, lambda s: lock_fraud_hold_scope(s, tenant.trip.id))
        run_short(db, lambda s: lock_driver_fraud_scopes(s, (tenant.profile.id,)))

        # Another campaign's trip processing completes meanwhile.
        async def process_other(session):
            return (
                await process_ended_trip(
                    session, trip_id=other_processing.trip.id, settings=settings
                )
            ).overall

        assert run_short(db, process_other) in {"completed", "partial"}


def test_same_campaign_read_waits_for_processing_then_succeeds_and_never_500s(
    postgis_db_sessionmaker, read_client, settings, monkeypatch
):
    db = postgis_db_sessionmaker
    processing = build_graph(db, "rq-same")
    headers = auth_headers(read_client, "advertiser-rq-same@example.com", PASSWORD)

    body = paused_trip_processing(monkeypatch, settings, processing.trip.id)
    with Holder(db, body) as holder:
        responses = advertiser_reads(read_client, headers, processing.campaign.id)
        assert statuses(responses) == {
            "daily_metrics": 503,
            "report": 503,
            "dashboard": 503,
        }
        for response in responses.values():
            assert response.json()["error"]["code"] == "TRY_AGAIN_SOON"
            assert response.json()["error"]["message"] == (
                "This page is busy. Try again in a moment."
            )

        # The same read without a timeout really waits on the processor.
        waiter_pid = {}

        async def snapshot(session):
            waiter_pid["pid"] = await session.scalar(text("SELECT pg_backend_pid()"))
            await lock_trip_disclosure_snapshot(
                session,
                tenant_id=processing.campaign.organization_id,
                campaign_id=processing.campaign.id,
            )

        async def observe():
            async with db() as session:
                task = asyncio.create_task(_plain(db, snapshot))
                for _ in range(500):
                    if "pid" in waiter_pid:
                        blockers = await session.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": waiter_pid["pid"]}
                        )
                        if holder.pid in blockers:
                            break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("the reader did not wait for the processor")
                assert not task.done()
                holder.release.set()
                await asyncio.wait_for(task, 20)

        asyncio.run(observe())
    assert holder.result in {"completed", "partial"}
    assert statuses(advertiser_reads(read_client, headers, processing.campaign.id)) == {
        "daily_metrics": 200,
        "report": 200,
        "dashboard": 200,
    }


async def _plain(sessionmaker, action):
    async with sessionmaker() as session:
        result = await action(session)
        await session.commit()
        return result


def test_concurrent_readers_of_one_campaign_and_organisation_all_succeed(
    postgis_db_sessionmaker, read_client
):
    db = postgis_db_sessionmaker
    tenant = heatmap_tenant(db, "rq-readers")
    headers = auth_headers(read_client, tenant.advertiser.email, PASSWORD)

    async def hold_snapshot(session, pause):
        await lock_trip_disclosure_snapshot(
            session, tenant_id=tenant.organization.id, campaign_id=None
        )
        await pause(session)

    root = f"/api/v1/advertiser/campaigns/{tenant.campaign.id}"
    paths = [f"{root}/daily-metrics", f"{root}/report", "/api/v1/advertiser/dashboard/summary"]
    with Holder(db, hold_snapshot):
        # An organisation-wide reader is open; same-campaign and same-
        # organisation readers share it and each other.
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(
                pool.map(lambda path: read_client.get(path, headers=headers), paths * 2)
            )
    assert [response.status_code for response in responses] == [200] * 6, [
        response.text for response in responses if response.status_code != 200
    ]


def test_driver_keys_serialise_one_driver_only(postgis_db_sessionmaker):
    db = postgis_db_sessionmaker
    first = heatmap_tenant(db, "rq-drv-a")
    second = heatmap_tenant(db, "rq-drv-b")

    async def hold_driver(session, pause):
        await lock_driver_fraud_scopes(session, (first.profile.id,))
        await pause(session)

    with Holder(db, hold_driver):
        run_short(db, lambda s: lock_driver_fraud_scopes(s, (second.profile.id,)))
        with pytest.raises(DBAPIError) as busy:
            run_short(db, lambda s: lock_driver_fraud_scopes(s, (first.profile.id,)))
        assert database_sqlstate(busy.value) == "55P03"


def test_opposite_input_orders_over_two_drivers_never_deadlock(postgis_db_sessionmaker):
    db = postgis_db_sessionmaker
    first = heatmap_tenant(db, "rq-order-a")
    second = heatmap_tenant(db, "rq-order-b")
    forward = (first, second)
    backward = (second, first)

    async def take(order):
        async with db() as session:
            await lock_driver_fraud_scopes(session, (item.profile.id for item in order))
            await asyncio.sleep(0.01)
            await lock_fraud_hold_scopes(session, (item.trip.id for item in order))
            await asyncio.sleep(0.01)
            await session.commit()

    async def race():
        for _ in range(10):
            await asyncio.wait_for(asyncio.gather(take(forward), take(backward)), 20)

    asyncio.run(race())


def test_replay_busy_while_a_reader_holds_the_member_trips_campaign(
    postgis_db_sessionmaker, settings
):
    db = postgis_db_sessionmaker
    count = settings.route_replay_min_valid_pings
    member_trip, member_analytics = replay_graph(
        db, "rq-member", ended_at=REPLAY_TIME + timedelta(minutes=30)
    )
    incoming_trip, incoming_analytics = replay_graph(
        db, "rq-incoming", ended_at=REPLAY_TIME + timedelta(hours=2)
    )
    run_detection(
        db,
        trip=member_trip,
        analytics=member_analytics,
        points=[ping(index) for index in range(count)],
        settings=settings,
        now=REPLAY_TIME + timedelta(hours=3),
    )

    async def member_tenant():
        async with db() as session:
            return await session.scalar(
                select(Campaign.organization_id).where(Campaign.id == member_trip.campaign_id)
            )

    tenant_id = asyncio.run(member_tenant())

    async def hold_reader(session, pause):
        await lock_trip_disclosure_snapshot(
            session, tenant_id=tenant_id, campaign_id=member_trip.campaign_id
        )
        await pause(session)

    async def detect(session):
        await route_replay.detect_route_replay(
            session,
            trip=incoming_trip,
            analytics=incoming_analytics,
            ordered_pings=[ping(index, shifted_seconds=3600) for index in range(count)],
            settings=settings,
            now=REPLAY_TIME + timedelta(hours=4),
        )

    async def signature_count():
        async with db() as session:
            return len(
                (
                    await session.scalars(
                        select(RouteReplaySignature.id).where(
                            RouteReplaySignature.trip_session_id == incoming_trip.id
                        )
                    )
                ).all()
            )

    with Holder(db, hold_reader):
        # Replay must not wait behind the reader's share lock on the member.
        with pytest.raises(FraudScopeBusy):
            asyncio.run(asyncio.wait_for(_plain(db, detect), 5))
        assert asyncio.run(signature_count()) == 0
    asyncio.run(_plain(db, detect))
    assert asyncio.run(signature_count()) == 1


def test_trip_job_retries_busy_without_reporting_an_error(settings, monkeypatch):
    from arq import Retry

    from app.jobs import trip_processing as job

    captured = []
    monkeypatch.setattr(job, "capture_exception", captured.append)

    async def busy(session, *, trip_id, settings):
        raise FraudScopeBusy(str(trip_id))

    monkeypatch.setattr(job, "process_ended_trip", busy)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def rollback(self):
            return None

        async def commit(self):
            raise AssertionError("a busy run must not commit")

    due = SimpleNamespace(id=uuid4(), ended_at=REPLAY_TIME)

    async def due_page(session, **kwargs):
        return [due]

    monkeypatch.setattr(job, "find_unprocessed_trip_page", due_page)
    ctx = {"settings": settings, "sessionmaker": Session}

    with pytest.raises(Retry):
        asyncio.run(job.process_trip(ctx, str(due.id)))
    sweep = asyncio.run(job.process_unprocessed_trips(ctx))
    assert sweep["skipped"] == 1 and sweep["failed"] == 0
    assert captured == []


def test_report_discovery_commits_each_campaign_before_the_next(
    postgis_db_sessionmaker, settings, monkeypatch
):
    from test_req217_reports import owner_graph
    from test_stored_files import FakeStorageProvider

    from app.models.user import User, UserRole, UserStatus
    from app.services import report_scheduling
    from app.services.report_authorization import (
        REPORT_ACTOR_EMAIL,
        REPORT_ACTOR_ID,
        REPORT_ACTOR_NAME,
        REPORT_ACTOR_PASSWORD,
    )

    db = postgis_db_sessionmaker
    graphs = [owner_graph(db, "rq-sched-a"), owner_graph(db, "rq-sched-b")]
    first, second = sorted((graph[2] for graph in graphs), key=lambda row: str(row.id))

    async def add_report_actor():
        async with db() as session:
            session.add(
                User(
                    id=REPORT_ACTOR_ID,
                    email=REPORT_ACTOR_EMAIL,
                    full_name=REPORT_ACTOR_NAME,
                    password_hash=REPORT_ACTOR_PASSWORD,
                    role=UserRole.ADMIN,
                    status=UserStatus.DISABLED,
                )
            )
            await session.commit()

    asyncio.run(add_report_actor())
    original = report_scheduling.create_report
    parked = {}

    async def create_report(session, **kwargs):
        if kwargs["campaigns"][0].id == second.id:
            await parked["pause"](session)
        return await original(session, **kwargs)

    monkeypatch.setattr(report_scheduling, "create_report", create_report)

    async def discover(session, pause):
        parked["pause"] = pause
        return await report_scheduling.discover_reports(
            session, settings=settings, storage=FakeStorageProvider(), limit=10
        )

    with Holder(db, discover) as holder:
        # Discovery is building the second campaign's report; the first
        # campaign's report was committed and its key released.
        async def read_first(session):
            await lock_trip_disclosure_snapshot(
                session, tenant_id=first.organization_id, campaign_id=first.id
            )

        run_short(db, read_first)
    assert holder.result == 2
