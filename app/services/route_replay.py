import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, case, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.route_replay import RouteReplaySignature, RouteReplayStatus
from app.models.trip import LocationPing, TripSession
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    FraudFlagType,
    TripAnalytics,
)
from app.services.fraud_holds import (
    fraud_hold_active_clause,
    lock_fraud_hold_scope,
    lock_fraud_reconciliation_gate,
)
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import analytics_output_fingerprint

SIGNATURE_ROW_CONSTRAINTS = frozenset({"uq_route_replay_signatures_trip_session_id"})
NONTERMINAL_FLAG_CONSTRAINTS = frozenset(
    {"uq_fraud_flags_trip_nonterminal_flag_type"}
)
ROUTE_REPLAY_ERROR_CODE = "route_replay_evaluation_failed"
UNAVAILABLE_FINGERPRINT = "0" * 64
ReplayKind = Literal["identical", "time_shifted"]


@dataclass(frozen=True)
class RouteFingerprints:
    payload_fingerprint: str
    normalized_fingerprint: str
    point_count: int


@dataclass(frozen=True)
class RouteReplayResult:
    signature: RouteReplaySignature
    replay_flag: FraudFlag | None
    match_kind: ReplayKind | None
    changed: bool


@dataclass(frozen=True)
class _GroupResult:
    replay_flag: FraudFlag | None
    match_kind: ReplayKind | None
    changed: bool


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rounded_coordinate(value: float, precision: int) -> str:
    quantum = Decimal(1).scaleb(-precision)
    return format(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP), "f")


def route_replay_config_fingerprint(settings: Settings) -> str:
    return stable_source_fingerprint(
        {
            "detector_version": settings.route_replay_detector_version,
            "coordinate_precision": settings.route_replay_coordinate_precision,
            "time_tolerance_seconds": settings.route_replay_time_tolerance_seconds,
            "min_valid_pings": settings.route_replay_min_valid_pings,
            "min_distance_m": str(Decimal(str(settings.route_replay_min_distance_m))),
            "max_evidence_matches": settings.route_replay_max_evidence_matches,
        }
    )


