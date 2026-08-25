"""Evaluate assignment activity obligations without touching lifecycle or money state."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.models.assignment_activity import (
    AssignmentActivityFlag,
    AssignmentActivityFlagEvent,
    AssignmentActivityFlagEventType,
    AssignmentActivityFlagStatus,
    AssignmentActivityFlagType,
)
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import TripAnalytics, TripAnalyticsStatus
from app.services.notifications import create_activity_flag_notice
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

logger = logging.getLogger(__name__)

INACTIVITY_WINDOW = timedelta(days=7)
UTC_WEEK = timedelta(days=7)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_completed_week_window(now: datetime) -> tuple[datetime, datetime]:
    """Return the immediately preceding complete Monday-to-Monday UTC week."""
    now = _utc(now)
    current_week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=now.weekday()
    )
    return current_week_start - UTC_WEEK, current_week_start


def parse_verified_hours_floor(
    settings: Settings | None = None,
) -> tuple[int | None, str | None]:
    """Parse Q20's explicit setting, failing closed with a stable reason."""
    settings = settings or get_settings()
    raw = settings.verified_hours_floor_per_week
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "missing_configuration"
    try:
        hours = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None, "invalid_configuration"
    if not hours.is_finite() or hours <= 0:
        return None, "invalid_configuration"
    seconds = hours * Decimal(3600)
    if seconds != seconds.to_integral_value():
        return None, "invalid_configuration"
    return int(seconds), None


def _evidence(
    *,
    flag_type: AssignmentActivityFlagType,
    window_start: datetime,
    window_end: datetime,
    threshold_seconds: int | None,
    observed_seconds: int,
    last_verified_activity_at: datetime | None,
    eligible_trip_count: int,
) -> dict[str, Any]:
    return {
        "activity_rule": flag_type.value,
        "window_start": _utc(window_start).isoformat(),
        "window_end": _utc(window_end).isoformat(),
        "threshold_seconds": threshold_seconds,
        "observed_seconds": observed_seconds,
        "last_verified_activity_at": (
            _utc(last_verified_activity_at).isoformat()
            if last_verified_activity_at is not None
            else None
        ),
        "eligible_trip_count": eligible_trip_count,
        "analytics_source": "computed_sealed_trip_analytics",
    }


async def _locked_assignment(
    session: AsyncSession, assignment_id: UUID
) -> CampaignAssignment | None:
    """Lock campaign then assignment, matching W3-03B/trip serialization."""
    assignment_ref = await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id)
    )
    if assignment_ref is None:
        return None
    await acquire_campaign_terms_lock(session, assignment_ref.campaign_id)
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == assignment_ref.campaign_id).with_for_update()
    )
    if campaign is None:
        return None
    return await session.scalar(
        select(CampaignAssignment).where(CampaignAssignment.id == assignment_id).with_for_update()
    )


