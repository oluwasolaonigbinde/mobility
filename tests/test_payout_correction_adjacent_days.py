"""C1: adjacent-day correction orders serialize shared cross-midnight trips."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from conftest import create_test_user, fetch_earnings_ledger_entries
from sqlalchemy import update
from test_payout_corrections import (
    RELEASE_AT,
    approve,
    correction_entries,
    raise_rule_rate,
    service,
    submit,
)
from test_payouts_v2 import (
    BASE_LAT,
    BASE_LON,
    build_v2_graph,
    create_signed_v2_test_trip_session,
    pipeline_to_v2,
    resign_signed_v2_manifest_receipt,
)
from test_trip_processing import add_pings, run_pipeline

from app.core.errors import AppError
from app.models.trip import TripSession
from app.services.payout_corrections import (
    create_correction_order,
    execute_correction_order,
    project_campaign_day,
)


def test_adjacent_day_orders_share_one_half_cent_effect_without_deadlock(
    postgis_db_sessionmaker,
    settings,
) -> None:
    # Eighteen seconds straddle Lagos midnight: at NGN 1/h the authoritative
    # HALF_UP total is 0.01 (exactly 0.005 before quantization); at NGN 3/h it
    # becomes 0.02. Both selected days therefore project the same +0.01 trip
    # effect before either order executes.
    started_at = datetime(2026, 7, 20, 22, 59, 51, tzinfo=UTC)
    ended_at = started_at + timedelta(seconds=18)
    graph = build_v2_graph(
        postgis_db_sessionmaker,
        "adjacent-day-race",
        started_at=started_at,
        ended_at=ended_at,
        hourly_rate="1.00",
    )
    pipeline_to_v2(
        postgis_db_sessionmaker,
        settings,
        graph,
        points=[
            (started_at, BASE_LAT, BASE_LON, 10.0),
            (started_at + timedelta(seconds=9), BASE_LAT + 0.00081, BASE_LON, 10.0),
            (ended_at, BASE_LAT + 0.00162, BASE_LON, 10.0),
        ],
        idempotency_key="adjacent-day-race",
    )
    initial_entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert [entry.amount for entry in initial_entries] == [Decimal("0.01")]

    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "3.00")
    approver = create_test_user(
        postgis_db_sessionmaker,
        email="approver-adjacent-day-race@example.com",
    )

    def create_for_day(lagos_day: date):
        return service(
            postgis_db_sessionmaker,
            lambda session: create_correction_order(
                session,
                campaign_id=graph.campaign.id,
                lagos_day=lagos_day,
                reason=f"adjacent-day {lagos_day.isoformat()}",
                created_by_user_id=graph.admin.id,
                settings=settings,
            ),
        )

    first = create_for_day(date(2026, 7, 20))
    second = create_for_day(date(2026, 7, 21))
    for order in (first, second):
        assert order.projected_delta["day_totals"]["delta_amount"] == "0.01"
        submit(postgis_db_sessionmaker, order.id, graph.admin.id)
        approve(postgis_db_sessionmaker, settings, order.id, approver.id)

    async def attempt(order_id):
        async with postgis_db_sessionmaker() as session:
            try:
                _, executed_now = await execute_correction_order(
                    session,
                    order_id=order_id,
                    actor_user_id=approver.id,
                    release_at=RELEASE_AT,
                    request_metadata={"source": "adjacent-day-race"},
                    settings=settings,
                )
                await session.commit()
                return order_id, "executed", executed_now
            except AppError as exc:
                return order_id, exc.code, False

    async def race():
        return await asyncio.wait_for(
            asyncio.gather(attempt(first.id), attempt(second.id)),
            timeout=10,
        )

    outcomes = asyncio.run(race())
    assert sorted((state, changed) for _, state, changed in outcomes) == [
        ("CORRECTION_ORDER_STALE", False),
        ("executed", True),
    ]
    assert [entry.amount for entry in correction_entries(postgis_db_sessionmaker)] == [
        Decimal("0.01")
    ]
    assert sum(
        entry.amount
        for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
        if entry.trip_session_id == graph.trip.id
    ) == Decimal("0.02")

    winner_id = next(order_id for order_id, state, _ in outcomes if state == "executed")
    loser_id = next(order_id for order_id, state, _ in outcomes if state != "executed")
    retry = asyncio.run(attempt(winner_id))
    assert retry == (winner_id, "executed", False)
    stale_retry = asyncio.run(attempt(loser_id))
    assert stale_retry == (loser_id, "CORRECTION_ORDER_INVALID_STATE", False)
    assert len(correction_entries(postgis_db_sessionmaker)) == 1


def test_uuid_lock_order_preserves_chronological_cap_order_across_adjacent_days(
    postgis_db_sessionmaker,
    settings,
) -> None:
    first_start = datetime(2026, 7, 20, 22, 59, 40, tzinfo=UTC)
    second_start = first_start + timedelta(seconds=10)
    end_at = first_start + timedelta(seconds=40)
    graph = build_v2_graph(
        postgis_db_sessionmaker,
        "adjacent-day-ordering",
        started_at=first_start,
        ended_at=end_at,
        daily_cap_hours="0.01",  # 36 seconds per Lagos day
    )
    second_trip = create_signed_v2_test_trip_session(
        postgis_db_sessionmaker,
        settings,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        started_at=second_start,
        ended_at=end_at,
    )

    # Force lock order to oppose cap order: the later trip's lower UUID locks
    # first, while the earlier trip must still consume the day cap first.
    earlier_high_id = UUID("f0000000-0000-0000-0000-000000000001")
    later_low_id = UUID("00000000-0000-0000-0000-000000000001")

    async def rekey_trips() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(TripSession)
                .where(TripSession.id == graph.trip.id)
                .values(id=earlier_high_id)
            )
            await session.execute(
                update(TripSession)
                .where(TripSession.id == second_trip.id)
                .values(id=later_low_id)
            )
            await session.commit()

    asyncio.run(rekey_trips())
    graph.trip.id = earlier_high_id
    second_trip.id = later_low_id
    resign_signed_v2_manifest_receipt(postgis_db_sessionmaker, settings, earlier_high_id)
    resign_signed_v2_manifest_receipt(postgis_db_sessionmaker, settings, later_low_id)

    def points(start_at: datetime, duration: int):
        return [
            (start_at + timedelta(seconds=offset), BASE_LAT + offset * 0.00008, BASE_LON, 10.0)
            for offset in range(0, duration + 1, 10)
        ]

    pipeline_to_v2(
        postgis_db_sessionmaker,
        settings,
        graph,
        points=points(first_start, 40),
        idempotency_key="adjacent-order-first",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=second_trip.id,
        points=points(second_start, 30),
        idempotency_key="adjacent-order-second",
    )
    run_pipeline(postgis_db_sessionmaker, second_trip.id, settings)

    next_day = date(2026, 7, 21)
    projection = service(
        postgis_db_sessionmaker,
        lambda session: project_campaign_day(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=next_day,
            settings=settings,
        ),
    )
    targets = {target.trip_session_id: target for target in projection.computations[0].trips}
    assert targets[earlier_high_id].payable_by_day[next_day.isoformat()] == 20
    assert targets[later_low_id].payable_by_day[next_day.isoformat()] == 16

    approver = create_test_user(
        postgis_db_sessionmaker,
        email="approver-adjacent-ordering@example.com",
    )

    def create_for_day(lagos_day: date):
        return service(
            postgis_db_sessionmaker,
            lambda session: create_correction_order(
                session,
                campaign_id=graph.campaign.id,
                lagos_day=lagos_day,
                reason=f"ordering {lagos_day.isoformat()}",
                created_by_user_id=graph.admin.id,
                settings=settings,
            ),
        )

    orders = (create_for_day(date(2026, 7, 20)), create_for_day(next_day))
    for order in orders:
        submit(postgis_db_sessionmaker, order.id, graph.admin.id)
        approve(postgis_db_sessionmaker, settings, order.id, approver.id)

    async def execute(order_id):
        async with postgis_db_sessionmaker() as session:
            _, executed_now = await execute_correction_order(
                session,
                order_id=order_id,
                actor_user_id=approver.id,
                release_at=None,
                request_metadata={"source": "ordering"},
                settings=settings,
            )
            await session.commit()
            return executed_now

    async def race():
        return await asyncio.wait_for(
            asyncio.gather(*(execute(order.id) for order in orders)),
            timeout=10,
        )

    assert asyncio.run(race()) == [True, True]
