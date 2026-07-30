import random
from datetime import UTC, datetime, timedelta

from app.services.payout_eligibility import (
    EligibilityParams,
    EligibilityPing,
    classify_session,
    haversine_m,
)

PARAMS = EligibilityParams(
    stationary_radius_m=200.0,
    stationary_window_seconds=300,
    stationary_grace_seconds=240,
    max_accuracy_m=75.0,
    teleport_kmh=180.0,
    max_ping_gap_seconds=120,
)
START = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
BASE_LAT = 6.45
BASE_LON = 3.40
# ~90 m of northward latitude per 30 s step (~3 m/s, ~11 km/h): clearly
# moving for the 200 m / 5 min stay-point rule, nowhere near the teleport bar.
LAT_STEP_30M = 0.00081


def ping(
    seconds: int,
    *,
    lat: float | None = None,
    lon: float | None = None,
    accuracy: float | None = 10.0,
    in_area: bool = True,
) -> EligibilityPing:
    return EligibilityPing(
        recorded_at=START + timedelta(seconds=seconds),
        latitude=BASE_LAT if lat is None else lat,
        longitude=BASE_LON if lon is None else lon,
        accuracy_m=accuracy,
        in_area=in_area,
    )


def moving_pings(
    start_second: int,
    end_second: int,
    *,
    step: int = 30,
    in_area: bool = True,
    accuracy: float | None = 10.0,
) -> list[EligibilityPing]:
    return [
        ping(
            second,
            lat=BASE_LAT + (second // step) * LAT_STEP_30M,
            accuracy=accuracy,
            in_area=in_area,
        )
        for second in range(start_second, end_second + 1, step)
    ]


def classify(pings, *, duration=1800, window=(None, None), params=PARAMS):
    return classify_session(
        session_started_at=START,
        session_ended_at=START + timedelta(seconds=duration),
        pings=pings,
        window_start_at=window[0],
        window_end_at=window[1],
        params=params,
    )


def assert_invariant(breakdown, duration) -> None:
    assert breakdown.eligible_seconds >= 0
    assert all(seconds > 0 for seconds in breakdown.excluded_seconds_by_reason.values())
    assert breakdown.total_seconds == duration


def test_fully_moving_trip_is_eligible_between_first_and_last_ping() -> None:
    breakdown = classify(moving_pings(0, 1800), duration=1800)
    assert breakdown.eligible_seconds == 1800
    assert breakdown.excluded_seconds_by_reason == {}
    assert_invariant(breakdown, 1800)


def test_no_pings_is_all_gps_gap() -> None:
    breakdown = classify([], duration=1800)
    assert breakdown.excluded_seconds_by_reason == {"gps_gap": 1800}
    assert_invariant(breakdown, 1800)


def test_single_ping_is_all_gps_gap() -> None:
    breakdown = classify([ping(900)], duration=1800)
    assert breakdown.eligible_seconds == 0
    assert breakdown.excluded_seconds_by_reason == {"gps_gap": 1800}
    assert_invariant(breakdown, 1800)


def test_session_edges_before_first_and_after_last_ping_are_gps_gap() -> None:
    breakdown = classify(moving_pings(300, 1500), duration=1800)
    assert breakdown.excluded_seconds_by_reason["gps_gap"] == 600
    assert breakdown.eligible_seconds == 1200
    assert_invariant(breakdown, 1800)


def test_mid_session_gap_over_threshold_earns_nothing() -> None:
    pings = moving_pings(0, 600) + moving_pings(900, 1800)
    breakdown = classify(pings, duration=1800)
    assert breakdown.excluded_seconds_by_reason["gps_gap"] == 300
    assert breakdown.eligible_seconds == 1500
    assert_invariant(breakdown, 1800)


def test_low_accuracy_endpoint_excludes_the_interval() -> None:
    pings = moving_pings(0, 1800)
    bad = pings[10]
    pings[10] = EligibilityPing(bad.recorded_at, bad.latitude, bad.longitude, 90.0, True)
    breakdown = classify(pings, duration=1800)
    # Both adjacent intervals touch the bad ping.
    assert breakdown.excluded_seconds_by_reason["low_accuracy"] == 60
    assert breakdown.eligible_seconds == 1740
    assert_invariant(breakdown, 1800)


def test_null_accuracy_fails_the_accuracy_gate() -> None:
    pings = moving_pings(0, 1800, accuracy=None)
    breakdown = classify(pings, duration=1800)
    assert breakdown.eligible_seconds == 0
    assert breakdown.excluded_seconds_by_reason == {"low_accuracy": 1800}
    assert_invariant(breakdown, 1800)


def test_teleport_sandwich_excludes_only_the_impossible_intervals() -> None:
    pings = moving_pings(0, 1800)
    # Jump ~5.5 km away and back within one 30 s interval each: ~660 km/h.
    jumped = pings[20]
    pings[20] = EligibilityPing(
        jumped.recorded_at, jumped.latitude + 0.05, jumped.longitude, 10.0, True
    )
    breakdown = classify(pings, duration=1800)
    assert breakdown.excluded_seconds_by_reason["teleport"] == 60
    assert breakdown.teleport_incident_count == 2
    assert breakdown.eligible_seconds == 1740
    assert_invariant(breakdown, 1800)


def test_zero_duration_interval_contributes_nothing_but_counts_incident() -> None:
    pings = moving_pings(0, 600)
    duplicate_time = pings[5]
    pings.insert(
        6,
        EligibilityPing(
            duplicate_time.recorded_at,
            duplicate_time.latitude + 0.05,
            duplicate_time.longitude,
            10.0,
            True,
        ),
    )
    breakdown = classify(pings, duration=600)
    assert breakdown.teleport_incident_count >= 1
    assert_invariant(breakdown, 600)


def test_geofence_requires_both_endpoints_inside() -> None:
    pings = moving_pings(0, 900) + moving_pings(930, 1800, in_area=False)
    breakdown = classify(pings, duration=1800)
    # The transition interval (inside -> outside) is excluded too.
    assert breakdown.excluded_seconds_by_reason["out_of_area"] == 900
    assert breakdown.eligible_seconds == 900
    assert_invariant(breakdown, 1800)


def test_window_clips_exactly_at_the_boundary() -> None:
    window_end = START + timedelta(seconds=1234)
    breakdown = classify(
        moving_pings(0, 1800),
        duration=1800,
        window=(None, window_end),
    )
    assert breakdown.eligible_seconds == 1234
    assert breakdown.excluded_seconds_by_reason["out_of_window"] == 566
    assert_invariant(breakdown, 1800)


def test_window_starting_mid_session_excludes_the_head() -> None:
    window_start = START + timedelta(seconds=600)
    breakdown = classify(
        moving_pings(0, 1800),
        duration=1800,
        window=(window_start, None),
    )
    assert breakdown.excluded_seconds_by_reason["out_of_window"] == 600
    assert breakdown.eligible_seconds == 1200
    assert_invariant(breakdown, 1800)


def test_stationary_stretch_pays_only_the_grace_period() -> None:
    pings = [ping(second) for second in range(0, 1801, 30)]
    breakdown = classify(pings, duration=1800)
    assert breakdown.eligible_seconds == PARAMS.stationary_grace_seconds
    assert breakdown.excluded_seconds_by_reason == {
        "stationary": 1800 - PARAMS.stationary_grace_seconds
    }
    assert_invariant(breakdown, 1800)


def test_short_stop_under_the_window_stays_eligible() -> None:
    # 2.5 minutes parked (stretch stays under the 5-minute stay-point window
    # once movement resumes) in the middle of a moving trip.
    parked_lat = BASE_LAT + (600 // 30) * LAT_STEP_30M
    pings = (
        moving_pings(0, 600)
        + [
            EligibilityPing(
                START + timedelta(seconds=second), parked_lat, BASE_LON, 10.0, True
            )
            for second in range(630, 751, 30)
        ]
        + [
            ping(
                second,
                lat=parked_lat + ((second - 750) // 30) * LAT_STEP_30M,
            )
            for second in range(780, 1801, 30)
        ]
    )
    breakdown = classify(pings, duration=1800)
    assert "stationary" not in breakdown.excluded_seconds_by_reason
    assert breakdown.eligible_seconds == 1800
    assert_invariant(breakdown, 1800)


def test_stationary_grace_crossing_window_boundary_prefers_window_reason() -> None:
    # Parked the whole session; the campaign window ends mid-grace.
    window_end = START + timedelta(seconds=120)
    pings = [ping(second) for second in range(0, 1801, 30)]
    breakdown = classify(pings, duration=1800, window=(None, window_end))
    assert breakdown.eligible_seconds == 120  # grace, clipped by the window
    assert breakdown.excluded_seconds_by_reason["out_of_window"] == 1680
    assert_invariant(breakdown, 1800)


def test_out_of_area_interlude_does_not_reset_the_stationary_grace() -> None:
    # Parked throughout, but a mid-stretch slice is flagged out_of_area:
    # the stay-point mask runs over the full series, so no second grace.
    pings = []
    for second in range(0, 1801, 30):
        in_area = not (600 <= second <= 720)
        pings.append(ping(second, in_area=in_area))
    breakdown = classify(pings, duration=1800)
    assert breakdown.eligible_seconds == PARAMS.stationary_grace_seconds
    assert (
        breakdown.excluded_seconds_by_reason["stationary"]
        + breakdown.excluded_seconds_by_reason["out_of_area"]
        == 1800 - PARAMS.stationary_grace_seconds
    )
    assert_invariant(breakdown, 1800)


def test_haversine_is_sane() -> None:
    assert haversine_m(BASE_LAT, BASE_LON, BASE_LAT, BASE_LON) == 0.0
    one_step = haversine_m(BASE_LAT, BASE_LON, BASE_LAT + LAT_STEP_30M, BASE_LON)
    assert 80.0 < one_step < 100.0


def test_property_every_random_session_partitions_exactly() -> None:
    rng = random.Random("payout-v2-property")
    for _ in range(200):
        duration = rng.randrange(0, 7200)
        count = rng.randrange(0, 60)
        pings = []
        for _ in range(count):
            second = rng.randrange(-120, duration + 120)
            pings.append(
                EligibilityPing(
                    recorded_at=START + timedelta(seconds=second, milliseconds=rng.randrange(1000)),
                    latitude=BASE_LAT + rng.uniform(-0.05, 0.05),
                    longitude=BASE_LON + rng.uniform(-0.05, 0.05),
                    accuracy_m=rng.choice([None, 5.0, 50.0, 80.0, 200.0]),
                    in_area=rng.random() < 0.8,
                )
            )
        breakdown = classify_session(
            session_started_at=START,
            session_ended_at=START + timedelta(seconds=duration),
            pings=pings,
            window_start_at=(
                START + timedelta(seconds=rng.randrange(0, max(duration, 1)))
                if duration and rng.random() < 0.5
                else None
            ),
            window_end_at=(
                START + timedelta(seconds=rng.randrange(0, max(duration, 1)))
                if duration and rng.random() < 0.5
                else None
            ),
            params=PARAMS,
        )
        assert breakdown.eligible_seconds >= 0
        assert all(
            seconds > 0 for seconds in breakdown.excluded_seconds_by_reason.values()
        )
        assert breakdown.total_seconds == duration
