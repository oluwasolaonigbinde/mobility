from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.services.audit import create_audit_event
from app.services.fraud_assessments import load_current_successful_assessment
from app.services.fraud_holds import fraud_hold_active_clause, lock_fraud_hold_scope
from app.services.payout_rule_serialization import database_clock


@dataclass(frozen=True)
class EarningsReleaseResult:
    trip_id: UUID
    released_entry_ids: tuple[UUID, ...]
    assessment_current: bool
    hold_active: bool


@dataclass(frozen=True)
class FraudFlagMoneyEffect:
    available_net: Decimal
    currency: str | None
    reversal_entry_id: UUID | None
    reversal_recommended: bool


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def find_pending_release_trip_ids(
    session: AsyncSession,
    *,
    limit: int,
    after: UUID | None = None,
) -> list[UUID]:
    if limit <= 0:
        return []
    now = await database_clock(session)
    filters = [
        EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PENDING.value,
        EarningsLedgerEntry.trip_session_id.is_not(None),
        or_(
            EarningsLedgerEntry.release_at.is_(None),
            EarningsLedgerEntry.release_at <= now,
        ),
    ]
    if after is not None:
        filters.append(EarningsLedgerEntry.trip_session_id > after)
    rows = await session.scalars(
        select(EarningsLedgerEntry.trip_session_id)
        .where(*filters)
        .distinct()
        .order_by(EarningsLedgerEntry.trip_session_id)
        .limit(limit)
    )
    return [trip_id for trip_id in rows if trip_id is not None]


async def release_pending_earnings_for_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
) -> EarningsReleaseResult:
    """Apply the one assessment/hold release authority under the trip lock."""
    await lock_fraud_hold_scope(session, trip_id)
    now = await database_clock(session)
    assessment = await load_current_successful_assessment(
        session,
        trip_id=trip_id,
        settings=settings,
    )
    active_hold = bool(
        await session.scalar(
            select(FraudFlag.id)
            .where(
                FraudFlag.trip_session_id == trip_id,
                fraud_hold_active_clause(),
            )
            .limit(1)
        )
    )
    if not assessment.current or active_hold:
        return EarningsReleaseResult(trip_id, (), assessment.current, active_hold)

    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PENDING.value,
                )
                .order_by(EarningsLedgerEntry.id)
                .with_for_update()
            )
        ).all()
    )
    released = [
        entry
        for entry in entries
        if entry.release_at is None or _utc(entry.release_at) <= _utc(now)
    ]
    for entry in released:
        entry.status = EarningsLedgerEntryStatus.AVAILABLE.value
    if released:
        await session.flush()
        await create_audit_event(
            session,
            actor_user_id=None,
            action="worker.earnings.released",
            entity_type="trip_session",
            entity_id=str(trip_id),
            metadata={
                "released_at": now.isoformat(),
                "ledger_entry_ids": [str(entry.id) for entry in released],
            },
        )
    return EarningsReleaseResult(
        trip_id,
        tuple(entry.id for entry in released),
        True,
        False,
    )


async def escalate_fraud_flag_if_due(
    session: AsyncSession,
    *,
    flag_id: UUID,
    review_sla_days: int,
) -> bool:
    if review_sla_days <= 0:
        raise ValueError("review_sla_days must be positive")
    stub = (
        await session.execute(
            select(FraudFlag.id, FraudFlag.trip_session_id).where(FraudFlag.id == flag_id)
        )
    ).one_or_none()
    if stub is None:
        return False
    await lock_fraud_hold_scope(session, stub.trip_session_id)
    now = await database_clock(session)
    flag = await session.scalar(select(FraudFlag).where(FraudFlag.id == flag_id).with_for_update())
    if (
        flag is None
        or flag.status not in {FraudFlagStatus.OPEN.value, FraudFlagStatus.ACKNOWLEDGED.value}
        or flag.escalated_at is not None
        or _utc(now) < _utc(flag.detected_at) + timedelta(days=review_sla_days)
    ):
        return False
    flag.escalated_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=None,
        action="worker.fraud_flag.review_escalated",
        entity_type="fraud_flag",
        entity_id=str(flag.id),
        metadata={
            "trip_session_id": str(flag.trip_session_id),
            "status": flag.status,
            "detected_at": flag.detected_at.isoformat(),
            "escalated_at": now.isoformat(),
            "review_sla_days": review_sla_days,
        },
    )
    return True


