"""REQ-312: the seeded demo live cars stay on the advertiser map while the worker runs."""

import asyncio
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select
from test_business_health import FakeRedis
from test_seed_demo import seed_demo_graph, seed_private_storage  # noqa: F401

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.trips import LocationPingBatchCreate
from app.seeds import live_car
from app.seeds.demo import palmpay_zone_specs, zone_geometries
from app.services import campaign_live_positions
from app.services import trips as trip_service
from app.services.campaign_live_positions import live_positions
from app.services.trip_evidence import batch_payload_hash
from app.services.trips import auto_end_inactive_trip

FIVE = timedelta(minutes=5)


def _ceil_slot(at: datetime) -> datetime:
    floor = at.replace(minute=at.minute // 5 * 5, second=0, microsecond=0)
    return floor if floor == at else floor + FIVE


async def _live_trips(sessionmaker, *, active_only=True):
    async with sessionmaker() as session:
        query = select(TripSession).where(
            TripSession.trip_metadata["seed_version"].as_string() == "demo-live-v1"
        )
        if active_only:
            query = query.where(TripSession.status == "active")
        return list(await session.scalars(query.order_by(TripSession.campaign_id)))


async def _row_counts(sessionmaker, trip_ids):
    async with sessionmaker() as session:
        batches = await session.scalar(
            select(func.count(LocationPingBatch.id)).where(
                LocationPingBatch.trip_session_id.in_(trip_ids)
            )
        )
        pings = await session.scalar(
            select(func.count(LocationPing.id)).where(LocationPing.trip_session_id.in_(trip_ids))
        )
        return batches, pings


async def _shows_live_car(sessionmaker, *, advertiser_id, trip, settings, now):
    """The campaign's map returns this trip's own latest delayed fix at ``now``."""
    bucket = campaign_live_positions.position_bucket(now)
    cutoff = bucket - timedelta(minutes=15)
    async with sessionmaker() as session:
        latest = (
            await session.execute(
                select(LocationPing.longitude, LocationPing.latitude)
                .where(
                    LocationPing.trip_session_id == trip.id,
                    LocationPing.recorded_at <= cutoff,
                    LocationPing.received_at <= cutoff,
                )
                .order_by(LocationPing.recorded_at.desc())
                .limit(1)
            )
        ).one_or_none()
        result = await live_positions(
            session, user_id=advertiser_id, campaign_id=trip.campaign_id, settings=settings
        )
        await session.commit()
    if latest is None:
        return False
    shown = {(p.longitude, p.latitude) for p in result.positions}
    return (round(latest[0], 3), round(latest[1], 3)) in shown


def _controlled_clocks(monkeypatch):
    clock: dict[str, datetime | None] = {"now": None}
    real_utc_now = trip_service.utc_now
    real_database_clock = campaign_live_positions.database_clock

    def utc_now():
        return clock["now"] or real_utc_now()

    async def database_clock(session):
        return clock["now"] or await real_database_clock(session)

    monkeypatch.setattr(trip_service, "utc_now", utc_now)
    monkeypatch.setattr(campaign_live_positions, "database_clock", database_clock)
    return clock


def test_both_live_cars_stay_visible_every_five_minutes_from_seed_to_cap(
    postgis_db_sessionmaker, settings, monkeypatch
):
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)
    clock = _controlled_clocks(monkeypatch)
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})

    async def walk():
        trips = await _live_trips(postgis_db_sessionmaker)
        assert len(trips) == 2 and len({trip.campaign_id for trip in trips}) == 2
        seeded = datetime.now(UTC).replace(microsecond=0)
        clock["now"] = seeded
        for trip in trips:
            assert await _shows_live_car(
                postgis_db_sessionmaker,
                advertiser_id=graph.advertiser.id,
                trip=trip,
                settings=settings,
                now=seeded,
            ), ("live car missing at seeding", trip.campaign_id)
        cap = min(trip.started_at for trip in trips) + timedelta(hours=12)
        # The arq cron fires on the five-minute marks; jobs start a few seconds late.
        tick = _ceil_slot(seeded) + timedelta(seconds=7)
        checks = 0
        while tick <= cap:
            clock["now"] = tick
            summary = await live_car.refresh_demo_live_cars(
                postgis_db_sessionmaker, settings=enabled, now=tick
            )
            assert summary["trips"] == 2, (tick, summary)
            if checks == 0:
                before = await _row_counts(postgis_db_sessionmaker, [t.id for t in trips])
                repeat = await live_car.refresh_demo_live_cars(
                    postgis_db_sessionmaker, settings=enabled, now=tick
                )
                # AC5: a second run in the same slot is a duplicate, never a new row.
                assert repeat["accepted"] == 0 and repeat["duplicates"] == 2, repeat
                assert await _row_counts(postgis_db_sessionmaker, [t.id for t in trips]) == before
            for trip in trips:
                assert await _shows_live_car(
                    postgis_db_sessionmaker,
                    advertiser_id=graph.advertiser.id,
                    trip=trip,
                    settings=settings,
                    now=tick,
                ), ("live car gap", tick - seeded, trip.campaign_id)
            checks += 1
            tick += FIVE
        # Seeding is about 40 minutes after the trip starts: about 136 checks to the cap.
        assert checks >= 130 and tick > cap, (checks, cap)
        print("REQ312_TIMELINE", checks, "five-minute checks, both cars shown", seeded, cap)
        # At the next tick, a capped car rolls over. A finished campaign stops.
        clock["now"] = cap + timedelta(minutes=10)
        async with postgis_db_sessionmaker() as session:
            finished = await session.get(Campaign, trips[0].campaign_id)
            finished.end_at = cap
            await session.commit()
        await live_car.refresh_demo_live_cars(
            postgis_db_sessionmaker, settings=enabled, now=clock["now"]
        )
        fresh = await _live_trips(postgis_db_sessionmaker)
        assert len(fresh) == 1 and fresh[0].campaign_id == trips[1].campaign_id
        assert fresh[0].id != trips[1].id
        assert await _shows_live_car(
            postgis_db_sessionmaker,
            advertiser_id=graph.advertiser.id,
            trip=fresh[0],
            settings=settings,
            now=clock["now"],
        )

    asyncio.run(walk())


