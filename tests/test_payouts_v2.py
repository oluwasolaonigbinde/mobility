import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from conftest import (
    auth_headers,
    create_test_payout_rule,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from sqlalchemy import select
from starlette import status as http_status
from test_trip_processing import PASSWORD, add_pings, build_graph, run_pipeline

from app.models.campaign_zone import CampaignZone
from app.models.payout import (
    CampaignPayoutRule,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.services.campaign_zones import geometry_expression
from app.services.payouts import (
    PAYOUT_V2,
    calculate_trip_payout,
    daily_cap_seconds,
    driver_earnings_summary,
    driver_trip_earnings_breakdown,
    lagos_day_for,
    lagos_day_utc_range,
    paycap_lock_key,
    price_payable_seconds,
    quantize_2,
    quantize_ngn_half_up,
    recompute_payout_day,
    v2_calculation_is_stale,
)
from app.services.trip_processing import find_unprocessed_trips

# Trips start at 09:00 Lagos (08:00 UTC) so the whole session sits inside one
# Africa/Lagos day.
TRIP_START = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
TRIP_END = TRIP_START + timedelta(minutes=30)
BASE_LAT = 6.45
BASE_LON = 3.40


def moving_points(
    start: datetime,
    *,
    minutes: int = 30,
    step_seconds: int = 30,
    accuracy: float = 10.0,
    lon: float = BASE_LON,
) -> list[tuple[datetime, float, float, float]]:
    # ~90 m per 30 s (~11 km/h): moving under the stay-point rule.
    return [
        (
            start + timedelta(seconds=second),
            BASE_LAT + (second // step_seconds) * 0.00081,
            lon,
            accuracy,
        )
        for second in range(0, minutes * 60 + 1, step_seconds)
    ]


def create_v2_rule(
    db_sessionmaker,
    *,
    campaign_id,
    created_by_user_id,
    hourly_rate: str = "1200.00",
    daily_cap_hours: str = "8.00",
    rule_status: str = "active",
    eligibility_params: dict | None = None,
) -> CampaignPayoutRule:
    async def create() -> CampaignPayoutRule:
        async with db_sessionmaker() as session:
            rule = CampaignPayoutRule(
                campaign_id=campaign_id,
                created_by_user_id=created_by_user_id,
                formula_version=PAYOUT_V2,
                status=rule_status,
                currency="NGN",
                hourly_rate_naira=Decimal(hourly_rate),
                daily_payable_hours_cap=Decimal(daily_cap_hours),
                eligibility_params=eligibility_params,
                rule_metadata={},
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    return asyncio.run(create())


def deactivate_rules(db_sessionmaker, campaign_id) -> None:
    async def deactivate() -> None:
        async with db_sessionmaker() as session:
            rules = (
                await session.execute(
                    select(CampaignPayoutRule).where(
                        CampaignPayoutRule.campaign_id == campaign_id
                    )
                )
            ).scalars()
            for rule in rules:
                rule.status = "inactive"
            await session.commit()

    asyncio.run(deactivate())


def calculate(db_sessionmaker, trip_id, settings, **kwargs):
    async def run():
        async with db_sessionmaker() as session:
            result = await calculate_trip_payout(
                session,
                trip_id=trip_id,
                payout_rule_id=kwargs.get("payout_rule_id"),
                metadata={"source": "test"},
                settings=settings,
                now=kwargs.get("now"),
                strict_staleness=kwargs.get("strict_staleness", True),
            )
            await session.commit()
            return result

    return asyncio.run(run())


def build_v2_graph(
    db_sessionmaker,
    tag: str,
    *,
    started_at: datetime = TRIP_START,
    ended_at: datetime = TRIP_END,
    hourly_rate: str = "1200.00",
    daily_cap_hours: str = "8.00",
) -> SimpleNamespace:
    graph = build_graph(
        db_sessionmaker, tag, started_at=started_at, ended_at=ended_at
    )
    graph.rule = create_v2_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        hourly_rate=hourly_rate,
        daily_cap_hours=daily_cap_hours,
    )
    return graph


def pipeline_to_v2(
    db_sessionmaker,
    settings,
    graph: SimpleNamespace,
    *,
    points=None,
    idempotency_key: str = "v2-batch",
):
    add_pings(
        db_sessionmaker,
        trip_id=graph.trip.id,
        points=points or moving_points(graph.trip.started_at),
        idempotency_key=idempotency_key,
    )
    return run_pipeline(db_sessionmaker, graph.trip.id, settings)


# --- Pure money / time-domain tests -----------------------------------------


def test_price_payable_seconds_is_half_up_at_2dp_exactly_once() -> None:
    assert price_payable_seconds(90, Decimal("100.00")) == Decimal("2.50")
    # 9 s at NGN 2/h = 0.005: HALF_UP lifts to 0.01 where v1's banker's
    # rounding (quantize_2) would drop to 0.00 - the two must never converge.
    assert price_payable_seconds(9, Decimal("2.00")) == Decimal("0.01")
    assert quantize_2(Decimal("0.005")) == Decimal("0.00")
    assert quantize_ngn_half_up(Decimal("0.005")) == Decimal("0.01")
    assert quantize_ngn_half_up(Decimal("0.015")) == Decimal("0.02")
    assert quantize_2(Decimal("0.015")) == Decimal("0.02")
    assert price_payable_seconds(0, Decimal("5000.00")) == Decimal("0.00")


def test_daily_cap_is_integer_seconds() -> None:
    rule = SimpleNamespace(daily_payable_hours_cap=Decimal("7.50"))
    assert daily_cap_seconds(rule) == 27000
    rule = SimpleNamespace(daily_payable_hours_cap=Decimal("0.25"))
    assert daily_cap_seconds(rule) == 900


def test_lagos_day_attribution_uses_zoneinfo_not_fixed_offset() -> None:
    # 23:50 Lagos on 20 Jul == 22:50 UTC -> bills against 20 Jul.
    assert lagos_day_for(datetime(2026, 7, 20, 22, 50, tzinfo=UTC)) == date(2026, 7, 20)
    # 23:10 UTC == 00:10 Lagos next day -> bills against 21 Jul.
    assert lagos_day_for(datetime(2026, 7, 20, 23, 10, tzinfo=UTC)) == date(2026, 7, 21)
    day_start_utc, day_end_utc = lagos_day_utc_range(date(2026, 7, 20))
    assert day_start_utc == datetime(2026, 7, 19, 23, 0, tzinfo=UTC)
    assert day_end_utc == datetime(2026, 7, 20, 23, 0, tzinfo=UTC)


def test_paycap_lock_key_is_deterministic_and_shared() -> None:
    from uuid import uuid4

    driver, campaign = uuid4(), uuid4()
    day = date(2026, 7, 20)
    key = paycap_lock_key(driver, campaign, day)
    assert key == paycap_lock_key(driver, campaign, day)
    assert key != paycap_lock_key(driver, campaign, date(2026, 7, 21))
    assert -(2**63) <= key < 2**63


# --- Full v2 computation (PostGIS) ------------------------------------------


def test_worker_pipeline_produces_v2_calculation_and_ledger(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v2-happy")
    result = pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    assert result.overall == "completed"
    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 1
    calculation = calculations[0]
    assert calculation.formula_version == PAYOUT_V2
    assert calculation.status == "calculated"
    assert calculation.eligible_seconds == 1800
    assert calculation.payable_seconds == 1800
    assert calculation.excluded_seconds_by_reason == {}
    assert calculation.inputs_fingerprint
    # 1800 s at NGN 1200/h = NGN 600.00, priced once.
    assert calculation.final_payout == Decimal("600.00")
    assert calculation.gross_payout == Decimal("600.00")
    assert calculation.quality_multiplier is None
    assert calculation.fraud_multiplier is None
    assert calculation.distance_component is None

    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("600.00")
    assert entries[0].entry_type == "trip_payout"
    assert entries[0].status == "pending"

    # Sum of posted entries is authoritative and matches the summary.
    async def summary():
        async with postgis_db_sessionmaker() as session:
            return await driver_earnings_summary(
                session, user_id=graph.driver.id, currency=None, settings=settings
            )

    totals = asyncio.run(summary()).totals_by_currency[0]
    assert totals.pending_amount == Decimal("600.00")
    assert totals.lifetime_earned_amount == Decimal("600.00")

    # Rerun is a no-op: v2 rows are write-once, sweep sees nothing due.
    rerun = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert {s.stage: s.outcome for s in rerun.stages}["payout"] == "reused"
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(postgis_db_sessionmaker)) == 1

    async def due():
        async with postgis_db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    assert asyncio.run(due()) == []


def test_cap_truncates_before_pricing_across_same_day_trips(
    postgis_db_sessionmaker, settings
) -> None:
    # Cap 0.25 h = 900 s. First trip consumes it fully; the second earns 0.
    graph = build_v2_graph(
        postgis_db_sessionmaker, "v2-cap", daily_cap_hours="0.25"
    )
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph, idempotency_key="cap-1")

    second_start = TRIP_END + timedelta(minutes=10)
    second_trip = _add_second_trip(
        postgis_db_sessionmaker, graph, started_at=second_start
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=second_trip.id,
        points=moving_points(second_start),
        idempotency_key="cap-2",
    )
    run_pipeline(postgis_db_sessionmaker, second_trip.id, settings)

    calculations = {
        calculation.trip_session_id: calculation
        for calculation in fetch_payout_calculations(postgis_db_sessionmaker)
    }
    first = calculations[graph.trip.id]
    second = calculations[second_trip.id]
    assert first.payable_seconds == 900
    assert first.final_payout == price_payable_seconds(900, Decimal("1200.00"))
    assert second.eligible_seconds == 1800
    assert second.payable_seconds == 0
    assert second.final_payout == Decimal("0.00")
    # Zero-amount calculation posts no entry; same-day totals never exceed cap.
    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert sum(
        (calculation.payable_seconds or 0) for calculation in calculations.values()
    ) <= 900


def _add_second_trip(db_sessionmaker, graph, *, started_at, minutes: int = 30):
    from conftest import create_test_trip_session

    from app.models.trip import TripSessionStatus

    return create_test_trip_session(
        db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
    )


def test_concurrent_same_day_trips_never_jointly_exceed_the_cap(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(
        postgis_db_sessionmaker, "v2-race", daily_cap_hours="0.50"
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(TRIP_START),
        idempotency_key="race-1",
    )
    second_start = TRIP_END + timedelta(minutes=10)
    second_trip = _add_second_trip(
        postgis_db_sessionmaker, graph, started_at=second_start
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=second_trip.id,
        points=moving_points(second_start),
        idempotency_key="race-2",
    )

    async def race() -> None:
        async def one(trip_id) -> None:
            async with postgis_db_sessionmaker() as session:
                await process_ended_trip_committed(session, trip_id)

        async def process_ended_trip_committed(session, trip_id) -> None:
            from app.services.trip_processing import process_ended_trip

            await process_ended_trip(session, trip_id=trip_id, settings=settings)
            await session.commit()

        await asyncio.gather(one(graph.trip.id), one(second_trip.id))

    asyncio.run(race())

    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    total_payable = sum(calculation.payable_seconds or 0 for calculation in calculations)
    assert total_payable <= 1800
    total_amount = sum(
        entry.amount for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    )
    assert total_amount <= price_payable_seconds(1800, Decimal("1200.00"))


def test_v1_to_v2_switch_never_double_pays_history(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "v1-switch", started_at=TRIP_START,
                        ended_at=TRIP_END)
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(TRIP_START),
        idempotency_key="switch-1",
    )
    run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1
    v1_entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert len(v1_entries) == 1

    # Campaign switches to the hourly model.
    deactivate_rules(postgis_db_sessionmaker, graph.campaign.id)
    create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )

    async def due():
        async with postgis_db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    # The historical v1-paid trip is NOT re-queued under v2...
    assert asyncio.run(due()) == []
    # ...and reprocessing reuses the v1 calculation without a second payout.
    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert {s.stage: s.outcome for s in result.stages}["payout"] == "reused"
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(postgis_db_sessionmaker)) == 1


