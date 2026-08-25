import asyncio
from datetime import UTC, datetime, timedelta

from conftest import (
    auth_headers,
    create_test_trip_analytics,
    create_test_trip_session,
)
from sqlalchemy import func, select, update
from test_trip_processing import build_graph

from app.models.assignment_activity import (
    AssignmentActivityFlag,
    AssignmentActivityFlagEvent,
    AssignmentActivityFlagType,
)
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.notification import Notification
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, TripAnalyticsStatus
from app.services.assignment_activity import (
    evaluate_assignment_activity,
    parse_verified_hours_floor,
    sweep_activity_flags,
    utc_completed_week_window,
)

PASSWORD = "long-secure-password"


def _settings(settings, value=None):
    settings.verified_hours_floor_per_week = value
    return settings


def _evaluate(db_sessionmaker, assignment_id, settings, now):
    async def run():
        async with db_sessionmaker() as session:
            result = await evaluate_assignment_activity(
                session,
                assignment_id=assignment_id,
                settings=settings,
                now=now,
            )
            await session.commit()
            return result

    return asyncio.run(run())


def _flags(db_sessionmaker):
    async def run():
        async with db_sessionmaker() as session:
            return list((await session.scalars(select(AssignmentActivityFlag))).all())

    return asyncio.run(run())


def test_missing_or_invalid_floor_config_fails_closed_but_inactivity_still_runs(
    db_sessionmaker, settings
):
    graph = build_graph(
        db_sessionmaker,
        "activity-config",
        started_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
    )
    result = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        _settings(settings, "not-a-number"),
        datetime(2026, 1, 8, 12, tzinfo=UTC),
    )
    assert result["weekly_floor"] == "skipped_configuration"
    assert result["inactivity"] == "opened"
    assert result["flags_opened"] == 1
    assert [flag.flag_type for flag in _flags(db_sessionmaker)] == [
        AssignmentActivityFlagType.INACTIVITY.value
    ]
    assert parse_verified_hours_floor(_settings(settings, None))[1] == "missing_configuration"
    assert parse_verified_hours_floor(_settings(settings, 0))[1] == "invalid_configuration"


def test_inactivity_is_exact_at_seven_days_and_recovery_is_idempotent(db_sessionmaker, settings):
    baseline = datetime(2026, 1, 1, 12, tzinfo=UTC)
    graph = build_graph(db_sessionmaker, "activity-inactive", started_at=baseline)
    configured = _settings(settings, 1)

    before = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7) - timedelta(microseconds=1),
    )
    assert before["inactivity"] == "waiting"
    assert _flags(db_sessionmaker) == []

    opened = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7),
    )
    assert opened["inactivity"] == "opened"
    flags = _flags(db_sessionmaker)
    assert len(flags) == 1
    assert flags[0].flag_type == AssignmentActivityFlagType.INACTIVITY.value

    retry = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7, minutes=5),
    )
    assert retry["flags_opened"] == 0
    assert len(_flags(db_sessionmaker)) == 1

    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=baseline + timedelta(days=7, minutes=10),
        ended_at=baseline + timedelta(days=7, minutes=20),
    )
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        active_tracking_seconds=60,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        last_ping_at=trip.ended_at,
        computed_at=trip.sealed_at + timedelta(seconds=1),
    )
    recovered = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7, minutes=30),
    )
    assert recovered["inactivity"] == "recovered"
    assert recovered["flags_recovered"] == 1
    again = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7, minutes=31),
    )
    assert again["flags_recovered"] == 0

    async def counts():
        async with db_sessionmaker() as session:
            return (
                await session.scalar(select(func.count()).select_from(AssignmentActivityFlag)),
                await session.scalar(select(func.count()).select_from(AssignmentActivityFlagEvent)),
                await session.scalar(select(func.count()).select_from(Notification)),
            )

    flag_count, event_count, notice_count = asyncio.run(counts())
    assert flag_count == 1
    assert event_count == 2
    assert notice_count == 2


