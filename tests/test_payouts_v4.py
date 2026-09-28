"""payout_v4 (D39): daily rate for reaching a daily distance target (Batch B).

Every pay value here is an explicit SYNTHETIC test value. The client's real
answers (Q1 shortfall formula and minimum, Q2 which miles count, Q3 cap and
the full-day amount) are still open and are never assumed by the code.
"""

import asyncio
import math
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest
from conftest import (
    auth_headers,
    create_test_campaign_assignment,
    create_test_vehicle,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
    fetch_payout_calculations,
)
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from test_payouts_v2 import (
    BASE_LAT,
    BASE_LON,
    TRIP_END,
    TRIP_START,
    calculate,
    create_signed_v2_test_trip_session,
    create_v2_rule,
    moving_points,
    run_recompute,
)
from test_payouts_v3 import (
    PAST_EFFECTIVE,
    accept_assignment,
    add_target_zone,
    build_offered_graph,
    materialize_offer,
)
from test_trip_processing import add_pings, build_graph, run_pipeline

from app.core.errors import AppError
from app.db.session import get_session
from app.main import create_app
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.payout import (
    AssignmentRuleBinding,
    CampaignPayoutRule,
    CampaignPayoutRuleRevision,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculationStatus,
)
from app.models.trip import LocationPing, TripSession
from app.models.vehicle import VehicleStatus
from app.schemas.payouts import (
    CampaignPayoutRuleRevisionCreate,
    CampaignPayoutRuleUpdate,
    CampaignPayoutV4RevisionCreate,
)
from app.services import payouts
from app.services.billing import _assignment_liability_calculation
from app.services.campaign_assignments import (
    premium_zone_geometry_hash,
    resolved_eligibility_snapshot,
)
from app.services.campaign_changes import _additional_window_liability
from app.services.payout_corrections import project_campaign_day
from app.services.payout_eligibility import (
    D39_STOP_OVERLAY,
    STATIONARY_POLICY_D39,
    STATIONARY_POLICY_V1,
    EligibilityParams,
    EligibilityPing,
    classify_session,
    credited_distance_m_by_day,
)
from app.services.payouts import (
    PAYOUT_V2,
    PAYOUT_V4,
    DailyRateTerms,
    create_payout_rule_revision,
    day_credited_distance_m,
    day_pay_naira,
    driver_trip_earnings_breakdown,
    publish_payout_v4_revision,
    v4_calculation_is_stale,
)
from app.services.trip_processing import find_unprocessed_trips

MILE = Fraction("1609.344")
EARTH_RADIUS_M = 6371000.0
PASSWORD = "long-secure-password"


# --- Independent expectations (never call the code under test) ---------------


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def metres_along(points, *, max_gap_seconds: int = 120) -> int:
    """Whole metres over consecutive pings, skipping GPS gaps."""
    total = Fraction(0)
    for first, second in zip(points, points[1:], strict=False):
        if (second[0] - first[0]).total_seconds() > max_gap_seconds:
            continue
        total += Fraction(haversine(first[1], first[2], second[1], second[2]))
    return math.floor(total)


def expected_pay(metres: int, *, rate, target, strategy, deduction=None, minimum="0") -> Decimal:
    if metres <= 0:
        return Decimal("0.00")
    miles = Decimal(metres) / Decimal("1609.344")
    rate, target = Decimal(rate), Decimal(target)
    if miles < Decimal(minimum):
        value = Decimal(0)
    elif miles >= target:
        value = rate
    elif strategy == "proportional":
        value = rate * miles / target
    else:
        value = max(Decimal(0), rate - Decimal(deduction) * (target - miles))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def terms(**overrides) -> DailyRateTerms:
    values = {
        "daily_rate_naira": Decimal("10000.00"),
        "daily_target_miles": Decimal("70"),
        "shortfall_strategy": "per_mile_deduction",
        "deduction_per_mile_naira": Decimal("140.00"),
        "minimum_miles": Decimal("0"),
        "outside_area_weight": Decimal("1"),
    }
    values.update(overrides)
    return DailyRateTerms(**values)


def miles_m(miles: str) -> int:
    return math.floor(Fraction(miles) * MILE)


# --- D(d): pure day-pay tables (synthetic ₦10,000 / 70 mi / ₦140) -------------


def test_per_mile_deduction_table_including_zero_and_the_jump() -> None:
    per_mile = terms()
    assert day_pay_naira(0, per_mile) == Decimal("0.00")
    # Just above zero the per-mile form jumps to rate - 140 x 70 = ₦200 (plus
    # 1 m of credit). Whether that jump is intended is the client's Q1 answer.
    assert day_pay_naira(1, per_mile) == Decimal("200.09")
    assert day_pay_naira(miles_m("35"), per_mile) == expected_pay(
        miles_m("35"), rate="10000", target="70", strategy="per_mile", deduction="140"
    )
    assert day_pay_naira(miles_m("69.5"), per_mile) == expected_pay(
        miles_m("69.5"), rate="10000", target="70", strategy="per_mile", deduction="140"
    )
    # At and beyond the target: exactly one day rate, never more (cap).
    assert day_pay_naira(math.ceil(Fraction(70) * MILE), per_mile) == Decimal("10000.00")
    assert day_pay_naira(miles_m("300"), per_mile) == Decimal("10000.00")
    # A deduction larger than the rate floors at ₦0, never negative.
    steep = terms(deduction_per_mile_naira=Decimal("500.00"))
    assert day_pay_naira(miles_m("10"), steep) == Decimal("0.00")


def test_proportional_table_and_minimum_distance() -> None:
    proportional = terms(shortfall_strategy="proportional", deduction_per_mile_naira=None)
    assert day_pay_naira(0, proportional) == Decimal("0.00")
    assert day_pay_naira(miles_m("35"), proportional) == expected_pay(
        miles_m("35"), rate="10000", target="70", strategy="proportional"
    )
    assert day_pay_naira(miles_m("70"), proportional) == expected_pay(
        miles_m("70"), rate="10000", target="70", strategy="proportional"
    )
    assert day_pay_naira(miles_m("71"), proportional) == Decimal("10000.00")
    with_minimum = terms(
        shortfall_strategy="proportional",
        deduction_per_mile_naira=None,
        minimum_miles=Decimal("20"),
    )
    assert day_pay_naira(miles_m("19.99"), with_minimum) == Decimal("0.00")
    at_minimum = math.ceil(Fraction(20) * MILE)
    assert day_pay_naira(at_minimum, with_minimum) == expected_pay(
        at_minimum, rate="10000", target="70", strategy="proportional", minimum="20"
    )


@pytest.mark.parametrize("strategy", ["proportional", "per_mile_deduction"])
def test_day_pay_is_monotone_and_trip_increments_sum_to_the_day(strategy) -> None:
    day_terms = terms(
        shortfall_strategy=strategy,
        deduction_per_mile_naira=None if strategy == "proportional" else Decimal("140.00"),
        minimum_miles=Decimal("5"),
    )
    rng = random.Random(39)
    previous = Decimal("0.00")
    for metres in sorted(rng.randrange(0, 150_000) for _ in range(400)):
        value = day_pay_naira(metres, day_terms)
        assert value >= previous
        previous = value
    # Three trips in a day: increments are never negative and telescope to
    # exactly D(day total) — including when the day crosses the minimum and
    # the target.
    for trips in ([miles_m("4"), miles_m("30"), miles_m("50")], [1, 2, miles_m("80")]):
        credited, increments = 0, []
        for added in trips:
            increments.append(
                day_pay_naira(credited + added, day_terms) - day_pay_naira(credited, day_terms)
            )
            credited += added
        assert all(increment >= 0 for increment in increments)
        assert sum(increments) == day_pay_naira(credited, day_terms)