async def find_due_fraud_flag_ids(
    session: AsyncSession,
    *,
    review_sla_days: int,
    limit: int,
) -> list[UUID]:
    if review_sla_days <= 0:
        raise ValueError("review_sla_days must be positive")
    if limit <= 0:
        return []
    now = await database_clock(session)
    return list(
        (
            await session.scalars(
                select(FraudFlag.id)
                .where(
                    FraudFlag.status.in_(
                        (FraudFlagStatus.OPEN.value, FraudFlagStatus.ACKNOWLEDGED.value)
                    ),
                    FraudFlag.escalated_at.is_(None),
                    FraudFlag.detected_at <= now - timedelta(days=review_sla_days),
                )
                .order_by(FraudFlag.detected_at, FraudFlag.id)
                .limit(limit)
            )
        ).all()
    )


async def fraud_flag_money_effect(
    session: AsyncSession,
    *,
    flag: FraudFlag,
    lock_entries: bool = False,
) -> FraudFlagMoneyEffect:
    statement = (
        select(EarningsLedgerEntry)
        .where(
            EarningsLedgerEntry.trip_session_id == flag.trip_session_id,
            EarningsLedgerEntry.status.in_(
                (
                    EarningsLedgerEntryStatus.AVAILABLE.value,
                    EarningsLedgerEntryStatus.PAID.value,
                )
            ),
        )
        .order_by(EarningsLedgerEntry.id)
    )
    if lock_entries:
        statement = statement.with_for_update()
    entries = list((await session.scalars(statement)).all())
    currencies = {entry.currency for entry in entries}
    if len(currencies) > 1:
        raise RuntimeError("one trip cannot have available earnings in multiple currencies")
    net = sum(
        (
            -entry.amount
            if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value
            else entry.amount
            for entry in entries
        ),
        Decimal("0"),
    )
    reversal = next(
        (entry for entry in entries if entry.source_fraud_flag_id == flag.id),
        None,
    )
    return FraudFlagMoneyEffect(
        available_net=net,
        currency=next(iter(currencies), None),
        reversal_entry_id=reversal.id if reversal is not None else None,
        reversal_recommended=(
            flag.status != FraudFlagStatus.DISMISSED.value and reversal is None and net > 0
        ),
    )


async def post_confirmed_fraud_reversal(
    session: AsyncSession,
    *,
    flag: FraudFlag,
    actor_user_id: UUID,
    occurred_at: datetime,
) -> EarningsLedgerEntry | None:
    """Post one positive, subtract-by-type reversal while the trip scope is held."""
    if flag.status != FraudFlagStatus.CONFIRMED.value:
        return None
    effect = await fraud_flag_money_effect(session, flag=flag, lock_entries=True)
    if not effect.reversal_recommended:
        return None
    source = await session.scalar(
        select(EarningsLedgerEntry)
        .where(
            EarningsLedgerEntry.trip_session_id == flag.trip_session_id,
            EarningsLedgerEntry.status.in_(
                (
                    EarningsLedgerEntryStatus.AVAILABLE.value,
                    EarningsLedgerEntryStatus.PAID.value,
                )
            ),
            EarningsLedgerEntry.entry_type != EarningsLedgerEntryType.REVERSAL.value,
        )
        .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
        .limit(1)
    )
    if source is None or effect.currency is None:
        return None
    reversal = EarningsLedgerEntry(
        payout_calculation_id=None,
        driver_profile_id=source.driver_profile_id,
        driver_user_id=source.driver_user_id,
        campaign_id=source.campaign_id,
        trip_session_id=source.trip_session_id,
        vehicle_id=source.vehicle_id,
        entry_type=EarningsLedgerEntryType.REVERSAL.value,
        status=EarningsLedgerEntryStatus.AVAILABLE.value,
        amount=effect.available_net,
        currency=effect.currency,
        description="Confirmed post-release fraud reversal",
        occurred_at=occurred_at,
        source_fraud_flag_id=flag.id,
        ledger_metadata={"source_fraud_flag_id": str(flag.id)},
    )
    session.add(reversal)
    await session.flush()
    from app.services.payout_debt import record_reversal_obligation

    await record_reversal_obligation(session, reversal_entry=reversal)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.fraud_flag.available_earnings_reversed",
        entity_type="fraud_flag",
        entity_id=str(flag.id),
        metadata={
            "trip_session_id": str(flag.trip_session_id),
            "ledger_entry_id": str(reversal.id),
            "amount": str(reversal.amount),
            "currency": reversal.currency,
        },
    )
    return reversal
