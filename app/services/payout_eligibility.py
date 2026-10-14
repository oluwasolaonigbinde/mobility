"""Deterministic payable-time classification for daily-rate payouts (D39).

Pure functions over an ended trip's ordered pings: the session is segmented
into contiguous intervals between consecutive pings, every interval gets
exactly one reason code, and payable time is the sum of intervals passing all
predicates. Geofence membership is precomputed by the caller (one PostGIS
query) so this module never touches the database.

Invariant (property-tested): eligible_seconds + sum of every excluded reason
== the session duration in whole seconds, always.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo

# The payable day is the Africa/Lagos calendar day (D4 cap, D9c). Frozen
# product rule, not configuration.
LAGOS_TZ = ZoneInfo("Africa/Lagos")

REASON_MOVING = "moving"
REASON_STATIONARY = "stationary"
REASON_GPS_GAP = "gps_gap"
REASON_OUT_OF_AREA = "out_of_area"
REASON_OUT_OF_WINDOW = "out_of_window"
REASON_TELEPORT = "teleport"
REASON_LOW_ACCURACY = "low_accuracy"

EXCLUSION_REASONS = (
    REASON_GPS_GAP,
    REASON_LOW_ACCURACY,
    REASON_TELEPORT,
    REASON_OUT_OF_WINDOW,
    REASON_OUT_OF_AREA,
    REASON_STATIONARY,
)

# D39(b) stop rule, payout_v4 only: movement continues through each stop of up
# to 5 minutes; a continuous stay LONGER than the frozen window adds nothing.
# No rolling detector and no whole-trip grace. The server fixes this overlay on
# every v4 revision; admins cannot change it.
STATIONARY_POLICY_D39 = "d39-stop-5min-v1"
D39_STOP_OVERLAY = {"stationary_window_min": 5, "stationary_grace_min": 0}
METRES_PER_MILE = Decimal("1609.344")

EARTH_RADIUS_M = 6371000.0


@dataclass(frozen=True)
class EligibilityParams:
    stationary_radius_m: float
    stationary_window_seconds: int
    stationary_grace_seconds: int
    max_accuracy_m: float
    teleport_kmh: float
    max_ping_gap_seconds: int

    def as_metadata(self) -> dict[str, float | int]:
        return {
            "stationary_radius_m": self.stationary_radius_m,
            "stationary_window_seconds": self.stationary_window_seconds,
            "stationary_grace_seconds": self.stationary_grace_seconds,
            "max_accuracy_m": self.max_accuracy_m,
            "teleport_kmh": self.teleport_kmh,
            "max_ping_gap_seconds": self.max_ping_gap_seconds,
        }


@dataclass(frozen=True)
class EligibilityPing:
    recorded_at: datetime
    latitude: float
    longitude: float
    accuracy_m: float | None
    in_area: bool
    # Membership of the binding's frozen target zones, for outside-area weighting.
    in_premium: bool = False


@dataclass(frozen=True)
class EligibleSlice:
    """One eligible elementary slice, in chronological order (MNY-06B).

    Slices are already cut at every ping offset, Lagos midnight, window edge,
    and stay-region boundary, so premium membership — like in_area — is
    constant within a slice: premium iff both governing pings are inside a
    frozen target zone, used for the daily-rate outside-area distance weight.
    """

    start_offset: int
    end_offset: int
    day: str
    premium: bool
    # The ping interval the slice belongs to and that interval's whole-second
    # length (payout_v4 prorates the interval's distance by eligible time).
    interval_index: int = -1
    interval_length: int = 0
    # The interval's real start (seconds from the trip start; negative when a
    # ping was recorded before Start) and duration. Distance driven before
    # the start must not be credited.
    interval_start_seconds: float = 0.0
    interval_seconds: float = 0.0

    @property
    def length(self) -> int:
        return self.end_offset - self.start_offset


@dataclass(frozen=True)
class EligibilityBreakdown:
    eligible_seconds: int
    excluded_seconds_by_reason: dict[str, int]
    teleport_incident_count: int
    # Eligible seconds split by Africa/Lagos calendar day (ISO date -> seconds).
    # A trip that crosses midnight contributes to two days; the cap is applied
    # per day against its own allowance (RM1, D4/D14). Sums to eligible_seconds.
    eligible_seconds_by_day: dict[str, int]
    # Chronological eligible slices with day and target membership. Slice
    # lengths always sum to eligible_seconds.
    eligible_slices: tuple[EligibleSlice, ...] = ()
    stationary_detector_evidence: dict = field(default_factory=dict)
    # Ping intervals shorter than one whole second (both pings floor to the
    # same offset) have no slice; those that would be eligible at that instant
    # are listed as (interval_index, day, premium) so v4 can credit their
    # distance. Time-based engines ignore them (they carry no seconds).
    eligible_instant_intervals: tuple[tuple[int, str, bool], ...] = ()

    @property
    def total_seconds(self) -> int:
        return self.eligible_seconds + sum(self.excluded_seconds_by_reason.values())


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _ping_seconds(start: datetime, ping: EligibilityPing) -> float:
    return (_utc(ping.recorded_at) - start).total_seconds()


def _stay_point_regions(
    pings: list[EligibilityPing],
    offsets: list[int],
    raw_seconds: list[float],
    params: EligibilityParams,
) -> list[tuple[int, int]]:
    """D39: only continuous stops strictly longer than the window are excluded."""
    regions: list[tuple[int, int]] = []
    count = len(pings)
    anchor = 0
    while anchor < count - 1:
        last_inside = anchor
        for j in range(anchor + 1, count):
            if raw_seconds[j] - raw_seconds[j - 1] > params.max_ping_gap_seconds:
                break
            if (
                haversine_m(
                    pings[anchor].latitude,
                    pings[anchor].longitude,
                    pings[j].latitude,
                    pings[j].longitude,
                )
                >= params.stationary_radius_m
            ):
                break
            last_inside = j
        duration = raw_seconds[last_inside] - raw_seconds[anchor]
        confirmed = duration > params.stationary_window_seconds
        if last_inside > anchor and confirmed:
            span_start = offsets[anchor]
            span_end = offsets[last_inside]
            if span_start < span_end:
                regions.append((span_start, span_end))
            anchor = last_inside + 1
        else:
            anchor += 1
    return regions


def _accuracy_fails(ping: EligibilityPing, params: EligibilityParams) -> bool:
    return ping.accuracy_m is None or ping.accuracy_m > params.max_accuracy_m


def _signal_reason(
    first: EligibilityPing,
    second: EligibilityPing,
    delta: float,
    params: EligibilityParams,
) -> str | None:
    if delta > params.max_ping_gap_seconds:
        return REASON_GPS_GAP
    if _accuracy_fails(first, params) or _accuracy_fails(second, params):
        return REASON_LOW_ACCURACY
    distance = haversine_m(first.latitude, first.longitude, second.latitude, second.longitude)
    speed_kmh = (distance / delta) * 3.6 if delta > 0 else math.inf
    if distance > 1.0 and speed_kmh > params.teleport_kmh:
        return REASON_TELEPORT
    return None


def lagos_day_at(start: datetime, offset_seconds: int) -> str:
    """ISO Africa/Lagos calendar date of an offset into the session."""
    return (_utc(start) + timedelta(seconds=offset_seconds)).astimezone(LAGOS_TZ).date().isoformat()


def _lagos_midnight_offsets(start: datetime, duration: int) -> list[int]:
    """Offsets of every Africa/Lagos midnight strictly inside the session.

    These become slice boundaries so no interval spans two payable days
    (RM1): the D4 cap is per calendar day, so a cross-midnight trip must
    charge each day's allowance separately.
    """
    offsets: list[int] = []
    day: date = _utc(start).astimezone(LAGOS_TZ).date()
    while True:
        day = day + timedelta(days=1)
        boundary = datetime.combine(day, time.min, tzinfo=LAGOS_TZ).astimezone(UTC)
        offset = math.floor((boundary - _utc(start)).total_seconds())
        if offset >= duration:
            return offsets
        if offset > 0:
            offsets.append(offset)


def classify_session(
    *,
    session_started_at: datetime,
    session_ended_at: datetime,
    pings: list[EligibilityPing],
    window_start_at: datetime | None,
    window_end_at: datetime | None,
    params: EligibilityParams,
    stationary_policy_marker: str = STATIONARY_POLICY_D39,
) -> EligibilityBreakdown:
    if stationary_policy_marker != STATIONARY_POLICY_D39:
        raise ValueError("Only the frozen daily-rate stop policy is supported")
    start = _utc(session_started_at)
    end = _utc(session_ended_at)
    duration = max(0, math.floor((end - start).total_seconds()))

    def off(seconds: float) -> int:
        return min(max(0, math.floor(seconds)), duration)

    excluded: dict[str, int] = dict.fromkeys(EXCLUSION_REASONS, 0)
    teleport_incidents = 0

    ordered = sorted(pings, key=lambda ping: _utc(ping.recorded_at))
    raw_seconds = [_ping_seconds(start, ping) for ping in ordered]
    offsets = [off(seconds) for seconds in raw_seconds]

    if duration == 0:
        return EligibilityBreakdown(
            eligible_seconds=0,
            excluded_seconds_by_reason={},
            teleport_incident_count=0,
            eligible_seconds_by_day={},
        )

    if not ordered:
        return EligibilityBreakdown(
            eligible_seconds=0,
            excluded_seconds_by_reason={REASON_GPS_GAP: duration},
            teleport_incident_count=0,
            eligible_seconds_by_day={},
        )

    window_from = off((_utc(window_start_at) - start).total_seconds()) if window_start_at else 0
    window_to = off((_utc(window_end_at) - start).total_seconds()) if window_end_at else duration

    stay_regions = _stay_point_regions(ordered, offsets, raw_seconds, params)
    stationary_regions = [(start, end, REASON_STATIONARY) for start, end in stay_regions]

    # Per ping-interval base reason (highest-precedence signal rules only).
    interval_reason: list[str | None] = []
    for index in range(len(ordered) - 1):
        first = ordered[index]
        second = ordered[index + 1]
        delta = raw_seconds[index + 1] - raw_seconds[index]
        signal_reason = _signal_reason(first, second, delta, params)
        is_teleport = signal_reason == REASON_TELEPORT
        if is_teleport:
            teleport_incidents += 1
        if signal_reason is not None:
            interval_reason.append(signal_reason)
        elif not (first.in_area and second.in_area):
            interval_reason.append(REASON_OUT_OF_AREA)
        else:
            interval_reason.append(None)  # moving/stationary decided per slice

    # Elementary slice boundaries: session edges, ping offsets, window edges,
    # and stationary-region/grace boundaries — classification is constant.
    cuts = {0, duration, window_from, window_to}
    cuts.update(offsets)
    cuts.update(_lagos_midnight_offsets(start, duration))
    for region_start, region_end, _reason in stationary_regions:
        cuts.add(min(max(0, region_start), duration))
        cuts.add(min(max(0, region_end), duration))
    boundaries = sorted(cuts)

    def interval_index_for(slice_start: int) -> int | None:
        if not ordered or slice_start < offsets[0] or slice_start >= offsets[-1]:
            return None
        low, high = 0, len(offsets) - 2
        while low <= high:
            mid = (low + high) // 2
            if offsets[mid] <= slice_start < offsets[mid + 1]:
                return mid
            if slice_start < offsets[mid]:
                high = mid - 1
            else:
                low = mid + 1
        return None

    def stationary_reason_at(point: int) -> str | None:
        return next(
            (
                reason
                for region_start, region_end, reason in stationary_regions
                if region_start <= point < region_end
            ),
            None,
        )

    eligible_instants: list[tuple[int, str, bool]] = []
    for index in range(len(ordered) - 1):
        point = offsets[index]
        if (
            offsets[index + 1] == point
            and raw_seconds[index] >= 0
            and interval_reason[index] is None
            and window_from <= point < window_to
            and point < duration
            and stationary_reason_at(point) is None
        ):
            eligible_instants.append(
                (
                    index,
                    lagos_day_at(start, point),
                    ordered[index].in_premium and ordered[index + 1].in_premium,
                )
            )

    eligible = 0
    eligible_by_day: dict[str, int] = {}
    eligible_slices: list[EligibleSlice] = []
    for slice_start, slice_end in zip(boundaries, boundaries[1:], strict=False):
        length = slice_end - slice_start
        if length <= 0:
            continue
        index = interval_index_for(slice_start)
        if index is None:
            excluded[REASON_GPS_GAP] += length
            continue
        base = interval_reason[index]
        if base == REASON_GPS_GAP:
            excluded[REASON_GPS_GAP] += length
            continue
        if base == REASON_LOW_ACCURACY:
            excluded[REASON_LOW_ACCURACY] += length
            continue
        if base == REASON_TELEPORT:
            excluded[REASON_TELEPORT] += length
            continue
        if slice_start < window_from or slice_start >= window_to:
            excluded[REASON_OUT_OF_WINDOW] += length
            continue
        if base == REASON_OUT_OF_AREA:
            excluded[REASON_OUT_OF_AREA] += length
            continue
        stationary_reason = stationary_reason_at(slice_start)
        if stationary_reason is not None:
            excluded[stationary_reason] += length
            continue
        eligible += length
        # Slices never span a Lagos midnight (boundary is a cut), so the
        # slice start's day owns the whole slice.
        day_key = lagos_day_at(start, slice_start)
        eligible_by_day[day_key] = eligible_by_day.get(day_key, 0) + length
        # Tier resolution (MNY-06B): like in_area, premium requires both
        # governing pings inside the frozen premium area.
        eligible_slices.append(
            EligibleSlice(
                start_offset=slice_start,
                end_offset=slice_end,
                day=day_key,
                premium=ordered[index].in_premium and ordered[index + 1].in_premium,
                interval_index=index,
                interval_length=offsets[index + 1] - offsets[index],
                interval_start_seconds=raw_seconds[index],
                interval_seconds=raw_seconds[index + 1] - raw_seconds[index],
            )
        )

    detector_evidence = {
        "version": stationary_policy_marker,
        "params": params.as_metadata(),
        "excluded_stop_ranges": [
            {"start_offset": start, "end_offset": end} for start, end in stay_regions
        ],
    }

    return EligibilityBreakdown(
        eligible_seconds=eligible,
        excluded_seconds_by_reason={
            reason: seconds for reason, seconds in excluded.items() if seconds > 0
        },
        teleport_incident_count=teleport_incidents,
        eligible_seconds_by_day=eligible_by_day,
        eligible_slices=tuple(eligible_slices),
        stationary_detector_evidence=detector_evidence,
        eligible_instant_intervals=tuple(eligible_instants),
    )


def credited_distance_m_by_day(
    *,
    pings: list[EligibilityPing],
    breakdown: EligibilityBreakdown,
    outside_area_weight: Decimal,
) -> dict[str, int]:
    """payout_v4 (D39) distance: whole metres credited to each Lagos day.

    Each eligible slice credits its ping interval's great-circle distance in
    proportion to the slice's share of that interval's seconds; a sub-second
    interval that is eligible at its instant credits its whole distance. Miles
    inside the frozen target zones count in full, others at
    ``outside_area_weight``. Excluded time (GPS gaps, low accuracy, teleports,
    out of window or area, long stops) credits nothing. Sums are exact
    fractions, rounded DOWN to whole metres per day before any pricing.
    ``pings`` must be the same list given to ``classify_session``.
    """
    ordered = sorted(pings, key=lambda ping: _utc(ping.recorded_at))
    outside = Fraction(outside_area_weight)

    def interval_metres(index: int) -> Fraction:
        first, second = ordered[index], ordered[index + 1]
        return Fraction(
            haversine_m(first.latitude, first.longitude, second.latitude, second.longitude)
        )

    totals: dict[str, Fraction] = {}
    for eligible_slice in breakdown.eligible_slices:
        # Share of the interval's whole-second span, times the part of the
        # interval actually driven after Start (exactly 1 for any interval
        # starting at or after it; fractional timestamps never reduce it).
        start = Fraction(eligible_slice.interval_start_seconds)
        duration = Fraction(eligible_slice.interval_seconds)
        in_trip = (start + duration - max(start, Fraction(0))) / duration
        share = (
            interval_metres(eligible_slice.interval_index)
            * Fraction(eligible_slice.length, eligible_slice.interval_length)
            * in_trip
        )
        weight = 1 if eligible_slice.premium else outside
        totals[eligible_slice.day] = totals.get(eligible_slice.day, Fraction(0)) + share * weight
    for index, day, premium in breakdown.eligible_instant_intervals:
        weight = 1 if premium else outside
        totals[day] = totals.get(day, Fraction(0)) + interval_metres(index) * weight
    return {day: math.floor(total) for day, total in sorted(totals.items())}