# --- Stop rule and distance: pure classifier ---------------------------------

T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
D39_PARAMS = EligibilityParams(
    stationary_radius_m=200.0,
    stationary_window_seconds=300,
    stationary_grace_seconds=0,
    max_accuracy_m=75.0,
    teleport_kmh=180.0,
    max_ping_gap_seconds=120,
)


def ping(seconds, lat, lon=BASE_LON, accuracy=10.0, *, start=T0, premium=True, in_area=True):
    return EligibilityPing(
        recorded_at=start + timedelta(seconds=seconds),
        latitude=lat,
        longitude=lon,
        accuracy_m=accuracy,
        in_area=in_area,
        in_premium=premium,
    )


def stop_trace(stop_seconds: int) -> list[EligibilityPing]:
    """Drive 333 m per 30 s, stop for ``stop_seconds``, then drive on."""
    pings = [ping(t, BASE_LAT + (t // 30) * 0.003) for t in range(0, 181, 30)]
    stop_lat = pings[-1].latitude
    stop_start = 180
    pings += [ping(stop_start + t, stop_lat) for t in range(10, stop_seconds, 10)]
    pings.append(ping(stop_start + stop_seconds, stop_lat))
    end = stop_start + stop_seconds
    pings += [ping(end + t, stop_lat + (t // 30) * 0.003) for t in range(30, 181, 30)]
    return pings


def classify(pings, *, marker=STATIONARY_POLICY_D39, params=D39_PARAMS, window_end=None):
    started = min(p.recorded_at for p in pings)
    ended = max(p.recorded_at for p in pings)
    return classify_session(
        session_started_at=started,
        session_ended_at=ended,
        pings=pings,
        window_start_at=None,
        window_end_at=window_end,
        params=params,
        stationary_policy_marker=marker,
    )


@pytest.mark.parametrize(("stop", "excluded"), [(299, 0), (300, 0), (301, 301)])
def test_d39_stop_rule_counts_stops_up_to_five_minutes(stop, excluded) -> None:
    breakdown = classify(stop_trace(stop))
    assert breakdown.excluded_seconds_by_reason.get("stationary", 0) == excluded
    assert "stationary_rolling_displacement" not in breakdown.excluded_seconds_by_reason
    evidence = breakdown.stationary_detector_evidence
    assert evidence["version"] == STATIONARY_POLICY_D39
    assert evidence["excluded_stop_ranges"] == (
        [{"start_offset": 180, "end_offset": 180 + stop}] if excluded else []
    )


def test_250s_stop_on_rolling_windows_counts_under_v4_but_not_v3_detector() -> None:
    # Moving 333 m per 30 s, then a 250 s stop aligned to 120 s windows
    # (240-490 s): D22's rolling detector confirms it; D39 does not.
    pings = [ping(t, BASE_LAT + (t // 30) * 0.003) for t in range(0, 241, 30)]
    stop_lat = pings[-1].latitude
    pings += [ping(240 + t, stop_lat) for t in range(10, 251, 10)]
    pings += [ping(490 + t, stop_lat + (t // 30) * 0.003) for t in range(30, 241, 30)]
    d39 = classify(pings)
    assert d39.excluded_seconds_by_reason == {}
    v3_params = EligibilityParams(
        stationary_radius_m=200.0,
        stationary_window_seconds=300,
        stationary_grace_seconds=0,
        max_accuracy_m=75.0,
        teleport_kmh=180.0,
        max_ping_gap_seconds=120,
    )
    v3 = classify(pings, marker=STATIONARY_POLICY_V1, params=v3_params)
    assert v3.excluded_seconds_by_reason["stationary_rolling_displacement"] > 0
    # The v3 detector keeps its own evidence shape.
    assert "window_observations" in v3.stationary_detector_evidence


def test_distance_prorates_by_eligible_time_and_skips_every_exclusion() -> None:
    pings = [ping(t, BASE_LAT + (t // 30) * 0.00081) for t in range(0, 601, 30)]
    straight = [(p.recorded_at, p.latitude, p.longitude) for p in pings]
    full = credited_distance_m_by_day(
        pings=pings, breakdown=classify(pings), outside_area_weight=Decimal("1")
    )
    assert full == {"2026-07-20": metres_along(straight)}

    # A GPS gap (> 120 s) credits nothing for that interval.
    gapped = pings[:6] + pings[11:]
    assert credited_distance_m_by_day(
        pings=gapped, breakdown=classify(gapped), outside_area_weight=Decimal("1")
    ) == {"2026-07-20": metres_along([(p.recorded_at, p.latitude, p.longitude) for p in gapped])}

    # Low accuracy removes both intervals touching the bad ping.
    blurred = list(pings)
    blurred[5] = ping(150, blurred[5].latitude, accuracy=150.0)
    expected = math.floor(
        sum(
            (
                Fraction(haversine(a[1], a[2], b[1], b[2]))
                for a, b in zip(straight, straight[1:], strict=False)
                if b[0] != straight[5][0] and a[0] != straight[5][0]
            ),
            Fraction(0),
        )
    )
    assert credited_distance_m_by_day(
        pings=blurred, breakdown=classify(blurred), outside_area_weight=Decimal("1")
    ) == {"2026-07-20": expected}

    # A teleport (10 km in 30 s) credits nothing for its interval.
    jumped = list(pings)
    jumped[10] = ping(300, BASE_LAT + 0.09)
    breakdown = classify(jumped)
    assert breakdown.excluded_seconds_by_reason["teleport"] == 60
    credited = credited_distance_m_by_day(
        pings=jumped, breakdown=breakdown, outside_area_weight=Decimal("1")
    )
    assert credited["2026-07-20"] < full["2026-07-20"]

    # The campaign window cuts an interval: only the eligible share counts
    # (15 of the 300-330 s interval's 30 seconds).
    window = classify(pings, window_end=T0 + timedelta(seconds=315))
    prorated = credited_distance_m_by_day(
        pings=pings, breakdown=window, outside_area_weight=Decimal("1")
    )
    first_ten = sum(
        (
            Fraction(haversine(a[1], a[2], b[1], b[2]))
            for a, b in zip(straight[:10], straight[1:11], strict=True)
        ),
        Fraction(0),
    )
    half_interval = Fraction(haversine(*straight[10][1:], *straight[11][1:])) / 2
    assert prorated == {"2026-07-20": math.floor(first_ten + half_interval)}


@pytest.mark.parametrize(("weight", "factor"), [("0", 0), ("0.5", Fraction(1, 2)), ("1", 1)])
def test_outside_area_weight_and_whole_metre_rounding(weight, factor) -> None:
    # First half inside the target zone, second half outside it.
    pings = [ping(t, BASE_LAT + (t // 30) * 0.00081, premium=t <= 300) for t in range(0, 601, 30)]
    points = [(p.recorded_at, p.latitude, p.longitude) for p in pings]
    inside = sum(
        (
            Fraction(haversine(a[1], a[2], b[1], b[2]))
            for a, b in zip(points[:11], points[1:11], strict=False)
        ),
        Fraction(0),
    )
    outside = sum(
        (
            Fraction(haversine(a[1], a[2], b[1], b[2]))
            for a, b in zip(points[10:], points[11:], strict=False)
        ),
        Fraction(0),
    )
    credited = credited_distance_m_by_day(
        pings=pings, breakdown=classify(pings), outside_area_weight=Decimal(weight)
    )
    # Exact fraction first, one floor to whole metres per day.
    assert credited == {"2026-07-20": math.floor(inside + outside * factor)}


def test_midnight_split_and_sub_second_intervals() -> None:
    # 23:50 -> 00:10 Lagos (22:50 -> 23:10 UTC).
    start = datetime(2026, 7, 20, 22, 50, tzinfo=UTC)
    pings = [ping(t, BASE_LAT + (t // 30) * 0.00081, start=start) for t in range(0, 1201, 30)]
    points = [(p.recorded_at, p.latitude, p.longitude) for p in pings]
    credited = credited_distance_m_by_day(
        pings=pings, breakdown=classify(pings), outside_area_weight=Decimal("1")
    )
    assert credited == {
        "2026-07-20": metres_along(points[:21]),
        "2026-07-21": metres_along(points[20:]),
    }
    # Two pings in the same whole second have no time slice, yet their
    # distance still counts when that instant is eligible.
    twin = [
        ping(0, BASE_LAT),
        ping(30, BASE_LAT + 0.00081),
        ping(30.4, BASE_LAT + 0.00082),
        ping(60, BASE_LAT + 0.00162),
    ]
    twin_points = [(p.recorded_at, p.latitude, p.longitude) for p in twin]
    assert credited_distance_m_by_day(
        pings=twin, breakdown=classify(twin), outside_area_weight=Decimal("1")
    ) == {"2026-07-20": metres_along(twin_points)}


def test_noisy_stationary_trace_jitter_is_bounded_and_long_stops_add_nothing() -> None:
    """Synthetic GPS noise (±5 m) while parked. A 4-minute stop counts as
    driving under D39, so its jitter is credited; a 10-minute stop is excluded
    whole. The measured jitter is the residual recorded for Batch B."""
    rng = random.Random(2026)

    def parked(seconds: int) -> list[EligibilityPing]:
        jitter = 5 / 111_320  # ~5 m in degrees of latitude
        return [
            ping(
                t, BASE_LAT + rng.uniform(-jitter, jitter), BASE_LON + rng.uniform(-jitter, jitter)
            )
            for t in range(0, seconds + 1, 10)
        ]

    short = parked(240)
    short_credit = credited_distance_m_by_day(
        pings=short, breakdown=classify(short), outside_area_weight=Decimal("1")
    )["2026-07-20"]
    assert 0 < short_credit <= 24 * 15  # at most ~15 m per 10 s interval
    long = parked(600)
    long_breakdown = classify(long)
    assert long_breakdown.eligible_seconds == 0
    assert (
        credited_distance_m_by_day(
            pings=long, breakdown=long_breakdown, outside_area_weight=Decimal("1")
        )
        == {}
    )


# --- PostGIS graph helpers ----------------------------------------------------

DEFAULT_TERMS = {
    "daily_rate_naira": "8000.00",
    "daily_target_miles": "8.000",
    "shortfall_strategy": "proportional",
    "deduction_per_mile_naira": None,
    "minimum_miles": "0.000",
    "outside_area_weight": "1.0000",
}


def create_v4_rule(db, *, campaign_id, admin_id, rule_status="active") -> CampaignPayoutRule:
    async def create():
        async with db() as session:
            rule = CampaignPayoutRule(
                campaign_id=campaign_id,
                created_by_user_id=admin_id,
                formula_version=PAYOUT_V4,
                status=rule_status,
                currency="NGN",
                rule_metadata={},
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    return asyncio.run(create())


def create_v4_revision(db, *, campaign_id, rule_id, admin_id, number=1, **overrides):
    values = {**DEFAULT_TERMS, **overrides}

    async def create():
        async with db() as session:
            revision = CampaignPayoutRuleRevision(
                campaign_id=campaign_id,
                payout_rule_id=rule_id,
                revision_number=number,
                effective_from=PAST_EFFECTIVE + timedelta(days=number),
                currency="NGN",
                eligibility_params=dict(D39_STOP_OVERLAY),
                formula_version=PAYOUT_V4,
                reason="synthetic test revision",
                created_by_user_id=admin_id,
                **{
                    key: (Decimal(value) if key != "shortfall_strategy" and value else value)
                    for key, value in values.items()
                },
            )
            session.add(revision)
            await session.commit()
            await session.refresh(revision)
            return revision

    return asyncio.run(create())


def insert_v4_binding(db, settings, *, assignment_id, revision, zone_ids):
    async def create():
        async with db() as session:
            campaign = await session.get(Campaign, revision.campaign_id)
            target_rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom))
                    .where(CampaignZone.id.in_(list(zone_ids)))
                    .order_by(CampaignZone.id)
                )
            ).all()
            exclusion_rows = (
                await session.execute(
                    select(CampaignZone.id, func.ST_AsText(CampaignZone.geom)).where(
                        CampaignZone.campaign_id == revision.campaign_id,
                        CampaignZone.zone_type == CampaignZoneType.EXCLUSION.value,
                    )
                )
            ).all()
            binding = AssignmentRuleBinding(
                assignment_id=assignment_id,
                revision_id=revision.id,
                currency=revision.currency,
                daily_rate_naira=revision.daily_rate_naira,
                daily_target_miles=revision.daily_target_miles,
                shortfall_strategy=revision.shortfall_strategy,
                deduction_per_mile_naira=revision.deduction_per_mile_naira,
                minimum_miles=revision.minimum_miles,
                outside_area_weight=revision.outside_area_weight,
                eligibility_params=revision.eligibility_params,
                resolved_eligibility_params=resolved_eligibility_snapshot(
                    settings, revision.eligibility_params
                ),
                formula_version=PAYOUT_V4,
                premium_zone_ids=[str(row[0]) for row in target_rows],
                premium_zone_geometry_hash=premium_zone_geometry_hash(target_rows),
                premium_zone_geometry_wkts=[str(row[1]) for row in target_rows],
                exclusion_zone_ids=[str(row[0]) for row in exclusion_rows],
                exclusion_zone_geometry_hash=premium_zone_geometry_hash(exclusion_rows),
                exclusion_zone_geometry_wkts=[str(row[1]) for row in exclusion_rows],
                stationary_policy_marker=STATIONARY_POLICY_D39,
                campaign_window_start_at=campaign.start_at,
                campaign_window_end_at=campaign.end_at,
                campaign_window_frozen=True,
                bound_at=datetime.now(UTC),
            )
            session.add(binding)
            await session.commit()
            await session.refresh(binding)
            return binding

    return asyncio.run(create())


def build_v4_graph(db, settings, tag, *, started_at=TRIP_START, ended_at=TRIP_END, **overrides):
    graph = build_graph(db, tag, started_at=started_at, ended_at=ended_at)
    graph.rule = create_v4_rule(db, campaign_id=graph.campaign.id, admin_id=graph.admin.id)
    graph.zone = add_target_zone(
        db,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="Target",
        lat_min=6.40,
        lat_max=6.60,
    )
    graph.revision = create_v4_revision(
        db,
        campaign_id=graph.campaign.id,
        rule_id=graph.rule.id,
        admin_id=graph.admin.id,
        **overrides,
    )
    graph.binding = insert_v4_binding(
        db,
        settings,
        assignment_id=graph.assignment.id,
        revision=graph.revision,
        zone_ids=[graph.zone.id],
    )
    graph.terms = {**DEFAULT_TERMS, **overrides}
    return graph


def add_trip(db, settings, graph, *, started_at, minutes=30, assignment=None, vehicle=None):
    return create_signed_v2_test_trip_session(
        db,
        settings,
        assignment_id=(assignment or graph.assignment).id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=(vehicle or graph.vehicle).id,
        started_by_user_id=graph.driver.id,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=minutes),
    )


def drive(db, settings, trip, *, minutes=30, key=None):
    points = moving_points(trip.started_at, minutes=minutes)
    add_pings(db, trip_id=trip.id, points=points, idempotency_key=key or f"v4-{trip.id}")
    result = run_pipeline(db, trip.id, settings)
    assert result.overall == "completed"
    return [(p[0], p[1], p[2]) for p in points]


def calculations_by_trip(db) -> dict:
    return {calc.trip_session_id: calc for calc in fetch_payout_calculations(db)}


def pay(graph, metres) -> Decimal:
    t = graph.terms
    return expected_pay(
        metres,
        rate=t["daily_rate_naira"],
        target=t["daily_target_miles"],
        strategy=t["shortfall_strategy"],
        deduction=t["deduction_per_mile_naira"],
        minimum=t["minimum_miles"],
    )


# --- Engine -------------------------------------------------------------------


def test_three_same_day_trips_earn_increments_that_sum_to_the_capped_day(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(db, settings, "v4-three")
    trips = [graph.trip]
    trips += [
        add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=h)) for h in (1, 2)
    ]
    day = "2026-07-20"
    metres = [metres_along(drive(db, settings, trip)) for trip in trips]
    calcs = calculations_by_trip(db)

    credited = 0
    for trip, added in zip(trips, metres, strict=True):
        calc = calcs[trip.id]
        assert calc.formula_version == PAYOUT_V4
        assert calc.distance_m_by_day == {day: added}
        increment = pay(graph, credited + added) - pay(graph, credited)
        assert calc.amount_by_day == {day: str(increment)}
        assert calc.final_payout == increment
        assert calc.payout_metadata["distance"]["prior_distance_m_by_day"] == {day: credited}
        assert calc.payout_metadata["daily_rate"]["shortfall_strategy"] == "proportional"
        assert calc.payout_metadata["stationary_detector"]["version"] == STATIONARY_POLICY_D39
        assert calc.payable_seconds is None and calc.inputs_fingerprint
        credited += added
    # 3 x ~5.4 km passes the synthetic 8-mile target: the day pays exactly
    # one day rate in total.
    assert sum(metres) > 8 * 1609.344
    assert sum(calcs[t.id].final_payout for t in trips) == Decimal("8000.00")
    entries = fetch_earnings_ledger_entries(db)
    assert sum(entry.amount for entry in entries) == Decimal("8000.00")
    assert {entry.ledger_metadata["formula_version"] for entry in entries} == {PAYOUT_V4}

    # Idempotent retry: reuse, no second calculation or ledger entry.
    calculation, ledger, created = calculate(db, trips[0].id, settings)
    assert created is False and calculation.id == calcs[trips[0].id].id
    assert len(fetch_earnings_ledger_entries(db)) == 3

    async def breakdown():
        async with db() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=trips[2].id
            )

    driver_view = asyncio.run(breakdown())
    assert driver_view.formula_version == PAYOUT_V4
    assert driver_view.daily_rate_days == [
        (date(2026, 7, 20), metres[2], calcs[trips[2].id].final_payout)
    ]


def test_minimum_distance_pays_nothing_until_the_day_crosses_it(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(
        db,
        settings,
        "v4-minimum",
        daily_rate_naira="3000.00",
        daily_target_miles="4.000",
        shortfall_strategy="per_mile_deduction",
        deduction_per_mile_naira="500.00",
        minimum_miles="3.500",
    )
    trip2 = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=1))
    first = metres_along(drive(db, settings, graph.trip))
    second = metres_along(drive(db, settings, trip2))
    calcs = calculations_by_trip(db)
    assert first < 3.5 * 1609.344 < first + second
    assert calcs[graph.trip.id].final_payout == Decimal("0.00")
    assert calcs[graph.trip.id].distance_m_by_day == {"2026-07-20": first}
    assert calcs[trip2.id].final_payout == pay(graph, first + second) == Decimal("3000.00")
    # No ledger entry for a ₦0 day share; the credited distance still counts.
    assert [entry.trip_session_id for entry in fetch_earnings_ledger_entries(db)] == [trip2.id]


def test_cross_midnight_trip_prices_each_lagos_day_separately(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    started = datetime(2026, 7, 20, 22, 30, tzinfo=UTC)  # 23:30 Lagos
    graph = build_v4_graph(
        db, settings, "v4-midnight", started_at=started, ended_at=started + timedelta(minutes=60)
    )
    points = drive(db, settings, graph.trip, minutes=60)
    calc = fetch_payout_calculations(db)[0]
    day_a, day_b = metres_along(points[:61]), metres_along(points[60:])
    assert calc.distance_m_by_day == {"2026-07-20": day_a, "2026-07-21": day_b}
    assert calc.amount_by_day == {
        "2026-07-20": str(pay(graph, day_a)),
        "2026-07-21": str(pay(graph, day_b)),
    }
    assert calc.final_payout == pay(graph, day_a) + pay(graph, day_b)


def test_insufficient_data_credits_no_distance_and_no_money(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(db, settings, "v4-insufficient")
    add_pings(db, trip_id=graph.trip.id, points=[(TRIP_START, BASE_LAT, BASE_LON, 10.0)])
    run_pipeline(db, graph.trip.id, settings)
    calc = fetch_payout_calculations(db)[0]
    assert calc.formula_version == PAYOUT_V4
    assert calc.status == "insufficient_data"
    assert calc.distance_m_by_day == {} and calc.amount_by_day == {}
    assert calc.final_payout == Decimal("0.00")
    assert fetch_earnings_ledger_entries(db) == []


def test_blocked_trip_credits_no_distance_and_later_trips_start_from_zero(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(db, settings, "v4-blocked")
    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=1))
    # The first trip's evidence is blocked (as a fraud/exclusion decision would).
    original_status = payouts._payout_status

    def blocked_for_first(analytics, estimate):
        if analytics.trip_session_id == graph.trip.id:
            return PayoutCalculationStatus.BLOCKED.value
        return original_status(analytics, estimate)

    monkeypatch.setattr(payouts, "_payout_status", blocked_for_first)
    drive(db, settings, graph.trip)
    added = metres_along(drive(db, settings, later))
    calcs = calculations_by_trip(db)
    blocked = calcs[graph.trip.id]
    assert blocked.status == "blocked"
    assert blocked.distance_m_by_day == {} and blocked.amount_by_day == {}
    assert blocked.final_payout == Decimal("0.00")
    assert calcs[later.id].payout_metadata["distance"]["prior_distance_m_by_day"] == {
        "2026-07-20": 0
    }
    assert calcs[later.id].final_payout == pay(graph, added)
    assert [e.trip_session_id for e in fetch_earnings_ledger_entries(db)] == [later.id]


def test_frozen_input_drift_is_flagged_never_requeued_or_repriced(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(db, settings, "v4-stale")
    drive(db, settings, graph.trip)
    calc = fetch_payout_calculations(db)[0]

    async def drift():
        async with db() as session:
            binding = await session.get(AssignmentRuleBinding, graph.binding.id)
            binding.daily_rate_naira = Decimal("9000.00")  # test-only tampering
            await session.commit()
        async with db() as session:
            trip = await session.get(TripSession, graph.trip.id)
            stale = await v4_calculation_is_stale(session, calc, trip=trip)
            due = await find_unprocessed_trips(session, limit=10, settings=settings)
            return stale, due

    stale, due = asyncio.run(drift())
    assert stale is True
    assert due == []
    with pytest.raises(AppError) as exc_info:
        calculate(db, graph.trip.id, settings, strict_staleness=True)
    assert exc_info.value.code == "PAYOUT_CALCULATION_STALE"
    assert {s.stage: s.outcome for s in run_pipeline(db, graph.trip.id, settings).stages}[
        "payout"
    ] == "reused"
    assert [c.final_payout for c in fetch_payout_calculations(db)] == [calc.final_payout]


def test_unbound_trip_on_daily_rate_campaign_fails_closed(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_graph(db, "v4-unbound", started_at=TRIP_START, ended_at=TRIP_END)
    create_v4_rule(db, campaign_id=graph.campaign.id, admin_id=graph.admin.id)
    add_pings(db, trip_id=graph.trip.id, points=moving_points(TRIP_START))
    with pytest.raises(AppError) as exc_info:
        run_pipeline(db, graph.trip.id, settings)
    assert exc_info.value.code == "PAYOUT_BINDING_NOT_FOUND"
    assert fetch_payout_calculations(db) == []


def build_mixed_day(db, settings, tag, *, hourly_first: bool):
    """Same driver/campaign/Lagos day: an unbound hourly (v2) trip and a bound
    daily-rate trip on a second vehicle."""
    graph = build_graph(db, tag, started_at=TRIP_START, ended_at=TRIP_END)
    graph.rule = create_v2_rule(
        db, campaign_id=graph.campaign.id, created_by_user_id=graph.admin.id
    )
    v4_rule = create_v4_rule(
        db, campaign_id=graph.campaign.id, admin_id=graph.admin.id, rule_status="inactive"
    )
    zone = add_target_zone(
        db,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
        name="T",
        lat_min=6.4,
        lat_max=6.6,
    )
    revision = create_v4_revision(
        db, campaign_id=graph.campaign.id, rule_id=v4_rule.id, admin_id=graph.admin.id
    )
    vehicle2 = create_test_vehicle(
        db,
        driver_profile_id=graph.profile.id,
        plate_number=f"M4-{tag[:9].upper()}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment2 = create_test_campaign_assignment(
        db,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=vehicle2.id,
        assigned_by_user_id=graph.admin.id,
        assignment_status=CampaignAssignmentStatus.ACCEPTED,
    )
    insert_v4_binding(
        db, settings, assignment_id=assignment2.id, revision=revision, zone_ids=[zone.id]
    )
    offset = timedelta(hours=1)
    graph.v4_trip = add_trip(
        db,
        settings,
        graph,
        started_at=TRIP_START + (offset if hourly_first else -offset),
        assignment=assignment2,
        vehicle=vehicle2,
    )
    graph.terms = dict(DEFAULT_TERMS)
    return graph


@pytest.mark.parametrize("hourly_first", [True, False])
def test_same_day_hourly_and_daily_rate_pay_is_refused_both_ways(
    postgis_db_sessionmaker, settings, hourly_first
) -> None:
    db = postgis_db_sessionmaker
    graph = build_mixed_day(db, settings, f"v4-mix-{int(hourly_first)}", hourly_first=hourly_first)
    first, second = (graph.trip, graph.v4_trip) if hourly_first else (graph.v4_trip, graph.trip)
    drive(db, settings, first)
    add_pings(
        db, trip_id=second.id, points=moving_points(second.started_at), idempotency_key="second"
    )
    with pytest.raises(AppError) as exc_info:
        run_pipeline(db, second.id, settings)
    assert exc_info.value.code == "PAYOUT_DAY_MIXED_FORMULA"
    assert [c.trip_session_id for c in fetch_payout_calculations(db)] == [first.id]


def test_recompute_refuses_a_day_holding_both_formula_families(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    db = postgis_db_sessionmaker
    graph = build_mixed_day(db, settings, "v4-mix-recompute", hourly_first=True)

    async def allow(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(payouts, "refuse_mixed_formula_day", allow)  # test-only setup
    drive(db, settings, graph.trip)
    drive(db, settings, graph.v4_trip)
    assert {c.formula_version for c in fetch_payout_calculations(db)} == {PAYOUT_V2, PAYOUT_V4}
    monkeypatch.undo()
    with pytest.raises(AppError) as exc_info:
        run_recompute(db, settings, graph, lagos_date=date(2026, 7, 20))
    assert exc_info.value.code == "PAYOUT_DAY_MIXED_FORMULA"


# --- Recompute-day ------------------------------------------------------------


def project(db, settings, graph, day: date) -> dict:
    async def run():
        async with db() as session:
            projection = await project_campaign_day(
                session, campaign_id=graph.campaign.id, lagos_day=day, settings=settings
            )
            await session.rollback()
            return {
                trip["trip_session_id"]: Decimal(trip["delta_amount"])
                for trip in projection.projected_delta["trips"]
            }

    return asyncio.run(run())


def test_voided_earlier_trip_shifts_the_day_and_projection_equals_execution(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(
        db, settings, "v4-void", daily_rate_naira="4000.00", daily_target_miles="4.000"
    )
    trip2 = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=1))
    first = metres_along(drive(db, settings, graph.trip))
    second = metres_along(drive(db, settings, trip2))
    calcs = calculations_by_trip(db)
    assert calcs[trip2.id].final_payout == pay(graph, first + second) - pay(graph, first)

    async def void_first() -> int:
        async with db() as session:
            await session.execute(
                update(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.trip_session_id == graph.trip.id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
                .values(status=EarningsLedgerEntryStatus.VOIDED.value)
            )
            await session.commit()
        async with db() as session:
            return await day_credited_distance_m(
                session,
                driver_profile_id=graph.profile.id,
                campaign_id=graph.campaign.id,
                lagos_day=date(2026, 7, 20),
                exclude_trip_id=trip2.id,
            )

    # A voided trip credits nothing to later arrivals...
    assert asyncio.run(void_first()) == 0
    projected = project(db, settings, graph, date(2026, 7, 20))
    # ...but only a day correction trues up the trip already priced after it.
    expected_trip2 = pay(graph, second) - calcs[trip2.id].final_payout
    assert projected == {str(graph.trip.id): Decimal("0.00"), str(trip2.id): expected_trip2}
    outcome = run_recompute(db, settings, graph, lagos_date=date(2026, 7, 20))
    executed = {str(t.trip_session_id): t.delta_amount for t in outcome.trips}
    assert executed == projected
    trip2_total = sum(
        e.amount if e.entry_type != "reversal" else -e.amount
        for e in fetch_earnings_ledger_entries(db)
        if e.trip_session_id == trip2.id
    )
    assert trip2_total == pay(graph, second)
    # Unchanged inputs: a second run posts nothing.
    assert all(
        t.delta_amount == 0
        for t in run_recompute(db, settings, graph, lagos_date=date(2026, 7, 20)).trips
    )


def test_correcting_day_a_then_day_b_of_a_cross_midnight_trip(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    started = datetime(2026, 7, 20, 22, 30, tzinfo=UTC)
    graph = build_v4_graph(
        db, settings, "v4-ab", started_at=started, ended_at=started + timedelta(minutes=60)
    )
    points = drive(db, settings, graph.trip, minutes=60)
    day_a, day_b = date(2026, 7, 20), date(2026, 7, 21)

    def drop_pings(first_second: int, last_second: int) -> list:
        lost = [started + timedelta(seconds=s) for s in range(first_second, last_second + 1, 30)]

        async def run():
            async with db() as session:
                await session.execute(
                    delete(LocationPing).where(
                        LocationPing.trip_session_id == graph.trip.id,
                        LocationPing.recorded_at.in_(lost),
                    )
                )
                await session.commit()

        asyncio.run(run())
        return lost

    # A 180 s hole on day A (test-only evidence change): day A shrinks.
    lost = set(drop_pings(600, 750))
    remaining = [p for p in points if p[0] not in lost]
    new_a = metres_along([p for p in remaining if p[0] <= started + timedelta(minutes=30)])
    old = fetch_payout_calculations(db)[0]
    projected_a = project(db, settings, graph, day_a)
    outcome_a = run_recompute(db, settings, graph, lagos_date=day_a)
    assert {str(t.trip_session_id): t.delta_amount for t in outcome_a.trips} == projected_a
    assert projected_a[str(graph.trip.id)] == pay(graph, new_a) - Decimal(
        old.amount_by_day["2026-07-20"]
    )

    # Then a hole on day B: correcting B keeps A's corrected amount.
    lost |= set(drop_pings(2700, 2850))
    remaining = [p for p in points if p[0] not in lost]
    new_b = metres_along([p for p in remaining if p[0] >= started + timedelta(minutes=30)])
    outcome_b = run_recompute(db, settings, graph, lagos_date=day_b)
    assert outcome_b.trips[0].delta_amount == pay(graph, new_b) - Decimal(
        old.amount_by_day["2026-07-21"]
    )
    posted = sum(
        e.amount if e.entry_type != "reversal" else -e.amount
        for e in fetch_earnings_ledger_entries(db)
    )
    assert posted == pay(graph, new_a) + pay(graph, new_b)
    latest = max(
        (e for e in fetch_earnings_ledger_entries(db) if e.ledger_metadata.get("recompute_day")),
        key=lambda e: e.created_at,
    )
    assert latest.ledger_metadata["breakdown"]["distance_m_by_day"] == {
        "2026-07-20": new_a,
        "2026-07-21": new_b,
    }

    async def breakdown():
        async with db() as session:
            return await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )

    view = asyncio.run(breakdown())
    assert view.superseded_by_recompute is True
    assert view.daily_rate_days == [
        (day_a, new_a, pay(graph, new_a)),
        (day_b, new_b, pay(graph, new_b)),
    ]


# --- Liability ceilings -------------------------------------------------------


def test_daily_rate_liability_is_one_day_rate_per_covered_day(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_v4_graph(db, settings, "v4-liability")

    async def run():
        async with db() as session:
            assignment = await session.get(CampaignAssignment, graph.assignment.id)
            calculation = await _assignment_liability_calculation(session, assignment)
            campaign = await session.get(Campaign, graph.campaign.id)
            extension = await _additional_window_liability(
                session,
                campaign=campaign,
                proposed_start_at=None,
                proposed_end_at=campaign.end_at + timedelta(days=2),
                lock_bindings=False,
            )
            return calculation, extension

    calculation, extension = asyncio.run(run())
    assert calculation.rate == Decimal("8000.00") and calculation.cap == Decimal("1")
    assert calculation.requested == Decimal("8000.00") * calculation.covered_days
    assert extension == Decimal("16000.00")


# --- Offers, acceptance and publishing ------------------------------------------


def test_v4_offer_freezes_daily_terms_and_acceptance_binds_them_verbatim(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    graph = build_offered_graph(db, "v4-offer")
    rule = create_v4_rule(db, campaign_id=graph.campaign.id, admin_id=graph.admin.id)
    revision = create_v4_revision(
        db,
        campaign_id=graph.campaign.id,
        rule_id=rule.id,
        admin_id=graph.admin.id,
        shortfall_strategy="per_mile_deduction",
        deduction_per_mile_naira="140.00",
        outside_area_weight="0.5000",
    )
    materialize_offer(db, settings, graph)

    async def offered():
        async with db() as session:
            return (await session.get(CampaignAssignment, graph.assignment.id)).offer_terms

    terms_ = asyncio.run(offered())
    payout = terms_["payout"]
    assert payout["formula_version"] == PAYOUT_V4
    assert {k: payout[k] for k in DEFAULT_TERMS} == {
        "daily_rate_naira": "8000.00",
        "daily_target_miles": "8.000",
        "shortfall_strategy": "per_mile_deduction",
        "deduction_per_mile_naira": "140.00",
        "minimum_miles": "0.000",
        "outside_area_weight": "0.5000",
    }
    assert not any("hourly" in key or key == "daily_payable_hours_cap" for key in payout)
    assert terms_["eligibility"]["stationary_policy_marker"] == STATIONARY_POLICY_D39
    assert terms_["eligibility"]["stationary_window_seconds"] == 300
    assert terms_["eligibility"]["stationary_grace_seconds"] == 0

    accept_assignment(db, settings, user_id=graph.driver.id, assignment_id=graph.assignment.id)

    async def bound():
        async with db() as session:
            return await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == graph.assignment.id
                )
            )

    binding = asyncio.run(bound())
    assert binding.formula_version == PAYOUT_V4
    assert binding.revision_id == revision.id
    assert binding.stationary_policy_marker == STATIONARY_POLICY_D39
    assert binding.hourly_rate_naira is None and binding.daily_payable_hours_cap is None
    assert (
        binding.daily_rate_naira,
        binding.deduction_per_mile_naira,
        binding.outside_area_weight,
    ) == (
        Decimal("8000.00"),
        Decimal("140.00"),
        Decimal("0.5000"),
    )

    # A later revision (published with the switch on) and switching
    # publishing off again change nothing for the accepted assignment.
    enabled = settings.model_copy(update={"payout_v4_publishing_enabled": True})
    publish(db, enabled, graph.campaign.id, graph.admin.id, daily_rate_naira=Decimal("9800.00"))
    after = asyncio.run(bound())
    assert (after.id, after.daily_rate_naira, after.revision_id) == (
        binding.id,
        Decimal("8000.00"),
        revision.id,
    )


def v4_payload(**overrides) -> dict:
    values = {
        "effective_from": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "daily_rate_naira": "10000.00",
        "daily_target_miles": "70",
        "shortfall_strategy": "per_mile_deduction",
        "deduction_per_mile_naira": "140.00",
        "minimum_miles": "0",
        "outside_area_weight": "0.5",
        "reason": "synthetic publication",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


def publish(db, settings, campaign_id, admin_id, **overrides):
    payload = CampaignPayoutV4RevisionCreate(
        **v4_payload(**{k: None if v is None else str(v) for k, v in overrides.items()})
    )

    async def run():
        async with db() as session:
            result = await publish_payout_v4_revision(
                session,
                campaign_id=campaign_id,
                payload=payload,
                actor_user_id=admin_id,
                settings=settings,
            )
            await session.commit()
            return result

    return asyncio.run(run())


@pytest.fixture
def v4_client(settings, postgis_db_sessionmaker):
    def make(enabled: bool) -> TestClient:
        app = create_app(settings.model_copy(update={"payout_v4_publishing_enabled": enabled}))

        async def session_override():
            async with postgis_db_sessionmaker() as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        return TestClient(app)

    return make


def test_publishing_is_switched_off_by_default_validated_and_audited(
    postgis_db_sessionmaker, v4_client
) -> None:
    db = postgis_db_sessionmaker
    graph = build_offered_graph(db, "v4-publish")
    url = f"/api/v1/admin/campaigns/{graph.campaign.id}/payout-v4-revisions"

    with v4_client(False) as client:
        headers = auth_headers(client, graph.admin.email, PASSWORD)
        assert client.get("/api/v1/admin/payout-v4/status", headers=headers).json() == {
            "publishing_enabled": False
        }
        refused = client.post(url, headers=headers, json=v4_payload())
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "PAYOUT_V4_POLICY_UNAVAILABLE"

    async def counts():
        async with db() as session:
            rules = await session.scalar(
                select(func.count())
                .select_from(CampaignPayoutRule)
                .where(CampaignPayoutRule.campaign_id == graph.campaign.id)
            )
            revisions = await session.scalar(
                select(func.count())
                .select_from(CampaignPayoutRuleRevision)
                .where(CampaignPayoutRuleRevision.campaign_id == graph.campaign.id)
            )
            return rules, revisions

    assert asyncio.run(counts()) == (0, 0)

    with v4_client(True) as client:
        headers = auth_headers(client, graph.admin.email, PASSWORD)
        assert client.get("/api/v1/admin/payout-v4/status", headers=headers).json() == {
            "publishing_enabled": True
        }
        invalid = (
            {"deduction_per_mile_naira": None},  # per-mile needs a deduction
            {"shortfall_strategy": "proportional"},  # ...and proportional must not have one
            {"outside_area_weight": "1.5"},
            {"minimum_miles": "71"},
            {"daily_rate_naira": "0"},
            {"shortfall_strategy": "pro_rata"},
            {"reason": " "},
        )
        for override in invalid:
            response = client.post(url, headers=headers, json=v4_payload(**override))
            assert response.status_code == 422, override
        missing_minimum = v4_payload()
        missing_minimum.pop("minimum_miles")
        assert client.post(url, headers=headers, json=missing_minimum).status_code == 422
        with_params = {**v4_payload(), "eligibility_params": {"stationary_window_min": 9}}
        assert client.post(url, headers=headers, json=with_params).status_code == 422
        assert asyncio.run(counts()) == (0, 0)

        created = client.post(url, headers=headers, json=v4_payload())
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["formula_version"] == PAYOUT_V4
        assert body["hourly_rate_naira"] is None
        assert body["daily_rate_naira"] == "10000.00"
        assert body["deduction_per_mile_naira"] == "140.00"
        assert body["eligibility_params"] == D39_STOP_OVERLAY
        # Chain guard: a second revision must start strictly later.
        again = client.post(
            url, headers=headers, json=v4_payload(effective_from=body["effective_from"])
        )
        assert again.status_code == 400
        listing = client.get(
            f"/api/v1/admin/campaigns/{graph.campaign.id}/payout-rules/{body['payout_rule_id']}/revisions",
            headers=headers,
        )
        assert [item["daily_target_miles"] for item in listing.json()["items"]] == ["70.000"]

    assert asyncio.run(counts()) == (1, 1)
    events = {event.action: event for event in fetch_audit_events(db)}
    assert (
        events["admin.campaign_payout_rule.created"].event_metadata["formula_version"] == PAYOUT_V4
    )
    after = events["admin.payout_rule_revision.created"].event_metadata["after"]
    assert (
        after["daily_rate_naira"] == "10000.00"
        and after["shortfall_strategy"] == "per_mile_deduction"
    )
    assert events["admin.payout_rule_revision.created"].event_metadata["before"] is None


def test_hourly_and_daily_rate_chains_never_extend_each_other(
    postgis_db_sessionmaker, settings
) -> None:
    db = postgis_db_sessionmaker
    enabled = settings.model_copy(update={"payout_v4_publishing_enabled": True})
    hourly = build_offered_graph(db, "v4-hourly-chain")
    create_v2_rule(db, campaign_id=hourly.campaign.id, created_by_user_id=hourly.admin.id)
    with pytest.raises(AppError) as exc_info:
        publish(db, enabled, hourly.campaign.id, hourly.admin.id)
    assert exc_info.value.code == "INVALID_PAYOUT_RULE_REVISION"

    daily = build_offered_graph(db, "v4-daily-chain")
    revision, previous, rule = publish(db, enabled, daily.campaign.id, daily.admin.id)
    assert previous is None and rule.formula_version == PAYOUT_V4

    async def hourly_revision_on_v4_rule():
        async with db() as session:
            await create_payout_rule_revision(
                session,
                campaign_id=daily.campaign.id,
                rule_id=rule.id,
                payload=CampaignPayoutRuleRevisionCreate(
                    effective_from=datetime.now(UTC) + timedelta(days=2),
                    hourly_rate_naira=Decimal("1000.00"),
                    daily_payable_hours_cap=Decimal("8.00"),
                    reason="must be refused",
                ),
                actor_user_id=daily.admin.id,
            )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(hourly_revision_on_v4_rule())
    assert exc_info.value.code == "INVALID_PAYOUT_RULE_REVISION"

    second, previous, created_rule = publish(
        db,
        enabled,
        daily.campaign.id,
        daily.admin.id,
        effective_from=(datetime.now(UTC) + timedelta(days=3)).isoformat(),
        shortfall_strategy="proportional",
        deduction_per_mile_naira=None,
    )
    assert (second.revision_number, previous.id, created_rule) == (2, revision.id, None)
    assert second.deduction_per_mile_naira is None


def test_daily_rate_rule_values_cannot_be_patched(postgis_db_sessionmaker, settings) -> None:
    db = postgis_db_sessionmaker
    enabled = settings.model_copy(update={"payout_v4_publishing_enabled": True})
    graph = build_offered_graph(db, "v4-patch")
    _, _, rule = publish(db, enabled, graph.campaign.id, graph.admin.id)

    async def patch(**fields):
        async with db() as session:
            return await payouts.update_campaign_payout_rule(
                session,
                campaign_id=graph.campaign.id,
                rule_id=rule.id,
                updated_by_user_id=graph.admin.id,
                payload=CampaignPayoutRuleUpdate(**fields),
            )

    for fields in (
        {"hourly_rate_naira": Decimal("1")},
        {"base_rate_per_km": Decimal("1")},
        {"currency": "USD"},
    ):
        with pytest.raises(AppError) as exc_info:
            asyncio.run(patch(**fields))
        assert exc_info.value.code == "INVALID_PAYOUT_RULE"
    updated, changed = asyncio.run(patch(status="inactive"))
    assert updated.status == "inactive" and changed == ["status"]


def test_publishing_defaults_off_and_configuration_holds_no_pay_value(settings) -> None:
    assert settings.payout_v4_publishing_enabled is False
    assert not any(
        word in name
        for name in type(settings).model_fields
        for word in ("daily_rate", "target_miles", "shortfall", "per_mile", "minimum_miles")
    )


def test_pings_recorded_before_the_trip_start_add_no_distance() -> None:
    # The app may upload pings buffered up to 15 minutes before Start: the
    # driving they record is not part of the trip.
    pre = [ping(t, BASE_LAT + (t // 30) * 0.00081) for t in range(-600, 0, 30)]
    trip = [ping(t, BASE_LAT + (t // 30) * 0.00081) for t in range(0, 601, 30)]
    in_trip_only = credited_distance_m_by_day(
        pings=trip, breakdown=classify(trip), outside_area_weight=Decimal("1")
    )
    started = classify_session(
        session_started_at=T0,
        session_ended_at=T0 + timedelta(seconds=600),
        pings=pre + trip,
        window_start_at=None,
        window_end_at=None,
        params=D39_PARAMS,
        stationary_policy_marker=STATIONARY_POLICY_D39,
    )
    with_buffered = credited_distance_m_by_day(
        pings=pre + trip, breakdown=started, outside_area_weight=Decimal("1")
    )
    assert with_buffered == in_trip_only

    # An interval that straddles the start credits only its in-trip share.
    straddle = [ping(-30, BASE_LAT), ping(30, BASE_LAT + 0.00162), ping(60, BASE_LAT + 0.00243)]
    breakdown = classify_session(
        session_started_at=T0,
        session_ended_at=T0 + timedelta(seconds=60),
        pings=straddle,
        window_start_at=None,
        window_end_at=None,
        params=D39_PARAMS,
        stationary_policy_marker=STATIONARY_POLICY_D39,
    )
    first_half = Fraction(haversine(BASE_LAT, BASE_LON, BASE_LAT + 0.00162, BASE_LON)) / 2
    last = Fraction(haversine(BASE_LAT + 0.00162, BASE_LON, BASE_LAT + 0.00243, BASE_LON))
    assert credited_distance_m_by_day(
        pings=straddle, breakdown=breakdown, outside_area_weight=Decimal("1")
    ) == {"2026-07-20": math.floor(first_half + last)}


def test_fractional_ping_timestamps_credit_their_full_distance() -> None:
    # Real phones stamp milliseconds: floored offsets must not shrink an
    # in-trip interval's distance (0.1 s -> 1.9 s floors to a 1 s span).
    pings = [
        ping(0.1, BASE_LAT),
        ping(1.9, BASE_LAT + 0.00005),
        ping(7.4, BASE_LAT + 0.0002),
        ping(12.95, BASE_LAT + 0.00035),
    ]
    breakdown = classify_session(
        session_started_at=T0,
        session_ended_at=T0 + timedelta(seconds=13),
        pings=pings,
        window_start_at=None,
        window_end_at=None,
        params=D39_PARAMS,
        stationary_policy_marker=STATIONARY_POLICY_D39,
    )
    points = [(p.recorded_at, p.latitude, p.longitude) for p in pings]
    assert credited_distance_m_by_day(
        pings=pings, breakdown=breakdown, outside_area_weight=Decimal("1")
    ) == {"2026-07-20": metres_along(points)}


def test_zero_delta_correction_still_records_the_new_distance_for_later_trips(
    postgis_db_sessionmaker, settings
) -> None:
    from test_payout_corrections import approve, create_order, execute, second_admin, submit

    db = postgis_db_sessionmaker
    # Synthetic minimum above one trip: the first trip is paid ₦0 before and
    # after its correction, so the correction moves no money.
    graph = build_v4_graph(
        db,
        settings,
        "v4-zero-delta",
        daily_rate_naira="3000.00",
        daily_target_miles="6.000",
        minimum_miles="5.000",
    )
    first = drive(db, settings, graph.trip)
    assert fetch_payout_calculations(db)[0].final_payout == Decimal("0.00")

    async def drop_hole() -> list[datetime]:
        lost = [TRIP_START + timedelta(seconds=s) for s in range(600, 751, 30)]
        async with db() as session:
            await session.execute(
                delete(LocationPing).where(
                    LocationPing.trip_session_id == graph.trip.id,
                    LocationPing.recorded_at.in_(lost),
                )
            )
            await session.commit()
        return lost

    lost = set(asyncio.run(drop_hole()))
    corrected = metres_along([p for p in first if p[0] not in lost])
    assert corrected < metres_along(first)
    order = create_order(db, settings, graph)
    submit(db, order.id, graph.admin.id)
    approver = second_admin(db, "v4-zero-delta")
    approve(db, settings, order.id, approver.id)
    executed = execute(db, settings, order.id, approver.id)
    executed_order = executed[0] if isinstance(executed, tuple) else executed
    recorded = executed_order.execution_result["drivers"][0]["trips"][0]
    assert recorded["delta_amount"] == "0.00"
    assert recorded["distance_m_by_day"] == {"2026-07-20": corrected}

    later = add_trip(db, settings, graph, started_at=TRIP_START + timedelta(hours=1))
    added = metres_along(drive(db, settings, later))
    calc = calculations_by_trip(db)[later.id]
    assert calc.payout_metadata["distance"]["prior_distance_m_by_day"] == {"2026-07-20": corrected}
    assert calc.final_payout == pay(graph, corrected + added) - pay(graph, corrected)


def test_incomplete_or_malformed_daily_rate_data_fails_closed() -> None:
    from app.services.campaign_assignments import _daily_rate_offer_terms
    from app.services.payouts import _daily_rate_days, daily_rate_terms

    complete = {
        "daily_rate_naira": Decimal("10000.00"),
        "daily_target_miles": Decimal("70"),
        "shortfall_strategy": "per_mile_deduction",
        "deduction_per_mile_naira": Decimal("140.00"),
        "minimum_miles": Decimal("0"),
        "outside_area_weight": Decimal("1"),
    }
    assert daily_rate_terms(SimpleNamespace(**complete)).daily_target_miles == Decimal("70")
    for broken in (
        {"daily_rate_naira": None},
        {"shortfall_strategy": "pro_rata"},
        {"deduction_per_mile_naira": None},
        {"shortfall_strategy": "proportional"},
    ):
        with pytest.raises(AppError) as exc_info:
            daily_rate_terms(SimpleNamespace(**{**complete, **broken}))
        assert exc_info.value.code == "PAYOUT_BINDING_INCOMPLETE"

    assert _daily_rate_days({"2026-07-20": 100}, {"2026-07-20": "1.00"}) == [
        (date(2026, 7, 20), 100, Decimal("1.00"))
    ]
    assert _daily_rate_days(None, {}) is None
    assert _daily_rate_days({"2026-07-20": -1}, {}) is None
    assert _daily_rate_days({"not-a-day": 1}, {}) is None

    offer = {key: str(value) for key, value in complete.items()}
    assert _daily_rate_offer_terms(offer) is not None
    for broken in (
        {"daily_rate_naira": "x"},
        {"hourly_rate_naira": "1000"},
        {"daily_rate_naira": "0"},
        {"minimum_miles": "71"},
        {"outside_area_weight": "1.5"},
        {"daily_target_miles": "NaN"},
        {"deduction_per_mile_naira": None},
        {"shortfall_strategy": "proportional"},
    ):
        assert _daily_rate_offer_terms({**offer, **broken}) is None, broken


def test_payout_status_maps_insufficient_blocked_and_excluded() -> None:
    from app.services.payouts import _payout_status

    def status(analytics: str, estimate: str) -> str:
        return _payout_status(SimpleNamespace(status=analytics), SimpleNamespace(status=estimate))

    assert status("computed", "estimated") == "calculated"
    assert status("insufficient_data", "estimated") == "insufficient_data"
    assert status("computed", "insufficient_data") == "insufficient_data"
    assert status("blocked", "estimated") == "blocked"
    assert status("computed", "excluded") == "blocked"
