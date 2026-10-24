"""Staff-recorded negative adjustments, appended to the original trip ledger."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSession
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.disbursements import (
    _reason,
    cancel_uncalled_trip_payouts,
    lock_payout_chains,
)
from app.services.fraud_holds import lock_fraud_hold_scope
from app.services.payout_balances import lock_driver_money_scope
from app.services.payouts.common import lagos_day_for


def _adjustment_day(trip: TripSession, requested: date | None) -> date:
    first = lagos_day_for(trip.started_at)
    last = lagos_day_for(trip.ended_at or trip.started_at)
    if requested is None:
        if first != last:
            raise AppError(
                "PAYOUT_ADJUSTMENT_DAY_REQUIRED",
                "Choose the Nigeria day to correct; this trip spans more than one day",
                status_code=422,
            )
        return first
    if not first <= requested <= last:
        raise AppError(
            "PAYOUT_ADJUSTMENT_DAY_INVALID",
            "Choose a Nigeria day within this trip",
            status_code=422,
        )
    return requested


async def record_negative_adjustment(
    session: AsyncSession,
    *,
    source_entry_id: UUID,
    request_id: UUID,
    amount: Decimal,
    currency: str,
    reason: str,
    actor_user_id: UUID,
    lagos_day: date | None = None,
) -> EarningsLedgerEntry:
    await require_active_admin(session, actor_user_id)
    reason = _reason(reason)
    if (
        not amount.is_finite()
        or not Decimal("0") < amount <= Decimal("999999999999.99")
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise AppError(
            "PAYOUT_ADJUSTMENT_AMOUNT_INVALID",
            "Enter a positive amount with at most two decimal places",
            status_code=422,
        )
    source = await session.get(EarningsLedgerEntry, source_entry_id)
    if source is None:
        raise AppError(
            "EARNINGS_LEDGER_ENTRY_NOT_FOUND", "Earnings ledger entry not found", status_code=404
        )
    if (
        source.trip_session_id is None
        or source.entry_type == "reversal"
        or source.status == "voided"
    ):
        raise AppError(
            "PAYOUT_ADJUSTMENT_SOURCE_INVALID", "Choose an existing trip credit", status_code=409
        )
    if currency != source.currency:
        raise AppError(
            "PAYOUT_ADJUSTMENT_CURRENCY_INVALID",
            "Use the source credit's currency",
            status_code=422,
        )
    await lock_fraud_hold_scope(session, source.trip_session_id)
    trip = await session.get(TripSession, source.trip_session_id)
    assert trip is not None  # The immutable source credit retains its trip FK.
    lagos_day = _adjustment_day(trip, lagos_day)
    chain = await lock_payout_chains(session, trip_ids=(source.trip_session_id,))
    await lock_driver_money_scope(
        session, driver_profile_id=source.driver_profile_id, currency=currency
    )
    source = await session.scalar(
        select(EarningsLedgerEntry)
        .where(
            EarningsLedgerEntry.id == source_entry_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert source is not None and source.trip_session_id is not None
    if source.status == "voided":
        raise AppError(
            "PAYOUT_ADJUSTMENT_SOURCE_INVALID", "Choose an existing trip credit", status_code=409
        )
    metadata = {
        "source_entry_id": str(source.id),
        "reason": reason,
        "actor_user_id": str(actor_user_id),
        "lagos_day": lagos_day.isoformat(),
    }
    existing = await session.get(EarningsLedgerEntry, request_id, populate_existing=True)
    if existing is not None:
        if (
            existing.entry_type != "reversal"
            or existing.amount != amount
            or existing.currency != currency
            or existing.ledger_metadata != metadata
        ):
            raise AppError(
                "PAYOUT_ADJUSTMENT_RETRY_CONFLICT",
                "This adjustment reference has different details",
                status_code=409,
            )
        return existing
    now = datetime.now(UTC)
    entry = EarningsLedgerEntry(
        id=request_id,
        payout_calculation_id=None,
        driver_profile_id=source.driver_profile_id,
        driver_user_id=source.driver_user_id,
        campaign_id=source.campaign_id,
        trip_session_id=source.trip_session_id,
        vehicle_id=source.vehicle_id,
        entry_type="reversal",
        status="available",
        amount=amount,
        currency=currency,
        description="Manual negative adjustment",
        occurred_at=now,
        ledger_metadata=metadata,
    )
    try:
        async with session.begin_nested():
            session.add(entry)
            await session.flush()
    except IntegrityError as exc:
        if integrity_constraint_name(exc) != "earnings_ledger_entries_pkey":
            raise
        raise AppError(
            "PAYOUT_ADJUSTMENT_RETRY_CONFLICT",
            "This adjustment reference is already used",
            status_code=409,
        ) from exc
    await cancel_uncalled_trip_payouts(
        session,
        trip_id=source.trip_session_id,
        chain_authority=chain,
        resolved_at=now,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.earnings.negative_adjustment",
        entity_type="earnings_ledger_entry",
        entity_id=str(entry.id),
        metadata={**metadata, "amount": str(amount), "currency": currency},
    )
    return entry