def test_weekly_floor_before_equality_and_after_use_only_computed_authoritative_rows(
    db_sessionmaker, settings
):
    started = datetime(2025, 12, 28, 12, tzinfo=UTC)
    graph = build_graph(db_sessionmaker, "activity-weekly", started_at=started)
    trip = graph.trip
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        active_tracking_seconds=3599,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        last_ping_at=datetime(2025, 12, 29, 12, tzinfo=UTC),
        computed_at=trip.sealed_at + timedelta(seconds=1),
    )
    configured = _settings(settings, 1)
    now = datetime(2026, 1, 8, 12, tzinfo=UTC)
    opened = _evaluate(db_sessionmaker, graph.assignment.id, configured, now)
    assert opened["weekly_floor"] == "opened"
    assert (
        sum(
            flag.flag_type == AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR.value
            for flag in _flags(db_sessionmaker)
        )
        == 1
    )

    async def update_seconds(seconds: int):
        async with db_sessionmaker() as session:
            row = await session.get(type(analytics), analytics.id)
            row.active_tracking_seconds = seconds
            await session.commit()

    asyncio.run(update_seconds(3600))
    recovered = _evaluate(db_sessionmaker, graph.assignment.id, configured, now)
    assert recovered["weekly_floor"] == "recovered"

    # A retry above equality remains one auditable floor occurrence.
    asyncio.run(update_seconds(3601))
    after = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        configured,
        now + timedelta(minutes=1),
    )
    assert after["weekly_floor"] == "recovered"
    assert (
        sum(
            flag.flag_type == AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR.value
            for flag in _flags(db_sessionmaker)
        )
        == 1
    )


def test_utc_completed_week_window_has_explicit_monday_edges() -> None:
    monday = datetime(2026, 1, 5, 0, tzinfo=UTC)
    assert utc_completed_week_window(monday) == (
        datetime(2025, 12, 29, 0, tzinfo=UTC),
        monday,
    )
    assert utc_completed_week_window(datetime(2026, 1, 11, 23, 59, 59, 999999, tzinfo=UTC)) == (
        datetime(2025, 12, 29, 0, tzinfo=UTC),
        monday,
    )
    assert utc_completed_week_window(datetime(2026, 1, 12, 0, tzinfo=UTC)) == (
        monday,
        datetime(2026, 1, 12, 0, tzinfo=UTC),
    )


def test_missing_insufficient_blocked_future_stale_and_wrong_linkage_never_count(
    db_sessionmaker, settings
):
    baseline = datetime(2026, 1, 1, 12, tzinfo=UTC)
    graph = build_graph(db_sessionmaker, "activity-authority", started_at=baseline)

    def add_trip(tag: str, started_at: datetime, *, status: str = "computed"):
        trip = create_test_trip_session(
            db_sessionmaker,
            assignment_id=graph.assignment.id,
            campaign_id=graph.campaign.id,
            driver_profile_id=graph.profile.id,
            vehicle_id=graph.vehicle.id,
            started_by_user_id=graph.driver.id,
            trip_status=TripSessionStatus.SEALED,
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=10),
        )
        analytics = create_test_trip_analytics(
            db_sessionmaker,
            trip_session_id=trip.id,
            assignment_id=graph.assignment.id,
            campaign_id=graph.campaign.id,
            driver_profile_id=graph.profile.id,
            vehicle_id=graph.vehicle.id,
            status=status,
            active_tracking_seconds=3600,
            started_at=trip.started_at,
            ended_at=trip.ended_at,
            last_ping_at=trip.ended_at,
            computed_at=trip.sealed_at + timedelta(seconds=1),
        )
        return trip, analytics

    _, insufficient = add_trip(
        "insufficient",
        datetime(2026, 1, 6, 12, tzinfo=UTC),
        status=TripAnalyticsStatus.INSUFFICIENT_DATA.value,
    )
    _, blocked = add_trip(
        "blocked",
        datetime(2026, 1, 7, 12, tzinfo=UTC),
        status=TripAnalyticsStatus.BLOCKED.value,
    )
    stale_trip, stale = add_trip("stale", datetime(2026, 1, 8, 12, tzinfo=UTC))
    future_trip, future = add_trip("future", datetime(2026, 1, 16, 12, tzinfo=UTC))

    async def make_stale_and_future() -> None:
        async with db_sessionmaker() as session:
            stale_row = await session.get(type(stale), stale.id)
            stale_row.computed_at = stale_trip.sealed_at - timedelta(seconds=1)
            future_row = await session.get(type(future), future.id)
            future_row.last_ping_at = future_trip.ended_at + timedelta(minutes=1)
            await session.commit()

    asyncio.run(make_stale_and_future())

    other = build_graph(db_sessionmaker, "activity-wrong-link", started_at=baseline)
    wrong_trip = graph.trip
    wrong = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=wrong_trip.id,
        assignment_id=other.assignment.id,
        campaign_id=other.campaign.id,
        driver_profile_id=other.profile.id,
        vehicle_id=other.vehicle.id,
        active_tracking_seconds=3600,
        started_at=wrong_trip.started_at,
        ended_at=wrong_trip.ended_at,
        last_ping_at=datetime(2026, 1, 9, 12, tzinfo=UTC),
        computed_at=wrong_trip.sealed_at + timedelta(seconds=1),
    )

    result = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        _settings(settings, 1),
        datetime(2026, 1, 15, 12, tzinfo=UTC),
    )
    assert result["weekly_floor"] == "opened"
    assert result["inactivity"] == "opened"
    flags = _flags(db_sessionmaker)
    assert all(flag.observed_seconds == 0 for flag in flags)
    assert all(flag.current_evidence["eligible_trip_count"] == 0 for flag in flags)
    assert insufficient.status == TripAnalyticsStatus.INSUFFICIENT_DATA.value
    assert blocked.status == TripAnalyticsStatus.BLOCKED.value
    assert wrong.assignment_id == other.assignment.id