async def _eligible_analytics(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    now: datetime,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> list[TripAnalytics]:
    """Read only authoritative, sealed analytics for a locked assignment.

    The assignment and campaign locks prevent new FK-backed contributors from
    entering while this query is evaluated. All linkage and chronology checks
    are repeated here because analytics rows are not themselves assignment
    authority.
    """
    now = _utc(now)
    conditions = [
        TripAnalytics.assignment_id == assignment.id,
        TripAnalytics.campaign_id == assignment.campaign_id,
        TripAnalytics.driver_profile_id == assignment.driver_profile_id,
        TripAnalytics.vehicle_id == assignment.vehicle_id,
        TripAnalytics.status == TripAnalyticsStatus.COMPUTED.value,
        TripAnalytics.active_tracking_seconds > 0,
        TripAnalytics.computed_at <= now,
        TripAnalytics.last_ping_at.is_not(None),
        TripAnalytics.last_ping_at <= now,
        TripSession.status == TripSessionStatus.SEALED.value,
        TripSession.assignment_id == assignment.id,
        TripSession.campaign_id == assignment.campaign_id,
        TripSession.driver_profile_id == assignment.driver_profile_id,
        TripSession.vehicle_id == assignment.vehicle_id,
        TripSession.started_at <= now,
        TripSession.ended_at.is_not(None),
        TripSession.ended_at <= now,
        TripSession.sealed_at.is_not(None),
        TripSession.sealed_at <= now,
        # D16: analytics computed before sealing cannot be reused as authority.
        TripAnalytics.computed_at >= TripSession.sealed_at,
        TripAnalytics.last_ping_at >= TripSession.started_at,
        TripAnalytics.last_ping_at <= TripSession.ended_at,
    ]
    if assignment.activated_at is not None:
        conditions.append(TripSession.started_at >= assignment.activated_at)
    else:
        # Active rows should always have an activation timestamp. Failing
        # closed here prevents pre-assignment analytics from becoming activity.
        return []
    if window_start is not None:
        conditions.append(TripAnalytics.last_ping_at >= window_start)
    if window_end is not None:
        conditions.append(TripAnalytics.last_ping_at < window_end)
    rows = await session.scalars(
        select(TripAnalytics)
        .join(TripSession, TripSession.id == TripAnalytics.trip_session_id)
        .where(*conditions)
        .order_by(TripAnalytics.last_ping_at, TripAnalytics.id)
    )
    # trip_session_id is unique in the authoritative model. Keep the explicit
    # set guard so a legacy/fixture join can never double count a trip.
    unique: dict[UUID, TripAnalytics] = {}
    for analytics in rows:
        unique.setdefault(analytics.trip_session_id, analytics)
    return list(unique.values())


async def _find_flag(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    flag_type: AssignmentActivityFlagType,
    window_start: datetime,
    window_end: datetime,
) -> AssignmentActivityFlag | None:
    return await session.scalar(
        select(AssignmentActivityFlag)
        .where(
            AssignmentActivityFlag.assignment_id == assignment_id,
            AssignmentActivityFlag.flag_type == flag_type.value,
            AssignmentActivityFlag.window_start == window_start,
            AssignmentActivityFlag.window_end == window_end,
        )
        .with_for_update()
    )


async def _append_event(
    session: AsyncSession,
    *,
    flag: AssignmentActivityFlag,
    event_type: AssignmentActivityFlagEventType,
    occurred_at: datetime,
    observed_seconds: int,
    evidence: dict[str, Any],
) -> AssignmentActivityFlagEvent:
    sequence = (
        int(
            await session.scalar(
                select(
                    func.coalesce(func.max(AssignmentActivityFlagEvent.sequence_number), 0)
                ).where(AssignmentActivityFlagEvent.flag_id == flag.id)
            )
            or 0
        )
        + 1
    )
    event = AssignmentActivityFlagEvent(
        flag_id=flag.id,
        assignment_id=flag.assignment_id,
        sequence_number=sequence,
        event_type=event_type.value,
        occurred_at=occurred_at,
        observed_seconds=observed_seconds,
        evidence=evidence,
    )
    session.add(event)
    await session.flush()
    return event


async def _open_flag(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    flag_type: AssignmentActivityFlagType,
    window_start: datetime,
    window_end: datetime,
    threshold_seconds: int | None,
    observed_seconds: int,
    last_verified_activity_at: datetime | None,
    eligible_trip_count: int,
    now: datetime,
) -> tuple[AssignmentActivityFlag, bool, bool]:
    evidence = _evidence(
        flag_type=flag_type,
        window_start=window_start,
        window_end=window_end,
        threshold_seconds=threshold_seconds,
        observed_seconds=observed_seconds,
        last_verified_activity_at=last_verified_activity_at,
        eligible_trip_count=eligible_trip_count,
    )
    flag = AssignmentActivityFlag(
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        flag_type=flag_type.value,
        status=AssignmentActivityFlagStatus.OPEN.value,
        window_start=window_start,
        window_end=window_end,
        threshold_seconds=threshold_seconds,
        observed_seconds=observed_seconds,
        last_verified_activity_at=last_verified_activity_at,
        first_detected_at=now,
        last_evaluated_at=now,
        current_evidence=evidence,
    )
    try:
        async with session.begin_nested():
            session.add(flag)
            await session.flush()
    except IntegrityError:
        existing = await _find_flag(
            session,
            assignment_id=assignment.id,
            flag_type=flag_type,
            window_start=window_start,
            window_end=window_end,
        )
        if existing is None:
            raise
        return existing, False, False
    await _append_event(
        session,
        flag=flag,
        event_type=AssignmentActivityFlagEventType.OPENED,
        occurred_at=now,
        observed_seconds=observed_seconds,
        evidence=evidence,
    )
    await create_activity_flag_notice(
        session,
        flag=flag,
        event_type=AssignmentActivityFlagEventType.OPENED,
    )
    return flag, True, True


async def _recover_flag(
    session: AsyncSession,
    *,
    flag: AssignmentActivityFlag,
    observed_seconds: int,
    last_verified_activity_at: datetime | None,
    eligible_trip_count: int,
    now: datetime,
) -> tuple[bool, bool]:
    if flag.status != AssignmentActivityFlagStatus.OPEN.value:
        return False, False
    flag.status = AssignmentActivityFlagStatus.RECOVERED.value
    flag.recovered_at = now
    flag.last_evaluated_at = now
    flag.observed_seconds = observed_seconds
    flag.last_verified_activity_at = last_verified_activity_at
    evidence = _evidence(
        flag_type=AssignmentActivityFlagType(flag.flag_type),
        window_start=flag.window_start,
        window_end=flag.window_end,
        threshold_seconds=flag.threshold_seconds,
        observed_seconds=observed_seconds,
        last_verified_activity_at=last_verified_activity_at,
        eligible_trip_count=eligible_trip_count,
    )
    flag.current_evidence = evidence
    await session.flush()
    await _append_event(
        session,
        flag=flag,
        event_type=AssignmentActivityFlagEventType.RECOVERED,
        occurred_at=now,
        observed_seconds=observed_seconds,
        evidence=evidence,
    )
    await create_activity_flag_notice(
        session,
        flag=flag,
        event_type=AssignmentActivityFlagEventType.RECOVERED,
    )
    return True, True


async def _evaluate_weekly_floor(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    threshold_seconds: int,
    now: datetime,
) -> tuple[str, int, int, int]:
    window_start, window_end = utc_completed_week_window(now)
    if assignment.activated_at is None or _utc(assignment.activated_at) > window_start:
        return "skipped_activation_window", 0, 0, 0
    analytics = await _eligible_analytics(
        session,
        assignment=assignment,
        now=now,
        window_start=window_start,
        window_end=window_end,
    )
    observed = sum(int(row.active_tracking_seconds) for row in analytics)
    last_activity = max(
        (_utc(row.last_ping_at) for row in analytics if row.last_ping_at is not None),
        default=None,
    )
    flag = await _find_flag(
        session,
        assignment_id=assignment.id,
        flag_type=AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR,
        window_start=window_start,
        window_end=window_end,
    )
    if flag is not None:
        flag.observed_seconds = observed
        flag.last_verified_activity_at = last_activity
        flag.last_evaluated_at = now
        flag.current_evidence = _evidence(
            flag_type=AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR,
            window_start=window_start,
            window_end=window_end,
            threshold_seconds=threshold_seconds,
            observed_seconds=observed,
            last_verified_activity_at=last_activity,
            eligible_trip_count=len(analytics),
        )
        await session.flush()
        if flag.status == AssignmentActivityFlagStatus.OPEN.value and observed >= threshold_seconds:
            recovered, notice = await _recover_flag(
                session,
                flag=flag,
                observed_seconds=observed,
                last_verified_activity_at=last_activity,
                eligible_trip_count=len(analytics),
                now=now,
            )
            return ("recovered" if recovered else "open"), 0, int(recovered), int(notice)
        return (
            "open" if flag.status == AssignmentActivityFlagStatus.OPEN.value else "recovered",
            0,
            0,
            0,
        )
    if observed >= threshold_seconds:
        return "healthy", 0, 0, 0
    _, opened, notice = await _open_flag(
        session,
        assignment=assignment,
        flag_type=AssignmentActivityFlagType.VERIFIED_HOURS_FLOOR,
        window_start=window_start,
        window_end=window_end,
        threshold_seconds=threshold_seconds,
        observed_seconds=observed,
        last_verified_activity_at=last_activity,
        eligible_trip_count=len(analytics),
        now=now,
    )
    return "opened", int(opened), 0, int(notice)


async def _evaluate_inactivity(
    session: AsyncSession,
    *,
    assignment: CampaignAssignment,
    now: datetime,
) -> tuple[str, int, int, int]:
    analytics = await _eligible_analytics(session, assignment=assignment, now=now)
    last_activity = max(
        (_utc(row.last_ping_at) for row in analytics if row.last_ping_at is not None),
        default=None,
    )
    baseline = last_activity or (
        _utc(assignment.activated_at) if assignment.activated_at is not None else None
    )
    if baseline is None or baseline > now:
        return "skipped_no_baseline", 0, 0, 0
    window_start = baseline
    window_end = baseline + INACTIVITY_WINDOW
    open_flags = list(
        (
            await session.scalars(
                select(AssignmentActivityFlag)
                .where(
                    AssignmentActivityFlag.assignment_id == assignment.id,
                    AssignmentActivityFlag.flag_type == AssignmentActivityFlagType.INACTIVITY.value,
                    AssignmentActivityFlag.status == AssignmentActivityFlagStatus.OPEN.value,
                )
                .order_by(AssignmentActivityFlag.window_start.desc())
                .with_for_update()
            )
        ).all()
    )
    recovered = 0
    notices = 0
    if last_activity is not None:
        for flag in open_flags:
            if last_activity > _utc(flag.window_start):
                changed, notice = await _recover_flag(
                    session,
                    flag=flag,
                    observed_seconds=sum(int(row.active_tracking_seconds) for row in analytics),
                    last_verified_activity_at=last_activity,
                    eligible_trip_count=len(analytics),
                    now=now,
                )
                recovered += int(changed)
                notices += int(notice)
    if now < window_end:
        return ("recovered" if recovered else "waiting"), 0, recovered, notices
    flag = await _find_flag(
        session,
        assignment_id=assignment.id,
        flag_type=AssignmentActivityFlagType.INACTIVITY,
        window_start=window_start,
        window_end=window_end,
    )
    if flag is not None:
        flag.last_evaluated_at = now
        flag.observed_seconds = sum(int(row.active_tracking_seconds) for row in analytics)
        flag.last_verified_activity_at = last_activity
        flag.current_evidence = _evidence(
            flag_type=AssignmentActivityFlagType.INACTIVITY,
            window_start=window_start,
            window_end=window_end,
            threshold_seconds=int(INACTIVITY_WINDOW.total_seconds()),
            observed_seconds=flag.observed_seconds,
            last_verified_activity_at=last_activity,
            eligible_trip_count=len(analytics),
        )
        await session.flush()
        return ("recovered" if recovered else flag.status), 0, recovered, notices
    _, opened, notice = await _open_flag(
        session,
        assignment=assignment,
        flag_type=AssignmentActivityFlagType.INACTIVITY,
        window_start=window_start,
        window_end=window_end,
        threshold_seconds=int(INACTIVITY_WINDOW.total_seconds()),
        observed_seconds=sum(int(row.active_tracking_seconds) for row in analytics),
        last_verified_activity_at=last_activity,
        eligible_trip_count=len(analytics),
        now=now,
    )
    return "opened", int(opened), 0, int(notice)


async def evaluate_assignment_activity(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate one active assignment under the campaign→assignment lock."""
    settings = settings or get_settings()
    threshold_seconds, skip_reason = parse_verified_hours_floor(settings)
    evaluation_now = _utc(now or await database_clock(session))
    assignment = await _locked_assignment(session, assignment_id)
    if assignment is None or assignment.status != CampaignAssignmentStatus.ACTIVE.value:
        return {
            "assignment_id": str(assignment_id),
            "weekly_floor": "skipped_assignment_state",
            "inactivity": "skipped_assignment_state",
            "flags_opened": 0,
            "flags_recovered": 0,
            "notices_created": 0,
            "skipped": 1,
            "skip_reason": "assignment_not_active",
            "errors": 0,
        }
    if threshold_seconds is None:
        weekly_state, weekly_opened, weekly_recovered, weekly_notices = (
            "skipped_configuration",
            0,
            0,
            0,
        )
    else:
        (
            weekly_state,
            weekly_opened,
            weekly_recovered,
            weekly_notices,
        ) = await _evaluate_weekly_floor(
            session,
            assignment=assignment,
            threshold_seconds=threshold_seconds,
            now=evaluation_now,
        )
    (
        inactivity_state,
        inactivity_opened,
        inactivity_recovered,
        inactivity_notices,
    ) = await _evaluate_inactivity(
        session,
        assignment=assignment,
        now=evaluation_now,
    )
    # Counts are derived from the two state transitions; no assignment or
    # financial table is written by this service.
    return {
        "assignment_id": str(assignment.id),
        "weekly_floor": weekly_state,
        "inactivity": inactivity_state,
        "flags_opened": weekly_opened + inactivity_opened,
        "flags_recovered": weekly_recovered + inactivity_recovered,
        "notices_created": weekly_notices + inactivity_notices,
        "skipped": int(weekly_state.startswith("skipped"))
        + int(inactivity_state.startswith("skipped")),
        "skip_reason": skip_reason,
        "errors": 0,
    }


async def sweep_activity_flags(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    assignment_ids: list[UUID],
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate one caller-bounded batch in isolated assignment transactions."""
    settings = settings or get_settings()
    _, skip_reason = parse_verified_hours_floor(settings)
    if skip_reason is not None:
        logger.warning(
            "job=sweep_activity_flags weekly_floor=skipped_configuration reason=%s",
            skip_reason,
        )
    if now is None:
        async with sessionmaker() as clock_session:
            evaluation_now = _utc(await database_clock(clock_session))
    else:
        evaluation_now = _utc(now)
    totals = {
        "selected": len(assignment_ids),
        "evaluated": 0,
        "flags_opened": 0,
        "flags_recovered": 0,
        "notices_created": 0,
        "skipped": 0,
        "errors": 0,
        "config": "skipped_weekly" if skip_reason is not None else "applied",
        "config_reason": skip_reason,
    }
    for assignment_id in assignment_ids:
        try:
            async with sessionmaker() as session:
                result = await evaluate_assignment_activity(
                    session,
                    assignment_id=assignment_id,
                    settings=settings,
                    now=evaluation_now,
                )
                await session.commit()
            # A missing/invalid weekly setting still evaluates the fixed
            # inactivity rule, so it is an evaluated assignment with one
            # skipped sub-rule rather than a skipped assignment.
            totals["evaluated"] += int(result.get("skip_reason") != "assignment_not_active")
            totals["flags_opened"] += int(result["flags_opened"])
            totals["flags_recovered"] += int(result["flags_recovered"])
            totals["notices_created"] += int(result["notices_created"])
            totals["skipped"] += int(result["skipped"])
        except Exception as exc:  # one assignment cannot poison the sweep
            totals["errors"] += 1
            logger.exception(
                "job=sweep_activity_flags assignment_id=%s outcome=error error_class=%s",
                assignment_id,
                type(exc).__name__,
            )
    logger.info(
        "job=sweep_activity_flags selected=%d evaluated=%d flags_opened=%d "
        "flags_recovered=%d notices_created=%d skipped=%d errors=%d",
        totals["selected"],
        totals["evaluated"],
        totals["flags_opened"],
        totals["flags_recovered"],
        totals["notices_created"],
        totals["skipped"],
        totals["errors"],
    )
    return totals


async def list_assignment_activity_flags(
    session: AsyncSession,
    *,
    assignment_id: UUID,
) -> list[AssignmentActivityFlag]:
    """Return current flag rows for an admin projection."""
    return list(
        (
            await session.scalars(
                select(AssignmentActivityFlag)
                .where(AssignmentActivityFlag.assignment_id == assignment_id)
                .order_by(
                    AssignmentActivityFlag.window_start.desc(),
                    AssignmentActivityFlag.flag_type,
                    AssignmentActivityFlag.id,
                )
            )
        ).all()
    )
