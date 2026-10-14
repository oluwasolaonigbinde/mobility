"""Chronological daily cap authority and retryable predecessor blocking."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import fetch_payout_calculations
from payout_fixtures import (
    TRIP_START,
    add_trip,
    build_v4_graph,
    create_signed_v2_test_trip_session,
    moving_points,
)
from sqlalchemy import update
from test_trip_processing import add_pings, run_pipeline

from app.core.errors import AppError
from app.models.trip import TripSession
from app.services import payouts


def build_daily_pair(db, settings, tag, *, trip2_started_at=None):
    graph = build_v4_graph(db, settings, tag, daily_rate_naira="600", daily_target_miles="1")
    graph.trip2 = add_trip(
        db, settings, graph, started_at=trip2_started_at or TRIP_START + timedelta(hours=1)
    )
    for trip in (graph.trip, graph.trip2):
        add_pings(
            db, trip_id=trip.id, points=moving_points(trip.started_at), idempotency_key=str(trip.id)
        )
    return graph


def test_direct_calculation_refuses_equal_start_higher_id_before_lower_id(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_daily_pair(
        postgis_db_sessionmaker,
        settings,
        "v3-order-id",
        trip2_started_at=TRIP_START,
    )
    predecessor_id, current_id = sorted((graph.trip.id, graph.trip2.id))

    from app.services.impressions import estimate_trip_impressions
    from app.services.trip_analytics import recompute_trip_analytics

    async def calculate_current_first() -> None:
        async with postgis_db_sessionmaker() as session:
            await recompute_trip_analytics(
                session,
                trip_id=current_id,
                metadata={"source": "test"},
                settings=settings,
            )
            await estimate_trip_impressions(
                session,
                trip_id=current_id,
                traffic_density_profile_id=None,
                metadata={"source": "test"},
                settings=settings,
            )
            with pytest.raises(AppError) as error:
                await payouts.calculate_trip_payout(
                    session,
                    trip_id=current_id,
                    payout_rule_id=None,
                    metadata={"source": "test"},
                    settings=settings,
                )
            assert error.value.code == "PAYOUT_DAY_PREDECESSOR_UNPROCESSED"
            assert error.value.status_code == 409
            assert error.value.details == {"predecessor_trip_id": str(predecessor_id)}

    asyncio.run(calculate_current_first())


def test_ended_unsealed_predecessor_retains_chronological_cap_authority(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_daily_pair(
        postgis_db_sessionmaker,
        settings,
        "unsealed-cap",
    )

    async def set_predecessor_seal(sealed):
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(TripSession)
                .where(TripSession.id == graph.trip.id)
                .values(
                    status="sealed" if sealed else "ended",
                    sealed_at=graph.trip.sealed_at if sealed else None,
                    seal_reason=graph.trip.seal_reason if sealed else None,
                )
            )
            await session.commit()

    asyncio.run(set_predecessor_seal(False))
    blocked = run_pipeline(postgis_db_sessionmaker, graph.trip2.id, settings)
    assert blocked.overall == "partial"
    assert blocked.stages[-1].reason == "payout_day_predecessor_unprocessed"
    assert blocked.stages[-1].row_ids == {"predecessor_trip_id": str(graph.trip.id)}
    assert fetch_payout_calculations(postgis_db_sessionmaker) == []
    asyncio.run(set_predecessor_seal(True))
    assert run_pipeline(postgis_db_sessionmaker, graph.trip2.id, settings).overall == "completed"
    calculations = {
        c.trip_session_id: c for c in fetch_payout_calculations(postgis_db_sessionmaker)
    }
    assert set(calculations) == {graph.trip.id, graph.trip2.id}
    assert calculations[graph.trip.id].final_payout == Decimal("600.00")
    assert calculations[graph.trip2.id].final_payout == Decimal("0.00")


@pytest.mark.parametrize("predecessor_status", ["ended", "sealed"])
def test_predecessor_ending_at_lagos_midnight_does_not_occupy_next_day(
    postgis_db_sessionmaker, settings, predecessor_status
) -> None:
    midnight = datetime(2026, 7, 20, 23, tzinfo=UTC)
    graph = build_v4_graph(
        postgis_db_sessionmaker,
        settings,
        "midnight-predecessor",
        started_at=midnight - timedelta(minutes=30),
        ended_at=midnight,
    )
    current = create_signed_v2_test_trip_session(
        postgis_db_sessionmaker,
        settings,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        started_at=midnight + timedelta(minutes=30),
        ended_at=midnight + timedelta(hours=1),
    )

    async def check():
        async with postgis_db_sessionmaker() as session:
            if predecessor_status == "ended":
                await session.execute(
                    update(TripSession)
                    .where(TripSession.id == graph.trip.id)
                    .values(
                        status="ended",
                        sealed_at=None,
                        seal_reason=None,
                    )
                )
            day = (midnight + timedelta(hours=1)).date()
            await payouts.acquire_paycap_lock(
                session, payouts.paycap_lock_key(graph.profile.id, graph.campaign.id, day)
            )
            await payouts.require_paycap_predecessors_processed(
                session,
                trip=current,
                lagos_days=[day],
            )

    asyncio.run(check())


def test_worker_leaves_later_payout_retryable_when_predecessor_cannot_progress(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    graph = build_daily_pair(
        postgis_db_sessionmaker,
        settings,
        "v3-order-blocked",
    )

    from app.services import trip_processing

    verify_manifest_receipt = trip_processing.verify_manifest_receipt
    monkeypatch.setattr(
        trip_processing,
        "verify_manifest_receipt",
        lambda trip, active_settings: (
            trip.id != graph.trip.id and verify_manifest_receipt(trip, active_settings)
        ),
    )
    result = run_pipeline(postgis_db_sessionmaker, graph.trip2.id, settings)

    assert result.overall == "partial"
    assert result.stages[-1].stage == "payout"
    assert result.stages[-1].outcome == "blocked"
    assert result.stages[-1].reason == "payout_day_predecessor_unprocessed"
    assert result.stages[-1].row_ids == {"predecessor_trip_id": str(graph.trip.id)}
    assert fetch_payout_calculations(postgis_db_sessionmaker) == []
