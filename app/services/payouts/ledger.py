"""Payouts: ledger domain operations."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.campaign import Campaign
from app.models.driver import DriverProfile
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.models.trip import TripSession
from app.services.payouts.common import (
    LEDGER_ENTRY_CONSTRAINTS,
    PAYOUT_V4,
    _aware_utc,
    lagos_day_utc_range,
    logger,
    merge_payout_metadata,
)


def latest_payout_calculation_ids(
    *,
    campaign_id: UUID | None = None,
    organization_id: UUID | None = None,
    trip_ids=None,
):
    """Ids of each trip's most recent calculation (calculated_at desc, id as
    tie-break, mirroring the reuse path). Reports render whichever formula
    version a row carries (architecture 16.1) and a trip counts once even when
    superseded calculations exist. Scope with the narrowest available filter
    so the ranking window stays small."""
    ranked_base = select(
        PayoutCalculation.id.label("calculation_id"),
        func.row_number()
        .over(
            partition_by=PayoutCalculation.trip_session_id,
            order_by=(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id.asc()),
        )
        .label("recency_rank"),
    )
    if campaign_id is not None:
        ranked_base = ranked_base.where(PayoutCalculation.campaign_id == campaign_id)
    if organization_id is not None:
        ranked_base = ranked_base.join(
            Campaign, Campaign.id == PayoutCalculation.campaign_id
        ).where(Campaign.organization_id == organization_id)
    if trip_ids is not None:
        ranked_base = ranked_base.where(PayoutCalculation.trip_session_id.in_(trip_ids))
    ranked = ranked_base.subquery()
    return select(ranked.c.calculation_id).where(ranked.c.recency_rank == 1)


def _day_trip_overlap(lagos_days: list[date]):
    clauses = []
    for day in lagos_days:
        day_start_utc, day_end_utc = lagos_day_utc_range(day)
        clauses.append(
            and_(
                TripSession.started_at < day_end_utc,
                func.coalesce(TripSession.ended_at, TripSession.started_at) >= day_start_utc,
            )
        )
    return or_(*clauses)


async def day_credited_distance_m(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    campaign_id: UUID,
    lagos_day: date,
    exclude_trip_id: UUID,
) -> int:
    """Whole metres already credited to a driver/campaign/Lagos day (payout_v4).

    Sums each earlier v4 calculation's stored per-day distance; the latest
    non-voided recompute-day breakdown for that calculation supersedes it.
    Trips whose trip_payout entry is
    voided credit nothing. Callers hold that day's paycap advisory lock.
    """
    day_key = lagos_day.isoformat()
    voided_trip_payout = (
        select(EarningsLedgerEntry.id)
        .where(
            EarningsLedgerEntry.trip_session_id == PayoutCalculation.trip_session_id,
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.VOIDED.value,
        )
        .correlate(PayoutCalculation)
        .exists()
    )
    rows = await session.execute(
        select(PayoutCalculation)
        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
        .where(
            PayoutCalculation.driver_profile_id == driver_profile_id,
            PayoutCalculation.campaign_id == campaign_id,
            PayoutCalculation.formula_version == PAYOUT_V4,
            PayoutCalculation.trip_session_id != exclude_trip_id,
            _day_trip_overlap([lagos_day]),
            ~voided_trip_payout,
        )
        .order_by(PayoutCalculation.calculated_at, PayoutCalculation.id)
    )
    # Latest calculation per trip (write-once rows; one per trip in practice).
    latest_by_trip = {calc.trip_session_id: calc for calc in rows.scalars().all()}
    total = 0
    for calculation in latest_by_trip.values():
        by_day, _ = await latest_daily_rate_position(session, calculation)
        total += int(by_day.get(day_key, 0) or 0)
    return total


async def latest_daily_rate_position(
    session: AsyncSession,
    calculation: PayoutCalculation,
) -> tuple[dict, dict]:
    """A payout_v4 trip's authoritative (distance_m_by_day, amount_by_day).

    The newest of: the write-once calculation, the latest non-voided
    recompute-day ledger breakdown, and the latest executed correction order
    that recorded this trip's position. Orders record the position even when
    the money delta is zero (a flat stretch of D below the minimum or at the
    target), so a re-measured distance is never lost for later arrivals.
    """
    best_at: datetime | None = None
    distance = dict(calculation.distance_m_by_day or {})
    amount = dict(calculation.amount_by_day or {})
    entries = await session.execute(
        select(EarningsLedgerEntry).where(
            EarningsLedgerEntry.trip_session_id == calculation.trip_session_id,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
            EarningsLedgerEntry.entry_type.in_(
                (
                    EarningsLedgerEntryType.ADJUSTMENT.value,
                    EarningsLedgerEntryType.REVERSAL.value,
                )
            ),
        )
    )
    for entry in entries.scalars().all():
        metadata = entry.ledger_metadata or {}
        breakdown = metadata.get("breakdown")
        if (
            metadata.get("recompute_day")
            and metadata.get("payout_calculation_id") == str(calculation.id)
            and metadata.get("formula_version") == PAYOUT_V4
            and isinstance(breakdown, dict)
            and isinstance(breakdown.get("distance_m_by_day"), dict)
        ):
            at = _aware_utc(entry.occurred_at)
            if best_at is None or at > best_at:
                best_at = at
                distance = dict(breakdown["distance_m_by_day"])
                amount = dict(breakdown.get("amount_by_day") or {})
    orders = await session.execute(
        select(PayoutCorrectionOrder).where(
            PayoutCorrectionOrder.campaign_id == calculation.campaign_id,
            PayoutCorrectionOrder.status == PayoutCorrectionOrderStatus.EXECUTED.value,
            PayoutCorrectionOrder.executed_at.is_not(None),
        )
    )
    for order in orders.scalars().all():
        at = _aware_utc(order.executed_at)
        if best_at is not None and at <= best_at:
            continue
        for driver in (order.execution_result or {}).get("drivers", []):
            for trip in driver.get("trips", []):
                if (
                    trip.get("trip_session_id") == str(calculation.trip_session_id)
                    and trip.get("payout_calculation_id") == str(calculation.id)
                    and isinstance(trip.get("distance_m_by_day"), dict)
                ):
                    best_at = at
                    distance = dict(trip["distance_m_by_day"])
                    amount = dict(trip.get("amount_by_day") or {})
    return distance, amount


async def ledger_for_calculation(
    session: AsyncSession,
    payout_calculation_id: UUID,
) -> EarningsLedgerEntry | None:
    return await session.scalar(
        select(EarningsLedgerEntry).where(
            EarningsLedgerEntry.payout_calculation_id == payout_calculation_id
        )
    )


async def trip_payout_entry_for_trip(
    session: AsyncSession,
    trip_session_id: UUID,
) -> EarningsLedgerEntry | None:
    return await session.scalar(
        select(EarningsLedgerEntry).where(
            EarningsLedgerEntry.trip_session_id == trip_session_id,
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
        )
    )


async def ensure_ledger_entry(
    session: AsyncSession,
    calculation: PayoutCalculation,
    *,
    metadata_prefix: dict | None = None,
) -> EarningsLedgerEntry | None:
    existing = await ledger_for_calculation(session, calculation.id)
    if existing is not None:
        return existing
    if (
        calculation.status != PayoutCalculationStatus.CALCULATED.value
        or calculation.final_payout <= 0
    ):
        return None
    # One trip_payout entry per trip across formula versions: a calculation
    # from another model never posts a second payout for an already-paid trip.
    other = await trip_payout_entry_for_trip(session, calculation.trip_session_id)
    if other is not None:
        logger.warning(
            "ledger_entry_skipped_duplicate_trip_payout trip_session_id=%s "
            "calculation_id=%s existing_entry_id=%s",
            calculation.trip_session_id,
            calculation.id,
            other.id,
        )
        return None
    profile = await session.get(DriverProfile, calculation.driver_profile_id)
    if profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    ledger_entry = EarningsLedgerEntry(
        payout_calculation_id=calculation.id,
        driver_profile_id=calculation.driver_profile_id,
        driver_user_id=profile.user_id,
        campaign_id=calculation.campaign_id,
        trip_session_id=calculation.trip_session_id,
        vehicle_id=calculation.vehicle_id,
        entry_type=EarningsLedgerEntryType.TRIP_PAYOUT.value,
        status=EarningsLedgerEntryStatus.PENDING.value,
        amount=calculation.final_payout,
        currency=calculation.currency,
        description="Trip payout",
        occurred_at=calculation.calculated_at,
        ledger_metadata=merge_payout_metadata(
            metadata_prefix,
            {
                "formula_version": calculation.formula_version,
                "payout_calculation_id": str(calculation.id),
            },
        ),
    )
    try:
        async with session.begin_nested():
            session.add(ledger_entry)
            await session.flush()
    except IntegrityError as exc:
        if not is_expected_uniqueness_conflict(
            exc,
            constraints=LEDGER_ENTRY_CONSTRAINTS,
        ):
            raise
        existing = await ledger_for_calculation(session, calculation.id)
        if existing is not None:
            return existing
        other = await trip_payout_entry_for_trip(session, calculation.trip_session_id)
        if other is not None:
            return None
        raise
    await session.refresh(ledger_entry)
    return ledger_entry


async def repair_missing_ledger_entries(
    session: AsyncSession,
    *,
    trip_id: UUID,
) -> list[EarningsLedgerEntry]:
    """Rule-agnostic ledger repair: money already computed is owed, whatever
    formula computed it. The one-trip_payout-per-trip guard in
    ensure_ledger_entry prevents cross-model double pay."""
    ledger_exists = (
        select(EarningsLedgerEntry.id)
        .where(EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id)
        .exists()
    )
    result = await session.execute(
        select(PayoutCalculation)
        .where(
            PayoutCalculation.trip_session_id == trip_id,
            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
            PayoutCalculation.final_payout > 0,
            ~ledger_exists,
        )
        .order_by(PayoutCalculation.calculated_at, PayoutCalculation.id)
    )
    repaired: list[EarningsLedgerEntry] = []
    for calculation in result.scalars().all():
        ledger = await ensure_ledger_entry(session, calculation)
        if ledger is not None:
            repaired.append(ledger)
    return repaired


async def existing_payout_calculation(
    session: AsyncSession,
    *,
    trip_id: UUID,
    formula_version: str,
    payout_rule_id: UUID,
) -> PayoutCalculation | None:
    return await session.scalar(
        select(PayoutCalculation).where(
            PayoutCalculation.trip_session_id == trip_id,
            PayoutCalculation.formula_version == formula_version,
            PayoutCalculation.payout_rule_id == payout_rule_id,
        )
    )


async def existing_payout_calculation_for_trip_formula(
    session: AsyncSession,
    *,
    trip_id: UUID,
    formula_version: str,
) -> PayoutCalculation | None:
    return await session.scalar(
        select(PayoutCalculation)
        .where(
            PayoutCalculation.trip_session_id == trip_id,
            PayoutCalculation.formula_version == formula_version,
        )
        .order_by(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id)
        .limit(1)
    )


async def existing_payout_calculation_for_trip_any_formula(
    session: AsyncSession,
    *,
    trip_id: UUID,
) -> PayoutCalculation | None:
    return await session.scalar(
        select(PayoutCalculation)
        .where(PayoutCalculation.trip_session_id == trip_id)
        .order_by(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id)
        .limit(1)
    )
