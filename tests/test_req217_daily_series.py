"""D118: one end-time WAT calculation, explicit empty days, private small slices."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.report_cohorts import ReportCohort
from app.services.reports import campaign_daily_series


def cohort_for(ended_at, *, cars=3, incomplete=False):
    trips, analytics, estimates = [], [], []
    for _ in range(cars):
        trip_id, car_id = uuid4(), uuid4()
        trips.append(SimpleNamespace(id=trip_id, ended_at=ended_at, vehicle_id=car_id))
        if incomplete:
            continue
        analytics.append(
            SimpleNamespace(
                trip_session_id=trip_id,
                vehicle_id=car_id,
                status="computed",
                distance_m=Decimal("1000"),
                moving_seconds=120,
            )
        )
        estimates.append(
            SimpleNamespace(
                trip_session_id=trip_id,
                status="estimated",
                estimated_impressions=Decimal("25"),
            )
        )
    return ReportCohort(tuple(trips), tuple(analytics), tuple(estimates), (), terminal_period=True)


def test_end_time_is_assigned_to_nigeria_day_and_empty_days_are_zero():
    cohort = cohort_for(datetime(2026, 10, 20, 23, 30, tzinfo=UTC))
    rows = campaign_daily_series(cohort, start_day=date(2026, 10, 15), end_day=date(2026, 10, 21))
    assert len(rows) == 7
    assert [row.date for row in rows] == [date(2026, 10, day) for day in range(15, 22)]
    assert rows[-1].vehicle_count == 3
    assert rows[-1].trip_count == 3
    assert rows[-1].distance_m == Decimal("3000")
    assert rows[-1].driving_seconds == 360
    assert rows[-1].estimated_impressions == Decimal("75")
    assert not rows[-1].suppressed
    for row in rows[:-1]:
        assert row.distance_m == row.vehicle_count == row.trip_count == row.driving_seconds == 0
        assert row.estimated_impressions == 0
        assert not row.suppressed


def test_two_car_day_is_withheld_and_cannot_be_unlocked_by_another_day():
    small = cohort_for(datetime(2026, 10, 20, 8, tzinfo=UTC), cars=2)
    large = cohort_for(datetime(2026, 10, 21, 8, tzinfo=UTC), cars=3)
    combined = ReportCohort(
        small.trips + large.trips,
        small.analytics + large.analytics,
        small.impressions + large.impressions,
        (),
        terminal_period=True,
    )
    rows = campaign_daily_series(combined, start_day=date(2026, 10, 20), end_day=date(2026, 10, 21))
    assert rows[0].suppressed
    assert rows[0].vehicle_count is rows[0].trip_count is rows[0].distance_m is None
    assert rows[0].driving_seconds is rows[0].estimated_impressions is None
    assert rows[1].distance_m == 3000


def test_unprocessed_trip_day_is_unknown_instead_of_a_false_zero():
    rows = campaign_daily_series(
        cohort_for(datetime(2026, 10, 20, 8, tzinfo=UTC), incomplete=True),
        start_day=date(2026, 10, 20),
        end_day=date(2026, 10, 20),
    )
    assert rows[0].suppressed
    assert rows[0].distance_m is rows[0].vehicle_count is rows[0].estimated_impressions is None
