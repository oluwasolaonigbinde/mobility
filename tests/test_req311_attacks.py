"""PostgreSQL reproductions of the contract's twelve disclosure attacks.

These exercise persisted trips, PostGIS areas, real HTTP reads and report snapshots.
The same file runs against the untouched 0fe8cf9d app for the red receipt.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import delete, func, select, update
from test_campaign_live_positions import (  # noqa: F401
    NOW as LIVE_NOW,
)
from test_campaign_live_positions import (
    add_point,
)
from test_campaign_live_positions import (
    driving_graph as make_live_graph,
)
from test_campaign_live_positions import (
    read as read_live,
)
from test_heatmaps import add_ping_batch
from test_req217_reports import driving_trip, owner_graph
from test_stored_files import FakeStorageProvider

from app.models.campaign import Campaign
from app.models.campaign_cancellation import CampaignCancellation
from app.models.campaign_report import CampaignReport
from app.models.campaign_zone import CampaignZone
from app.models.impression import ImpressionEstimate
from app.models.trip import LocationPing, TripSession
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.services.campaign_report_data import build_report_snapshot
from app.services.campaign_reports import create_report
from app.services.report_scheduling import next_due_window, report_cutoff

LAGOS = ZoneInfo("Africa/Lagos")
MONDAY = datetime(2020, 1, 6, tzinfo=LAGOS)
CLOCK = datetime(2020, 1, 27, 12, tzinfo=UTC)
PASSWORD = "long-secure-password"


@pytest.fixture
def live_graph(db_sessionmaker, monkeypatch):
    return make_live_graph.__wrapped__(db_sessionmaker, monkeypatch)


@pytest.fixture
def graph(db_sessionmaker, settings, monkeypatch):
    owner, organization, campaign = owner_graph(db_sessionmaker, "attack")

    async def clock(_session):
        return CLOCK

    monkeypatch.setattr("app.services.payout_rule_serialization.database_clock", clock)
    return owner, organization, campaign


def trips(maker, campaign, count=3, day=0, *, prefix="cars", longitudes=None):
    result = []
    for index in range(count):
        trip = driving_trip(
            maker,
            campaign=campaign,
            suffix=f"{prefix}-{day}-{index}",
            ended_at=MONDAY + timedelta(days=day, hours=12),
        )
        if longitudes is not None:
            add_ping_batch(
                maker,
                trip_id=trip.id,
                points=[
                    (trip.started_at + timedelta(minutes=i), 6.5, longitudes[index])
                    for i in (10, 11)
                ],
                idempotency_key=str(trip.id),
            )
        result.append(trip)
    return result


def area(maker, owner, campaign, name="A", west=3.39, east=3.42):
    from app.services.campaign_zones import geometry_expression

    async def save():
        async with maker() as session:
            geometry = {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [west, 6.49],
                            [east, 6.49],
                            [east, 6.51],
                            [west, 6.51],
                            [west, 6.49],
                        ]
                    ]
                ],
            }
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=owner.id,
                name=name,
                zone_type="target",
                zone_metadata={},
                geom=geometry_expression(json.dumps(geometry)),
            )
            session.add(zone)
            await session.commit()
            return zone

    return asyncio.run(save())


def snapshot(maker, settings, owner, campaign, start=MONDAY, end=None, now=CLOCK):
    async def run():
        async with maker() as session:
            value = await build_report_snapshot(
                session,
                campaigns=[campaign],
                actor_user_id=owner.id,
                start=start,
                end=end or start + timedelta(days=7),
                settings=settings,
                storage=FakeStorageProvider(),
                now=now,
                budget={"snapshot_bytes": 0, "pixels": 40_000_000},
            )
            return value["campaigns"][0]

    return asyncio.run(run())


def test_attack_a_total_minus_released_days(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    trips(db_sessionmaker, campaign)
    trips(db_sessionmaker, campaign, 1, 1)
    value = snapshot(db_sessionmaker, settings, owner, campaign)
    visible = sum(Decimal(d["distance_m"]) for d in value["daily"] if d["distance_m"] is not None)
    assert Decimal(value["measured"]["distance_m"]) - visible == 0
    assert value["note"] == "Some days hidden."


def test_attack_b_overlapping_windows(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    trips(db_sessionmaker, campaign)
    trips(db_sessionmaker, campaign, 1, 1)
    trips(db_sessionmaker, campaign, 3, 2)
    left = snapshot(db_sessionmaker, settings, owner, campaign, end=MONDAY + timedelta(days=2))
    right = snapshot(
        db_sessionmaker,
        settings,
        owner,
        campaign,
        start=MONDAY + timedelta(days=1),
        end=MONDAY + timedelta(days=3),
    )
    assert Decimal(left["measured"]["distance_m"]) == 3000
    assert Decimal(right["measured"]["distance_m"]) == 3000


def test_attack_c_poll_today_twice(db_client, db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    day = (CLOCK.astimezone(LAGOS).date() - MONDAY.date()).days
    trips(db_sessionmaker, campaign, day=day)
    headers = auth_headers(db_client, owner.email, PASSWORD)
    start = CLOCK.astimezone(LAGOS).replace(hour=0, minute=0, second=0, microsecond=0)
    query = {"start_at": start.isoformat(), "end_at": (start + timedelta(days=1)).isoformat()}
    path = f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics"
    first = db_client.get(path, headers=headers, params=query).json()["items"][0]
    trips(db_sessionmaker, campaign, count=1, day=day, prefix="later")
    second = db_client.get(path, headers=headers, params=query).json()["items"][0]
    assert first["distance_m"] is second["distance_m"] is None
    assert first["status"] == second["status"] == "not_ready"


@pytest.mark.parametrize("edge", ["partial", "preseal", "hold", "formula"])
def test_attack_d_unfinal_day_cannot_release(db_sessionmaker, settings, graph, edge):
    owner, _, campaign = graph
    # Four cars where one trip drops out: the three left would otherwise publish.
    rows = trips(db_sessionmaker, campaign, count=4 if edge in {"partial", "formula"} else 3)

    async def alter():
        async with db_sessionmaker() as session:
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == rows[0].id)
            )
            if edge == "partial":
                await session.execute(
                    delete(ImpressionEstimate).where(
                        ImpressionEstimate.trip_session_id == rows[0].id
                    )
                )
                await session.delete(analytics)
            elif edge == "preseal":
                analytics.computed_at = rows[0].sealed_at - timedelta(seconds=1)
            elif edge == "hold":
                trip = rows[0]
                session.add(
                    FraudFlag(
                        trip_session_id=trip.id,
                        trip_analytics_id=analytics.id,
                        assignment_id=trip.assignment_id,
                        campaign_id=campaign.id,
                        driver_profile_id=trip.driver_profile_id,
                        vehicle_id=trip.vehicle_id,
                        flag_type="route_replay",
                        severity="high",
                        status="open",
                        description="Synthetic attack hold",
                        evidence={},
                        detected_at=CLOCK,
                    )
                )
            else:
                analytics.formula_version = "old-formula"
            await session.commit()

    asyncio.run(alter())
    value = snapshot(db_sessionmaker, settings, owner, campaign)
    assert value["daily"][0]["distance_m"] is None
    assert value["daily"][0]["status"] == "not_ready"


def test_attack_e_clock_windows_and_no_reflood(db_sessionmaker, settings, graph, monkeypatch):
    from app.models.notification import Notification
    from app.models.user import User
    from app.services.campaign_report_delivery import publish_campaign_report
    from app.services.report_authorization import (
        REPORT_ACTOR_EMAIL,
        REPORT_ACTOR_ID,
        REPORT_ACTOR_NAME,
        REPORT_ACTOR_PASSWORD,
    )
    from app.services.report_scheduling import discover_reports

    owner, _, campaign = graph
    start, end = MONDAY, MONDAY + timedelta(days=7)
    storage = FakeStorageProvider()

    async def existing():
        async with db_sessionmaker() as session:
            stored = await session.get(Campaign, campaign.id)
            stored.start_at = MONDAY + timedelta(hours=12)
            campaign.start_at = stored.start_at
            await session.commit()
            report = await create_report(
                session,
                actor_user_id=owner.id,
                campaigns=[campaign],
                request_id=uuid4(),
                request_fingerprint="a" * 64,
                start=start,
                end=end,
                kind="weekly",
                settings=settings,
                storage=FakeStorageProvider(),
                now=CLOCK,
            )
            await session.commit()
            # A legacy issued weekly end on the same Lagos date, at clock time.
            await session.execute(
                update(CampaignReport)
                .where(CampaignReport.id == report.id)
                .values(period_end_at=end + timedelta(hours=4))
            )
            await session.commit()
            return report.id, set(await session.scalars(select(CampaignReport.period_end_at)))

    prior_id, known = asyncio.run(existing())
    assert (
        next_due_window(
            start + timedelta(hours=12), start + timedelta(days=30), end + timedelta(days=1), known
        )
        is None
    )

    from app.services.report_scheduling import rerun_campaign_report

    admin = create_test_user(db_sessionmaker, email="legacy-rerun@example.com")

    async def clock(_session):
        return end + timedelta(days=1)

    monkeypatch.setattr("app.services.payout_rule_serialization.database_clock", clock)
    monkeypatch.setattr("app.services.report_scheduling.database_clock", clock)

    async def rerun():
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=prior_id, storage=storage)
            == "ready"
        )
        async with db_sessionmaker() as session:
            before = await session.scalar(select(func.count()).select_from(Notification))
            assert before > 0
            session.add(
                User(
                    id=REPORT_ACTOR_ID,
                    email=REPORT_ACTOR_EMAIL,
                    full_name=REPORT_ACTOR_NAME,
                    password_hash=REPORT_ACTOR_PASSWORD,
                    role="admin",
                    status="disabled",
                )
            )
            await session.commit()
        for _ in range(2):
            async with db_sessionmaker() as session:
                assert (
                    await discover_reports(session, settings=settings, storage=storage, limit=10)
                    == 0
                )
                assert not session.info.get("outbox_jobs")
                await session.commit()
                notices = await session.scalar(select(func.count()).select_from(Notification))
                assert notices == before
        async with db_sessionmaker() as session:
            value = await rerun_campaign_report(
                session,
                actor_user_id=admin.id,
                campaign_id=campaign.id,
                request_id=uuid4(),
                settings=settings,
                storage=storage,
            )
            assert value.rerun_of_id == prior_id
            assert value.version == 2
            await session.commit()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=value.id, storage=storage)
            == "ready"
        )
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(CampaignReport)) == 2

    asyncio.run(rerun())


@pytest.mark.parametrize("overlap", [False, True], ids=["f-complement", "g-overlap"])
def test_attack_fg_exact_membership_partitions(db_sessionmaker, settings, graph, overlap):
    owner, _, campaign = graph
    area(db_sessionmaker, owner, campaign)
    if overlap:
        area(db_sessionmaker, owner, campaign, "B", 3.41, 3.46)
    positions = [3.4, 3.4, 3.415, 3.44 if overlap else 3.48, 3.44 if overlap else 3.48]
    trips(db_sessionmaker, campaign, 5, longitudes=positions)
    value = snapshot(db_sessionmaker, settings, owner, campaign)
    assert value["areas"] == []
    assert Decimal(value["measured"]["distance_m"]) == 5000


def test_attack_h_area_across_windows(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    area(db_sessionmaker, owner, campaign)
    trips(db_sessionmaker, campaign, longitudes=[3.4] * 3)
    trips(db_sessionmaker, campaign, 1, 7, longitudes=[3.4])
    week = snapshot(db_sessionmaker, settings, owner, campaign)
    extra = snapshot(db_sessionmaker, settings, owner, campaign, end=MONDAY + timedelta(days=8))
    assert week["areas"][0]["trip_count"] == extra["areas"][0]["trip_count"] == 3


def test_attack_i_areas_page_excludes_partial_week(db_client, db_sessionmaker, graph, monkeypatch):
    owner, _, campaign = graph
    area(db_sessionmaker, owner, campaign)
    trips(db_sessionmaker, campaign, longitudes=[3.4] * 3)

    async def clock(_session):
        return MONDAY + timedelta(days=3)

    monkeypatch.setattr("app.services.payout_rule_serialization.database_clock", clock)
    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        headers=auth_headers(db_client, owner.email, PASSWORD),
    )
    assert response.status_code == 200
    assert sum(a["trip_count"] for a in response.json()["areas"]) == 0
    assert "totals" not in response.json()


def test_attack_j_unused_routes_are_absent(db_client, db_sessionmaker, graph):
    owner, _, campaign = graph
    trips(db_sessionmaker, campaign)
    headers = auth_headers(db_client, owner.email, PASSWORD)
    root = f"/api/v1/advertiser/campaigns/{campaign.id}"
    paths = [
        root + "/" + suffix for suffix in ("summary", "trips", "impressions/summary", "heatmap")
    ]
    paths.append("/api/v1/advertiser/dashboard/summary")
    statuses = {p: db_client.get(p, headers=headers).status_code for p in paths}
    assert set(statuses.values()) == {404}, statuses


def test_attack_k_live_bucket_and_rounding(db_client, db_sessionmaker, live_graph, monkeypatch):
    from app.services import campaign_live_positions

    add_point(db_sessionmaker, live_graph, age=16, received_age=16, lon=3.401234, lat=6.501234)

    async def clock1(_session):
        return LIVE_NOW + timedelta(minutes=1)

    monkeypatch.setattr(campaign_live_positions, "database_clock", clock1)
    first = read_live(db_client, live_graph).json()["positions"]
    add_point(db_sessionmaker, live_graph, age=14.5, received_age=14.5, lon=3.402345, lat=6.502345)

    async def clock2(_session):
        return LIVE_NOW + timedelta(minutes=4)

    monkeypatch.setattr(campaign_live_positions, "database_clock", clock2)
    second = read_live(db_client, live_graph).json()["positions"]
    assert first == second == [{"longitude": 3.401, "latitude": 6.501}]


def test_attack_l_period_distinct_cars_removed(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    area(db_sessionmaker, owner, campaign)
    trips(db_sessionmaker, campaign, longitudes=[3.4] * 3)
    value = snapshot(db_sessionmaker, settings, owner, campaign)
    assert "cars_driven" not in value["measured"]
    assert Decimal(value["measured"]["average_cars_per_day"]) == Decimal(3) / 7
    assert all("vehicle_count" not in row for row in value["areas"])


@pytest.mark.parametrize("status", ["insufficient_data", "blocked"])
def test_final_noncomputed_analytics_releases_empty_day(db_sessionmaker, settings, graph, status):
    owner, _, campaign = graph
    trips(db_sessionmaker, campaign)

    async def change():
        async with db_sessionmaker() as session:
            await session.execute(update(TripAnalytics).values(status=status))
            await session.commit()

    asyncio.run(change())
    value = snapshot(db_sessionmaker, settings, owner, campaign)
    assert value["daily"][0]["distance_m"] is not None
    assert Decimal(value["daily"][0]["distance_m"]) == 0
    assert value["daily"][0]["status"] == "released"


def test_auto_end_backdates_across_midnight_without_early_release(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    source = trips(db_sessionmaker, campaign)[0]

    async def run():
        async with db_sessionmaker() as session:
            active = TripSession(
                assignment_id=source.assignment_id,
                campaign_id=campaign.id,
                driver_profile_id=source.driver_profile_id,
                vehicle_id=source.vehicle_id,
                started_by_user_id=source.started_by_user_id,
                status="active",
                started_at=MONDAY + timedelta(hours=23, minutes=59),
                evidence_protocol_version=2,
                trip_metadata={},
            )
            session.add(active)
            await session.commit()
            return active.id

    ident = asyncio.run(run())
    before = snapshot(db_sessionmaker, settings, owner, campaign)
    assert before["daily"][0]["distance_m"] is None
    assert before["daily"][0]["status"] == "not_ready"

    async def finish():
        from app.services.trips import auto_end_inactive_trip

        async with db_sessionmaker() as session:
            await auto_end_inactive_trip(session, trip_id=ident, settings=settings, now=CLOCK)
            await session.commit()
            trip = await session.get(TripSession, ident)
            assert trip.ended_at.astimezone(LAGOS).date() == MONDAY.date()

    asyncio.run(finish())
    after = snapshot(db_sessionmaker, settings, owner, campaign)
    assert after["daily"][0]["distance_m"] is None
    assert after["daily"][0]["status"] == "not_ready"


@pytest.mark.parametrize("seconds,expected", [(-1, "not_ready"), (0, "released")])
def test_lagos_midnight_boundary(db_sessionmaker, settings, graph, seconds, expected):
    owner, _, campaign = graph
    trips(db_sessionmaker, campaign)
    value = snapshot(
        db_sessionmaker,
        settings,
        owner,
        campaign,
        end=MONDAY + timedelta(days=1),
        now=MONDAY + timedelta(days=1, seconds=seconds),
    )
    published = value["daily"][0]["distance_m"]
    assert (published is None) if expected == "not_ready" else (Decimal(published) == 3000)
    assert value["daily"][0]["status"] == expected


def test_midday_cancellation_uses_following_lagos_midnight(db_sessionmaker, graph):
    owner, organization, campaign = graph

    async def run():
        async with db_sessionmaker() as session:
            row = await session.get(Campaign, campaign.id)
            row.status = "cancelled"
            session.add(
                CampaignCancellation(
                    campaign_id=campaign.id,
                    organization_id=organization.id,
                    requested_by_user_id=owner.id,
                    client_request_id=uuid4(),
                    request_fingerprint="c" * 64,
                    reason="Synthetic midday cutoff",
                    prior_status="active",
                    cutoff_at=MONDAY + timedelta(hours=12),
                    disposition="no_settlement",
                    refundable_amount=0,
                    currency="NGN",
                    released_liability_amount=0,
                    cancelled_assignment_count=0,
                )
            )
            await session.commit()
            return await report_cutoff(session, row)

    assert asyncio.run(run()) == MONDAY + timedelta(days=1)


def test_future_days_are_not_ready(db_client, graph):
    owner, _, campaign = graph
    start = CLOCK.astimezone(LAGOS).replace(hour=0, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics",
        headers=auth_headers(db_client, owner.email, PASSWORD),
        params={"start_at": start.isoformat(), "end_at": (start + timedelta(days=2)).isoformat()},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert all(
        row["status"] == "not_ready" and row["distance_m"] is None
        for row in response.json()["items"]
    )


def test_retention_gap_is_per_week(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    area(db_sessionmaker, owner, campaign)
    trips(db_sessionmaker, campaign, longitudes=[3.4] * 3)
    later = trips(db_sessionmaker, campaign, day=7, longitudes=[3.4] * 3)

    async def remove():
        async with db_sessionmaker() as session:
            await session.execute(
                delete(LocationPing).where(LocationPing.trip_session_id == later[0].id)
            )
            await session.commit()

    asyncio.run(remove())
    value = snapshot(db_sessionmaker, settings, owner, campaign, end=MONDAY + timedelta(days=14))
    assert value["areas"][0]["trip_count"] == 3


def test_preseal_recompute_releases_only_after_seal(db_sessionmaker, settings, graph):
    owner, _, campaign = graph
    records = trips(db_sessionmaker, campaign)

    async def set_time(after):
        async with db_sessionmaker() as session:
            await session.execute(
                update(TripAnalytics)
                .where(TripAnalytics.trip_session_id == records[0].id)
                .values(computed_at=records[0].sealed_at + timedelta(seconds=1 if after else -1))
            )
            await session.commit()

    asyncio.run(set_time(False))
    before = snapshot(db_sessionmaker, settings, owner, campaign)
    assert before["daily"][0]["distance_m"] is None
    assert before["daily"][0]["status"] == "not_ready"
    asyncio.run(set_time(True))
    after = snapshot(db_sessionmaker, settings, owner, campaign)
    assert after["daily"][0]["status"] == "released"
    assert Decimal(after["measured"]["distance_m"]) == 3000


def test_scheduler_and_rerun_wait_for_closed_days(db_sessionmaker, settings, graph):
    from app.core.errors import AppError
    from app.models.user import User, UserRole, UserStatus
    from app.services.report_authorization import (
        REPORT_ACTOR_EMAIL,
        REPORT_ACTOR_ID,
        REPORT_ACTOR_NAME,
        REPORT_ACTOR_PASSWORD,
    )
    from app.services.report_scheduling import discover_reports, rerun_campaign_report

    owner, _, campaign = graph
    original = trips(db_sessionmaker, campaign)[0]

    async def run():
        async with db_sessionmaker() as session:
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
            session.add(
                TripSession(
                    assignment_id=original.assignment_id,
                    campaign_id=campaign.id,
                    driver_profile_id=original.driver_profile_id,
                    vehicle_id=original.vehicle_id,
                    started_by_user_id=original.started_by_user_id,
                    status="active",
                    started_at=MONDAY,
                    evidence_protocol_version=2,
                    trip_metadata={},
                )
            )
            await session.commit()
        async with db_sessionmaker() as session:
            count = await discover_reports(
                session, settings=settings, storage=FakeStorageProvider(), limit=10
            )
            assert count == 0
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as error:
                await rerun_campaign_report(
                    session,
                    actor_user_id=REPORT_ACTOR_ID,
                    campaign_id=campaign.id,
                    request_id=uuid4(),
                    settings=settings,
                    storage=FakeStorageProvider(),
                )
            assert error.value.code == "REPORT_NOT_DUE"

    asyncio.run(run())
