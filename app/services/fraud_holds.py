"""Fraud holds and the trip/money lock scopes.

Lock order (REQ-252). There is no system-wide lock. Every transaction takes
blocking locks in this order, each level sorted by ``str(uuid)`` (the same
order as PostgreSQL's uuid comparison):

0. Payout control row (``automatic_payouts`` run, ``disbursements`` claim).
1. Campaign terms keys (``payout_rule_serialization``): exclusive for terms,
   cancellation, trip processing and payout calculation; shared for ping
   ingestion and the advertiser read snapshot.
2. Driver fraud keys (``lock_driver_fraud_scopes``): only where a rule covers
   all of a driver's trips. An open dispute blocks every automatic payout for
   that driver, so dispute create/reply and the automatic run and claim take it.
3. Trip scopes (``lock_fraud_hold_scope(s)``): trip advisory key, then the trip
   row ``FOR UPDATE``.
4. Route-replay fingerprint keys.
5. Batch/line/intent and flag rows, then the driver money row
   (``lock_driver_money_scope``), then ledger rows, then payees.

Try-locks (``try_lock_fraud_hold_scope``) never wait, so they may be taken out
of this order. Route replay holds fingerprint keys and only try-locks other
group members; anyone else waiting on a fingerprint key therefore never forms
a cycle with it.

The advertiser read snapshot (``disclosure.lock_trip_disclosure_snapshot``)
freezes contributors with shared campaign keys plus ``FOR SHARE`` row locks.
That freeze holds only while every writer of trip analytics, impressions,
payout calculations, fraud flags or ledger rows takes either the exclusive
campaign key or the trip row ``FOR UPDATE`` first. Verified writers:
``evidence_verification`` (flag), ``impressions.estimate_trip_impressions``,
``payout_adjustments``, ``route_replay._write_replay_flag``,
``trip_analytics`` (analytics and flags), ``payouts.engine``,
``payouts.corrections`` and ``payouts.ledger``. A new writer must do the same.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.trip import TripSession
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
)
from app.services.audit import create_audit_event
from app.services.notifications import create_fraud_review_resolved_notice

HOLD_ACTIVE_STATUSES = frozenset(
    {
        FraudFlagStatus.OPEN.value,
        FraudFlagStatus.CONFIRMED.value,
    }
)
FRAUD_REVIEW_TRANSITIONS = {
    FraudFlagStatus.OPEN.value: frozenset(
        {FraudFlagStatus.CONFIRMED.value, FraudFlagStatus.DISMISSED.value}
    ),
    FraudFlagStatus.CONFIRMED.value: frozenset(),
    FraudFlagStatus.DISMISSED.value: frozenset(),
}


@dataclass(frozen=True)
class FraudReviewResult:
    flag: FraudFlag
    previous_status: str
    changed: bool


def hold_active(status_or_flag: str | FraudFlag) -> bool:
    status_value = (
        status_or_flag.status if isinstance(status_or_flag, FraudFlag) else status_or_flag
    )
    return status_value in HOLD_ACTIVE_STATUSES


def fraud_hold_active_clause(status_column=None):
    column = FraudFlag.status if status_column is None else status_column
    return column.in_(tuple(sorted(HOLD_ACTIVE_STATUSES)))


class FraudScopeBusy(Exception):
    """Another transaction holds a trip this one may only try-lock; retry later."""


def _signed_key(label: str) -> int:
    digest = hashlib.sha256(label.encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _trip_lock_key(trip_id: UUID) -> int:
    return _signed_key(f"fraud-hold:trip:{trip_id}")


def _driver_lock_key(driver_profile_id: UUID) -> int:
    return _signed_key(f"fraud-hold:driver:{driver_profile_id}")


def _aware_utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


async def lock_driver_fraud_scopes(
    session: AsyncSession,
    driver_profile_ids: Iterable[UUID],
) -> tuple[UUID, ...]:
    """Serialize driver-wide dispute rules; take before any trip scope."""
    ordered = tuple(sorted(set(driver_profile_ids), key=str))
    for driver_profile_id in ordered:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _driver_lock_key(driver_profile_id)},
        )
    return ordered


async def lock_fraud_hold_scope(session: AsyncSession, trip_id: UUID) -> None:
    """Serialize detection, review, fraud-derived pricing and later release."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": _trip_lock_key(trip_id)},
    )
    await session.execute(select(TripSession.id).where(TripSession.id == trip_id).with_for_update())


async def try_lock_fraud_hold_scope(session: AsyncSession, trip_id: UUID) -> None:
    """Take a trip scope without waiting, or raise ``FraudScopeBusy``."""
    acquired = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": _trip_lock_key(trip_id)},
    )
    if not acquired:
        raise FraudScopeBusy(str(trip_id))
    # The advisory key is ours, but a reader may share-lock the row; skip
    # rather than wait so this out-of-order lock can never join a cycle.
    locked = await session.scalar(
        select(TripSession.id).where(TripSession.id == trip_id).with_for_update(skip_locked=True)
    )
    if locked is None:
        raise FraudScopeBusy(str(trip_id))


async def lock_fraud_hold_scopes(
    session: AsyncSession,
    trip_ids: Iterable[UUID],
) -> tuple[UUID, ...]:
    """Lock a multi-trip money decision under one stable global order."""
    ordered_trip_ids = tuple(sorted(set(trip_ids), key=str))
    for trip_id in ordered_trip_ids:
        await lock_fraud_hold_scope(session, trip_id)
    return ordered_trip_ids