def test_input_drift_never_requeues_v2_but_flags_stale_on_admin_surface(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v2-drift")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]

    async def mutate_rate() -> None:
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.hourly_rate_naira = Decimal("1500.00")
            await session.commit()

    asyncio.run(mutate_rate())

    async def checks() -> tuple[list, bool]:
        async with postgis_db_sessionmaker() as session:
            due = await find_unprocessed_trips(session, limit=10, settings=settings)
            from app.models.trip import TripSession

            trip = await session.get(TripSession, graph.trip.id)
            stale = await v2_calculation_is_stale(
                session, calculation, trip=trip, settings=settings
            )
            return due, stale

    due, stale = asyncio.run(checks())
    assert due == []  # write-once: no perpetual re-queue on drift
    assert stale is True  # ...but drift is detectable without recomputation

    # Worker path reuses without error; admin strict path flags 409.
    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert {s.stage: s.outcome for s in result.stages}["payout"] == "reused"

    from app.core.errors import AppError

    try:
        calculate(postgis_db_sessionmaker, graph.trip.id, settings, strict_staleness=True)
        raise AssertionError("expected PAYOUT_CALCULATION_STALE")
    except AppError as exc:
        assert exc.code == "PAYOUT_CALCULATION_STALE"

    # Money unchanged: still one calculation, one entry, original amount.
    calculations = fetch_payout_calculations(postgis_db_sessionmaker)
    assert len(calculations) == 1
    assert calculations[0].final_payout == Decimal("600.00")


def test_zone_edits_change_the_inputs_fingerprint(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v2-zone")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    calculation = fetch_payout_calculations(postgis_db_sessionmaker)[0]

    async def add_zone_and_check() -> bool:
        import json

        async with postgis_db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=graph.campaign.id,
                created_by_user_id=graph.admin.id,
                name="Late zone",
                zone_type="target",
                geom=geometry_expression(
                    json.dumps(
                        {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [3.0, 6.0],
                                    [3.9, 6.0],
                                    [3.9, 6.9],
                                    [3.0, 6.9],
                                    [3.0, 6.0],
                                ]
                            ],
                        }
                    )
                ),
                zone_metadata={},
            )
            session.add(zone)
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            from app.models.trip import TripSession

            trip = await session.get(TripSession, graph.trip.id)
            return await v2_calculation_is_stale(
                session, calculation, trip=trip, settings=settings
            )

    assert asyncio.run(add_zone_and_check()) is True


