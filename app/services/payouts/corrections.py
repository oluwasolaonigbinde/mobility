"""Payouts: corrections domain operations."""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSession, TripSessionStatus
from app.services.impressions import (
    quantize_2,
)
from app.services.payout_balances import lock_driver_money_scope
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
)
from app.services.payouts.common import (
    PAYOUT_V4,
    acquire_paycap_lock,
    correction_release_at_required,
    lagos_day_utc_range,
    paycap_lock_key,
    signed_ledger_amount_expression,
    utc_now,
)
from app.services.payouts.daily import DailyRateTerms, binding_for_assignment, day_pay_naira
from app.services.payouts.engine import classify_daily_rate_trip
from app.services.payouts.evidence import campaign_zone_state
from app.services.payouts.ledger import latest_daily_rate_position, trip_payout_entry_for_trip
from app.services.payouts.rules import get_campaign
from app.services.trip_analytics import (
    ensure_postgis,
)


@dataclass(frozen=True)
class RecomputeDayTripOutcome:
    trip_session_id: UUID
    payout_calculation_id: UUID | None
    previous_posted_amount: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    eligible_seconds: int
    entry: EarningsLedgerEntry | None
    voided: bool
    # payout_v4: the trip's full per-day position after this run, recorded in
    # the order's execution_result even when the money delta is zero.
    distance_m_by_day: dict[str, int] | None = None
    amount_by_day: dict[str, str] | None = None


@dataclass(frozen=True)
class RecomputeDayOutcome:
    campaign_id: UUID
    driver_profile_id: UUID
    lagos_date: date
    trips: list[RecomputeDayTripOutcome]
    adjustment_count: int
    reversal_count: int


@dataclass(frozen=True)
class DayTripTarget:
    """One trip's recomputed target for a Lagos day (PR6 pure core output).

    Carries everything both consumers need: the writer (differential ledger
    entries) and the correction-order projection (per-trip deltas plus the
    PR12 fingerprint inputs). No database write happens to produce one.
    """

    trip_session_id: UUID
    vehicle_id: UUID | None
    payout_calculation_id: UUID
    formula_version: str
    currency: str
    previous_posted_amount: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    eligible_seconds: int
    excluded_seconds_by_reason: dict[str, int]
    voided: bool
    current_ping_fingerprint: str | None
    stored_inputs_fingerprint: str | None
    governing_values: dict
    stationary_detector_evidence: dict | None
    # payout_v4 only: whole metres and money increments per Lagos day after
    # this recompute, and the distance credited before this trip on the day.
    distance_m_by_day: dict[str, int] | None = None
    amount_by_day: dict[str, str] | None = None
    prior_distance_m: int | None = None


@dataclass(frozen=True)
class DayComputation:
    """PR6 pure computation core result for one driver/campaign/Lagos-day."""

    campaign_id: UUID
    driver_profile_id: UUID
    lagos_date: date
    currency: str | None
    trips: list[DayTripTarget]
    zone_state_fingerprint: str
    window_start_at: datetime | None
    window_end_at: datetime | None


async def _latest_recompute_breakdown(
    session: AsyncSession,
    trip_id: UUID,
    *,
    payout_calculation_id: UUID,
    formula_version: str,
) -> dict | None:
    """The trip's latest non-voided recompute-day breakdown, if any.

    A prior true-up supersedes the write-once calculation's stored per-day
    allocation (the same chain day_consumed_payable_seconds reads): when day B
    of a cross-midnight trip is recomputed after a day-A true-up, day A's
    authoritative allocation comes from that entry, never from the stale
    calculation row — otherwise the day-B run would silently revert day A's
    correction."""
    entries = await session.execute(
        select(EarningsLedgerEntry)
        .where(
            EarningsLedgerEntry.trip_session_id == trip_id,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
            EarningsLedgerEntry.entry_type.in_(
                (
                    EarningsLedgerEntryType.ADJUSTMENT.value,
                    EarningsLedgerEntryType.REVERSAL.value,
                )
            ),
        )
        .order_by(
            EarningsLedgerEntry.occurred_at,
            EarningsLedgerEntry.created_at,
            EarningsLedgerEntry.id,
        )
    )
    breakdown: dict | None = None
    for entry in entries.scalars().all():
        metadata = entry.ledger_metadata or {}
        if (
            metadata.get("recompute_day")
            and metadata.get("payout_calculation_id") == str(payout_calculation_id)
            and metadata.get("formula_version") == formula_version
            and isinstance(metadata.get("breakdown"), dict)
        ):
            breakdown = metadata["breakdown"]
    return breakdown