def test_activity_evaluation_does_not_mutate_lifecycle_earnings_or_fraud_rows(
    db_sessionmaker, settings
):
    graph = build_graph(
        db_sessionmaker,
        "activity-no-mutation",
        started_at=datetime(2025, 12, 28, 12, tzinfo=UTC),
    )

    async def snapshot():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            return (
                assignment.status,
                assignment.updated_at,
                await session.scalar(select(func.count()).select_from(EarningsLedgerEntry)),
                await session.scalar(select(func.count()).select_from(PayoutCalculation)),
                await session.scalar(select(func.count()).select_from(FraudFlag)),
            )

    before = asyncio.run(snapshot())
    result = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        _settings(settings, 1),
        datetime(2026, 1, 8, 12, tzinfo=UTC),
    )
    after = asyncio.run(snapshot())
    assert result["flags_opened"] == 2
    assert after == before


def test_non_active_assignment_is_skipped_without_mutating_assignment(db_sessionmaker, settings):
    graph = build_graph(db_sessionmaker, "activity-state")

    async def deactivate():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            assignment.status = CampaignAssignmentStatus.DEACTIVATED.value
            await session.commit()
            await session.refresh(assignment)
            return assignment.updated_at

    updated_at = asyncio.run(deactivate())
    result = _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        _settings(settings, 1),
        datetime(2026, 1, 8, 12, tzinfo=UTC),
    )
    assert result["skip_reason"] == "assignment_not_active"

    async def read():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            return assignment.status, assignment.updated_at

    status, after = asyncio.run(read())
    assert status == CampaignAssignmentStatus.DEACTIVATED.value
    assert after == updated_at


def test_worker_returns_truthful_config_skip_and_processes_inactivity(db_sessionmaker, settings):
    graph = build_graph(
        db_sessionmaker,
        "activity-worker",
        started_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
    )

    async def run():
        return await sweep_activity_flags(
            db_sessionmaker,
            assignment_ids=[graph.assignment.id],
            settings=_settings(settings, None),
            now=datetime(2026, 1, 8, 12, tzinfo=UTC),
        )

    result = asyncio.run(run())
    assert result["selected"] == 1
    assert result["evaluated"] == 1
    assert result["config"] == "skipped_weekly"
    assert result["config_reason"] == "missing_configuration"
    assert result["flags_opened"] == 1


def test_bounded_batch_rolls_back_one_failure_without_losing_later_work(
    db_sessionmaker, settings, monkeypatch
) -> None:
    failed = build_graph(db_sessionmaker, "isol-fail")
    succeeded = build_graph(db_sessionmaker, "isol-pass")

    async def fake_evaluate(session, *, assignment_id, settings, now):
        await session.execute(
            update(CampaignAssignment)
            .where(CampaignAssignment.id == assignment_id)
            .values(notes=f"evaluated:{assignment_id}")
        )
        if assignment_id == failed.assignment.id:
            raise RuntimeError("isolated failure")
        return {
            "skip_reason": None,
            "flags_opened": 0,
            "flags_recovered": 0,
            "notices_created": 0,
            "skipped": 0,
        }

    monkeypatch.setattr(
        "app.services.assignment_activity.evaluate_assignment_activity",
        fake_evaluate,
    )

    result = asyncio.run(
        sweep_activity_flags(
            db_sessionmaker,
            assignment_ids=[failed.assignment.id, succeeded.assignment.id],
            settings=_settings(settings, None),
            now=datetime(2026, 1, 8, 12, tzinfo=UTC),
        )
    )

    async def notes() -> tuple[str | None, str | None]:
        async with db_sessionmaker() as session:
            failed_row = await session.get(CampaignAssignment, failed.assignment.id)
            succeeded_row = await session.get(CampaignAssignment, succeeded.assignment.id)
            return failed_row.notes, succeeded_row.notes

    failed_note, succeeded_note = asyncio.run(notes())
    assert result["errors"] == 1
    assert result["evaluated"] == 1
    assert failed_note is None
    assert succeeded_note == f"evaluated:{succeeded.assignment.id}"