# --- Recompute-day (PostGIS) -------------------------------------------------


def run_recompute(db_sessionmaker, settings, graph, *, lagos_date=None):
    async def run():
        async with db_sessionmaker() as session:
            outcome = await recompute_payout_day(
                session,
                campaign_id=graph.campaign.id,
                driver_profile_id=graph.profile.id,
                lagos_date=lagos_date or lagos_day_for(graph.trip.started_at),
                request_metadata={"source": "test"},
                settings=settings,
            )
            await session.commit()
            return outcome

    return asyncio.run(run())


def driver_totals(db_sessionmaker, settings, user_id):
    async def run():
        async with db_sessionmaker() as session:
            summary = await driver_earnings_summary(
                session, user_id=user_id, currency=None, settings=settings
            )
            return summary.totals_by_currency[0]

    return asyncio.run(run())


def test_recompute_day_is_idempotent_with_unchanged_inputs(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-idem")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    before = fetch_earnings_ledger_entries(postgis_db_sessionmaker)

    outcome = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert outcome.adjustment_count == 0
    assert outcome.reversal_count == 0
    assert [trip.delta_amount for trip in outcome.trips] == [Decimal("0.00")]
    assert len(fetch_earnings_ledger_entries(postgis_db_sessionmaker)) == len(before)


def test_recompute_day_posts_adjustment_on_upward_delta(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-up")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)

    async def raise_rate() -> None:
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.hourly_rate_naira = Decimal("1500.00")
            await session.commit()

    asyncio.run(raise_rate())
    outcome = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert outcome.adjustment_count == 1
    assert outcome.reversal_count == 0
    # 1800 s: 750.00 target - 600.00 posted = 150.00 adjustment.
    delta_entry = next(
        entry
        for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
        if entry.entry_type == EarningsLedgerEntryType.ADJUSTMENT.value
    )
    assert delta_entry.amount == Decimal("150.00")
    assert delta_entry.payout_calculation_id is None
    assert delta_entry.status == "pending"  # inherits the trip_payout status
    assert delta_entry.ledger_metadata["breakdown"]["target_amount"] == "750.00"

    totals_after = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    assert totals_after.pending_amount == totals_before.pending_amount + Decimal("150.00")

    # Second run: no-op.
    second = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert second.adjustment_count == 0
    assert second.reversal_count == 0


def test_recompute_day_posts_reversal_on_downward_delta_and_never_increases(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-down")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)

    async def lower_rate() -> None:
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.hourly_rate_naira = Decimal("900.00")
            await session.commit()

    asyncio.run(lower_rate())
    outcome = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert outcome.adjustment_count == 0
    assert outcome.reversal_count == 1
    reversal = next(
        entry
        for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
        if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value
    )
    # Downward correction = POSITIVE reversal amount, netted negative.
    assert reversal.amount == Decimal("150.00")
    totals_after = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    assert totals_after.pending_amount == totals_before.pending_amount - Decimal("150.00")
    assert totals_after.pending_amount == Decimal("450.00")
    assert totals_after.lifetime_earned_amount <= totals_before.lifetime_earned_amount

    # Idempotent after settling.
    second = run_recompute(postgis_db_sessionmaker, settings, graph)
    assert second.reversal_count == 0


def test_recompute_day_gives_voided_trips_nothing_and_frees_their_cap(
    postgis_db_sessionmaker, settings
) -> None:
    # Cap 0.25 h: trip 1 consumed all 900 s, trip 2 got 0. Voiding trip 1
    # frees the cap; the true-up pays trip 2 instead - and never re-pays 1.
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-void", daily_cap_hours="0.25")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph, idempotency_key="void-1")
    second_start = TRIP_END + timedelta(minutes=10)
    second_trip = _add_second_trip(postgis_db_sessionmaker, graph, started_at=second_start)
    add_pings(
        postgis_db_sessionmaker,
        trip_id=second_trip.id,
        points=moving_points(second_start),
        idempotency_key="void-2",
    )
    run_pipeline(postgis_db_sessionmaker, second_trip.id, settings)

    async def void_first() -> None:
        async with postgis_db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == graph.trip.id,
                    EarningsLedgerEntry.entry_type
                    == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_first())
    outcome = run_recompute(postgis_db_sessionmaker, settings, graph)

    by_trip = {trip.trip_session_id: trip for trip in outcome.trips}
    assert by_trip[graph.trip.id].voided is True
    assert by_trip[graph.trip.id].target_amount == Decimal("0.00")
    assert by_trip[graph.trip.id].entry is None  # posted(non-voided)=0, delta=0
    assert by_trip[second_trip.id].payable_seconds == 900
    assert by_trip[second_trip.id].delta_amount == price_payable_seconds(
        900, Decimal("1200.00")
    )
    totals = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    # Only the freed-cap adjustment for trip 2 counts (voided excluded).
    assert totals.pending_amount == price_payable_seconds(900, Decimal("1200.00"))


def test_recompute_day_refuses_v1_campaigns_and_mixed_days(
    postgis_db_sessionmaker, settings
) -> None:
    from app.core.errors import AppError

    graph = build_graph(postgis_db_sessionmaker, "rc-guards", started_at=TRIP_START,
                        ended_at=TRIP_END)
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(TRIP_START),
        idempotency_key="guards-1",
    )
    run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)

    # v1-governed campaign -> 400.
    try:
        run_recompute(postgis_db_sessionmaker, settings, graph)
        raise AssertionError("expected INVALID_PAYOUT_RULE")
    except AppError as exc:
        assert exc.code == "INVALID_PAYOUT_RULE"

    # Switch to v2: the day now holds a v1 calculation -> mixed-day refusal.
    deactivate_rules(postgis_db_sessionmaker, graph.campaign.id)
    graph.rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    try:
        run_recompute(postgis_db_sessionmaker, settings, graph)
        raise AssertionError("expected PAYOUT_DAY_MIXED_FORMULAS")
    except AppError as exc:
        assert exc.code == "PAYOUT_DAY_MIXED_FORMULAS"