def test_refresh_gate_no_ops_and_reseed_brings_the_car_back(
    postgis_db_sessionmaker, settings, monkeypatch
):
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)
    clock = _controlled_clocks(monkeypatch)
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})

    async def gate_and_recover():
        trips = await _live_trips(postgis_db_sessionmaker)
        ids = [trip.id for trip in trips]
        before = await _row_counts(postgis_db_sessionmaker, ids)
        due = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=20)
        clock["now"] = due
        for name, gated in (
            ("flag off", settings),
            (
                "production with flag on",
                settings.model_copy(
                    update={"environment": "production", "demo_live_car_refresh": True}
                ),
            ),
            (
                "staging with ALLOW_DEMO_SEED only",
                settings.model_copy(update={"environment": "staging", "allow_demo_seed": True}),
            ),
        ):
            summary = await live_car.refresh_demo_live_cars(
                postgis_db_sessionmaker, settings=gated, now=due
            )
            assert summary == {"trips": 0, "accepted": 0, "duplicates": 0}, (name, summary)
            assert await _row_counts(postgis_db_sessionmaker, ids) == before, name
        abandoned = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=3)
        async with postgis_db_sessionmaker() as session:
            for trip in trips:
                assert await auto_end_inactive_trip(
                    session, trip_id=trip.id, settings=settings, now=abandoned
                )
            await session.commit()
        clock["now"] = abandoned
        summary = await live_car.refresh_demo_live_cars(
            postgis_db_sessionmaker, settings=enabled, now=abandoned
        )
        assert summary == {"trips": 0, "accepted": 0, "duplicates": 0}, summary
        assert await _row_counts(postgis_db_sessionmaker, ids) == before
        clock["now"] = None
        return ids

    ended = asyncio.run(gate_and_recover())
    # AC6: reseeding after auto-end starts a fresh trip and the car shows again.
    seed_demo_graph(postgis_db_sessionmaker, settings)

    async def recovered():
        fresh = await _live_trips(postgis_db_sessionmaker)
        assert len(fresh) == 2 and not {trip.id for trip in fresh} & set(ended)
        assert len(await _live_trips(postgis_db_sessionmaker, active_only=False)) == 4
        for trip in fresh:
            assert await _shows_live_car(
                postgis_db_sessionmaker,
                advertiser_id=graph.advertiser.id,
                trip=trip,
                settings=settings,
                now=datetime.now(UTC),
            )

    asyncio.run(recovered())


