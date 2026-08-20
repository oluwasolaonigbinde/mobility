"""Deterministic payable-time classification for payout_v2 (D2, Q5).

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
from zoneinfo import ZoneInfo

# The payable day is the Africa/Lagos calendar day (D4 cap, D9c). Frozen
# product rule, not configuration.
LAGOS_TZ = ZoneInfo("Africa/Lagos")

REASON_MOVING = "moving"
REASON_STATIONARY = "stationary"
REASON_STATIONARY_ROLLING = "stationary_rolling_displacement"
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
    REASON_STATIONARY_ROLLING,
)

STATIONARY_POLICY_V1 = "stationary-rd-v1"

EARTH_RADIUS_M = 6371000.0


@dataclass(frozen=True)
class EligibilityParams:
    stationary_radius_m: float
    stationary_window_seconds: int
    stationary_grace_seconds: int
    max_accuracy_m: float
    teleport_kmh: float
    max_ping_gap_seconds: int
    rolling_window_seconds: int = 120
    rolling_stride_seconds: int = 120
    rolling_max_displacement_m: float = 25.0
    rolling_confirmation_windows: int = 2
    rolling_release_windows: int = 1

    def as_legacy_metadata(self) -> dict[str, float | int]:
        return {
            "stationary_radius_m": self.stationary_radius_m,
            "stationary_window_seconds": self.stationary_window_seconds,
            "stationary_grace_seconds": self.stationary_grace_seconds,
            "max_accuracy_m": self.max_accuracy_m,
            "teleport_kmh": self.teleport_kmh,
            "max_ping_gap_seconds": self.max_ping_gap_seconds,
        }

    def as_metadata(self) -> dict[str, float | int]:
        return {
            **self.as_legacy_metadata(),
            "rolling_window_seconds": self.rolling_window_seconds,
            "rolling_stride_seconds": self.rolling_stride_seconds,
            "rolling_max_displacement_m": self.rolling_max_displacement_m,
            "rolling_confirmation_windows": self.rolling_confirmation_windows,
            "rolling_release_windows": self.rolling_release_windows,
        }


@dataclass(frozen=True)
class EligibilityPing:
    recorded_at: datetime
    latitude: float
    longitude: float
    accuracy_m: float | None
    in_area: bool
    # payout_v3 tier resolution only (MNY-06B): membership of the binding's
    # frozen premium (target) zones. Plays no role in eligibility/exclusion.
    in_premium: bool = False


@dataclass(frozen=True)
class EligibleSlice:
    """One eligible elementary slice, in chronological order (MNY-06B).

    Slices are already cut at every ping offset, Lagos midnight, window edge,
    and stay-region boundary, so premium membership — like in_area — is
    constant within a slice: premium iff both governing pings are inside a
    frozen premium zone. payout_v2 ignores these; payout_v3 prices them.
    """

    start_offset: int
    end_offset: int
    day: str
    premium: bool

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
    # Chronological eligible slices with day + tier (payout_v3 only). Slice
    # lengths always sum to eligible_seconds.
    eligible_slices: tuple[EligibleSlice, ...] = ()
    stationary_detector_evidence: dict = field(default_factory=dict)

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
    """Legacy confirmed stay-point spans before shared grace allocation.

    Detection runs over the full ping series so area/window exclusions never
    reset it; only a GPS gap breaks a stretch. Rolling and legacy ranges are
    unioned before the existing whole-trip grace is spent once.
    """
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
        if last_inside > anchor and duration >= params.stationary_window_seconds:
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


def _position_at(
    offset: float,
    pings: list[EligibilityPing],
    raw_seconds: list[float],
    params: EligibilityParams,
) -> tuple[float, float] | None:
    """Resolve an endpoint without ever interpolating through invalid evidence."""
    for index, ping_offset in enumerate(raw_seconds):
        if math.isclose(offset, ping_offset, abs_tol=1e-9):
            ping = pings[index]
            if _accuracy_fails(ping, params):
                return None
            return ping.latitude, ping.longitude
    for index in range(len(pings) - 1):
        first_offset = raw_seconds[index]
        second_offset = raw_seconds[index + 1]
        if first_offset < offset < second_offset:
            delta = second_offset - first_offset
            if _signal_reason(pings[index], pings[index + 1], delta, params) is not None:
                return None
            ratio = (offset - first_offset) / delta
            return (
                pings[index].latitude + (pings[index + 1].latitude - pings[index].latitude) * ratio,
                pings[index].longitude
                + (pings[index + 1].longitude - pings[index].longitude) * ratio,
            )
    return None


def _rolling_stationary_regions(
    pings: list[EligibilityPing],
    raw_seconds: list[float],
    duration: int,
    params: EligibilityParams,
) -> tuple[list[tuple[int, int]], list[dict], list[dict]]:
    """Classify fixed elapsed windows under stationary-rd-v1 hysteresis."""
    if len(pings) < 2:
        return [], [], []

    segments: list[tuple[int, int]] = []
    segment_start = 0
    gaps: list[tuple[int, int]] = []
    for index in range(len(pings) - 1):
        if raw_seconds[index + 1] - raw_seconds[index] > params.max_ping_gap_seconds:
            segments.append((segment_start, index))
            gaps.append((index, index + 1))
            segment_start = index + 1
    segments.append((segment_start, len(pings) - 1))

    ranges: list[tuple[int, int]] = []
    observations: list[dict] = []
    resets: list[dict] = []
    for segment_number, (first_index, last_index) in enumerate(segments):
        accepted = next(
            (
                index
                for index in range(first_index, last_index + 1)
                if 0 <= raw_seconds[index] <= duration and not _accuracy_fails(pings[index], params)
            ),
            None,
        )
        if segment_number > 0:
            gap_first, gap_second = gaps[segment_number - 1]
            resets.append(
                {
                    "event": "gps_gap_reset",
                    "gap_start_offset": max(0, math.floor(raw_seconds[gap_first])),
                    "gap_end_offset": min(duration, math.floor(raw_seconds[gap_second])),
                    "reanchor_offset": (
                        min(duration, max(0, math.floor(raw_seconds[accepted])))
                        if accepted is not None
                        else None
                    ),
                }
            )
        if accepted is None and segment_number > 0:
            continue

        # v1 starts on the trip clock. Only a GPS-gap reset changes the anchor
        # to the first subsequent accepted-quality ping.
        anchor = 0.0 if segment_number == 0 else raw_seconds[accepted]
        segment_end = min(float(duration), raw_seconds[last_index])
        confirmed = False
        streak_starts: list[float] = []
        moving_starts: list[float] = []
        active_start: float | None = None
        window_start = anchor
        while window_start + params.rolling_window_seconds <= segment_end + 1e-9:
            window_end = window_start + params.rolling_window_seconds
            contaminated = False
            for index in range(first_index, last_index):
                interval_start = raw_seconds[index]
                interval_end = raw_seconds[index + 1]
                if interval_end <= window_start or interval_start >= window_end:
                    continue
                reason = _signal_reason(
                    pings[index], pings[index + 1], interval_end - interval_start, params
                )
                if reason in (REASON_LOW_ACCURACY, REASON_TELEPORT):
                    contaminated = True
                    break
            start_position = _position_at(window_start, pings, raw_seconds, params)
            end_position = _position_at(window_end, pings, raw_seconds, params)
            displacement: float | None = None
            if start_position is None or end_position is None:
                contaminated = True
            else:
                displacement = haversine_m(*start_position, *end_position)

            transition: str | None = None
            if contaminated:
                verdict = "contaminated"
                moving_starts.clear()
                if not confirmed:
                    streak_starts.clear()
            elif displacement <= params.rolling_max_displacement_m:
                verdict = "stationary"
                moving_starts.clear()
                if not confirmed:
                    if not streak_starts or math.isclose(
                        streak_starts[-1] + params.rolling_stride_seconds,
                        window_start,
                        abs_tol=1e-9,
                    ):
                        streak_starts.append(window_start)
                    else:
                        streak_starts = [window_start]
                    if len(streak_starts) >= params.rolling_confirmation_windows:
                        confirmed = True
                        active_start = streak_starts[-params.rolling_confirmation_windows]
                        transition = "confirmed"
            else:
                verdict = "moving"
                streak_starts.clear()
                if confirmed:
                    if not moving_starts or math.isclose(
                        moving_starts[-1] + params.rolling_stride_seconds,
                        window_start,
                        abs_tol=1e-9,
                    ):
                        moving_starts.append(window_start)
                    else:
                        moving_starts = [window_start]
                    if len(moving_starts) >= params.rolling_release_windows:
                        release_at = moving_starts[-params.rolling_release_windows]
                        if active_start is not None and active_start < release_at:
                            ranges.append((math.floor(active_start), math.floor(release_at)))
                        confirmed = False
                        active_start = None
                        moving_starts.clear()
                        transition = "released"

            observations.append(
                {
                    "start_offset": math.floor(window_start),
                    "end_offset": math.floor(window_end),
                    "verdict": verdict,
                    "net_displacement_m": (
                        round(displacement, 3) if displacement is not None else None
                    ),
                    **({"transition": transition} if transition else {}),
                }
            )
            window_start += params.rolling_stride_seconds

        if confirmed and active_start is not None and active_start < segment_end:
            ranges.append((math.floor(active_start), math.floor(segment_end)))

    return ranges, observations, resets


def _stationary_exclusion_regions(
    legacy_ranges: list[tuple[int, int]],
    rolling_ranges: list[tuple[int, int]],
    grace_seconds: int,
) -> tuple[list[tuple[int, int, str]], list[dict]]:
    """Union both detectors, then spend the existing grace once in time order."""
    all_ranges = sorted(legacy_ranges + rolling_ranges)
    merged: list[list[int]] = []
    for start, end in all_ranges:
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    grace_remaining = max(0, grace_seconds)
    exclusions: list[tuple[int, int, str]] = []
    allocations: list[dict] = []
    source_cuts = sorted({point for region in all_ranges for point in region})
    for start, end in merged:
        granted = min(grace_remaining, end - start)
        grace_remaining -= granted
        allocations.append(
            {
                "range_start_offset": start,
                "range_end_offset": end,
                "granted_seconds": granted,
            }
        )
        excluded_from = start + granted
        cuts = [excluded_from, end]
        cuts.extend(point for point in source_cuts if excluded_from < point < end)
        cuts = sorted(set(cuts))
        for slice_start, slice_end in zip(cuts, cuts[1:], strict=False):
            if slice_start >= slice_end:
                continue
            rolling = any(a <= slice_start < b for a, b in rolling_ranges)
            exclusions.append(
                (
                    slice_start,
                    slice_end,
                    REASON_STATIONARY_ROLLING if rolling else REASON_STATIONARY,
                )
            )
    return exclusions, allocations


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
    stationary_policy_marker: str | None = None,
) -> EligibilityBreakdown:
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

    legacy_stay_regions = _stay_point_regions(ordered, offsets, raw_seconds, params)
    rolling_regions: list[tuple[int, int]] = []
    rolling_observations: list[dict] = []
    reset_events: list[dict] = []
    if stationary_policy_marker == STATIONARY_POLICY_V1:
        rolling_regions, rolling_observations, reset_events = _rolling_stationary_regions(
            ordered, raw_seconds, duration, params
        )
    stationary_regions, grace_allocation = _stationary_exclusion_regions(
        legacy_stay_regions,
        rolling_regions,
        params.stationary_grace_seconds,
    )

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
        stationary_reason = next(
            (
                reason
                for region_start, region_end, reason in stationary_regions
                if region_start <= slice_start < region_end
            ),
            None,
        )
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
            )
        )

    return EligibilityBreakdown(
        eligible_seconds=eligible,
        excluded_seconds_by_reason={
            reason: seconds for reason, seconds in excluded.items() if seconds > 0
        },
        teleport_incident_count=teleport_incidents,
        eligible_seconds_by_day=eligible_by_day,
        eligible_slices=tuple(eligible_slices),
        stationary_detector_evidence=(
            {
                "version": stationary_policy_marker,
                "params": params.as_metadata(),
                "classified_stationary_ranges": [
                    {"start_offset": start, "end_offset": end} for start, end in rolling_regions
                ],
                "window_observations": rolling_observations,
                "reset_events": reset_events,
                "grace_allocation": grace_allocation,
            }
            if stationary_policy_marker == STATIONARY_POLICY_V1
            else {}
        ),
    )