# --- Driver breakdown + API surface ------------------------------------------


def test_driver_breakdown_service_matches_calculation_and_survives_recompute(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "bd-v2")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    async def breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )

    first = asyncio.run(breakdown())
    assert first.formula_version == PAYOUT_V2
    assert first.eligible_seconds == 1800
    assert first.capped_seconds == 1800
    assert first.hourly_rate == Decimal("1200.00")
    assert first.amount == Decimal("600.00")
    assert first.superseded_by_recompute is False
    assert first.cap_seconds == 8 * 3600
    assert first.day_payable_seconds == 1800
    # rate x capped time == amount (dispute-prevention invariant).
    assert price_payable_seconds(first.capped_seconds, first.hourly_rate) == first.amount

    async def raise_rate() -> None:
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.hourly_rate_naira = Decimal("1500.00")
            await session.commit()

    asyncio.run(raise_rate())
    run_recompute(postgis_db_sessionmaker, settings, graph)

    second = asyncio.run(breakdown())
    assert second.superseded_by_recompute is True
    assert second.hourly_rate == Decimal("1500.00")
    assert second.amount == Decimal("750.00")
    # The invariant still holds after the true-up.
    assert (
        price_payable_seconds(second.capped_seconds, second.hourly_rate) == second.amount
    )


