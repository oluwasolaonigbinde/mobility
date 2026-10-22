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
from app.services.payout_balances import lock_driver_money_scope
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

    driver_scope = (
        await session.execute(
            select(
                EarningsLedgerEntry.driver_profile_id,
                EarningsLedgerEntry.currency,
            )
            .where(EarningsLedgerEntry.trip_session_id == trip_id)
            .limit(1)
        )
    ).one_or_none()
    if driver_scope is not None:
        await lock_driver_money_scope(
            session,
            driver_profile_id=driver_scope.driver_profile_id,
            currency=driver_scope.currency,
        )

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
        from app.models.notification import NotificationType
        from app.services.notifications import create_driver_business_notification

        await create_driver_business_notification(
            session,
            driver_profile_id=released[0].driver_profile_id,
            type_key=NotificationType.PAYOUT_RELEASED,
            event_key=f"payout:released:v1:{trip_id}",
            payload={"trip_session_id": str(trip_id)},
            manual_contact_purpose="earnings_release",
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
        or flag.status not in {FraudFlagStatus.OPEN.value}
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
                    FraudFlag.status.in_((FraudFlagStatus.OPEN.value,)),
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
    return FraudFlagMoneyEffect(
        available_net=net,
        currency=next(iter(currencies), None),
    )
