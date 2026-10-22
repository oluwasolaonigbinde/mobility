"""Payouts: breakdown domain operations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
)
from app.models.trip import TripSession
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.impressions import (
    quantize_2,
)
from app.services.payouts.common import PAYOUT_V4, payout_calculation_not_found
from app.services.payouts.ledger import existing_payout_calculation_for_trip_any_formula
from app.services.trips import trip_not_found


@dataclass(frozen=True)
class DriverTripBreakdown:
    trip_session_id: UUID
    formula_version: str
    currency: str
    amount: Decimal
    eligible_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    superseded_by_recompute: bool
    entries: list[EarningsLedgerEntry]
    # payout_v4: (Lagos day, whole metres counted, pay this trip added).
    daily_rate_days: list[tuple[date, int, Decimal]] | None = None


def _daily_rate_days(
    distance_m_by_day: object,
    amount_by_day: object,
) -> list[tuple[date, int, Decimal]] | None:
    """Parse a stored payout_v4 per-day position; None when malformed."""
    if not isinstance(distance_m_by_day, dict) or not isinstance(amount_by_day, dict):
        return None
    try:
        days = []
        for key in sorted(set(distance_m_by_day) | set(amount_by_day)):
            metres = int(distance_m_by_day.get(key, 0) or 0)
            amount = Decimal(str(amount_by_day.get(key, "0.00")))
            if metres < 0 or amount < 0:
                return None
            days.append((date.fromisoformat(key), metres, quantize_2(amount)))
    except (ArithmeticError, TypeError, ValueError):
        return None
    return days


def _recompute_explanation_from_stored_metadata(
    source: dict,
) -> tuple[int | None, dict[str, int] | None] | None:
    """Validate the paired driver-explanation values on a recompute entry.

    Legacy entries did not store exclusion reasons. They remain authoritative
    for their stored eligible seconds, but the missing reason map is unknown —
    it must never fall back to the superseded calculation's stale reasons.
    """
    eligible_raw = source.get("eligible_seconds")
    if eligible_raw is None:
        eligible_seconds = None
    elif type(eligible_raw) is int and eligible_raw >= 0:
        eligible_seconds = eligible_raw
    else:
        return None

    if "excluded_seconds_by_reason" not in source:
        return eligible_seconds, None
    excluded_raw = source["excluded_seconds_by_reason"]
    if not isinstance(excluded_raw, dict):
        return None
    excluded: dict[str, int] = {}
    for reason, seconds in excluded_raw.items():
        if not isinstance(reason, str) or not reason or type(seconds) is not int or seconds < 0:
            return None
        excluded[reason] = seconds
    return eligible_seconds, excluded


async def driver_trip_earnings_breakdown(
    session: AsyncSession,
    *,
    user_id: UUID,
    trip_id: UUID,
) -> DriverTripBreakdown:
    """Driver transparency surface (next-steps S1 decision 8): verified time,
    exclusions by reason, rate, capped time, amount, and cap progress — always
    from the payout calculation (never trip_analytics). The displayed amount
    is the sum of posted entries; after a day true-up the newest differential
    entry's stored breakdown supersedes the calculation row so
    rate x capped time == amount still holds."""
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    trip = await session.get(TripSession, trip_id)
    if trip is None or trip.driver_profile_id != profile.id:
        raise trip_not_found()

    entries_result = await session.execute(
        select(EarningsLedgerEntry)
        .where(
            EarningsLedgerEntry.trip_session_id == trip.id,
            EarningsLedgerEntry.driver_profile_id == profile.id,
        )
        .order_by(
            EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.created_at, EarningsLedgerEntry.id
        )
    )
    entries = list(entries_result.scalars().all())
    calculation = await existing_payout_calculation_for_trip_any_formula(session, trip_id=trip.id)
    if calculation is None and not entries:
        raise payout_calculation_not_found()

    currency = calculation.currency if calculation is not None else entries[0].currency
    amount = Decimal("0.00")
    for entry in entries:
        if entry.status == EarningsLedgerEntryStatus.VOIDED.value:
            continue
        if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value:
            amount -= entry.amount
        else:
            amount += entry.amount
    amount = quantize_2(amount)
    formula_version = calculation.formula_version if calculation else PAYOUT_V4
    eligible_seconds: int | None = None
    excluded: dict[str, int] | None = None
    superseded = False

    daily_rate_days: list[tuple[date, int, Decimal]] | None = None
    if calculation is not None and calculation.formula_version == PAYOUT_V4:
        eligible_seconds = calculation.eligible_seconds
        excluded = calculation.excluded_seconds_by_reason or {}
        daily_rate_days = _daily_rate_days(
            calculation.distance_m_by_day or {}, calculation.amount_by_day or {}
        )
        for entry in reversed(entries):
            entry_metadata = entry.ledger_metadata or {}
            stored = entry_metadata.get("breakdown")
            if (
                entry.status != EarningsLedgerEntryStatus.VOIDED.value
                and entry.entry_type
                in (
                    EarningsLedgerEntryType.ADJUSTMENT.value,
                    EarningsLedgerEntryType.REVERSAL.value,
                )
                and entry_metadata.get("recompute_day")
                and entry_metadata.get("payout_calculation_id") == str(calculation.id)
                and entry_metadata.get("formula_version") == PAYOUT_V4
                and isinstance(stored, dict)
            ):
                superseded = True
                daily_rate_days = _daily_rate_days(
                    stored.get("distance_m_by_day"), stored.get("amount_by_day")
                )
                eligible_seconds, excluded = _recompute_explanation_from_stored_metadata(
                    stored
                ) or (None, None)
                break
        # The per-day explanation must add up to the posted amount; otherwise
        # (a voided payout, say) the entries alone are the visible authority.
        if daily_rate_days is not None and (
            quantize_2(sum((day[2] for day in daily_rate_days), Decimal("0.00"))) != amount
        ):
            daily_rate_days = None

    return DriverTripBreakdown(
        trip_session_id=trip.id,
        formula_version=formula_version,
        currency=currency,
        amount=amount,
        eligible_seconds=eligible_seconds,
        excluded_seconds_by_reason=excluded,
        superseded_by_recompute=superseded,
        entries=entries,
        daily_rate_days=daily_rate_days,
    )
