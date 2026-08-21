import hashlib
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
        FraudFlagStatus.ACKNOWLEDGED.value,
        FraudFlagStatus.CONFIRMED.value,
    }
)
FRAUD_RECONCILIATION_GATE_KEY = int.from_bytes(
    hashlib.sha256(b"fraud-hold:route-reconciliation-gate").digest()[:8],
    byteorder="big",
    signed=True,
)
FRAUD_REVIEW_TRANSITIONS = {
    FraudFlagStatus.OPEN.value: frozenset({FraudFlagStatus.ACKNOWLEDGED.value}),
    FraudFlagStatus.ACKNOWLEDGED.value: frozenset(
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


def _trip_lock_key(trip_id: UUID) -> int:
    digest = hashlib.sha256(f"fraud-hold:trip:{trip_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _aware_utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


async def lock_fraud_reconciliation_gate(
    session: AsyncSession,
    *,
    exclusive: bool,
) -> None:
    """Gate cross-trip reconciliation against ordinary per-trip consumers."""
    if session.get_bind().dialect.name != "postgresql":
        return
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    await session.execute(
        text(f"SELECT {function}(:key)"),
        {"key": FRAUD_RECONCILIATION_GATE_KEY},
    )


async def lock_fraud_hold_scope(
    session: AsyncSession,
    trip_id: UUID,
    *,
    reconciliation_gate_held: bool = False,
) -> None:
    """Serialize detection, review, fraud-derived pricing and later release."""
    if not reconciliation_gate_held:
        await lock_fraud_reconciliation_gate(session, exclusive=False)
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _trip_lock_key(trip_id)},
        )
    await session.execute(
        select(TripSession.id).where(TripSession.id == trip_id).with_for_update()
    )


async def fraud_hold_counts(session: AsyncSession, trip_id: UUID) -> dict[str, int]:
    await lock_fraud_hold_scope(session, trip_id)
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
    return await session.scalar(
        select(FraudFlag).where(FraudFlag.id == flag_id).with_for_update()
    )


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
    # now-stale assessment. Assign the application timestamp explicitly rather
    # than relying on SQLite's lower-precision CURRENT_TIMESTAMP in tests.
    update_watermark = reviewed_at
    if flag.updated_at is not None and _aware_utc(update_watermark) <= _aware_utc(
        flag.updated_at
    ):
        update_watermark = _aware_utc(flag.updated_at) + timedelta(microseconds=1)
    flag.updated_at = update_watermark
    await session.flush()
    await session.refresh(flag)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=(
            "admin.fraud_flag.acknowledged"
            if target_status == FraudFlagStatus.ACKNOWLEDGED.value
            else "admin.fraud_flag.resolved"
        ),
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
    if target_status == FraudFlagStatus.CONFIRMED.value:
        from app.services.earnings_release import post_confirmed_fraud_reversal

        await post_confirmed_fraud_reversal(
            session,
            flag=flag,
            actor_user_id=actor_user_id,
            occurred_at=reviewed_at,
        )
    if target_status in {
        FraudFlagStatus.CONFIRMED.value,
        FraudFlagStatus.DISMISSED.value,
    }:
        await create_fraud_review_resolved_notice(session, flag)
    return FraudReviewResult(flag=flag, previous_status=previous_status, changed=True)


async def acknowledge_fraud_flag(
    session: AsyncSession,
    *,
    flag_id: UUID,
    actor_user_id: UUID,
    now: datetime | None = None,
) -> FraudReviewResult:
    return await _review_fraud_flag(
        session,
        flag_id=flag_id,
        actor_user_id=actor_user_id,
        target_status=FraudFlagStatus.ACKNOWLEDGED.value,
        resolution_note=None,
        now=now,
    )


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
        raise invalid_fraud_review_transition("acknowledged", outcome)
    return await _review_fraud_flag(
        session,
        flag_id=flag_id,
        actor_user_id=actor_user_id,
        target_status=outcome,
        resolution_note=resolution_note,
        now=now,
    )
