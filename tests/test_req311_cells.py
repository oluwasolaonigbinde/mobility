"""REQ-311 fixed-cell attack and closure regressions."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from test_seed_demo import seed_private_storage  # noqa: F401

from app.services.report_cohorts import ReportCohort
from app.services.reports import campaign_daily_series

DAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 10, tzinfo=UTC)


def fixture(cars=3, **changes):
    trips, rows = [], []
    for i in range(cars):
        ident = uuid4()
        trip = NS(
            id=ident,
            vehicle_id=i,
            ended_at=datetime(2026, 11, 2, 12, tzinfo=UTC),
            status="sealed",
            sealed_at=datetime(2026, 11, 2, 13, tzinfo=UTC),
            evidence_adjudication_outcome=None,
        )
        row = NS(
            trip_session_id=ident,
            vehicle_id=i,
            status="computed",
            computed_at=datetime(2026, 11, 2, 14, tzinfo=UTC),
            distance_m=Decimal(100 + i),
            moving_seconds=10 + i,
        )
        for k, v in changes.items():
            setattr(trip if hasattr(trip, k) else row, k, v)
        trips.append(trip)
        rows.append(row)
    return ReportCohort(tuple(trips), tuple(rows), (), (), terminal_period=True)


def series(cohort, **kw):
    return campaign_daily_series(cohort, start_day=DAY, end_day=DAY, now=NOW, **kw)


def test_fixed_day_outputs():
    from app.services.disclosure import released_totals

    large, small = fixture(), fixture(1)
    small.trips[0].ended_at += timedelta(days=1)
    cohort = ReportCohort(large.trips + small.trips, large.analytics + small.analytics, (), ())
    days = campaign_daily_series(cohort, start_day=DAY, end_day=DAY + timedelta(days=1), now=NOW)
    totals = released_totals(days)
    assert totals["distance_m"] == Decimal(303)
    assert totals["trip_count"] == 3
    assert totals["average_cars_per_day"] == 3
    assert "cars_driven" not in totals
    assert days[1].status == "not_enough_cars"


def test_preseal_day_not_ready():
    row = series(fixture(computed_at=datetime(2026, 11, 2, 12, tzinfo=UTC)))[0]
    assert row.status == "not_ready"
    assert row.distance_m is None


def test_insufficient_data_is_final():
    cohort = fixture()
    for row in cohort.analytics:
        row.status = "insufficient_data"
    row = series(cohort)[0]
    assert row.status == "released" and row.distance_m == 0


@pytest.mark.parametrize(
    "at,status",
    [("2026-11-02T22:59:59+00:00", "not_ready"), ("2026-11-02T23:00:00+00:00", "released")],
)
def test_midnight(at, status):
    rows = campaign_daily_series(
        fixture(), start_day=DAY, end_day=DAY, now=datetime.fromisoformat(at)
    )
    assert rows[0].status == status


def test_partition_rule():
    from app.services.disclosure import area_week_figures

    trips = [NS(id=str(i), vehicle_id=i) for i in range(5)]

    def cell(i):
        return {
            "trip_session_id": str(i),
            "grid_x": 0,
            "grid_y": 0,
            "cell_ping_count": 1,
            "total_ping_count": 1,
        }

    assert (
        area_week_figures(
            trips, {"a": [cell(i) for i in (0, 1, 2)], "b": [cell(i) for i in (2, 3, 4)]}, {}
        )
        is None
    )
    trips = trips[:3]
    result = area_week_figures(
        trips,
        {"a": [cell(i) for i in range(3)], "b": [cell(i) for i in range(3)]},
        {str(i): Decimal(10) for i in range(3)},
    )
    assert result["a"] == {"trip_count": 3, "estimated_views": Decimal(30)}


def test_k_live_bucket():
    from app.services.campaign_live_positions import position_bucket

    a = datetime(2026, 11, 2, 12, 1, tzinfo=UTC)
    assert position_bucket(a) == position_bucket(a + timedelta(minutes=3))


def test_postgres_closure_and_additive_totals(db_sessionmaker, settings):
    import asyncio

    from conftest import sign_test_trip_manifest
    from sqlalchemy import select
    from test_req217_reports import driving_trip, owner_graph

    from app.models.trip import TripSession
    from app.models.trip_analytics import TripAnalytics
    from app.services.disclosure import load_cells, midnight, released_totals

    owner, org, campaign = owner_graph(db_sessionmaker, "req311")
    for i in range(3):
        driving_trip(
            db_sessionmaker,
            campaign=campaign,
            suffix=f"req311-{i}",
            ended_at=datetime(2020, 1, 2, 12, tzinfo=UTC),
        )

    async def check():
        async with db_sessionmaker() as session:
            trips = list(
                await session.scalars(
                    select(TripSession).where(TripSession.campaign_id == campaign.id)
                )
            )
            for trip in trips:
                trip.status = "sealed"
                trip.sealed_at = trip.ended_at
                trip.seal_reason = "client_complete"
                sign_test_trip_manifest(trip)
            await session.commit()
            start = midnight(datetime(2020, 1, 2, tzinfo=UTC))
            end = start + timedelta(days=1)

            async def read():
                return (
                    await load_cells(
                        session,
                        campaign_id=campaign.id,
                        start=start,
                        end=end,
                        settings=settings,
                        now=NOW,
                    )
                )[1]

            days = await read()
            assert days[0].status == "released"
            assert released_totals(days)["distance_m"] == 3000
            row = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == trips[0].id)
            )
            from app.models.trip_analytics import FraudFlag

            t = trips[0]
            flag = FraudFlag(
                trip_session_id=t.id,
                trip_analytics_id=row.id,
                assignment_id=t.assignment_id,
                campaign_id=t.campaign_id,
                driver_profile_id=t.driver_profile_id,
                vehicle_id=t.vehicle_id,
                flag_type="route_replay",
                severity="high",
                status="open",
                description="Synthetic hold",
                evidence={},
                detected_at=NOW,
            )
            session.add(flag)
            await session.commit()
            assert (await read())[0].status == "not_ready"
            await session.delete(flag)
            await session.commit()
            active = TripSession(
                assignment_id=t.assignment_id,
                campaign_id=t.campaign_id,
                driver_profile_id=t.driver_profile_id,
                vehicle_id=t.vehicle_id,
                started_by_user_id=t.started_by_user_id,
                status="active",
                started_at=start,
                evidence_protocol_version=2,
                trip_metadata={},
            )
            session.add(active)
            await session.commit()
            assert (await read())[0].status == "not_ready"
            await session.delete(active)
            await session.commit()
            row.computed_at = trips[0].sealed_at - timedelta(seconds=1)
            await session.commit()
            assert (await read())[0].status == "not_ready"
            row.computed_at = NOW
            row.status = "insufficient_data"
            await session.commit()
            # Final insufficient analytics closes the day; two driving cars stay hidden.
            assert (await read())[0].status == "not_enough_cars"
            changed = settings.model_copy(update={"route_analytics_formula_version": "changed"})
            days = (
                await load_cells(
                    session,
                    campaign_id=campaign.id,
                    start=start,
                    end=end,
                    settings=changed,
                    now=NOW,
                )
            )[1]
            assert days[0].status == "not_ready"

    asyncio.run(check())


def test_seeded_bounded_all_windows():
    import json
    import random

    from app.services.disclosure import area_week_figures, released_totals

    rng = random.Random(311)
    # Expected distance, trips and time come directly from these raw facts.
    raw = [
        [(car, rng.randint(1, 999), rng.randint(1, 99)) for car in range(rng.randint(0, 6))]
        for _ in range(10)
    ]
    trips = []
    analytics = []
    for offset, facts in enumerate(raw):
        for car, distance, seconds in facts:
            ident = uuid4()
            at = datetime(2026, 10, 5 + offset, 12, tzinfo=UTC)
            trips.append(
                NS(
                    id=ident,
                    vehicle_id=car,
                    ended_at=at,
                    status="sealed",
                    sealed_at=at,
                    evidence_adjudication_outcome=None,
                )
            )
            analytics.append(
                NS(
                    trip_session_id=ident,
                    vehicle_id=car,
                    status="computed",
                    computed_at=at,
                    distance_m=Decimal(distance),
                    moving_seconds=seconds,
                )
            )
    cohort = ReportCohort(tuple(trips), tuple(analytics), (), ())
    # Three overlapping target areas. Raw first-week trips touch all three.
    raw_membership = {str(t.id): {"a", "b", "c"} for t in trips}
    estimates = {str(r.trip_session_id): r.distance_m for r in analytics}
    expected_windows = []
    for lo in range(10):
        for hi in range(lo + 1, 11):
            rows = campaign_daily_series(
                cohort,
                start_day=date(2026, 10, 5) + timedelta(days=lo),
                end_day=date(2026, 10, 5) + timedelta(days=hi - 1),
                now=NOW,
            )
            actual = released_totals(rows)
            released = [facts for facts in raw[lo:hi] if len(facts) == 0 or len(facts) >= 3]
            assert actual["distance_m"] == sum(d for facts in released for _, d, _ in facts)
            assert actual["trip_count"] == sum(len(facts) for facts in released)
            assert actual["driving_seconds"] == sum(
                sec for facts in released for _, _, sec in facts
            )
            assert all(
                row.status != "released" or row.vehicle_count == 0 or row.vehicle_count >= 3
                for row in rows
            )
            expected_car_days = sum(len(facts) for facts in released)
            assert actual["average_cars_per_day"] == (
                Decimal(expected_car_days) / len(released) if released else None
            )
            assert actual["driving_days"] == sum(bool(facts) for facts in released)
            expected_views = None if any(released) else Decimal(0)
            assert actual["estimated_views"] == expected_views
            expected_windows.append(
                {
                    "start": lo,
                    "end": hi,
                    "distance_m": sum(d for facts in released for _, d, _ in facts),
                    "trip_count": sum(len(facts) for facts in released),
                    "driving_seconds": sum(sec for facts in released for _, _, sec in facts),
                    "estimated_views": expected_views,
                }
            )
            # The only complete week inside ten days starts at index zero.
            if lo == 0 and hi >= 7:
                selected_days = {
                    date(2026, 10, 5) + timedelta(days=i)
                    for i in range(7)
                    if len(raw[i]) == 0 or len(raw[i]) >= 3
                }
                selected = [t for t in trips if t.ended_at.date() in selected_days]
                cells = {
                    area: [
                        {
                            "trip_session_id": str(t.id),
                            "grid_x": str(t.id),
                            "grid_y": 0,
                            "cell_ping_count": 1,
                            "total_ping_count": 1,
                        }
                        for t in selected
                        if area in raw_membership[str(t.id)]
                    ]
                    for area in ("a", "b", "c")
                }
                figures = area_week_figures(selected, cells, estimates)
                assert figures is not None
                expected_trips = sum(
                    len(facts) for facts in raw[:7] if len(facts) == 0 or len(facts) >= 3
                )
                expected_views = sum(
                    d
                    for facts in raw[:7]
                    if len(facts) == 0 or len(facts) >= 3
                    for _, d, _ in facts
                )
                assert all(
                    v["trip_count"] == expected_trips and v["estimated_views"] == expected_views
                    for v in figures.values()
                )
    print("BOUNDED_RAW_FIXTURES", json.dumps(raw))
    print("BOUNDED_EXPECTED_WINDOWS", json.dumps(expected_windows, default=str))
    print("Bounded raw-fixture check PASS: seed=311, 6 cars, 10 days, 3 areas, 55 windows")


def test_schedule_date_identity_and_cancellation():
    from app.services.disclosure import after_day, midnight
    from app.services.report_scheduling import next_due_window

    start = datetime(2026, 11, 2, 12, tzinfo=UTC)
    end = after_day(datetime(2026, 11, 20, 12, tzinfo=UTC))
    due = midnight(start) + timedelta(days=7)
    assert next_due_window(start, end, NOW, {due + timedelta(hours=4)}) is None
    assert after_day(datetime(2026, 11, 2, 12, tzinfo=UTC)) == datetime(2026, 11, 2, 23, tzinfo=UTC)


def test_fresh_seed_money_and_exports(postgis_db_sessionmaker, settings, monkeypatch):
    import asyncio
    import json
    import os
    from pathlib import Path

    from sqlalchemy import select
    from test_req310_reporting_worker import run_reporting_worker_paths
    from test_seed_demo import seed_demo_graph

    from app.models.campaign_report import CampaignReport
    from app.services.campaign_report_rendering import render_campaign_csv, render_campaign_pdf

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "2")
    seed_demo_graph(postgis_db_sessionmaker, settings)

    from app.models.campaign import Campaign
    from app.services import disclosure as advertiser_cells
    from app.services.campaign_performance import live_campaign_performance
    from app.services.payout_rule_serialization import database_clock

    counts = {"qualifying_weeks": 0, "weeks_with_positive_figures": 0, "by_campaign": []}
    original = advertiser_cells.area_week_figures

    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        if result is not None:
            counts["qualifying_weeks"] += 1
            counts["weeks_with_positive_figures"] += int(
                any(r["trip_count"] for r in result.values())
            )
        return result

    monkeypatch.setattr(advertiser_cells, "area_week_figures", counted)

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            reports = list(
                await session.scalars(
                    select(CampaignReport)
                    .where(CampaignReport.status == "ready")
                    .order_by(CampaignReport.created_at)
                )
            )
            assert reports
            now = await database_clock(session)
            campaigns = list(
                await session.scalars(select(Campaign).where(Campaign.start_at.is_not(None)))
            )
            for campaign in campaigns:
                before_weeks = counts["qualifying_weeks"]
                before_positive = counts["weeks_with_positive_figures"]
                await live_campaign_performance(
                    session, campaign=campaign, settings=settings, now=now
                )
                counts["by_campaign"].append(
                    {
                        "name": campaign.name,
                        "qualifying_weeks": counts["qualifying_weeks"] - before_weeks,
                        "weeks_with_positive_figures": counts["weeks_with_positive_figures"]
                        - before_positive,
                    }
                )
            # Prefer a report with driving, so the exported totals are meaningful.
            return next(
                (
                    report.snapshot
                    for report in reports
                    if any(
                        Decimal(item["measured"]["distance_m"]) > 0
                        for item in report.snapshot["campaigns"]
                    )
                ),
                reports[0].snapshot,
            )

    # Counted after the sweeps: this is the state an advertiser actually sees.
    before, swept, after = asyncio.run(
        run_reporting_worker_paths(postgis_db_sessionmaker, settings, monkeypatch)
    )
    assert before == swept == after
    snapshot = asyncio.run(inspect())
    # The week count covers the live performance reads only, not the export below.
    monkeypatch.setattr(advertiser_cells, "area_week_figures", original)

    async def through_today():
        from app.adapters.storage import build_storage_provider
        from app.services.campaign_report_data import build_report_snapshot

        async with postgis_db_sessionmaker() as session:
            now = await database_clock(session)
            running = await session.scalar(
                select(Campaign).where(Campaign.name == "Marula Kitchens — Wuse Lunch Rush")
            )
            return await build_report_snapshot(
                session,
                campaigns=[running],
                actor_user_id=running.created_by_user_id,
                start=advertiser_cells.midnight(running.start_at),
                end=advertiser_cells.after_day(now),
                settings=settings,
                storage=build_storage_provider(settings),
                now=now,
                budget={"snapshot_bytes": 0, "pixels": 40_000_000},
            )

    # Today is never closed, so a report through today must carry the note.
    current = asyncio.run(through_today())
    assert current["campaigns"][0]["note"] == "Some days hidden."
    assert current["campaigns"][0]["daily"][-1]["status"] == "not_ready"
    root = os.environ.get("REQ311_EVIDENCE")
    if root:
        root = Path(root)
        for name, value in [("money-before.json", before), ("money-after.json", after)]:
            (root / name).write_text(
                json.dumps({k: list(v) for k, v in value.items()}, default=str, indent=2)
            )
        (root / "seed-weeks.json").write_text(json.dumps(counts, indent=2))
        (root / "report.csv").write_bytes(render_campaign_csv(snapshot))
        (root / "report.pdf").write_bytes(render_campaign_pdf(snapshot))
        (root / "report-through-today.csv").write_bytes(render_campaign_csv(current))
        (root / "report-through-today.pdf").write_bytes(render_campaign_pdf(current))
        (root / "seed-snapshot.json").write_text(json.dumps(snapshot, default=str, indent=2))