def test_activity_evidence_is_admin_only_and_sanitized(
    db_client, db_sessionmaker, settings
) -> None:
    tag = "activity-api-visibility"
    graph = build_graph(
        db_sessionmaker,
        tag,
        started_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
    )
    _evaluate(
        db_sessionmaker,
        graph.assignment.id,
        _settings(settings, None),
        datetime(2026, 1, 8, 12, tzinfo=UTC),
    )

    admin_response = db_client.get(
        "/api/v1/admin/campaign-assignments",
        headers=auth_headers(db_client, f"admin-{tag}@example.com", PASSWORD),
    )
    driver_response = db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=auth_headers(db_client, f"driver-{tag}@example.com", PASSWORD),
    )

    assert admin_response.status_code == 200
    admin_flag = admin_response.json()["items"][0]["activity_flags"][0]
    assert admin_flag["flag_type"] == AssignmentActivityFlagType.INACTIVITY.value
    assert admin_flag["eligible_trip_count"] == 0
    assert "evidence" not in admin_flag
    assert "analytics_source" not in admin_response.text
    assert driver_response.status_code == 200
    assert driver_response.json()["items"][0]["activity_flags"] is None
    assert "eligible_trip_count" not in driver_response.text


def test_postgres_concurrent_sweeps_converge_to_one_flag_per_condition(
    postgis_db_sessionmaker, settings
):
    graph = build_graph(
        postgis_db_sessionmaker,
        "activity-open-race",
        started_at=datetime(2025, 12, 28, 12, tzinfo=UTC),
    )
    configured = _settings(settings, 1)
    barrier = asyncio.Barrier(2)
    now = datetime(2026, 1, 8, 12, tzinfo=UTC)

    async def run_one():
        async with postgis_db_sessionmaker() as session:
            await barrier.wait()
            result = await evaluate_assignment_activity(
                session,
                assignment_id=graph.assignment.id,
                settings=configured,
                now=now,
            )
            await session.commit()
            return result

    async def run_both():
        return await asyncio.gather(run_one(), run_one())

    results = asyncio.run(run_both())

    async def counts():
        async with postgis_db_sessionmaker() as session:
            flags = list((await session.scalars(select(AssignmentActivityFlag))).all())
            events = await session.scalar(
                select(func.count()).select_from(AssignmentActivityFlagEvent)
            )
            notices = await session.scalar(select(func.count()).select_from(Notification))
            return flags, events, notices

    flags, event_count, notice_count = asyncio.run(counts())
    assert sum(result["flags_opened"] for result in results) == 2
    assert len(flags) == 2
    assert {flag.flag_type for flag in flags} == {
        AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR.value,
        AssignmentActivityFlagType.INACTIVITY.value,
    }
    assert event_count == 2
    assert notice_count == 2


def test_postgres_concurrent_recovery_is_one_event_and_notice(postgis_db_sessionmaker, settings):
    baseline = datetime(2026, 1, 1, 12, tzinfo=UTC)
    graph = build_graph(postgis_db_sessionmaker, "activity-recovery-race", started_at=baseline)
    configured = _settings(settings, None)
    _evaluate(
        postgis_db_sessionmaker,
        graph.assignment.id,
        configured,
        baseline + timedelta(days=7),
    )
    trip = create_test_trip_session(
        postgis_db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=baseline + timedelta(days=7, minutes=10),
        ended_at=baseline + timedelta(days=7, minutes=20),
    )
    create_test_trip_analytics(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        active_tracking_seconds=60,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        last_ping_at=trip.ended_at,
        computed_at=trip.sealed_at + timedelta(seconds=1),
    )
    barrier = asyncio.Barrier(2)
    now = baseline + timedelta(days=7, minutes=30)

    async def run_one():
        async with postgis_db_sessionmaker() as session:
            await barrier.wait()
            result = await evaluate_assignment_activity(
                session,
                assignment_id=graph.assignment.id,
                settings=configured,
                now=now,
            )
            await session.commit()
            return result

    async def run_both():
        return await asyncio.gather(run_one(), run_one())

    results = asyncio.run(run_both())

    async def state():
        async with postgis_db_sessionmaker() as session:
            flag = await session.scalar(select(AssignmentActivityFlag))
            events = await session.scalar(
                select(func.count()).select_from(AssignmentActivityFlagEvent)
            )
            notices = await session.scalar(select(func.count()).select_from(Notification))
            return flag, events, notices

    flag, event_count, notice_count = asyncio.run(state())
    assert sum(result["flags_recovered"] for result in results) == 1
    assert flag.status == "recovered"
    assert event_count == 2
    assert notice_count == 2
