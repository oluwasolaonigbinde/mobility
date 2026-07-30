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
from dataclasses import dataclass
from datetime import UTC, datetime

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


@dataclass(frozen=True)
class EligibilityBreakdown:
    eligible_seconds: int
    excluded_seconds_by_reason: dict[str, int]
    teleport_incident_count: int

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
    """Confirmed stay-point spans as excluded offset regions (grace applied).

    Detection runs over the full ping series so exclusions like out_of_area
    never reset the grace clock; only a gps_gap interval (position unknown)
    breaks a stretch. Returns [start_offset, end_offset) pairs of the
    *excluded* portion (anchor time + grace .. last ping inside the radius).
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
            excluded_from = offsets[anchor] + params.stationary_grace_seconds
            excluded_to = offsets[last_inside]
            if excluded_from < excluded_to:
                regions.append((excluded_from, excluded_to))
            anchor = last_inside + 1
        else:
            anchor += 1
    return regions


def classify_session(
    *,
    session_started_at: datetime,
    session_ended_at: datetime,
    pings: list[EligibilityPing],
    window_start_at: datetime | None,
    window_end_at: datetime | None,
    params: EligibilityParams,
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
        )

    if not ordered:
        return EligibilityBreakdown(
            eligible_seconds=0,
            excluded_seconds_by_reason={REASON_GPS_GAP: duration},
            teleport_incident_count=0,
        )

    window_from = off((_utc(window_start_at) - start).total_seconds()) if window_start_at else 0
    window_to = off((_utc(window_end_at) - start).total_seconds()) if window_end_at else duration

    stay_regions = _stay_point_regions(ordered, offsets, raw_seconds, params)

    def accuracy_fails(ping: EligibilityPing) -> bool:
        # Null accuracy fails the gate: pay demands affirmative signal quality
        # (payout_v2 frozen policy, decisions-log).
        return ping.accuracy_m is None or ping.accuracy_m > params.max_accuracy_m

    # Per ping-interval base reason (highest-precedence signal rules only).
    interval_reason: list[str | None] = []
    for index in range(len(ordered) - 1):
        first = ordered[index]
        second = ordered[index + 1]
        delta = raw_seconds[index + 1] - raw_seconds[index]
        distance = haversine_m(
            first.latitude, first.longitude, second.latitude, second.longitude
        )
        speed_kmh = (distance / delta) * 3.6 if delta > 0 else math.inf
        is_teleport = distance > 1.0 and speed_kmh > params.teleport_kmh
        if is_teleport:
            teleport_incidents += 1
        if delta > params.max_ping_gap_seconds:
            interval_reason.append(REASON_GPS_GAP)
        elif accuracy_fails(first) or accuracy_fails(second):
            interval_reason.append(REASON_LOW_ACCURACY)
        elif is_teleport:
            interval_reason.append(REASON_TELEPORT)
        elif not (first.in_area and second.in_area):
            interval_reason.append(REASON_OUT_OF_AREA)
        else:
            interval_reason.append(None)  # moving/stationary decided per slice

    # Elementary slice boundaries: session edges, ping offsets, window edges,
    # and stay-region grace boundaries — classification is constant per slice.
    cuts = {0, duration, window_from, window_to}
    cuts.update(offsets)
    for region_start, region_end in stay_regions:
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
        in_stay_exclusion = any(
            region_start <= slice_start < region_end
            for region_start, region_end in stay_regions
        )
        if in_stay_exclusion:
            excluded[REASON_STATIONARY] += length
            continue
        eligible += length

    return EligibilityBreakdown(
        eligible_seconds=eligible,
        excluded_seconds_by_reason={
            reason: seconds for reason, seconds in excluded.items() if seconds > 0
        },
        teleport_incident_count=teleport_incidents,
    )