def test_historical_v1_trips_still_render_in_breakdown_and_reports(
    db_client, db_sessionmaker, settings
) -> None:
    from conftest import create_test_impression_estimate, create_test_traffic_density_profile
    from test_trip_processing import seed_analytics

    graph = build_graph(db_sessionmaker, "bd-v1")
    analytics = seed_analytics(db_sessionmaker, graph)
    density_profile = create_test_traffic_density_profile(
        db_sessionmaker,
        name="Breakdown v1 density",
        is_default=False,
    )
    create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=graph.trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        traffic_density_profile_id=density_profile.id,
        estimated_impressions=Decimal("1000"),
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )
    calculate(db_sessionmaker, graph.trip.id, settings)

    headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    response = db_client.get(
        f"/api/v1/driver/trips/{graph.trip.id}/earnings-breakdown", headers=headers
    )
    assert response.status_code == http_status.HTTP_200_OK
    payload = response.json()
    assert payload["formula_version"] == "payout_v1"
    assert payload["eligible_seconds"] is None
    assert payload["excluded_seconds_by_reason"] is None
    assert payload["hourly_rate"] is None
    assert payload["cap"] is None
    assert payload["superseded_by_recompute"] is False
    assert Decimal(payload["amount"]) >= 0
    assert len(payload["entries"]) == 1

    # v1 rows still render in the admin calculations list (regression, 16.1).
    from conftest import auth_headers as _auth

    admin_headers = _auth(db_client, graph.admin.email, PASSWORD)
    listed = db_client.get(
        "/api/v1/admin/payout-calculations",
        headers=admin_headers,
        params={"trip_session_id": str(graph.trip.id)},
    )
    assert listed.status_code == http_status.HTTP_200_OK
    item = listed.json()["items"][0]
    assert item["formula_version"] == "payout_v1"
    assert item["distance_component"] is not None
    assert item["eligible_seconds"] is None


