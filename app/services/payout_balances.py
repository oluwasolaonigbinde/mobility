"""Computed trip worth, verified cash and final recovery offsets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disbursement import PayoutBatchLine, PayoutRecoveryOffset, PayoutSubmissionIntent
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
    offsets_funded: Decimal = ZERO
    offsets_received: Decimal = ZERO
    offset_at: datetime | None = None

    @property
    def debt(self) -> Decimal:
        return max(self.settled - self.earned_net, ZERO)

    @property
    def settled(self) -> Decimal:
        return self.cash_paid + self.offsets_funded - self.offsets_received


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


def _trip_awards(entries):
    """Trip worth is recomputed pay less explicit deductions, floored at zero."""
    from app.services.payouts.common import is_manual_deduction

    earned = ZERO
    manual_deductions = ZERO
    released = ZERO
    negatives = ZERO
    for entry in entries:
        if entry.status == "voided":
            continue
        if entry.entry_type == "reversal":
            negatives += entry.amount
            if is_manual_deduction(entry):
                manual_deductions += entry.amount
            else:
                earned -= entry.amount
        else:
            earned += entry.amount
            if entry.status in {"available", "paid"}:
                released += entry.amount
    return max(earned - manual_deductions, ZERO), released, negatives


def trip_cash_position(
    entries, line_rows, *, offsets_funded=ZERO, offsets_received=ZERO, offset_at=None
) -> TripMoneyPosition:
    earned, released, negatives = _trip_awards(entries)
    paid = ZERO
    reserved = ZERO
    in_flight = ZERO
    failed = ZERO
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
    position = TripMoneyPosition(
        cash_paid=paid, offsets_funded=offsets_funded, offsets_received=offsets_received
    )
    released_net = max(min(released - negatives, earned), ZERO)
    remaining = max(released_net - position.settled, ZERO)
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
        offsets_funded=offsets_funded,
        offsets_received=offsets_received,
        offset_at=offset_at,
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
    offsets = (
        await session.execute(
            select(PayoutRecoveryOffset, EarningsLedgerEntry.trip_session_id)
            .join(
                EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutRecoveryOffset.funding_entry_id
            )
            .where(
                EarningsLedgerEntry.status != "voided",
                or_(
                    PayoutRecoveryOffset.source_trip_id.in_([scope[0] for scope in by_trip]),
                    PayoutRecoveryOffset.funding_entry_id.in_(trip_by_entry),
                ),
            )
        )
    ).all()
    funded, received, times = {}, {}, {}
    for offset, funding_trip in offsets:
        source_scope = (offset.source_trip_id, offset.currency)
        funding_scope = (funding_trip, offset.currency)
        received[source_scope] = received.get(source_scope, ZERO) + offset.amount
        funded[funding_scope] = funded.get(funding_scope, ZERO) + offset.amount
        times[funding_scope] = max(times.get(funding_scope, offset.created_at), offset.created_at)
    return {
        trip_id: trip_cash_position(
            trip_entries,
            lines_by_trip.get(trip_id, []),
            offsets_funded=funded.get(trip_id, ZERO),
            offsets_received=received.get(trip_id, ZERO),
            offset_at=times.get(trip_id),
        )
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
            for field in DriverMoneyBalance.__dataclass_fields__
            if field not in {"driver_profile_id", "currency"}
        },
    )


async def driver_recovery_positions(session, *, driver_profile_id, currency):
    entries = list(
        (
            await session.scalars(
                select(EarningsLedgerEntry)
                .where(
                    EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                    EarningsLedgerEntry.currency == currency,
                )
                .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
            )
        ).all()
    )
    return await trip_money_positions(session, entries)


async def allocate_payout_recovery(
    session, *, entry, payable, request_id, actor_user_id=None, automatic_run_id=None
):
    """Caller holds the driver money row. Offsets are final on insertion."""
    from app.services.audit import create_audit_event

    positions = await driver_recovery_positions(
        session, driver_profile_id=entry.driver_profile_id, currency=entry.currency
    )
    remaining = payable
    for (trip_id, currency), position in positions.items():
        if trip_id == entry.trip_session_id or position.debt <= ZERO:
            continue
        amount = min(remaining, position.debt)
        if amount <= ZERO:
            break
        offset = PayoutRecoveryOffset(
            source_trip_id=trip_id,
            funding_entry_id=entry.id,
            driver_profile_id=entry.driver_profile_id,
            currency=currency,
            amount=amount,
            request_id=request_id,
            actor_user_id=actor_user_id,
            automatic_run_id=automatic_run_id,
        )
        session.add(offset)
        await session.flush()
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="system.payout.recovery_offset"
            if automatic_run_id
            else "admin.payout.recovery_offset",
            entity_type="payout_recovery_offset",
            entity_id=str(offset.id),
            metadata={
                "source_trip_id": str(trip_id),
                "funding_entry_id": str(entry.id),
                "amount": str(amount),
                "currency": currency,
                "request_id": str(request_id),
            },
        )
        remaining -= amount
    if remaining == ZERO:
        entry.status = "paid"
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="system.earnings.offset_settled"
            if automatic_run_id
            else "admin.earnings.offset_settled",
            entity_type="earnings_ledger_entry",
            entity_id=str(entry.id),
            metadata={
                "amount": str(payable),
                "currency": entry.currency,
                "settled_at": datetime.now(UTC).isoformat(),
            },
        )
    return remaining