def _after_cap_reseed_and_sweep(sessionmaker, settings, monkeypatch, clock, *, start, change):
    """Seed at ``start``, reach the cap, reseed 15 minutes after it, then sweep.

    ``change=False`` is the control: no refresher, and the reseed keeps the capped trip
    (as before REQ-312), so only the clock and the sweep are the same.
    """
    from test_req310_reporting_worker import payout_snapshot

    from app.jobs import trip_processing as jobs
    from app.seeds import demo, rich
    from app.services import trip_processing as processing
    from app.services.trips import find_trips_to_auto_end

    seed_clock = {"now": start}
    for module in (rich, demo):
        monkeypatch.setattr(module, "utc_now", lambda: seed_clock["now"])
    clock["now"] = start
    graph = seed_demo_graph(sessionmaker, settings)
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})

    async def reach_the_cap():
        trips = await _live_trips(sessionmaker)
        cap = min(trip.started_at for trip in trips) + timedelta(hours=12)
        after_cap = cap + timedelta(minutes=15)
        if change:
            # The worker's last run under the cap catches up every slot since seeding.
            last_run = cap - timedelta(seconds=1)
            clock["now"] = last_run
            fed = await live_car.refresh_demo_live_cars(
                sessionmaker, settings=enabled, now=last_run
            )
            assert fed["trips"] == 2 and fed["accepted"] >= 2 * 130, fed
            async with sessionmaker() as session:
                # Before auto-end: the last receipt is ten minutes old, not two hours.
                due = await find_trips_to_auto_end(session, now=after_cap, limit=100)
                assert not {trip.id for trip in trips} & set(due)
        return trips, after_cap

    capped, after_cap = asyncio.run(reach_the_cap())
    # The whole reseed and the sweep run at the after-cap time.
    seed_clock["now"] = clock["now"] = after_cap
    with monkeypatch.context() as control:
        if not change:
            control.setattr(live_car, "LIVE_CAR_CAP", timedelta(days=36500))
        seed_demo_graph(sessionmaker, settings)

    async def database_now(_session):
        return after_cap

    monkeypatch.setattr(processing, "database_now", database_now)

    async def sweep():
        await jobs.process_unprocessed_trips(
            {
                "settings": settings.model_copy(update={"worker_sweep_batch_size": 2000}),
                "sessionmaker": sessionmaker,
            }
        )
        return await payout_snapshot(sessionmaker)

    return graph, capped, after_cap, asyncio.run(sweep())


async def _live_car_money(sessionmaker):
    """Payouts, ledger rows, bindings and fraud flags on any demo live-car trip or assignment."""
    from app.models.payout import AssignmentRuleBinding, EarningsLedgerEntry, PayoutCalculation
    from app.models.trip_analytics import FraudFlag

    live = await _live_trips(sessionmaker, active_only=False)
    trip_ids = [trip.id for trip in live]
    assignment_ids = [trip.assignment_id for trip in live]
    async with sessionmaker() as session:
        counts = {}
        for name, model, condition in (
            (
                "payouts",
                PayoutCalculation,
                PayoutCalculation.trip_session_id.in_(trip_ids)
                | PayoutCalculation.assignment_id.in_(assignment_ids),
            ),
            ("ledger", EarningsLedgerEntry, EarningsLedgerEntry.trip_session_id.in_(trip_ids)),
            (
                "bindings",
                AssignmentRuleBinding,
                AssignmentRuleBinding.assignment_id.in_(assignment_ids),
            ),
            ("fraud_flags", FraudFlag, FraudFlag.trip_session_id.in_(trip_ids)),
        ):
            counts[name] = await session.scalar(select(func.count(model.id)).where(condition))
    return len(live), counts