def test_breakdown_permissions_and_ownership(db_client, db_sessionmaker, settings) -> None:
    from conftest import create_test_user

    from app.models.user import UserRole

    graph = build_graph(db_sessionmaker, "bd-perm")
    other_driver = create_test_user(
        db_sessionmaker,
        email="other-driver-perm@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    from conftest import create_test_driver_profile

    create_test_driver_profile(
        db_sessionmaker, user_id=other_driver.id, license_number="OTH-1"
    )

    assert (
        db_client.get(f"/api/v1/driver/trips/{graph.trip.id}/earnings-breakdown").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
    admin_headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    assert (
        db_client.get(
            f"/api/v1/driver/trips/{graph.trip.id}/earnings-breakdown",
            headers=admin_headers,
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    other_headers = auth_headers(db_client, other_driver.email, PASSWORD)
    assert (
        db_client.get(
            f"/api/v1/driver/trips/{graph.trip.id}/earnings-breakdown",
            headers=other_headers,
        ).status_code
        == http_status.HTTP_404_NOT_FOUND
    )


def test_recompute_day_endpoint_permissions_and_audit(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-api")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    body = {
        "campaign_id": str(graph.campaign.id),
        "driver_profile_id": str(graph.profile.id),
        "lagos_date": lagos_day_for(graph.trip.started_at).isoformat(),
    }
    assert (
        postgis_db_client.post("/api/v1/admin/payouts/recompute-day", json=body).status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
    driver_headers = auth_headers(postgis_db_client, graph.driver.email, PASSWORD)
    assert (
        postgis_db_client.post(
            "/api/v1/admin/payouts/recompute-day", json=body, headers=driver_headers
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )

    admin_headers = auth_headers(postgis_db_client, graph.admin.email, PASSWORD)
    response = postgis_db_client.post(
        "/api/v1/admin/payouts/recompute-day", json=body, headers=admin_headers
    )
    assert response.status_code == http_status.HTTP_200_OK
    payload = response.json()
    assert payload["adjustment_count"] == 0
    assert payload["reversal_count"] == 0
    assert payload["trips"][0]["delta_amount"] == "0.00"

    events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.payout_day.recomputed"
    ]
    assert len(events) == 1
    assert events[0].event_metadata["campaign_id"] == str(graph.campaign.id)
    assert events[0].event_metadata["trips"][0]["delta_amount"] == "0.00"


# --- Rule CRUD API (model XOR) -----------------------------------------------


def test_rule_api_supports_both_models_with_xor_validation(
    db_client, db_sessionmaker
) -> None:
    from conftest import create_test_campaign, create_test_organization, create_test_user

    from app.models.campaign import CampaignStatus
    from app.models.user import UserRole

    admin = create_test_user(
        db_sessionmaker, email="rule-admin@example.com", password=PASSWORD
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="rule-adv@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker, name="Rules Org", owner_user_id=advertiser.id
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    base = f"/api/v1/admin/campaigns/{campaign.id}/payout-rules"

    # v2 create requires the cap (D4).
    missing_cap = db_client.post(
        base,
        headers=headers,
        json={"formula_version": "payout_v2", "hourly_rate_naira": "1200.00"},
    )
    assert missing_cap.status_code == http_status.HTTP_400_BAD_REQUEST
    assert missing_cap.json()["error"]["code"] == "INVALID_PAYOUT_RULE"

    # v2 create requires a rate when no platform default is configured.
    missing_rate = db_client.post(
        base,
        headers=headers,
        json={"formula_version": "payout_v2", "daily_payable_hours_cap": "8.00"},
    )
    assert missing_rate.status_code == http_status.HTTP_400_BAD_REQUEST

    # v2 with v1 fields -> XOR violation.
    mixed = db_client.post(
        base,
        headers=headers,
        json={
            "formula_version": "payout_v2",
            "hourly_rate_naira": "1200.00",
            "daily_payable_hours_cap": "8.00",
            "base_rate_per_km": "10.00",
        },
    )
    assert mixed.status_code == http_status.HTTP_400_BAD_REQUEST

    # Unknown eligibility keys rejected.
    bad_params = db_client.post(
        base,
        headers=headers,
        json={
            "formula_version": "payout_v2",
            "hourly_rate_naira": "1200.00",
            "daily_payable_hours_cap": "8.00",
            "eligibility_params": {"nope": 1},
        },
    )
    assert bad_params.status_code == http_status.HTTP_400_BAD_REQUEST

    created = db_client.post(
        base,
        headers=headers,
        json={
            "formula_version": "payout_v2",
            "hourly_rate_naira": "1200.00",
            "daily_payable_hours_cap": "8.00",
            "eligibility_params": {"stationary_grace_min": 5},
        },
    )
    assert created.status_code == http_status.HTTP_201_CREATED
    rule = created.json()
    assert rule["formula_version"] == "payout_v2"
    assert rule["hourly_rate_naira"] == "1200.00"
    assert rule["daily_payable_hours_cap"] == "8.00"
    assert rule["base_rate_per_km"] is None
    assert rule["eligibility_params"] == {"stationary_grace_min": 5}

    # v2 update may tune v2 fields but never v1 fields.
    updated = db_client.patch(
        f"{base}/{rule['id']}",
        headers=headers,
        json={"hourly_rate_naira": "1300.00"},
    )
    assert updated.status_code == http_status.HTTP_200_OK
    assert updated.json()["hourly_rate_naira"] == "1300.00"
    cross_model = db_client.patch(
        f"{base}/{rule['id']}",
        headers=headers,
        json={"base_rate_per_km": "10.00"},
    )
    assert cross_model.status_code == http_status.HTTP_400_BAD_REQUEST

    # A v1 rule create still works and serializes every rate as a string.
    v1_created = db_client.post(
        base,
        headers=headers,
        json={"base_rate_per_km": "10.00", "status": "inactive"},
    )
    assert v1_created.status_code == http_status.HTTP_201_CREATED
    v1_rule = v1_created.json()
    assert v1_rule["formula_version"] == "payout_v1"
    for field in (
        "base_rate_per_km",
        "base_rate_per_active_hour",
        "min_payout_per_trip",
        "low_fraud_multiplier",
    ):
        assert isinstance(v1_rule[field], str)
    assert v1_rule["hourly_rate_naira"] is None
    # v1 rules must not set v2 fields.
    v1_mixed = db_client.patch(
        f"{base}/{v1_rule['id']}",
        headers=headers,
        json={"hourly_rate_naira": "900.00"},
    )
    assert v1_mixed.status_code == http_status.HTTP_400_BAD_REQUEST


def test_min_floor_no_longer_lifts_flagged_v1_trips(
    db_sessionmaker, settings
) -> None:
    from conftest import create_test_user
    from test_payouts import add_fraud_flag, create_payout_graph

    admin = create_test_user(
        db_sessionmaker, email="floor-admin@example.com", password=PASSWORD
    )
    _, _, campaign, _, _, _, trip, analytics, _ = create_payout_graph(
        db_sessionmaker,
        admin=admin,
        advertiser_email="floor-adv@example.com",
        driver_email="floor-driver@example.com",
        plate_number="FLR-1",
    )
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=Decimal("0.10"),
        min_payout_per_trip=Decimal("1500.00"),
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        severity="low",
        flag_type="impossible_speed",
    )

    calculation, _, _ = calculate(db_sessionmaker, trip.id, settings)
    # Flagged trip: the floor no longer applies (architecture 17 loophole).
    assert calculation.final_payout < Decimal("1500.00")


def test_recompute_reallocation_governs_later_same_day_cap_accounting(
    postgis_db_sessionmaker, settings
) -> None:
    # Review finding: after a true-up reallocates the day, a NEW same-day trip
    # must see the reallocated consumption, never a fresh cap.
    graph = build_v2_graph(postgis_db_sessionmaker, "rc-cap", daily_cap_hours="0.25")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph, idempotency_key="rccap-1")
    second_start = TRIP_END + timedelta(minutes=10)
    second_trip = _add_second_trip(postgis_db_sessionmaker, graph, started_at=second_start)
    add_pings(
        postgis_db_sessionmaker,
        trip_id=second_trip.id,
        points=moving_points(second_start),
        idempotency_key="rccap-2",
    )
    run_pipeline(postgis_db_sessionmaker, second_trip.id, settings)

    async def void_first() -> None:
        async with postgis_db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == graph.trip.id,
                    EarningsLedgerEntry.entry_type
                    == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_first())
    # True-up moves the freed 900 s of cap to trip 2.
    run_recompute(postgis_db_sessionmaker, settings, graph)

    # A third trip on the same Lagos day must find the cap fully consumed.
    third_start = second_start + timedelta(minutes=40)
    third_trip = _add_second_trip(postgis_db_sessionmaker, graph, started_at=third_start)
    add_pings(
        postgis_db_sessionmaker,
        trip_id=third_trip.id,
        points=moving_points(third_start),
        idempotency_key="rccap-3",
    )
    run_pipeline(postgis_db_sessionmaker, third_trip.id, settings)

    calculations = {
        calculation.trip_session_id: calculation
        for calculation in fetch_payout_calculations(postgis_db_sessionmaker)
    }
    assert calculations[third_trip.id].payable_seconds == 0
    assert calculations[third_trip.id].final_payout == Decimal("0.00")
    # Non-voided posted money never exceeds cap x rate.
    posted = sum(
        entry.amount if entry.entry_type != "reversal" else -entry.amount
        for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
        if entry.status != EarningsLedgerEntryStatus.VOIDED.value
    )
    assert posted <= price_payable_seconds(900, Decimal("1200.00"))


def test_v2_to_v1_switch_never_requeues_or_double_pays(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "v2-to-v1")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    deactivate_rules(postgis_db_sessionmaker, graph.campaign.id)
    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        base_rate_per_km=10,
    )

    async def due():
        async with postgis_db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    assert asyncio.run(due()) == []
    result = run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    assert {s.stage: s.outcome for s in result.stages}["payout"] == "reused"
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1
    assert len(fetch_earnings_ledger_entries(postgis_db_sessionmaker)) == 1


def test_explicit_rule_recompute_never_mints_second_v2_calculation(
    postgis_db_sessionmaker, settings
) -> None:
    from app.core.errors import AppError

    graph = build_v2_graph(postgis_db_sessionmaker, "explicit-v2")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    deactivate_rules(postgis_db_sessionmaker, graph.campaign.id)
    second_rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        hourly_rate="1500.00",
    )

    try:
        calculate(
            postgis_db_sessionmaker,
            graph.trip.id,
            settings,
            payout_rule_id=second_rule.id,
        )
        raise AssertionError("expected PAYOUT_CALCULATION_STALE")
    except AppError as exc:
        assert exc.code == "PAYOUT_CALCULATION_STALE"
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == 1


def test_recompute_day_refuses_currency_drift(
    postgis_db_sessionmaker, settings
) -> None:
    from app.core.errors import AppError

    graph = build_v2_graph(postgis_db_sessionmaker, "rc-currency")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)

    async def drift_currency() -> None:
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.currency = "USD"
            await session.commit()

    asyncio.run(drift_currency())
    try:
        run_recompute(postgis_db_sessionmaker, settings, graph)
        raise AssertionError("expected PAYOUT_DAY_CURRENCY_MISMATCH")
    except AppError as exc:
        assert exc.code == "PAYOUT_DAY_CURRENCY_MISMATCH"
    # No differential entries were posted.
    entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    assert all(entry.entry_type == "trip_payout" for entry in entries)
