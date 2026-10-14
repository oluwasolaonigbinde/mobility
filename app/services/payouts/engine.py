"""Payouts: engine domain operations."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.payout import (
    AssignmentRuleBinding,
    CampaignPayoutRuleRevision,
    EarningsLedgerEntry,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSession
from app.models.trip_analytics import (
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.services.fraud_holds import fraud_hold_counts
from app.services.impressions import (
    ensure_current_estimate_source,
    impression_output_fingerprint,
    quantize_2,
)
from app.services.payout_eligibility import (
    METRES_PER_MILE,
    EligibilityBreakdown,
    EligibilityParams,
    classify_session,
    credited_distance_m_by_day,
)
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
)
from app.services.payouts.common import (
    PAYOUT_CALCULATION_CONSTRAINTS,
    PAYOUT_V4,
    _aware_utc,
    acquire_paycap_lock,
    invalid_rule_values,
    lagos_day_for,
    merge_payout_metadata,
    paycap_lock_key,
    payout_calculation_stale,
    payout_time_bounds,
    require_paycap_predecessors_processed,
    rule_not_found,
    utc_now,
)
from app.services.payouts.daily import (
    DailyRateTerms,
    binding_for_assignment,
    daily_rate_terms,
    day_pay_naira,
    frozen_campaign_window,
    v4_governing_values,
    v4_inputs_fingerprint,
)
from app.services.payouts.evidence import (
    ensure_payout_sources_match,
    frozen_eligibility_params,
    get_analytics_for_trip,
    get_impression_estimate_for_trip,
    get_trip_for_payout,
    load_eligibility_pings,
    ping_set_fingerprint,
)
from app.services.payouts.ledger import (
    day_credited_distance_m,
    ensure_ledger_entry,
    existing_payout_calculation,
    existing_payout_calculation_for_trip_any_formula,
)
from app.services.payouts.rules import get_campaign
from app.services.trip_analytics import (
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
    ensure_postgis,
)


@dataclass(frozen=True)
class DailyRateClassification:
    """One trip classified under its frozen payout_v4 binding (no writes)."""

    terms: DailyRateTerms
    params: EligibilityParams
    governing_values: dict
    breakdown: EligibilityBreakdown
    distance_m_by_day: dict[str, int]
    ping_fingerprint: str
    inputs_fingerprint: str
    window_start_at: datetime | None
    window_end_at: datetime | None
    effective_window_end_at: datetime | None
    financial_cutoff_at: datetime | None


async def classify_daily_rate_trip(
    session: AsyncSession,
    *,
    trip: TripSession,
    binding: AssignmentRuleBinding,
) -> DailyRateClassification:
    """Classify and measure a trip exclusively from its frozen v4 binding.

    Exclusions, the D39 stop rule and the target/outside weighting all come
    from the acceptance-time snapshot; mutable Settings, rules and zones never
    participate. Shared by the engine, staleness and recompute-day.
    """
    revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
    if revision is None or revision.currency != binding.currency:
        raise invalid_rule_values(
            "the frozen assignment binding must match its payout revision currency"
        )
    terms = daily_rate_terms(binding)
    params = frozen_eligibility_params(binding)
    window_start_at, window_end_at = frozen_campaign_window(binding)
    economic_end, effective_window_end, cutoff = await payout_time_bounds(
        session, trip=trip, window_end_at=window_end_at
    )
    ping_rows = await load_eligibility_pings(
        session,
        trip_id=trip.id,
        campaign_id=trip.campaign_id,
        frozen_premium_zone_wkts=list(binding.premium_zone_geometry_wkts or []),
        frozen_exclusion_zone_wkts=list(binding.exclusion_zone_geometry_wkts or []),
        recorded_through=economic_end,
    )
    pings = [row.ping for row in ping_rows]
    breakdown = classify_session(
        session_started_at=trip.started_at,
        session_ended_at=economic_end,
        pings=pings,
        window_start_at=window_start_at,
        window_end_at=effective_window_end,
        params=params,
        stationary_policy_marker=binding.stationary_policy_marker,
    )
    distance_by_day = credited_distance_m_by_day(
        pings=pings,
        breakdown=breakdown,
        outside_area_weight=terms.outside_area_weight,
    )
    governing_values = v4_governing_values(binding, terms, params)
    ping_fingerprint = ping_set_fingerprint(ping_rows)
    return DailyRateClassification(
        terms=terms,
        params=params,
        governing_values=governing_values,
        breakdown=breakdown,
        distance_m_by_day=distance_by_day,
        ping_fingerprint=ping_fingerprint,
        inputs_fingerprint=v4_inputs_fingerprint(
            governing_values=governing_values,
            ping_fingerprint=ping_fingerprint,
            window_end_at=effective_window_end,
        ),
        window_start_at=window_start_at,
        window_end_at=window_end_at,
        effective_window_end_at=effective_window_end,
        financial_cutoff_at=cutoff,
    )


def _payout_status(analytics: TripAnalytics, estimate: ImpressionEstimate) -> str:
    if (
        analytics.status == TripAnalyticsStatus.INSUFFICIENT_DATA.value
        or estimate.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value
    ):
        return PayoutCalculationStatus.INSUFFICIENT_DATA.value
    if (
        analytics.status == TripAnalyticsStatus.BLOCKED.value
        or estimate.status == ImpressionEstimateStatus.EXCLUDED.value
    ):
        return PayoutCalculationStatus.BLOCKED.value
    return PayoutCalculationStatus.CALCULATED.value


async def calculate_trip_payout_v4(
    session: AsyncSession,
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    binding: AssignmentRuleBinding,
    counts: dict[str, int],
    metadata: dict,
    settings: Settings,
    metadata_prefix: dict | None = None,
    now: datetime | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    """payout_v4 (D39): a daily rate for reaching a daily distance target.

    Priced only from the assignment's frozen binding. Each Lagos day the trip
    touches is priced as an increment on the distance already credited that
    day: D(before + this) - D(before), so a day's trips together earn exactly
    D(day total) and never more than the day rate. The same per-day paycap
    locks and predecessor gate as the hourly engines order arrivals; a day
    that already holds hourly pay is refused. Insufficient or blocked trips
    credit 0 m and ₦0. Write-once, like v2/v3.
    """
    ensure_postgis(session)
    calculated_at = now or utc_now()
    await get_campaign(session, trip.campaign_id)
    classified = await classify_daily_rate_trip(session, trip=trip, binding=binding)
    breakdown = classified.breakdown
    revision_rule_id = await session.scalar(
        select(CampaignPayoutRuleRevision.payout_rule_id).where(
            CampaignPayoutRuleRevision.id == binding.revision_id
        )
    )

    if revision_rule_id is None:
        raise rule_not_found()
    assert trip.ended_at is not None
    lagos_day = lagos_day_for(trip.started_at)
    day_keys = sorted(
        set(breakdown.eligible_seconds_by_day) | set(classified.distance_m_by_day)
    ) or [lagos_day.isoformat()]
    lagos_days = [date.fromisoformat(key) for key in day_keys]
    for day in lagos_days:
        await acquire_paycap_lock(
            session, paycap_lock_key(trip.driver_profile_id, trip.campaign_id, day)
        )
    await require_paycap_predecessors_processed(session, trip=trip, lagos_days=lagos_days)

    status_value = _payout_status(analytics, estimate)
    distance_by_day = (
        {key: value for key, value in classified.distance_m_by_day.items() if value > 0}
        if status_value == PayoutCalculationStatus.CALCULATED.value
        else {}
    )
    prior_by_day: dict[str, int] = {}
    amount_by_day: dict[str, Decimal] = {}
    for day in lagos_days:
        key = day.isoformat()
        prior_by_day[key] = await day_credited_distance_m(
            session,
            driver_profile_id=trip.driver_profile_id,
            campaign_id=trip.campaign_id,
            lagos_day=day,
            exclude_trip_id=trip.id,
        )
        added = distance_by_day.get(key, 0)
        if added > 0:
            amount_by_day[key] = day_pay_naira(
                prior_by_day[key] + added, classified.terms
            ) - day_pay_naira(prior_by_day[key], classified.terms)
    amount = quantize_2(sum(amount_by_day.values(), Decimal("0.00")))

    payout_metadata = {
        "formula_version": PAYOUT_V4,
        "payout_rule_id": str(revision_rule_id),
        "binding": {
            "binding_id": str(binding.id),
            "revision_id": str(binding.revision_id),
            "currency": binding.currency,
            "bound_at": binding.bound_at.isoformat(),
            "campaign_window_start_at": (
                classified.window_start_at.isoformat()
                if classified.window_start_at is not None
                else None
            ),
            "campaign_window_end_at": (
                classified.window_end_at.isoformat()
                if classified.window_end_at is not None
                else None
            ),
            "target_zone_ids": list(binding.premium_zone_ids or []),
            "target_zone_geometry_hash": binding.premium_zone_geometry_hash,
            "exclusion_zone_ids": list(binding.exclusion_zone_ids or []),
            "exclusion_zone_geometry_hash": binding.exclusion_zone_geometry_hash,
            "stationary_policy_marker": binding.stationary_policy_marker,
            "resolved_eligibility_params": binding.resolved_eligibility_params,
        },
        "daily_rate": classified.terms.as_metadata(),
        "source_analytics_id": str(analytics.id),
        "source_impression_estimate_id": str(estimate.id),
        "fraud_flag_counts": counts,
        "request_metadata": metadata,
        "lagos_day": lagos_day.isoformat(),
        "lagos_days": day_keys,
        "distance": {
            "prior_distance_m_by_day": prior_by_day,
            "distance_m_by_day": distance_by_day,
            "measured_distance_m_by_day": classified.distance_m_by_day,
            # Time after a GPS gap longer than max_ping_gap_seconds credits no
            # distance; it is listed with the other exclusions.
            "rounding": "whole metres down per day before pricing",
            "metres_per_mile": str(METRES_PER_MILE),
        },
        "eligibility_params": classified.params.as_metadata(),
        "ping_set_fingerprint": classified.ping_fingerprint,
        "teleport_incident_count": breakdown.teleport_incident_count,
        "stationary_detector": breakdown.stationary_detector_evidence,
        "components": {
            "eligible_seconds": breakdown.eligible_seconds,
            "eligible_seconds_by_day": breakdown.eligible_seconds_by_day,
            "excluded_seconds_by_reason": breakdown.excluded_seconds_by_reason,
            "amount_by_day": {key: str(value) for key, value in amount_by_day.items()},
            "amount": str(amount),
        },
        "source_analytics_formula_version": analytics.formula_version,
        "source_analytics_computed_at": analytics.computed_at.isoformat(),
        "source_analytics_fingerprint": analytics_output_fingerprint(analytics),
        "source_impression_formula_version": estimate.formula_version,
        "source_impression_estimated_at": estimate.estimated_at.isoformat(),
        "source_impression_fingerprint": impression_output_fingerprint(estimate),
        "financial_cutoff_at": (
            classified.financial_cutoff_at.isoformat()
            if classified.financial_cutoff_at is not None
            else None
        ),
        "recorded_trip_end_at": _aware_utc(trip.ended_at).isoformat(),
    }
    payout_metadata = merge_payout_metadata(metadata_prefix, payout_metadata)

    calculation = PayoutCalculation(
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        impression_estimate_id=estimate.id,
        payout_rule_id=revision_rule_id,
        assignment_id=analytics.assignment_id,
        campaign_id=analytics.campaign_id,
        driver_profile_id=analytics.driver_profile_id,
        vehicle_id=analytics.vehicle_id,
        formula_version=PAYOUT_V4,
        status=status_value,
        currency=binding.currency,
        gross_payout=amount,
        final_payout=amount,
        eligible_seconds=breakdown.eligible_seconds,
        excluded_seconds_by_reason=breakdown.excluded_seconds_by_reason,
        distance_m_by_day=distance_by_day,
        amount_by_day={key: str(value) for key, value in amount_by_day.items()},
        inputs_fingerprint=classified.inputs_fingerprint,
        calculated_at=calculated_at,
        payout_metadata=payout_metadata,
    )
    try:
        async with session.begin_nested():
            session.add(calculation)
            await session.flush()
    except IntegrityError as exc:
        if not is_expected_uniqueness_conflict(
            exc,
            constraints=PAYOUT_CALCULATION_CONSTRAINTS,
        ):
            raise
        existing = await existing_payout_calculation(
            session,
            trip_id=trip.id,
            formula_version=PAYOUT_V4,
            payout_rule_id=revision_rule_id,
        )
        if existing is None:
            raise
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation, metadata_prefix=metadata_prefix)
    return calculation, ledger, True


async def v4_calculation_is_stale(
    session: AsyncSession,
    calculation: PayoutCalculation,
    *,
    trip: TripSession,
) -> bool:
    """Detect input drift for a payout_v4 calculation without recomputing
    money: re-derive the fingerprint from the frozen binding and the current
    ping set. Money is never auto-rewritten."""
    binding = await binding_for_assignment(session, trip.assignment_id)
    if (
        binding is None
        or binding.formula_version != PAYOUT_V4
        or not binding.campaign_window_frozen
    ):
        return True
    classified = await classify_daily_rate_trip(session, trip=trip, binding=binding)
    return (
        calculation.currency != binding.currency
        or calculation.inputs_fingerprint != classified.inputs_fingerprint
    )


async def calculate_trip_payout(
    session: AsyncSession,
    *,
    trip_id: UUID,
    payout_rule_id: UUID | None,
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
    strict_staleness: bool = True,
    metadata_prefix: dict | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    """Price signed evidence using the assignment's frozen daily-rate terms.

    Calculations are write-once; corrections change the ledger through the
    approved correction-order path. Strict callers reject stale inputs.
    """
    trip = await get_trip_for_payout(session, trip_id, settings)
    # Serialize the whole money read/write chain with the immutable
    # cancellation cutoff, not only the final cutoff lookup.
    await acquire_campaign_terms_lock(session, trip.campaign_id)
    analytics = await get_analytics_for_trip(session, trip.id)
    ensure_current_analytics_formula(analytics, settings)
    estimate = await get_impression_estimate_for_trip(session, trip_id=trip.id, settings=settings)
    counts = await fraud_hold_counts(session, trip.id)
    ensure_current_estimate_source(
        estimate,
        analytics,
        settings,
        fraud_counts=counts,
    )
    ensure_payout_sources_match(trip=trip, analytics=analytics, estimate=estimate)

    binding = await binding_for_assignment(session, trip.assignment_id)
    if binding is None or binding.formula_version != PAYOUT_V4:
        raise AppError(
            "PAYOUT_BINDING_NOT_FOUND",
            "This trip has no frozen daily-rate terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
    if revision is None:
        raise rule_not_found()
    if payout_rule_id is not None and payout_rule_id != revision.payout_rule_id:
        raise invalid_rule_values("an explicit rule must match the assignment's frozen rule")
    existing = await existing_payout_calculation_for_trip_any_formula(session, trip_id=trip.id)
    if existing is not None:
        if (
            existing.formula_version != PAYOUT_V4
            or existing.payout_rule_id != revision.payout_rule_id
        ):
            raise payout_calculation_stale()
        if strict_staleness and await v4_calculation_is_stale(session, existing, trip=trip):
            raise payout_calculation_stale()
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
        return existing, ledger, False
    return await calculate_trip_payout_v4(
        session,
        trip=trip,
        analytics=analytics,
        estimate=estimate,
        binding=binding,
        counts=counts,
        metadata=metadata,
        settings=settings,
        metadata_prefix=metadata_prefix,
        now=now,
    )