def test_reseed_after_the_cap_before_auto_end_ends_the_capped_trip(
    postgis_db_sessionmaker, settings, monkeypatch
):
    from conftest import isolated_postgis_sessionmaker

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    clock = _controlled_clocks(monkeypatch)
    # One pinned start for both runs. The reseed 12 h later may cross UTC midnight, when the
    # seed's rolling day window (rich.py:533-534) adds a day of ordinary seeded trips and
    # their money (CI run 43229285581); the control sees the same, so equality is exact.
    # A start far in the past is not usable: parts of the seed read the real clock.
    start = datetime.now(UTC).replace(second=0, microsecond=0)
    with isolated_postgis_sessionmaker() as control_db:
        _, kept, _, control_money = _after_cap_reseed_and_sweep(
            control_db, settings, monkeypatch, clock, start=start, change=False
        )

        async def control_kept_the_capped_trips():
            still = await _live_trips(control_db)
            assert {trip.id for trip in still} == {trip.id for trip in kept}

        asyncio.run(control_kept_the_capped_trips())
    graph, capped, after_cap, money = _after_cap_reseed_and_sweep(
        postgis_db_sessionmaker, settings, monkeypatch, clock, start=start, change=True
    )
    capped_ids = [trip.id for trip in capped]
    # Exact: the refresher, the capped end-and-seal and the fresh trip add no money at all.
    assert money == control_money

    async def recovered():
        fresh = await _live_trips(postgis_db_sessionmaker)
        assert len(fresh) == 2 and not {trip.id for trip in fresh} & set(capped_ids), fresh
        for trip in fresh:
            assert await _shows_live_car(
                postgis_db_sessionmaker,
                advertiser_id=graph.advertiser.id,
                trip=trip,
                settings=settings,
                now=after_cap,
            ), ("fresh live car missing after the cap", trip.campaign_id)
        async with postgis_db_sessionmaker() as session:
            ended = list(
                await session.scalars(select(TripSession).where(TripSession.id.in_(capped_ids)))
            )
            assert [(trip.status, trip.seal_reason) for trip in ended] == [
                ("sealed", "client_complete")
            ] * 2, [(trip.status, trip.seal_reason, trip.end_reason) for trip in ended]
        assert await _live_car_money(postgis_db_sessionmaker) == (
            4,
            {"payouts": 0, "ledger": 0, "bindings": 0, "fraud_flags": 0},
        )

    asyncio.run(recovered())


def _rectangle(spec):
    ring = spec[2]["coordinates"][0]
    lons, lats = [point[0] for point in ring], [point[1] for point in ring]
    return min(lons), max(lons), min(lats), max(lats)


def _inside(rectangle, lon, lat):
    west, east, south, north = rectangle
    return west < lon < east and south < lat < north


def _metres(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111_320, (a[1] - b[1]) * 111_320 * math.cos(lat))


def test_path_is_bounded_moving_plausible_and_never_shared():
    specs = (*zone_geometries(), *palmpay_zone_specs())
    targets = [_rectangle(spec) for spec in specs if spec[1] == "target"]
    exclusions = [_rectangle(spec) for spec in specs if spec[1] == "exclusion"]
    assert len(targets) == 2 and len(exclusions) == 1
    started = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    fixes: dict[int, list] = {0: [], 1: []}
    for offset in (0, 1):
        slot = started
        while slot < started + timedelta(hours=12):
            batch = live_car.live_car_batch(
                trip_id=UUID(int=offset + 1),
                started_at=started,
                path_offset=offset,
                slot=slot,
                batch_sequence=0,
            )
            assert isinstance(batch, LocationPingBatchCreate)
            # Pure function of the trip and the slot: identical payload hash every time.
            again = live_car.live_car_batch(
                trip_id=UUID(int=offset + 1),
                started_at=started,
                path_offset=offset,
                slot=slot,
                batch_sequence=0,
            )
            assert batch_payload_hash(batch) == batch_payload_hash(again)
            assert batch.idempotency_key == again.idempotency_key
            for ping in batch.pings:
                assert slot <= ping.recorded_at < slot + FIVE
                assert ping.accuracy_m is not None and ping.accuracy_m <= 75
                assert ping.speed_mps is not None and 3 <= ping.speed_mps <= 15
                assert all(_inside(r, ping.lon, ping.lat) for r in targets)
                assert not any(_inside(r, ping.lon, ping.lat) for r in exclusions)
                fixes[offset].append((ping.recorded_at, (ping.lat, ping.lon)))
            slot += FIVE
    keys = set()
    for offset, points in fixes.items():
        for (at_a, a), (at_b, b) in zip(points, points[1:], strict=False):
            assert _metres(a, b) / (at_b - at_a).total_seconds() <= 15
        # Moves more than 200 m in every 30-minute window (the parked check never hides it).
        for index in range(30, len(points)):
            window = [p for _, p in points[index - 30 : index + 1]]
            assert max(_metres(window[-1], p) for p in window) > 200, (offset, index)
        keys |= {(offset, round(p[0], 5), round(p[1], 5)) for _, p in points}
    shared = {(lat, lon) for o, lat, lon in keys if o == 0} & {
        (lat, lon) for o, lat, lon in keys if o == 1
    }
    assert not shared


class _FakeSession:
    def __init__(self, *, trip_ids=(), got=None):
        self.trip_ids = list(trip_ids)
        self.got = got
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalars(self, _statement):
        return self.trip_ids

    async def get(self, _model, _key):
        return self.got

    async def commit(self):
        self.commits += 1


