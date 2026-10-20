"""Payouts: daily domain operations."""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.payout import (
    AssignmentRuleBinding,
)
from app.services.payout_eligibility import (
    METRES_PER_MILE,
    EligibilityParams,
)
from app.services.payouts.common import (
    DECIMAL_2,
    PAYOUT_V4,
)
from app.services.provenance import stable_source_fingerprint


@dataclass(frozen=True)
class DailyRateTerms:
    """The payout_v4 pay terms frozen on a binding (all client values, D39)."""

    daily_rate_naira: Decimal
    daily_target_miles: Decimal
    # Fixed zero rules remain frozen audit inputs. Keep their original decimal
    # scale so removing the knobs cannot change an existing input fingerprint.
    minimum_miles: Decimal = Decimal("0")
    outside_area_weight: Decimal = Decimal("0")

    def as_metadata(self) -> dict[str, str | None]:
        return {
            "daily_rate_naira": str(self.daily_rate_naira),
            "daily_target_miles": str(self.daily_target_miles),
            "shortfall_strategy": "proportional",
            "deduction_per_mile_naira": None,
            "minimum_miles": str(self.minimum_miles),
            "outside_area_weight": str(self.outside_area_weight),
        }


def daily_rate_terms(binding: AssignmentRuleBinding) -> DailyRateTerms:
    """Read the frozen v4 terms, failing closed on an incomplete binding."""
    required = (
        binding.daily_rate_naira,
        binding.daily_target_miles,
        binding.shortfall_strategy,
        binding.minimum_miles,
        binding.outside_area_weight,
    )
    if (
        any(value is None for value in required)
        or binding.shortfall_strategy != "proportional"
        or binding.deduction_per_mile_naira is not None
        or binding.minimum_miles != 0
        or binding.outside_area_weight != 0
    ):
        raise AppError(
            "PAYOUT_BINDING_INCOMPLETE",
            "The payout_v4 assignment binding does not contain complete daily-rate"
            " terms; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    assert binding.daily_rate_naira is not None
    assert binding.daily_target_miles is not None
    assert binding.minimum_miles is not None
    assert binding.outside_area_weight is not None
    return DailyRateTerms(
        daily_rate_naira=Decimal(binding.daily_rate_naira),
        daily_target_miles=Decimal(binding.daily_target_miles),
        minimum_miles=Decimal(binding.minimum_miles),
        outside_area_weight=Decimal(binding.outside_area_weight),
    )


def _half_up_naira(value: Fraction) -> Decimal:
    """Exact 2dp NGN ROUND_HALF_UP of a non-negative fraction."""
    cents = math.floor(value * 100 + Fraction(1, 2))
    return (Decimal(cents) / 100).quantize(DECIMAL_2)


def day_pay_naira(distance_m: int, terms: DailyRateTerms) -> Decimal:
    """D(d): a day's pay for ``distance_m`` whole credited metres (payout_v4).

    D43: rate x miles / target, capped at the day rate, with no minimum.
    D is non-decreasing, so per-trip increments sum to D(day total).
    """
    if distance_m <= 0:
        return Decimal("0.00")
    miles = Fraction(distance_m) / Fraction(METRES_PER_MILE)
    rate = Fraction(terms.daily_rate_naira)
    target = Fraction(terms.daily_target_miles)
    if miles >= target:
        return _half_up_naira(rate)
    return _half_up_naira(rate * miles / target)


def v4_governing_values(
    binding: AssignmentRuleBinding,
    terms: DailyRateTerms,
    params: EligibilityParams,
) -> dict:
    """Every frozen input a payout_v4 amount depends on (replay + fingerprint)."""
    return {
        "engine": PAYOUT_V4,
        "binding_id": binding.id,
        "revision_id": binding.revision_id,
        **terms.as_metadata(),
        "eligibility_params": params.as_metadata(),
        "frozen_eligibility_params": binding.eligibility_params or {},
        "resolved_eligibility_params": binding.resolved_eligibility_params,
        "target_zone_ids": list(binding.premium_zone_ids or []),
        "target_zone_geometry_hash": binding.premium_zone_geometry_hash,
        "exclusion_zone_ids": list(binding.exclusion_zone_ids or []),
        "exclusion_zone_geometry_hash": binding.exclusion_zone_geometry_hash,
        "stationary_policy_marker": binding.stationary_policy_marker,
        "campaign_window_start_at": binding.campaign_window_start_at,
        "campaign_window_end_at": binding.campaign_window_end_at,
        "currency": binding.currency,
    }


def v4_inputs_fingerprint(
    *,
    governing_values: dict,
    ping_fingerprint: str,
    window_end_at: datetime | None,
) -> str:
    return stable_source_fingerprint(
        {
            "formula_version": PAYOUT_V4,
            "governing_values": governing_values,
            "ping_set_fingerprint": ping_fingerprint,
            "window_end_at": window_end_at,
        }
    )


async def binding_for_assignment(
    session: AsyncSession,
    assignment_id: UUID,
) -> AssignmentRuleBinding | None:
    return await session.scalar(
        select(AssignmentRuleBinding).where(AssignmentRuleBinding.assignment_id == assignment_id)
    )


def frozen_campaign_window(
    binding: AssignmentRuleBinding,
) -> tuple[datetime | None, datetime | None]:
    """Return authoritative accepted windows or fail closed."""
    if not binding.campaign_window_frozen:
        raise AppError(
            "PAYOUT_BINDING_WINDOW_NOT_FROZEN",
            "The payout binding predates the accepted campaign-window freeze; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    return binding.campaign_window_start_at, binding.campaign_window_end_at