def payout_day_unsupported_formula() -> AppError:
    return AppError(
        "PAYOUT_DAY_UNSUPPORTED_FORMULA",
        "The day contains a calculation without frozen daily-rate terms",
        status_code=status.HTTP_409_CONFLICT,
    )


def payout_day_currency_mismatch() -> AppError:
    # A currency drift would zero the posted-position sum and double-pay the
    # day; refuse instead of true-ing up.
    return AppError(
        "PAYOUT_DAY_CURRENCY_MISMATCH",
        "The day's calculations and the governing rule use different currencies; resolve manually",
        status_code=status.HTTP_409_CONFLICT,
    )


async def _posted_amount_for_trip(
    session: AsyncSession,
    *,
    trip_session_id: UUID,
    driver_profile_id: UUID,
    currency: str,
) -> Decimal:
    mismatched_currency_entry_id = await session.scalar(
        select(EarningsLedgerEntry.id)
        .where(
            EarningsLedgerEntry.trip_session_id == trip_session_id,
            EarningsLedgerEntry.currency != currency,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
        .limit(1)
    )
    if mismatched_currency_entry_id is not None:
        raise payout_day_currency_mismatch()
    total = await session.scalar(
        select(func.coalesce(func.sum(signed_ledger_amount_expression()), 0)).where(
            EarningsLedgerEntry.trip_session_id == trip_session_id,
            EarningsLedgerEntry.driver_profile_id == driver_profile_id,
            EarningsLedgerEntry.currency == currency,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
    )
    return quantize_2(Decimal(str(total or 0)))


async def _daily_rate_day_target(
    session: AsyncSession,
    *,
    trip: TripSession,
    calculation: PayoutCalculation,
    voided: bool,
    day_key: str,
    credited_before_m: int,
    driver_profile_id: UUID,
) -> DayTripTarget:
    """One payout_v4 trip's recomputed target for the day being corrected.

    The day's distance is re-measured from the frozen binding and credited
    after every earlier trip of the day, in start order; the trip's other
    Lagos days keep their stored distance and money (the latest correction
    breakdown supersedes the write-once calculation), so correcting day B of
    a cross-midnight trip never undoes an earlier day-A correction. A voided
    or blocked trip targets 0 m and ₦0; an insufficient-data trip is priced
    from a fresh classification under the explicit correction authority.
    """
    binding = await binding_for_assignment(session, trip.assignment_id)
    if binding is None or binding.formula_version != PAYOUT_V4:
        raise AppError(
            "PAYOUT_BINDING_NOT_FOUND",
            "A payout_v4 calculation exists but its assignment has no frozen"
            " daily-rate binding; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    if calculation.currency != binding.currency:
        raise payout_day_currency_mismatch()
    classified = await classify_daily_rate_trip(session, trip=trip, binding=binding)
    governing_values = {
        **classified.governing_values,
        "financial_cutoff_at": (
            classified.financial_cutoff_at.isoformat()
            if classified.financial_cutoff_at is not None
            else None
        ),
    }
    breakdown = classified.breakdown
    if voided or calculation.status == PayoutCalculationStatus.BLOCKED.value:
        distance_by_day: dict[str, int] = {}
        amount_by_day: dict[str, str] = {}
        eligible_seconds = 0
        excluded: dict[str, int] = {}
    else:
        stored_distance, stored_amount = await latest_daily_rate_position(session, calculation)
        distance_by_day = {
            key: int(value) for key, value in stored_distance.items() if key != day_key
        }
        amount_by_day = {key: str(value) for key, value in stored_amount.items() if key != day_key}
        day_distance = classified.distance_m_by_day.get(day_key, 0)
        if day_distance > 0:
            distance_by_day[day_key] = day_distance
            amount_by_day[day_key] = str(
                day_pay_naira(credited_before_m + day_distance, classified.terms)
                - day_pay_naira(credited_before_m, classified.terms)
            )
        eligible_seconds = breakdown.eligible_seconds
        excluded = breakdown.excluded_seconds_by_reason
    target_amount = quantize_2(
        sum((Decimal(value) for value in amount_by_day.values()), Decimal("0.00"))
    )
    posted = await _posted_amount_for_trip(
        session,
        trip_session_id=trip.id,
        driver_profile_id=driver_profile_id,
        currency=calculation.currency,
    )
    return DayTripTarget(
        trip_session_id=trip.id,
        vehicle_id=trip.vehicle_id,
        payout_calculation_id=calculation.id,
        formula_version=PAYOUT_V4,
        currency=calculation.currency,
        previous_posted_amount=posted,
        target_amount=target_amount,
        delta_amount=quantize_2(target_amount - posted),
        eligible_seconds=eligible_seconds,
        excluded_seconds_by_reason=excluded,
        voided=voided,
        current_ping_fingerprint=classified.ping_fingerprint,
        stored_inputs_fingerprint=calculation.inputs_fingerprint,
        governing_values=governing_values,
        stationary_detector_evidence=breakdown.stationary_detector_evidence,
        distance_m_by_day=distance_by_day,
        amount_by_day=amount_by_day,
        prior_distance_m=credited_before_m,
    )


async def compute_payout_day_targets(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    driver_profile_id: UUID,
    lagos_date: date,
    settings: Settings,
) -> DayComputation:
    """Project daily-rate corrections in chronological order under money locks."""
    ensure_postgis(session)
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await get_campaign(session, campaign_id)
    day_range = lagos_day_utc_range(lagos_date)
    day_key = lagos_date.isoformat()

    # Adjacent Lagos-day orders can share a cross-midnight trip while taking
    # different paycap advisory locks. Lock every overlapping trip first, in
    # stable UUID order, so only one projection/execution can price that shared
    # ledger position at a time. This also matches the pipeline's trip-before-
    # paycap order and prevents reverse-order deadlocks across multi-trip days.
    trips_result = await session.execute(
        select(TripSession)
        .where(
            TripSession.campaign_id == campaign_id,
            TripSession.driver_profile_id == driver_profile_id,
            # Sealed trips are the ones that hold money; `ended` (pre-seal)
            # trips are included defensively — they have no calculations yet,
            # but excluding them here must never be the thing that frees cap.
            TripSession.status.in_([TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value]),
            TripSession.ended_at.is_not(None),
            # Overlap, not start-day containment (RM1): a trip that began the
            # previous evening can hold part of this day's cap.
            TripSession.started_at < day_range[1],
            TripSession.ended_at >= day_range[0],
        )
        .order_by(TripSession.id)
        .with_for_update()
    )
    locked_trips = list(trips_result.scalars().all())
    await acquire_paycap_lock(session, paycap_lock_key(driver_profile_id, campaign_id, lagos_date))

    # Cap consumption remains chronological after the distinct lock-ordering
    # phase above.
    trips = sorted(locked_trips, key=lambda trip: (trip.started_at, trip.id))
    trip_ids = [trip.id for trip in trips]

    calculations_by_trip: dict[UUID, PayoutCalculation] = {}
    if trip_ids:
        calc_result = await session.execute(
            select(PayoutCalculation)
            .where(PayoutCalculation.trip_session_id.in_(trip_ids))
            .order_by(PayoutCalculation.calculated_at, PayoutCalculation.id)
        )
        for calculation in calc_result.scalars().all():
            # Latest calculation per trip wins (calculated_at asc overwrite),
            # mirroring the reuse path and the day-pool accounting.
            calculations_by_trip[calculation.trip_session_id] = calculation

    latest_calculations = [
        calculations_by_trip[trip.id] for trip in trips if trip.id in calculations_by_trip
    ]
    day_formulas = {calculation.formula_version for calculation in latest_calculations}
    if day_formulas - {PAYOUT_V4}:
        raise payout_day_unsupported_formula()
    currencies = {calculation.currency for calculation in latest_calculations}
    if len(currencies) > 1:
        raise payout_day_currency_mismatch()
    day_currency = next(iter(currencies), None)

    zone_state = await campaign_zone_state(session, campaign_id)

    credited_m = 0  # payout_v4: distance credited so far on the day, in order.
    targets: list[DayTripTarget] = []
    for trip in trips:
        calculation = calculations_by_trip.get(trip.id)
        if calculation is None:
            # Never computed: initial computation is the pipeline's job.
            continue
        trip_payout_entry = await trip_payout_entry_for_trip(session, trip.id)
        voided = (
            trip_payout_entry is not None
            and trip_payout_entry.status == EarningsLedgerEntryStatus.VOIDED.value
        )
        target = await _daily_rate_day_target(
            session,
            trip=trip,
            calculation=calculation,
            voided=voided,
            day_key=day_key,
            credited_before_m=credited_m,
            driver_profile_id=driver_profile_id,
        )
        credited_m += int((target.distance_m_by_day or {}).get(day_key, 0))
        targets.append(target)

    return DayComputation(
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        lagos_date=lagos_date,
        currency=day_currency,
        trips=targets,
        zone_state_fingerprint=zone_state.fingerprint,
        window_start_at=campaign.start_at,
        window_end_at=campaign.end_at,
    )


async def write_day_differentials(  # noqa: C901
    session: AsyncSession,
    *,
    computation: DayComputation,
    request_metadata: dict,
    recompute_at: datetime,
    correction_order_id: UUID | None = None,
    release_at: datetime | None = None,
    chain_authority,
) -> RecomputeDayOutcome:
    """Execution mode of the PR6 core: posts append-only differential entries
    for the computation's nonzero deltas — adjustment for upward deltas (freed
    cap), positive reversal for downward deltas (netted negative in
    summaries). Under a correction order (MNY-06C), positive deltas post as
    PENDING with the order's own release_at (Q22); negative deltas keep the
    trip-local negative adjustment semantics; no future trip is reduced.
    Calculations are never edited; running twice with unchanged inputs posts
    nothing.
    """
    campaign_id = computation.campaign_id
    driver_profile_id = computation.driver_profile_id
    lagos_date = computation.lagos_date
    from app.services.disbursements import cancel_uncalled_trip_payouts

    profile = await lock_driver_money_scope(
        session, driver_profile_id=driver_profile_id, currency=computation.currency or ""
    )
    if profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    outcomes: list[RecomputeDayTripOutcome] = []
    adjustment_count = 0
    reversal_count = 0
    recompute_run_id = str(
        UUID(
            bytes=hashlib.sha256(
                f"recompute:{campaign_id}:{driver_profile_id}:{lagos_date}:"
                f"{recompute_at.isoformat()}".encode()
            ).digest()[:16]
        )
    )

    for target in computation.trips:
        entry: EarningsLedgerEntry | None = None
        delta = target.delta_amount
        if delta != 0:
            trip_payout_entry = await trip_payout_entry_for_trip(session, target.trip_session_id)
            entry_type = (
                EarningsLedgerEntryType.ADJUSTMENT.value
                if delta > 0
                else EarningsLedgerEntryType.REVERSAL.value
            )
            if delta > 0 and correction_order_id is not None:
                # Q22: positive correction deltas post as pending with their
                # own release date, never inheriting availability.
                if release_at is None:
                    raise correction_release_at_required()
                entry_status = EarningsLedgerEntryStatus.PENDING.value
            else:
                paid_credit_id = None
                if delta < 0:
                    paid_credit_id = await session.scalar(
                        select(EarningsLedgerEntry.id)
                        .where(
                            EarningsLedgerEntry.driver_profile_id == driver_profile_id,
                            EarningsLedgerEntry.trip_session_id == target.trip_session_id,
                            EarningsLedgerEntry.currency == target.currency,
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PAID.value,
                            EarningsLedgerEntry.entry_type
                            != EarningsLedgerEntryType.REVERSAL.value,
                        )
                        .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
                        .limit(1)
                    )
                entry_status = (
                    EarningsLedgerEntryStatus.AVAILABLE.value
                    if paid_credit_id is not None
                    else (
                        trip_payout_entry.status
                        if trip_payout_entry is not None
                        and trip_payout_entry.status != EarningsLedgerEntryStatus.VOIDED.value
                        else EarningsLedgerEntryStatus.PENDING.value
                    )
                )
            breakdown_metadata = {
                "eligible_seconds": target.eligible_seconds,
                "excluded_seconds_by_reason": target.excluded_seconds_by_reason,
                "target_amount": str(target.target_amount),
                "previous_posted_amount": str(target.previous_posted_amount),
                "delta_amount": str(delta),
            }
            if target.distance_m_by_day is not None:
                # payout_v4: the trip's full per-day position after this
                # correction; later corrections and the day-distance reader
                # take it as authoritative over the calculation row.
                breakdown_metadata["distance_m_by_day"] = target.distance_m_by_day
                breakdown_metadata["amount_by_day"] = target.amount_by_day
                breakdown_metadata["prior_distance_m"] = target.prior_distance_m
                breakdown_metadata["daily_rate"] = {
                    key: target.governing_values[key] for key in DailyRateTerms.__dataclass_fields__
                }
            if target.stationary_detector_evidence is not None:
                breakdown_metadata["stationary_detector"] = target.stationary_detector_evidence
            ledger_metadata = {
                "recompute_day": True,
                "recompute_run_id": recompute_run_id,
                "lagos_day": lagos_date.isoformat(),
                "payout_calculation_id": str(target.payout_calculation_id),
                "formula_version": target.formula_version,
                "breakdown": breakdown_metadata,
                "request_metadata": request_metadata,
            }
            if target.formula_version == PAYOUT_V4:
                ledger_metadata["binding_id"] = str(target.governing_values["binding_id"])
                ledger_metadata["revision_id"] = str(target.governing_values["revision_id"])
                frozen_start = target.governing_values["campaign_window_start_at"]
                frozen_end = target.governing_values["campaign_window_end_at"]
                ledger_metadata["campaign_window_start_at"] = (
                    frozen_start.isoformat() if frozen_start is not None else None
                )
                ledger_metadata["campaign_window_end_at"] = (
                    frozen_end.isoformat() if frozen_end is not None else None
                )
            if correction_order_id is not None:
                ledger_metadata["correction_order_id"] = str(correction_order_id)
            entry = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=driver_profile_id,
                driver_user_id=profile.user_id,
                campaign_id=campaign_id,
                trip_session_id=target.trip_session_id,
                vehicle_id=target.vehicle_id,
                entry_type=entry_type,
                status=entry_status,
                amount=abs(delta),
                currency=target.currency,
                description=("Day true-up adjustment" if delta > 0 else "Day true-up reversal"),
                occurred_at=recompute_at,
                release_at=(release_at if delta > 0 and correction_order_id is not None else None),
                ledger_metadata=ledger_metadata,
            )
            session.add(entry)
            await session.flush()
            if delta > 0:
                adjustment_count += 1
            else:
                reversal_count += 1
                await cancel_uncalled_trip_payouts(
                    session,
                    trip_id=target.trip_session_id,
                    chain_authority=chain_authority,
                    resolved_at=recompute_at,
                )
        outcomes.append(
            RecomputeDayTripOutcome(
                trip_session_id=target.trip_session_id,
                payout_calculation_id=target.payout_calculation_id,
                previous_posted_amount=target.previous_posted_amount,
                target_amount=target.target_amount,
                delta_amount=delta,
                eligible_seconds=target.eligible_seconds,
                entry=entry,
                voided=target.voided,
                distance_m_by_day=target.distance_m_by_day,
                amount_by_day=target.amount_by_day,
            )
        )

    return RecomputeDayOutcome(
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        lagos_date=lagos_date,
        trips=outcomes,
        adjustment_count=adjustment_count,
        reversal_count=reversal_count,
    )


async def recompute_payout_day(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    driver_profile_id: UUID,
    lagos_date: date,
    request_metadata: dict,
    settings: Settings,
    now: datetime | None = None,
) -> RecomputeDayOutcome:
    """Admin day true-up (16.1 amendment, next-steps S1 decision 6), now the
    PR6 core in execution mode. Direct API access is retired (PR7): every
    retroactive recompute runs through an approved correction order, whose
    executor calls the core and writer with the order's id and release_at."""
    recompute_at = now or utc_now()
    computation = await compute_payout_day_targets(
        session,
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        lagos_date=lagos_date,
        settings=settings,
    )
    from app.services.disbursements import lock_payout_chains

    chains = await lock_payout_chains(
        session, trip_ids=tuple(target.trip_session_id for target in computation.trips)
    )
    return await write_day_differentials(
        session,
        computation=computation,
        request_metadata=request_metadata,
        recompute_at=recompute_at,
        chain_authority=chains,
    )