def test_job_feeds_the_refresher_the_current_time(settings, monkeypatch):
    from app.jobs import demo_live_car

    now = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    seen = {}

    async def refresh(sessionmaker, *, settings, now):
        seen.update(sessionmaker=sessionmaker, settings=settings, now=now)
        return {"trips": 0, "accepted": 0, "duplicates": 0}

    monkeypatch.setattr(demo_live_car, "refresh_demo_live_cars", refresh)
    monkeypatch.setattr(trip_service, "utc_now", lambda: now)
    ctx = {"sessionmaker": object(), "settings": settings}
    assert asyncio.run(demo_live_car.refresh_demo_live_cars_job(ctx)) == {
        "trips": 0,
        "accepted": 0,
        "duplicates": 0,
    }
    assert seen == {"sessionmaker": ctx["sessionmaker"], "settings": settings, "now": now}


def test_a_trip_that_ended_meanwhile_is_skipped_without_counting(settings, monkeypatch):
    from app.core.errors import AppError

    ended, live = UUID(int=1), UUID(int=2)
    sessions: list[_FakeSession] = []

    def sessionmaker():
        session = _FakeSession(trip_ids=[ended, live])
        sessions.append(session)
        return session

    async def catch_up(_session, *, trip_id, settings, now):
        if trip_id == ended:
            raise AppError("TRIP_ALREADY_ENDED", "Trip has already ended")
        return 3, 1

    monkeypatch.setattr(live_car, "_catch_up", catch_up)
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})
    summary = asyncio.run(
        live_car.refresh_demo_live_cars(
            sessionmaker, settings=enabled, now=datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
        )
    )
    assert summary == {"trips": 1, "accepted": 3, "duplicates": 1}
    # The listing session, then one per trip; only the live trip's work is committed.
    assert [s.commits for s in sessions] == [0, 0, 1]


def test_missing_trip_or_driver_is_never_fed_or_ended(settings):
    now = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    result = asyncio.run(
        live_car._catch_up(_FakeSession(), trip_id=UUID(int=1), settings=settings, now=now)
    )
    assert result == (0, 0)
    trip = TripSession(id=UUID(int=1), driver_profile_id=UUID(int=2))
    with pytest.raises(RuntimeError, match="has no driver profile"):
        asyncio.run(live_car.end_capped_live_car(_FakeSession(), trip=trip, settings=settings))


def test_catch_up_records_the_same_gps_attempt_as_ingest(settings, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    now = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    trip = TripSession(
        id=UUID(int=1),
        campaign_id=UUID(int=4),
        driver_profile_id=UUID(int=2),
        status="active",
        started_at=now - FIVE,
        trip_metadata={},
    )
    session = AsyncMock()
    session.get.side_effect = [
        trip,
        SimpleNamespace(id=UUID(int=2), user_id=UUID(int=3), onboarding_status="active"),
        SimpleNamespace(status="active", start_at=None, end_at=None),
        SimpleNamespace(status="active"),
        SimpleNamespace(status="active", driver_profile_id=UUID(int=2)),
        SimpleNamespace(status="active"),
    ]
    session.scalar.return_value = 0
    session.scalar.side_effect = [True, None, 0]
    ingest = AsyncMock(return_value=SimpleNamespace(duplicate=False))
    record = AsyncMock()
    monkeypatch.setattr(trip_service, "ingest_location_ping_batch", ingest)
    monkeypatch.setattr("app.core.gps_health.record_gps_attempt", record)
    assert asyncio.run(
        live_car._catch_up(session, trip_id=trip.id, settings=settings, now=now)
    ) == (1, 0)
    record.assert_awaited_once_with(settings, ingest.await_args.kwargs["telemetry"])


def test_refresh_ignores_ordinary_active_trip_with_demo_metadata(postgis_db_sessionmaker, settings):
    maker = postgis_db_sessionmaker
    now = live_car.live_car_slot(datetime.now(UTC))
    driver = create_test_user(maker, email="ordinary-live-car@example.test", role=UserRole.DRIVER)
    profile = create_test_driver_profile(
        maker, user_id=driver.id, onboarding_status=DriverOnboardingStatus.ACTIVE
    )
    vehicle = create_test_vehicle(
        maker, driver_profile_id=profile.id, vehicle_status=VehicleStatus.ACTIVE
    )
    admin = create_test_user(maker, email="ordinary-live-car-admin@example.test")
    org, _ = create_test_organization(maker)
    campaign = create_test_campaign(
        maker,
        organization_id=org.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
    )
    assignment = create_test_campaign_assignment(
        maker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
    )
    trip = create_test_trip_session(
        maker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        started_at=now - live_car.LIVE_CAR_CAP,
        metadata={"seed_version": live_car.LIVE_CAR_VERSION, "path_offset": 1},
    )
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})

    async def exercise():
        assert await live_car.refresh_demo_live_cars(maker, settings=enabled, now=now) == {
            "trips": 0,
            "accepted": 0,
            "duplicates": 0,
        }
        async with maker() as session:
            assert await live_car._catch_up(
                session, trip_id=trip.id, settings=enabled, now=now
            ) == (0, 0)
            await session.commit()
        assert await _row_counts(maker, [trip.id]) == (0, 0)
        async with maker() as session:
            unchanged = await session.get(TripSession, trip.id)
            assert unchanged.status == "active" and unchanged.ended_at is None
            assert unchanged.started_at == trip.started_at
            assert unchanged.trip_metadata == trip.trip_metadata
            assert set(await session.scalars(select(TripSession.id))) == {trip.id}

    asyncio.run(exercise())