def canonical_route_fingerprints(
    pings: Sequence[LocationPing],
    *,
    detector_version: str,
    coordinate_precision: int,
    time_tolerance_seconds: int,
    min_valid_pings: int,
    min_distance_m: float,
) -> RouteFingerprints:
    """Hash absolute and time-shift-invariant facts for an already ordered route."""
    if time_tolerance_seconds <= 0:
        raise ValueError("time_tolerance_seconds must be positive")
    if coordinate_precision < 0:
        raise ValueError("coordinate_precision must be non-negative")
    if not pings:
        raise ValueError("at least one ping is required")

    first_at = _utc(pings[0].recorded_at)
    parameters = {
        "coordinate_precision": coordinate_precision,
        "time_tolerance_seconds": time_tolerance_seconds,
        "min_valid_pings": min_valid_pings,
        "min_distance_m": str(Decimal(str(min_distance_m))),
    }
    absolute_points: list[dict[str, object]] = []
    normalized_points: list[dict[str, object]] = []
    previous_at: datetime | None = None
    for ping in pings:
        recorded_at = _utc(ping.recorded_at)
        if previous_at is not None and recorded_at < previous_at:
            raise ValueError("pings must be ordered by recorded_at")
        previous_at = recorded_at
        coordinates = {
            "latitude": _rounded_coordinate(ping.latitude, coordinate_precision),
            "longitude": _rounded_coordinate(ping.longitude, coordinate_precision),
        }
        absolute_points.append(
            {
                **coordinates,
                "recorded_at": recorded_at,
                "sequence_number": ping.sequence_number,
                "accuracy_m": ping.accuracy_m,
                "speed_mps": ping.speed_mps,
                "heading_degrees": ping.heading_degrees,
                "altitude_m": ping.altitude_m,
                "metadata": ping.ping_metadata,
            }
        )
        elapsed_seconds = (recorded_at - first_at).total_seconds()
        elapsed_bucket = int(
            (Decimal(str(elapsed_seconds)) / Decimal(time_tolerance_seconds)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        normalized_points.append({**coordinates, "elapsed_bucket": elapsed_bucket})

    common = {"detector_version": detector_version, "parameters": parameters}
    return RouteFingerprints(
        payload_fingerprint=stable_source_fingerprint(
            {**common, "mode": "absolute", "points": absolute_points}
        ),
        normalized_fingerprint=stable_source_fingerprint(
            {**common, "mode": "time_shifted", "points": normalized_points}
        ),
        point_count=len(pings),
    )


def _signed_advisory_key(namespace: str, fingerprint: str) -> int:
    digest = hashlib.sha256(f"route-replay:{namespace}:{fingerprint}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _advisory_lock(session: AsyncSession, key: int) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _signature_lock_keys(signature: RouteReplaySignature | None) -> set[int]:
    if (
        signature is None
        or signature.status != RouteReplayStatus.COMPUTED.value
        or signature.payload_fingerprint is None
        or signature.normalized_fingerprint is None
    ):
        return set()
    return {
        _signed_advisory_key("payload", signature.payload_fingerprint),
        _signed_advisory_key("normalized", signature.normalized_fingerprint),
    }


def _fingerprint_lock_keys(fingerprints: RouteFingerprints | None) -> set[int]:
    if fingerprints is None:
        return set()
    return {
        _signed_advisory_key("payload", fingerprints.payload_fingerprint),
        _signed_advisory_key("normalized", fingerprints.normalized_fingerprint),
    }


async def _lock_transition_fingerprints(
    session: AsyncSession,
    *,
    old_signature: RouteReplaySignature | None,
    new_fingerprints: RouteFingerprints | None,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    keys = sorted(
        _signature_lock_keys(old_signature) | _fingerprint_lock_keys(new_fingerprints)
    )
    for key in keys:
        await _advisory_lock(session, key)


async def _signature_for_trip(
    session: AsyncSession,
    trip_id: UUID,
    *,
    for_update: bool = False,
) -> RouteReplaySignature | None:
    statement = select(RouteReplaySignature).where(
        RouteReplaySignature.trip_session_id == trip_id
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _upsert_signature(
    session: AsyncSession,
    *,
    existing: RouteReplaySignature | None,
    trip: TripSession,
    analytics: TripAnalytics,
    status: str,
    detector_version: str,
    detector_config_fingerprint: str,
    source_fingerprint: str,
    fingerprints: RouteFingerprints | None,
    point_count: int,
    error_code: str | None,
    now: datetime,
) -> tuple[RouteReplaySignature, bool]:
    values = {
        "trip_analytics_id": analytics.id,
        "status": status,
        "detector_version": detector_version,
        "detector_config_fingerprint": detector_config_fingerprint,
        "source_analytics_fingerprint": source_fingerprint,
        "payload_fingerprint": (
            fingerprints.payload_fingerprint if fingerprints is not None else None
        ),
        "normalized_fingerprint": (
            fingerprints.normalized_fingerprint if fingerprints is not None else None
        ),
        "point_count": point_count,
        "error_code": error_code,
        "computed_at": now,
    }
    signature = existing
    if signature is None:
        candidate = RouteReplaySignature(trip_session_id=trip.id, **values)
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(exc, constraints=SIGNATURE_ROW_CONSTRAINTS):
                raise
            signature = await _signature_for_trip(session, trip.id, for_update=True)
            if signature is None:
                raise
        else:
            await session.refresh(candidate)
            return candidate, True

    stable_values = {field: value for field, value in values.items() if field != "computed_at"}
    changed = any(getattr(signature, field) != value for field, value in stable_values.items())
    if not changed:
        values["computed_at"] = signature.computed_at
    for field, value in values.items():
        setattr(signature, field, value)
    await session.flush()
    await session.refresh(signature)
    return signature, changed


def _current_signature_predicate():
    stored_output = TripAnalytics.analytics_metadata["output_fingerprint"].as_string()
    return or_(
        stored_output == RouteReplaySignature.source_analytics_fingerprint,
        and_(
            stored_output.is_(None),
            RouteReplaySignature.computed_at >= TripAnalytics.computed_at,
        ),
    )


def _group_members(detector_version: str, normalized_fingerprint: str):
    return (
        select(
            RouteReplaySignature.trip_session_id.label("trip_id"),
            RouteReplaySignature.payload_fingerprint.label("payload_fingerprint"),
            TripSession.driver_profile_id.label("driver_profile_id"),
            func.coalesce(TripSession.ended_at, TripSession.started_at).label("occurred_at"),
            TripAnalytics.id.label("analytics_id"),
            TripAnalytics.computed_at.label("analytics_computed_at"),
        )
        .join(TripSession, TripSession.id == RouteReplaySignature.trip_session_id)
        .join(TripAnalytics, TripAnalytics.id == RouteReplaySignature.trip_analytics_id)
        .where(
            RouteReplaySignature.status == RouteReplayStatus.COMPUTED.value,
            RouteReplaySignature.detector_version == detector_version,
            RouteReplaySignature.normalized_fingerprint == normalized_fingerprint,
            _current_signature_predicate(),
        )
        .subquery()
    )


async def _affected_group_trip_ids(
    session: AsyncSession,
    group_keys: set[tuple[str, str]],
) -> set[UUID]:
    trip_ids: set[UUID] = set()
    for detector_version, normalized_fingerprint in sorted(group_keys):
        members = _group_members(detector_version, normalized_fingerprint)
        trip_ids.update(
            (
                await session.scalars(select(members.c.trip_id))
            ).all()
        )
    return trip_ids


async def _nonterminal_replay_flag(
    session: AsyncSession,
    trip_id: UUID,
) -> FraudFlag | None:
    return await session.scalar(
        select(FraudFlag)
        .where(
            FraudFlag.trip_session_id == trip_id,
            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
            fraud_hold_active_clause(),
        )
        .with_for_update()
    )


async def _cleanup_group_open_flags(
    session: AsyncSession,
    members,
    *,
    keep_trip_id: UUID | None,
) -> bool:
    conditions = [
        FraudFlag.trip_session_id.in_(select(members.c.trip_id)),
        FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
        FraudFlag.status == FraudFlagStatus.OPEN.value,
    ]
    if keep_trip_id is not None:
        conditions.append(FraudFlag.trip_session_id != keep_trip_id)
    result = await session.execute(
        delete(FraudFlag)
        .where(*conditions)
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)


async def _remove_open_replay_flag(session: AsyncSession, trip_id: UUID) -> bool:
    result = await session.execute(
        delete(FraudFlag)
        .where(
            FraudFlag.trip_session_id == trip_id,
            FraudFlag.flag_type == FraudFlagType.ROUTE_REPLAY.value,
            FraudFlag.status == FraudFlagStatus.OPEN.value,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)


async def _write_replay_flag(
    session: AsyncSession,
    *,
    target,
    match_kind: ReplayKind,
    total_match_count: int,
    cross_account_match_count: int,
    sampled_trip_ids: list[UUID],
    settings: Settings,
) -> tuple[FraudFlag, bool]:
    evidence = {
        "detector_version": settings.route_replay_detector_version,
        "match_kind": match_kind,
        "total_match_count": total_match_count,
        "cross_account_match_count": cross_account_match_count,
        "sampled_matched_trip_ids": [str(trip_id) for trip_id in sampled_trip_ids],
    }
    trip = await session.get(TripSession, target.trip_id)
    analytics = await session.get(TripAnalytics, target.analytics_id)
    if trip is None or analytics is None:
        raise RuntimeError("route replay target evidence is missing")
    values = {
        "trip_analytics_id": analytics.id,
        "assignment_id": trip.assignment_id,
        "campaign_id": trip.campaign_id,
        "driver_profile_id": trip.driver_profile_id,
        "vehicle_id": trip.vehicle_id,
        "severity": FraudFlagSeverity.HIGH.value,
        "description": "This trip's route matches a route submitted by another driver.",
        "evidence": evidence,
        "detected_at": analytics.computed_at,
    }
    flag = await _nonterminal_replay_flag(session, trip.id)
    if flag is not None and flag.status != FraudFlagStatus.OPEN.value:
        return flag, False
    if flag is None:
        candidate = FraudFlag(
            trip_session_id=trip.id,
            flag_type=FraudFlagType.ROUTE_REPLAY.value,
            status=FraudFlagStatus.OPEN.value,
            **values,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            if not is_expected_uniqueness_conflict(
                exc,
                constraints=NONTERMINAL_FLAG_CONSTRAINTS,
            ):
                raise
            flag = await _nonterminal_replay_flag(session, trip.id)
            if flag is None:
                raise
            if flag.status != FraudFlagStatus.OPEN.value:
                return flag, False
        else:
            await session.refresh(candidate)
            return candidate, True

    changed = any(getattr(flag, field) != value for field, value in values.items())
    for field, value in values.items():
        setattr(flag, field, value)
    await session.flush()
    await session.refresh(flag)
    return flag, changed


async def _reconcile_group(
    session: AsyncSession,
    *,
    detector_version: str,
    normalized_fingerprint: str,
    settings: Settings,
) -> _GroupResult:
    members = _group_members(detector_version, normalized_fingerprint)
    target = (
        await session.execute(
            select(members)
            .order_by(members.c.occurred_at.desc(), members.c.trip_id.desc())
            .limit(1)
        )
    ).one_or_none()
    if target is None:
        return _GroupResult(None, None, False)

    totals = (
        await session.execute(
            select(
                func.count().label("total"),
                func.coalesce(
                    func.sum(
                        case(
                            (members.c.driver_profile_id != target.driver_profile_id, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("cross_account"),
            ).where(members.c.trip_id != target.trip_id)
        )
    ).one()
    total_match_count = int(totals.total)
    cross_account_match_count = int(totals.cross_account)
    if total_match_count == 0 or cross_account_match_count == 0:
        changed = await _cleanup_group_open_flags(session, members, keep_trip_id=None)
        return _GroupResult(None, None, changed)

    exact_match_exists = bool(
        await session.scalar(
            select(func.count())
            .select_from(members)
            .where(
                members.c.trip_id != target.trip_id,
                members.c.payload_fingerprint == target.payload_fingerprint,
            )
        )
    )
    match_kind: ReplayKind = "identical" if exact_match_exists else "time_shifted"
    sampled_trip_ids = list(
        (
            await session.scalars(
                select(members.c.trip_id)
                .where(members.c.trip_id != target.trip_id)
                .order_by(members.c.occurred_at, members.c.trip_id)
                .limit(settings.route_replay_max_evidence_matches)
            )
        ).all()
    )
    cleanup_changed = await _cleanup_group_open_flags(
        session, members, keep_trip_id=target.trip_id
    )
    flag, flag_changed = await _write_replay_flag(
        session,
        target=target,
        match_kind=match_kind,
        total_match_count=total_match_count,
        cross_account_match_count=cross_account_match_count,
        sampled_trip_ids=sampled_trip_ids,
        settings=settings,
    )
    return _GroupResult(flag, match_kind, cleanup_changed or flag_changed)


async def detect_route_replay(
    session: AsyncSession,
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    ordered_pings: Sequence[LocationPing],
    settings: Settings,
    now: datetime,
) -> RouteReplayResult:
    """Transition one signature and reconcile every affected normalized group."""
    detector_version = settings.route_replay_detector_version
    config_fingerprint = route_replay_config_fingerprint(settings)
    source_fingerprint = UNAVAILABLE_FINGERPRINT
    status = RouteReplayStatus.ERROR.value
    error_code: str | None = ROUTE_REPLAY_ERROR_CODE
    fingerprints: RouteFingerprints | None = None
    try:
        source_fingerprint = analytics_output_fingerprint(analytics)
        if len(ordered_pings) < settings.route_replay_min_valid_pings or Decimal(
            analytics.distance_m
        ) < Decimal(str(settings.route_replay_min_distance_m)):
            status = RouteReplayStatus.INSUFFICIENT_DATA.value
            error_code = None
        else:
            fingerprints = canonical_route_fingerprints(
                ordered_pings,
                detector_version=detector_version,
                coordinate_precision=settings.route_replay_coordinate_precision,
                time_tolerance_seconds=settings.route_replay_time_tolerance_seconds,
                min_valid_pings=settings.route_replay_min_valid_pings,
                min_distance_m=settings.route_replay_min_distance_m,
            )
            status = RouteReplayStatus.COMPUTED.value
            error_code = None
    except Exception:
        pass

    # Cross-trip reconciliation can remove or replace another trip's replay
    # flag. Exclude ordinary review/money holders first, discover every old/new
    # group member while detector membership is stable, then lock all affected
    # trip scopes in one deterministic order before any signature/flag write.
    await lock_fraud_reconciliation_gate(session, exclusive=True)
    old_signature = await _signature_for_trip(session, trip.id)
    old_group = (
        (old_signature.detector_version, old_signature.normalized_fingerprint)
        if old_signature is not None
        and old_signature.status == RouteReplayStatus.COMPUTED.value
        and old_signature.normalized_fingerprint is not None
        else None
    )
    new_group = (
        (detector_version, fingerprints.normalized_fingerprint)
        if fingerprints is not None
        else None
    )
    group_keys = {group for group in (old_group, new_group) if group is not None}
    affected_trip_ids = await _affected_group_trip_ids(session, group_keys)
    affected_trip_ids.add(trip.id)
    for affected_trip_id in sorted(affected_trip_ids, key=str):
        await lock_fraud_hold_scope(
            session,
            affected_trip_id,
            reconciliation_gate_held=True,
        )
    await _lock_transition_fingerprints(
        session,
        old_signature=old_signature,
        new_fingerprints=fingerprints,
    )
    locked_signature = await _signature_for_trip(session, trip.id, for_update=True)
    signature, signature_changed = await _upsert_signature(
        session,
        existing=locked_signature,
        trip=trip,
        analytics=analytics,
        status=status,
        detector_version=detector_version,
        detector_config_fingerprint=config_fingerprint,
        source_fingerprint=source_fingerprint,
        fingerprints=fingerprints,
        point_count=len(ordered_pings),
        error_code=error_code,
        now=now,
    )

    changed = signature_changed
    current_group_result = _GroupResult(None, None, False)
    seen: set[tuple[str, str]] = set()
    for group_key in (old_group, new_group):
        if group_key is None or group_key in seen:
            continue
        seen.add(group_key)
        group_result = await _reconcile_group(
            session,
            detector_version=group_key[0],
            normalized_fingerprint=group_key[1],
            settings=settings,
        )
        changed = changed or group_result.changed
        if group_key == new_group:
            current_group_result = group_result

    if fingerprints is None:
        changed = await _remove_open_replay_flag(session, trip.id) or changed
    return RouteReplayResult(
        signature,
        current_group_result.replay_flag,
        current_group_result.match_kind,
        changed,
    )
