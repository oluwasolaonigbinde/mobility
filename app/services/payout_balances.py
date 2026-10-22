"""Trip-local cash authority; a negative adjustment never reduces another trip."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disbursement import PayoutBatchLine, PayoutSubmissionIntent
from app.models.driver import DriverProfile
from app.models.payout import EarningsLedgerEntry

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class TripMoneyPosition:
    unpaid_authority: Decimal = ZERO
    earned_net: Decimal = ZERO
    released_available: Decimal = ZERO
    reserved: Decimal = ZERO
    in_flight: Decimal = ZERO
    terminal_failed: Decimal = ZERO
    cash_paid: Decimal = ZERO
    batch_payable: Decimal = ZERO


@dataclass(frozen=True)
class DriverMoneyBalance:
    driver_profile_id: UUID
    currency: str
    earned_net: Decimal
    released_available: Decimal
    reserved: Decimal
    in_flight: Decimal
    terminal_failed: Decimal
    cash_paid: Decimal
    batch_payable: Decimal


async def lock_driver_money_scope(
    session: AsyncSession, *, driver_profile_id: UUID, currency: str
) -> DriverProfile:
    """Keep cash, adjustments and reservations serialized on the driver's row."""
    profile = await session.scalar(
        select(DriverProfile).where(DriverProfile.id == driver_profile_id).with_for_update()
    )
    if profile is None:
        raise ValueError("Driver profile was not found")
    return profile


def trip_cash_position(entries, line_rows) -> TripMoneyPosition:
    earned = ZERO
    released = ZERO
    negatives = ZERO
    paid = ZERO
    reserved = ZERO
    in_flight = ZERO
    failed = ZERO
    for entry in entries:
        if entry.status == "voided":
            continue
        if entry.entry_type == "reversal":
            negatives += entry.amount
            earned -= entry.amount
        else:
            earned += entry.amount
            if entry.status in {"available", "paid"}:
                released += entry.amount
    predecessor_ids = {
        line.predecessor_line_id for line, _ in line_rows if line.predecessor_line_id is not None
    }
    for line, intent in line_rows:
        if line.status == "succeeded":
            # Count every real transfer, including an eventual duplicate success.
            paid += line.amount
        elif line.reservation_active:
            if line.status == "submitted" or (
                intent is not None and intent.state in {"claimed", "query_only"}
            ):
                in_flight += line.amount
            else:
                reserved += line.amount
        elif line.status == "failed" and line.id not in predecessor_ids:
            failed += line.amount
    remaining = max(released - negatives - paid, ZERO)
    payable = max(remaining - reserved - in_flight, ZERO)
    return TripMoneyPosition(
        earned_net=earned,
        unpaid_authority=remaining,
        released_available=payable - min(failed, payable),
        reserved=reserved,
        in_flight=in_flight,
        terminal_failed=min(failed, payable),
        cash_paid=paid,
        batch_payable=payable,
    )


async def trip_money_positions(
    session: AsyncSession, entries
) -> dict[tuple[UUID, str], TripMoneyPosition]:
    if not entries:
        return {}
    rows = (
        await session.execute(
            select(PayoutBatchLine, PayoutSubmissionIntent)
            .outerjoin(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
            )
            .where(PayoutBatchLine.ledger_entry_id.in_([entry.id for entry in entries]))
        )
    ).all()
    by_trip = {}
    trip_by_entry = {}
    for entry in entries:
        by_trip.setdefault((entry.trip_session_id, entry.currency), []).append(entry)
        trip_by_entry[entry.id] = (entry.trip_session_id, entry.currency)
    lines_by_trip = {}
    for line, intent in rows:
        lines_by_trip.setdefault(trip_by_entry[line.ledger_entry_id], []).append((line, intent))
    return {
        trip_id: trip_cash_position(trip_entries, lines_by_trip.get(trip_id, []))
        for trip_id, trip_entries in by_trip.items()
    }


async def trip_money_position(
    session: AsyncSession, *, trip_session_id: UUID, currency: str
) -> TripMoneyPosition:
    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_session_id,
                    EarningsLedgerEntry.currency == currency,
                )
            )
        ).all()
    )
    return (await trip_money_positions(session, entries)).get(
        (trip_session_id, currency), TripMoneyPosition()
    )


async def driver_money_balance(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    currency: str,
    campaign_id: UUID | None = None,
) -> DriverMoneyBalance:
    normalized = currency.strip().upper()
    query = select(EarningsLedgerEntry).where(
        EarningsLedgerEntry.driver_profile_id == driver_profile_id,
        EarningsLedgerEntry.currency == normalized,
    )
    if campaign_id is not None:
        query = query.where(EarningsLedgerEntry.campaign_id == campaign_id)
    positions = (
        await trip_money_positions(session, list((await session.scalars(query)).all()))
    ).values()
    return DriverMoneyBalance(
        driver_profile_id=driver_profile_id,
        currency=normalized,
        **{
            field: sum((getattr(position, field) for position in positions), ZERO)
            for field in TripMoneyPosition.__dataclass_fields__
            if field != "unpaid_authority"
        },
    )