def test_live_car_rollover_and_health_check_use_real_demo_evidence(
    postgis_db_sessionmaker, settings, monkeypatch
):
    from app.core.gps_health import record_attempt
    from app.models.audit import AuditEvent
    from app.models.disbursement import PayoutAutomaticAlert
    from app.seeds.rich import ensure_reporting_live_car
    from app.services.business_health import health_counts, publish_health_alerts
    from app.services.campaign_reports import SEED_CAMPAIGN_CREATED

    maker = postgis_db_sessionmaker
    driver = create_test_user(maker, email="live-car-driver@example.test", role=UserRole.DRIVER)
    admin = create_test_user(maker, email="live-car-admin@example.test")
    profile = create_test_driver_profile(
        maker, user_id=driver.id, onboarding_status=DriverOnboardingStatus.ACTIVE
    )
    vehicle = create_test_vehicle(
        maker, driver_profile_id=profile.id, vehicle_status=VehicleStatus.ACTIVE
    )
    org, _ = create_test_organization(maker)
    now = live_car.live_car_slot(datetime.now(UTC))
    campaign = create_test_campaign(
        maker,
        organization_id=org.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
    )
    assignment = create_test_campaign_assignment(
        maker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
    )
    redis = FakeRedis()
    clock = _controlled_clocks(monkeypatch)
    enabled = settings.model_copy(update={"demo_live_car_refresh": True})
    monkeypatch.setattr(live_car, "LIVE_CAR_CAP", timedelta(minutes=45))

    async def record(_settings, attempt):
        await record_attempt(redis, rejected=attempt.rejected, now=clock["now"])

    monkeypatch.setattr("app.core.gps_health.record_gps_attempt", record)

    async def exercise():
        async with maker() as session:
            session.add(
                AuditEvent(
                    action=SEED_CAMPAIGN_CREATED, entity_type="campaign", entity_id=str(campaign.id)
                )
            )
            await session.flush()
            await ensure_reporting_live_car(
                session,
                campaign=campaign,
                assignment=assignment,
                settings=settings,
                path_offset=0,
                now=now,
            )
            await session.commit()
        [capped] = await _live_trips(maker)
        clock["now"] = now + FIVE
        production = enabled.model_copy(update={"environment": "production"})
        assert (
            await live_car.refresh_demo_live_cars(maker, settings=production, now=clock["now"])
        )["trips"] == 0
        assert (await live_car.refresh_demo_live_cars(maker, settings=enabled, now=clock["now"]))[
            "trips"
        ] == 1
        [fresh] = await _live_trips(maker)
        assert fresh.id != capped.id
        async with maker() as session:
            assert (await session.get(TripSession, capped.id)).status == "sealed"
            health_time = clock["now"] + timedelta(minutes=1)
            counts = await health_counts(session, now=health_time, settings=enabled, redis=redis)
            await publish_health_alerts(session, now=health_time, counts=counts)
            assert not await session.scalar(
                select(PayoutAutomaticAlert.id).where(
                    PayoutAutomaticAlert.detail["check"]
                    .as_string()
                    .in_(["gps_telemetry_unavailable", "gps_rejections", "stale_trips"])
                )
            )
            (await session.get(Campaign, campaign.id)).end_at = clock["now"]
            await session.commit()
        clock["now"] += FIVE
        await live_car.refresh_demo_live_cars(maker, settings=enabled, now=clock["now"])
        assert await _live_trips(maker) == []

    asyncio.run(exercise())
