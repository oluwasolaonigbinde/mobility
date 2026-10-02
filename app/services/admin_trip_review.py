from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip import LocationPing, LocationPingBatch
from app.models.trip_analytics import FraudFlag
from app.schemas.trip_analytics import AdminTripRoutePointRead
from app.services.fraud_holds import fraud_hold_active_clause


@dataclass(frozen=True)
class HeldTripPay:
    amount: Decimal
    currency: str | None


async def read_held_trip_pay(session: AsyncSession, *, trip_id: UUID) -> HeldTripPay:
    active_hold = (
        select(FraudFlag.id)
        .where(FraudFlag.trip_session_id == trip_id, fraud_hold_active_clause())
        .exists()
    )
    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PENDING.value,
                    active_hold,
                )
            )
        ).all()
    )
    currencies = {entry.currency for entry in entries}
    if len(currencies) > 1:
        raise RuntimeError("one trip cannot have held earnings in multiple currencies")
    net = max(
        sum(
            (
                -entry.amount
                if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value
                else entry.amount
                for entry in entries
            ),
            Decimal("0"),
        ),
        Decimal("0"),
    )
    return HeldTripPay(net, next(iter(currencies), None) if net else None)


async def read_flag_route(
    session: AsyncSession, *, flag_id: UUID, limit: int, offset: int
) -> tuple[FraudFlag, list[AdminTripRoutePointRead], int]:
    flag = await session.get(FraudFlag, flag_id)
    if flag is None:
        raise AppError(
            status_code=404, code="FRAUD_FLAG_NOT_FOUND", message="Trip review not found"
        )
    query = (
        select(
            LocationPing.id, LocationPing.recorded_at, LocationPing.latitude, LocationPing.longitude
        )
        .join(LocationPingBatch, LocationPingBatch.id == LocationPing.batch_id)
        .where(
            LocationPing.trip_session_id == flag.trip_session_id,
            LocationPingBatch.trip_session_id == flag.trip_session_id,
        )
    )
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = (
        await session.execute(
            query.order_by(LocationPing.recorded_at, LocationPing.id).limit(limit).offset(offset)
        )
    ).all()
    return (
        flag,
        [
            AdminTripRoutePointRead(
                id=row.id,
                recorded_at=row.recorded_at,
                latitude=row.latitude,
                longitude=row.longitude,
            )
            for row in rows
        ],
        total,
    )