async def active_fraud_hold_counts(session: AsyncSession, trip_id: UUID) -> dict[str, int]:
    """Count active holds without locking; for reads and callers holding the scope."""
    result = await session.execute(
        select(FraudFlag.severity, func.count(FraudFlag.id))
        .where(
            FraudFlag.trip_session_id == trip_id,
            fraud_hold_active_clause(),
        )
        .group_by(FraudFlag.severity)
    )
    counts = {severity.value: 0 for severity in FraudFlagSeverity}
    for severity, count in result.all():
        counts[str(severity)] = int(count)
    return counts


async def fraud_hold_counts(session: AsyncSession, trip_id: UUID) -> dict[str, int]:
    """Lock the trip scope, then count; for money decisions."""
    await lock_fraud_hold_scope(session, trip_id)
    return await active_fraud_hold_counts(session, trip_id)


def fraud_flag_not_found() -> AppError:
    return AppError(
        "FRAUD_FLAG_NOT_FOUND",
        "Fraud flag was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def invalid_fraud_review_transition(current_status: str, target_status: str) -> AppError:
    return AppError(
        "FRAUD_FLAG_INVALID_TRANSITION",
        "The fraud flag cannot make that review transition",
        status_code=status.HTTP_409_CONFLICT,
        details={"current_status": current_status, "target_status": target_status},
    )


def fraud_review_replay_conflict(current_status: str, target_status: str) -> AppError:
    return AppError(
        "FRAUD_FLAG_REVIEW_REPLAY_CONFLICT",
        "The completed fraud review does not match this retry",
        status_code=status.HTTP_409_CONFLICT,
        details={"current_status": current_status, "target_status": target_status},
    )


async def _flag_stub(session: AsyncSession, flag_id: UUID) -> tuple[UUID, UUID] | None:
    row = (
        await session.execute(
            select(FraudFlag.id, FraudFlag.trip_session_id).where(FraudFlag.id == flag_id)
        )
    ).one_or_none()
    return (row.id, row.trip_session_id) if row is not None else None


async def _locked_flag(session: AsyncSession, flag_id: UUID) -> FraudFlag | None:
    return await session.scalar(select(FraudFlag).where(FraudFlag.id == flag_id).with_for_update())


async def _review_fraud_flag(
    session: AsyncSession,
    *,
    flag_id: UUID,
    actor_user_id: UUID,
    target_status: str,
    resolution_note: str | None,
    now: datetime | None,
) -> FraudReviewResult:
    stub = await _flag_stub(session, flag_id)
    if stub is None:
        raise fraud_flag_not_found()
    await lock_fraud_hold_scope(session, stub[1])
    flag = await _locked_flag(session, flag_id)
    if flag is None:
        raise fraud_flag_not_found()

    normalized_note = resolution_note.strip() if resolution_note is not None else None
    previous_status = flag.status
    if previous_status == target_status:
        if (
            flag.reviewed_by_user_id == actor_user_id
            and flag.reviewed_at is not None
            and flag.resolution_note == normalized_note
        ):
            return FraudReviewResult(flag=flag, previous_status=previous_status, changed=False)
        raise fraud_review_replay_conflict(previous_status, target_status)

    if target_status not in FRAUD_REVIEW_TRANSITIONS.get(previous_status, frozenset()):
        raise invalid_fraud_review_transition(previous_status, target_status)

    reviewed_at = now or datetime.now(UTC)
    flag.status = target_status
    flag.reviewed_by_user_id = actor_user_id
    flag.reviewed_at = reviewed_at
    flag.resolution_note = normalized_note
    # The DB-derived worker sweep uses the flag update watermark to reselect a
    # now-stale assessment. Keep this watermark strictly increasing even if
    # the injected review time precedes the prior database timestamp.
    update_watermark = reviewed_at
    if flag.updated_at is not None and _aware_utc(update_watermark) <= _aware_utc(flag.updated_at):
        update_watermark = _aware_utc(flag.updated_at) + timedelta(microseconds=1)
    flag.updated_at = update_watermark
    await session.flush()
    await session.refresh(flag)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.fraud_flag.resolved",
        entity_type="fraud_flag",
        entity_id=str(flag.id),
        metadata={
            "status_before": previous_status,
            "status_after": target_status,
            "trip_session_id": str(flag.trip_session_id),
            "campaign_id": str(flag.campaign_id),
            "driver_profile_id": str(flag.driver_profile_id),
            "flag_type": flag.flag_type,
            "severity": flag.severity,
            "resolution_note": normalized_note,
        },
    )
    if target_status in {
        FraudFlagStatus.CONFIRMED.value,
        FraudFlagStatus.DISMISSED.value,
    }:
        await create_fraud_review_resolved_notice(session, flag)
    return FraudReviewResult(flag=flag, previous_status=previous_status, changed=True)


async def resolve_fraud_flag(
    session: AsyncSession,
    *,
    flag_id: UUID,
    actor_user_id: UUID,
    outcome: str,
    resolution_note: str,
    now: datetime | None = None,
) -> FraudReviewResult:
    if outcome not in {
        FraudFlagStatus.CONFIRMED.value,
        FraudFlagStatus.DISMISSED.value,
    }:
        raise invalid_fraud_review_transition("open", outcome)
    return await _review_fraud_flag(
        session,
        flag_id=flag_id,
        actor_user_id=actor_user_id,
        target_status=outcome,
        resolution_note=resolution_note,
        now=now,
    )
