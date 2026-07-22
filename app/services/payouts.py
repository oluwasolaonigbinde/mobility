from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.campaign import Campaign
from app.models.driver import DriverProfile
from app.models.impression import ImpressionEstimate, ImpressionEstimateStatus
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlag,
    FraudFlagSeverity,
    FraudFlagStatus,
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.schemas.payouts import CampaignPayoutRuleCreate, CampaignPayoutRuleUpdate
from app.services.campaigns import get_advertiser_campaign
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.impressions import (
    ensure_current_estimate_source,
    impression_output_fingerprint,
    quantize_2,
    quantize_4,
)
from app.services.trip_analytics import (
    analytics_not_found,
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
)
from app.services.trips import trip_not_found

DECIMAL_2 = Decimal("0.01")
ZERO = Decimal("0")
NON_NULL_RULE_UPDATE_FIELDS = {
    "status",
    "currency",
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
}
PAYOUT_SOURCE_FIELDS = ("campaign_id", "assignment_id", "driver_profile_id", "vehicle_id")
PAYOUT_CALCULATION_CONSTRAINTS = frozenset({"uq_payout_calculations_trip_formula_rule"})
LEDGER_ENTRY_CONSTRAINTS = frozenset(
    {"uq_earnings_ledger_entries_payout_calculation_id"}
)


@dataclass(frozen=True)
class DriverCurrencyEarnings:
    currency: str
    pending_amount: Decimal
    available_amount: Decimal
    voided_amount: Decimal
    lifetime_earned_amount: Decimal
    ledger_entry_count: int


@dataclass(frozen=True)
class DriverEarnings:
    driver_profile_id: UUID
    totals_by_currency: list[DriverCurrencyEarnings]


@dataclass(frozen=True)
class CampaignCurrencyCost:
    currency: str
    final_payout_total: Decimal
    gross_payout_total: Decimal
    calculated_trip_count: int
    blocked_trip_count: int
    insufficient_data_trip_count: int
    ledger_entry_count: int


@dataclass(frozen=True)
class CampaignCost:
    campaign_id: UUID
    formula_version: str
    totals_by_currency: list[CampaignCurrencyCost]
    start_at: datetime | None
    end_at: datetime | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(maximum, value))


def decimal_km(meters: Decimal) -> Decimal:
    return Decimal(meters or 0) / Decimal("1000")


def default_decimal(value: Decimal | None, fallback: float | Decimal) -> Decimal:
    if value is not None:
        return Decimal(value)
    return Decimal(str(fallback))


def rule_not_found() -> AppError:
    return AppError(
        "PAYOUT_RULE_NOT_FOUND",
        "Payout rule was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def rule_inactive() -> AppError:
    return AppError(
        "PAYOUT_RULE_INACTIVE",
        "Payout rule is not active",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def payout_calculation_not_found() -> AppError:
    return AppError(
        "PAYOUT_CALCULATION_NOT_FOUND",
        "Payout calculation was not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def impression_estimate_not_found() -> AppError:
    return AppError(
        "IMPRESSION_ESTIMATE_NOT_FOUND",
        "Impression estimate was not found for the trip",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def invalid_rule_values(message: str) -> AppError:
    return AppError(
        "INVALID_PAYOUT_RULE",
        message,
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def payout_source_mismatch(mismatches: list[dict[str, str]]) -> AppError:
    return AppError(
        "PAYOUT_SOURCE_MISMATCH",
        "Trip, analytics, and impression estimate source fields must match",
        status_code=status.HTTP_400_BAD_REQUEST,
        details={"mismatches": mismatches},
    )


def payout_calculation_stale() -> AppError:
    return AppError(
        "PAYOUT_CALCULATION_STALE",
        "The payout calculation predates the current analytics or impression source",
        status_code=status.HTTP_409_CONFLICT,
    )


def validate_currency_code(value: str | None, *, fallback: str | None = None) -> str | None:
    if value is None:
        value = fallback
    if value is None:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise AppError(
            "INVALID_CURRENCY",
            "Currency must be a 3-letter code",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized


async def get_campaign(session: AsyncSession, campaign_id: UUID) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


def ensure_rule_caps(*, min_payout: Decimal, max_payout: Decimal | None) -> None:
    if max_payout is not None and max_payout < min_payout:
        raise invalid_rule_values("max_payout_per_trip must not be below min_payout_per_trip")


def validate_rule_update_nulls(update_values: dict) -> None:
    null_fields = sorted(
        field
        for field in NON_NULL_RULE_UPDATE_FIELDS
        if field in update_values and update_values[field] is None
    )
    if null_fields:
        raise invalid_rule_values(f"{', '.join(null_fields)} must not be null")


def create_rule_values(
    payload: CampaignPayoutRuleCreate,
    settings: Settings,
) -> dict:
    min_payout = default_decimal(
        payload.min_payout_per_trip,
        settings.payout_default_min_payout_per_trip,
    )
    max_payout = (
        Decimal(payload.max_payout_per_trip)
        if payload.max_payout_per_trip is not None
        else (
            Decimal(str(settings.payout_default_max_payout_per_trip))
            if settings.payout_default_max_payout_per_trip is not None
            else None
        )
    )
    ensure_rule_caps(min_payout=min_payout, max_payout=max_payout)
    formula_version = payload.formula_version or settings.payout_formula_version
    if formula_version != settings.payout_formula_version:
        raise invalid_rule_values("formula_version must match the configured payout formula")
    return {
        "formula_version": formula_version,
        "status": payload.status.value,
        "currency": validate_currency_code(payload.currency, fallback=settings.default_currency),
        "base_rate_per_km": default_decimal(
            payload.base_rate_per_km,
            settings.payout_default_base_rate_per_km,
        ),
        "base_rate_per_active_hour": default_decimal(
            payload.base_rate_per_active_hour,
            settings.payout_default_base_rate_per_active_hour,
        ),
        "target_zone_bonus_rate_per_km": default_decimal(
            payload.target_zone_bonus_rate_per_km,
            settings.payout_default_target_zone_bonus_rate_per_km,
        ),
        "bonus_zone_bonus_rate_per_km": default_decimal(
            payload.bonus_zone_bonus_rate_per_km,
            settings.payout_default_bonus_zone_bonus_rate_per_km,
        ),
        "estimated_impression_rate_per_1000": default_decimal(
            payload.estimated_impression_rate_per_1000,
            settings.payout_default_estimated_impression_rate_per_1000,
        ),
        "min_payout_per_trip": min_payout,
        "max_payout_per_trip": max_payout,
        "low_fraud_multiplier": default_decimal(
            payload.low_fraud_multiplier,
            settings.payout_default_low_fraud_multiplier,
        ),
        "medium_fraud_multiplier": default_decimal(
            payload.medium_fraud_multiplier,
            settings.payout_default_medium_fraud_multiplier,
        ),
        "high_fraud_multiplier": default_decimal(
            payload.high_fraud_multiplier,
            settings.payout_default_high_fraud_multiplier,
        ),
        "rule_metadata": payload.metadata,
    }


async def deactivate_other_active_rules(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID | None = None,
) -> None:
    statement = (
        update(CampaignPayoutRule)
        .where(
            CampaignPayoutRule.campaign_id == campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .values(status=CampaignPayoutRuleStatus.INACTIVE.value, updated_at=utc_now())
    )
    if rule_id is not None:
        statement = statement.where(CampaignPayoutRule.id != rule_id)
    await session.execute(statement)


async def create_campaign_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    created_by_user_id: UUID,
    payload: CampaignPayoutRuleCreate,
    settings: Settings,
) -> CampaignPayoutRule:
    await get_campaign(session, campaign_id)
    values = create_rule_values(payload, settings)
    if values["status"] == CampaignPayoutRuleStatus.ACTIVE.value:
        await deactivate_other_active_rules(session, campaign_id=campaign_id)
    rule = CampaignPayoutRule(
        campaign_id=campaign_id,
        created_by_user_id=created_by_user_id,
        **values,
    )
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    return rule


async def list_campaign_payout_rules(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    limit: int,
    offset: int,
    rule_status: str | None,
) -> tuple[list[CampaignPayoutRule], int]:
    await get_campaign(session, campaign_id)
    filters = [CampaignPayoutRule.campaign_id == campaign_id]
    if rule_status is not None:
        filters.append(CampaignPayoutRule.status == rule_status)

    statement = select(CampaignPayoutRule).where(*filters)
    count_statement = select(func.count()).select_from(CampaignPayoutRule).where(*filters)
    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_campaign_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
) -> CampaignPayoutRule:
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.id == rule_id,
            CampaignPayoutRule.campaign_id == campaign_id,
        )
    )
    if rule is None:
        raise rule_not_found()
    return rule


async def update_campaign_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
    updated_by_user_id: UUID,
    payload: CampaignPayoutRuleUpdate,
) -> tuple[CampaignPayoutRule, list[str]]:
    rule = await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    update_values = payload.model_dump(exclude_unset=True)
    validate_rule_update_nulls(update_values)
    changed_fields = list(update_values)
    metadata_update = update_values.pop("metadata", None) if "metadata" in update_values else None
    if "status" in update_values and update_values["status"] is not None:
        update_values["status"] = update_values["status"].value
    prospective_min = update_values.get("min_payout_per_trip", rule.min_payout_per_trip)
    prospective_max = update_values.get("max_payout_per_trip", rule.max_payout_per_trip)
    ensure_rule_caps(min_payout=Decimal(prospective_min), max_payout=prospective_max)

    if update_values.get("status") == CampaignPayoutRuleStatus.ACTIVE.value:
        await deactivate_other_active_rules(session, campaign_id=campaign_id, rule_id=rule.id)
    if metadata_update is not None:
        rule.rule_metadata = metadata_update
    for field, value in update_values.items():
        setattr(rule, field, value)
    rule.updated_by_user_id = updated_by_user_id
    rule.updated_at = utc_now()
    await session.flush()
    await session.refresh(rule)
    return rule, changed_fields


async def get_trip_for_payout(session: AsyncSession, trip_id: UUID) -> TripSession:
    trip = await session.get(TripSession, trip_id)
    if trip is None:
        raise trip_not_found()
    if trip.status != TripSessionStatus.ENDED.value or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_ENDED",
            "Payout can only be calculated for ended trips",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return trip


async def get_analytics_for_trip(session: AsyncSession, trip_id: UUID) -> TripAnalytics:
    analytics = await session.scalar(
        select(TripAnalytics).where(TripAnalytics.trip_session_id == trip_id)
    )
    if analytics is None:
        raise analytics_not_found()
    return analytics


async def get_impression_estimate_for_trip(
    session: AsyncSession,
    *,
    trip_id: UUID,
    settings: Settings,
) -> ImpressionEstimate:
    estimate = await session.scalar(
        select(ImpressionEstimate)
        .where(
            ImpressionEstimate.trip_session_id == trip_id,
            ImpressionEstimate.formula_version == settings.impression_formula_version,
        )
        .order_by(ImpressionEstimate.estimated_at.desc(), ImpressionEstimate.id)
        .limit(1)
    )
    if estimate is None:
        raise impression_estimate_not_found()
    return estimate


def ensure_payout_sources_match(
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
) -> None:
    mismatches = []
    for field in PAYOUT_SOURCE_FIELDS:
        trip_value = getattr(trip, field)
        analytics_value = getattr(analytics, field)
        estimate_value = getattr(estimate, field)
        if analytics_value != trip_value:
            mismatches.append(
                {
                    "field": field,
                    "source": "trip_analytics",
                    "expected": str(trip_value),
                    "actual": str(analytics_value),
                }
            )
        if estimate_value != trip_value:
            mismatches.append(
                {
                    "field": field,
                    "source": "impression_estimate",
                    "expected": str(trip_value),
                    "actual": str(estimate_value),
                }
            )
    if estimate.trip_analytics_id != analytics.id:
        mismatches.append(
            {
                "field": "trip_analytics_id",
                "source": "impression_estimate",
                "expected": str(analytics.id),
                "actual": str(estimate.trip_analytics_id),
            }
        )
    if mismatches:
        raise payout_source_mismatch(mismatches)


def ensure_current_payout_calculation_source(
    calculation: PayoutCalculation,
    *,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    counts: dict[str, int],
) -> None:
    if (
        calculation.trip_analytics_id != analytics.id
        or calculation.impression_estimate_id != estimate.id
    ):
        raise payout_calculation_stale()
    metadata = calculation.payout_metadata or {}
    if metadata.get("fraud_flag_counts") != counts:
        raise payout_calculation_stale()
    calculated_at = calculation.calculated_at
    estimated_at = estimate.estimated_at
    if calculated_at.tzinfo is None:
        calculated_at = calculated_at.replace(tzinfo=UTC)
    if estimated_at.tzinfo is None:
        estimated_at = estimated_at.replace(tzinfo=UTC)
    analytics_fingerprint = metadata.get("source_analytics_fingerprint")
    impression_fingerprint = metadata.get("source_impression_fingerprint")
    if analytics_fingerprint is not None or impression_fingerprint is not None:
        if (
            analytics_fingerprint != analytics_output_fingerprint(analytics)
            or impression_fingerprint != impression_output_fingerprint(estimate)
        ):
            raise payout_calculation_stale()
        return
    analytics_formula = metadata.get("source_analytics_formula_version")
    impression_formula = metadata.get("source_impression_formula_version")
    if analytics_formula is not None or impression_formula is not None:
        if (
            analytics_formula != analytics.formula_version
            or impression_formula != estimate.formula_version
            or calculated_at < estimated_at
        ):
            raise payout_calculation_stale()
        return
    if calculated_at < estimated_at:
        raise payout_calculation_stale()


async def resolve_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    payout_rule_id: UUID | None,
) -> CampaignPayoutRule:
    if payout_rule_id is not None:
        rule = await get_campaign_payout_rule(
            session,
            campaign_id=campaign_id,
            rule_id=payout_rule_id,
        )
        if rule.status != CampaignPayoutRuleStatus.ACTIVE.value:
            raise rule_inactive()
        return rule
    rule = await session.scalar(
        select(CampaignPayoutRule)
        .where(
            CampaignPayoutRule.campaign_id == campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(1)
    )
    if rule is None:
        raise rule_not_found()
    return rule


async def open_fraud_counts(session: AsyncSession, trip_id: UUID) -> dict[str, int]:
    result = await session.execute(
        select(FraudFlag.severity, func.count(FraudFlag.id))
        .where(
            FraudFlag.trip_session_id == trip_id,
            FraudFlag.status == FraudFlagStatus.OPEN.value,
        )
        .group_by(FraudFlag.severity)
    )
    counts = {severity.value: 0 for severity in FraudFlagSeverity}
    for severity, count in result.all():
        counts[str(severity)] = int(count)
    return counts


def payout_fraud_multiplier(counts: dict[str, int], rule: CampaignPayoutRule) -> Decimal:
    if counts[FraudFlagSeverity.HIGH.value] > 0:
        return Decimal(rule.high_fraud_multiplier)
    if counts[FraudFlagSeverity.MEDIUM.value] > 0:
        return Decimal(rule.medium_fraud_multiplier)
    if counts[FraudFlagSeverity.LOW.value] > 0:
        return Decimal(rule.low_fraud_multiplier)
    return Decimal("1.0")


def zero_payout_values(
    *,
    status_value: str,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    rule: CampaignPayoutRule,
    counts: dict[str, int],
    request_metadata: dict,
    calculated_at: datetime,
) -> dict:
    quality_multiplier = quantize_4(
        clamp_decimal(Decimal(analytics.quality_score or 0), Decimal("0"), Decimal("1"))
    )
    fraud_multiplier = quantize_4(payout_fraud_multiplier(counts, rule))
    reason = (
        "blocked"
        if status_value == PayoutCalculationStatus.BLOCKED.value
        else "insufficient_data"
    )
    return {
        "status": status_value,
        "currency": rule.currency,
        "distance_component": Decimal("0.00"),
        "active_time_component": Decimal("0.00"),
        "target_zone_bonus_component": Decimal("0.00"),
        "bonus_zone_bonus_component": Decimal("0.00"),
        "impression_component": Decimal("0.00"),
        "gross_payout": Decimal("0.00"),
        "quality_multiplier": quality_multiplier,
        "fraud_multiplier": fraud_multiplier,
        "cap_adjustment": Decimal("0.00"),
        "final_payout": Decimal("0.00"),
        "calculated_at": calculated_at,
        "payout_metadata": {
            "formula_version": rule.formula_version,
            "source_analytics_id": str(analytics.id),
            "source_impression_estimate_id": str(estimate.id),
            "payout_rule_id": str(rule.id),
            "fraud_flag_counts": counts,
            "quality_score": str(analytics.quality_score),
            "request_metadata": request_metadata,
            "components": {"reason": reason, "final_payout": "0.00"},
        },
    }


def payout_values(
    *,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    rule: CampaignPayoutRule,
    counts: dict[str, int],
    request_metadata: dict,
    calculated_at: datetime,
) -> dict:
    quality_multiplier = quantize_4(
        clamp_decimal(Decimal(analytics.quality_score or 0), Decimal("0"), Decimal("1"))
    )
    fraud_multiplier = quantize_4(payout_fraud_multiplier(counts, rule))
    distance_km = decimal_km(analytics.distance_m)
    active_hours = Decimal(analytics.active_tracking_seconds or 0) / Decimal("3600")
    target_zone_distance_km = decimal_km(analytics.target_zone_distance_m)
    bonus_zone_distance_km = decimal_km(analytics.bonus_zone_distance_m)

    distance_component = quantize_2(distance_km * rule.base_rate_per_km)
    active_time_component = quantize_2(active_hours * rule.base_rate_per_active_hour)
    target_zone_bonus_component = quantize_2(
        target_zone_distance_km * rule.target_zone_bonus_rate_per_km
    )
    bonus_zone_bonus_component = quantize_2(
        bonus_zone_distance_km * rule.bonus_zone_bonus_rate_per_km
    )
    impression_component = quantize_2(
        (estimate.estimated_impressions / Decimal("1000"))
        * rule.estimated_impression_rate_per_1000
    )
    gross_payout = quantize_2(
        distance_component
        + active_time_component
        + target_zone_bonus_component
        + bonus_zone_bonus_component
        + impression_component
    )
    quality_adjusted_payout = gross_payout * quality_multiplier
    fraud_adjusted_payout = quality_adjusted_payout * fraud_multiplier
    final_before_cap = max(Decimal("0"), fraud_adjusted_payout)
    final_payout = final_before_cap
    cap_adjustment = Decimal("0")
    if rule.max_payout_per_trip is not None and final_payout > rule.max_payout_per_trip:
        cap_adjustment += Decimal(rule.max_payout_per_trip) - final_payout
        final_payout = Decimal(rule.max_payout_per_trip)
    if gross_payout > 0 and Decimal("0") < final_payout < rule.min_payout_per_trip:
        cap_adjustment += Decimal(rule.min_payout_per_trip) - final_payout
        final_payout = Decimal(rule.min_payout_per_trip)

    final_payout = quantize_2(max(Decimal("0"), final_payout))
    cap_adjustment = quantize_2(cap_adjustment)
    return {
        "status": PayoutCalculationStatus.CALCULATED.value,
        "currency": rule.currency,
        "distance_component": distance_component,
        "active_time_component": active_time_component,
        "target_zone_bonus_component": target_zone_bonus_component,
        "bonus_zone_bonus_component": bonus_zone_bonus_component,
        "impression_component": impression_component,
        "gross_payout": gross_payout,
        "quality_multiplier": quality_multiplier,
        "fraud_multiplier": fraud_multiplier,
        "cap_adjustment": cap_adjustment,
        "final_payout": final_payout,
        "calculated_at": calculated_at,
        "payout_metadata": {
            "formula_version": rule.formula_version,
            "source_analytics_id": str(analytics.id),
            "source_impression_estimate_id": str(estimate.id),
            "payout_rule_id": str(rule.id),
            "fraud_flag_counts": counts,
            "quality_score": str(analytics.quality_score),
            "request_metadata": request_metadata,
            "inputs": {
                "distance_km": str(distance_km),
                "active_hours": str(active_hours),
                "target_zone_distance_km": str(target_zone_distance_km),
                "bonus_zone_distance_km": str(bonus_zone_distance_km),
                "estimated_impressions": str(estimate.estimated_impressions),
            },
            "rates": {
                "base_rate_per_km": str(rule.base_rate_per_km),
                "base_rate_per_active_hour": str(rule.base_rate_per_active_hour),
                "target_zone_bonus_rate_per_km": str(rule.target_zone_bonus_rate_per_km),
                "bonus_zone_bonus_rate_per_km": str(rule.bonus_zone_bonus_rate_per_km),
                "estimated_impression_rate_per_1000": str(
                    rule.estimated_impression_rate_per_1000
                ),
            },
            "components": {
                "distance_component": str(distance_component),
                "active_time_component": str(active_time_component),
                "target_zone_bonus_component": str(target_zone_bonus_component),
                "bonus_zone_bonus_component": str(bonus_zone_bonus_component),
                "impression_component": str(impression_component),
                "gross_payout": str(gross_payout),
                "quality_adjusted_payout": str(quality_adjusted_payout),
                "fraud_adjusted_payout": str(fraud_adjusted_payout),
                "cap_adjustment": str(cap_adjustment),
                "final_payout": str(final_payout),
            },
        },
    }


async def ledger_for_calculation(
    session: AsyncSession,
    payout_calculation_id: UUID,
) -> EarningsLedgerEntry | None:
    return await session.scalar(
        select(EarningsLedgerEntry).where(
            EarningsLedgerEntry.payout_calculation_id == payout_calculation_id
        )
    )


async def ensure_ledger_entry(
    session: AsyncSession,
    calculation: PayoutCalculation,
) -> EarningsLedgerEntry | None:
    existing = await ledger_for_calculation(session, calculation.id)
    if existing is not None:
        return existing
    if (
        calculation.status != PayoutCalculationStatus.CALCULATED.value
        or calculation.final_payout <= 0
    ):
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
        ledger_metadata={
            "formula_version": calculation.formula_version,
            "payout_calculation_id": str(calculation.id),
        },
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
        raise
    await session.refresh(ledger_entry)
    return ledger_entry


async def repair_missing_ledger_entries(
    session: AsyncSession,
    *,
    trip_id: UUID,
    formula_version: str,
) -> list[EarningsLedgerEntry]:
    ledger_exists = (
        select(EarningsLedgerEntry.id)
        .where(EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id)
        .exists()
    )
    result = await session.execute(
        select(PayoutCalculation)
        .where(
            PayoutCalculation.trip_session_id == trip_id,
            PayoutCalculation.formula_version == formula_version,
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


async def calculate_trip_payout(
    session: AsyncSession,
    *,
    trip_id: UUID,
    payout_rule_id: UUID | None,
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    trip = await get_trip_for_payout(session, trip_id)
    analytics = await get_analytics_for_trip(session, trip.id)
    ensure_current_analytics_formula(analytics, settings)
    estimate = await get_impression_estimate_for_trip(session, trip_id=trip.id, settings=settings)
    counts = await open_fraud_counts(session, trip.id)
    ensure_current_estimate_source(
        estimate,
        analytics,
        settings,
        fraud_counts=counts,
    )
    ensure_payout_sources_match(trip=trip, analytics=analytics, estimate=estimate)

    if payout_rule_id is None:
        existing = await existing_payout_calculation_for_trip_formula(
            session,
            trip_id=trip.id,
            formula_version=settings.payout_formula_version,
        )
        if existing is not None:
            ensure_current_payout_calculation_source(
                existing,
                analytics=analytics,
                estimate=estimate,
                counts=counts,
            )
            ledger = await ensure_ledger_entry(session, existing)
            return existing, ledger, False

    rule = await resolve_payout_rule(
        session,
        campaign_id=trip.campaign_id,
        payout_rule_id=payout_rule_id,
    )

    existing = await existing_payout_calculation(
        session,
        trip_id=trip.id,
        formula_version=settings.payout_formula_version,
        payout_rule_id=rule.id,
    )
    if existing is not None:
        ensure_current_payout_calculation_source(
            existing,
            analytics=analytics,
            estimate=estimate,
            counts=counts,
        )
        ledger = await ensure_ledger_entry(session, existing)
        return existing, ledger, False

    calculated_at = now or utc_now()
    if (
        analytics.status == TripAnalyticsStatus.INSUFFICIENT_DATA.value
        or estimate.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value
    ):
        values = zero_payout_values(
            status_value=PayoutCalculationStatus.INSUFFICIENT_DATA.value,
            analytics=analytics,
            estimate=estimate,
            rule=rule,
            counts=counts,
            request_metadata=metadata,
            calculated_at=calculated_at,
        )
    elif (
        analytics.status == TripAnalyticsStatus.BLOCKED.value
        or estimate.status == ImpressionEstimateStatus.EXCLUDED.value
    ):
        values = zero_payout_values(
            status_value=PayoutCalculationStatus.BLOCKED.value,
            analytics=analytics,
            estimate=estimate,
            rule=rule,
            counts=counts,
            request_metadata=metadata,
            calculated_at=calculated_at,
        )
    else:
        values = payout_values(
            analytics=analytics,
            estimate=estimate,
            rule=rule,
            counts=counts,
            request_metadata=metadata,
            calculated_at=calculated_at,
        )
    values["payout_metadata"].update(
        {
            "source_analytics_formula_version": analytics.formula_version,
            "source_analytics_computed_at": analytics.computed_at.isoformat(),
            "source_analytics_fingerprint": analytics_output_fingerprint(analytics),
            "source_impression_formula_version": estimate.formula_version,
            "source_impression_estimated_at": estimate.estimated_at.isoformat(),
            "source_impression_fingerprint": impression_output_fingerprint(estimate),
        }
    )

    calculation = PayoutCalculation(
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        impression_estimate_id=estimate.id,
        payout_rule_id=rule.id,
        assignment_id=analytics.assignment_id,
        campaign_id=analytics.campaign_id,
        driver_profile_id=analytics.driver_profile_id,
        vehicle_id=analytics.vehicle_id,
        formula_version=settings.payout_formula_version,
        **values,
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
            formula_version=settings.payout_formula_version,
            payout_rule_id=rule.id,
        )
        if existing is None:
            raise
        ensure_current_payout_calculation_source(
            existing,
            analytics=analytics,
            estimate=estimate,
            counts=counts,
        )
        ledger = await ensure_ledger_entry(session, existing)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation)
    return calculation, ledger, True


async def list_payout_calculations(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    campaign_id: UUID | None,
    trip_session_id: UUID | None,
    driver_profile_id: UUID | None,
    vehicle_id: UUID | None,
    calculation_status: str | None,
    currency: str | None,
) -> tuple[list[PayoutCalculation], int]:
    filters = []
    if campaign_id is not None:
        filters.append(PayoutCalculation.campaign_id == campaign_id)
    if trip_session_id is not None:
        filters.append(PayoutCalculation.trip_session_id == trip_session_id)
    if driver_profile_id is not None:
        filters.append(PayoutCalculation.driver_profile_id == driver_profile_id)
    if vehicle_id is not None:
        filters.append(PayoutCalculation.vehicle_id == vehicle_id)
    if calculation_status is not None:
        filters.append(PayoutCalculation.status == calculation_status)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(PayoutCalculation.currency == normalized_currency)

    statement = select(PayoutCalculation)
    count_statement = select(func.count()).select_from(PayoutCalculation)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(PayoutCalculation.calculated_at.desc(), PayoutCalculation.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def driver_earnings_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    currency: str | None,
    settings: Settings,
) -> DriverEarnings:
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    filters = [
        EarningsLedgerEntry.driver_profile_id == profile.id,
        EarningsLedgerEntry.driver_user_id == user_id,
    ]
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(EarningsLedgerEntry.currency == normalized_currency)

    result = await session.execute(
        select(
            EarningsLedgerEntry.currency,
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status
                            == EarningsLedgerEntryStatus.PENDING.value,
                            EarningsLedgerEntry.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status
                            == EarningsLedgerEntryStatus.AVAILABLE.value,
                            EarningsLedgerEntry.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.VOIDED.value,
                            EarningsLedgerEntry.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(EarningsLedgerEntry.id),
        )
        .where(*filters)
        .group_by(EarningsLedgerEntry.currency)
    )
    totals = []
    for row in result.all():
        pending = quantize_2(Decimal(str(row[1] or 0)))
        available = quantize_2(Decimal(str(row[2] or 0)))
        voided = quantize_2(Decimal(str(row[3] or 0)))
        totals.append(
            DriverCurrencyEarnings(
                currency=row[0],
                pending_amount=pending,
                available_amount=available,
                voided_amount=voided,
                lifetime_earned_amount=quantize_2(pending + available),
                ledger_entry_count=int(row[4] or 0),
            )
        )
    if not totals:
        totals.append(
            DriverCurrencyEarnings(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                pending_amount=Decimal("0.00"),
                available_amount=Decimal("0.00"),
                voided_amount=Decimal("0.00"),
                lifetime_earned_amount=Decimal("0.00"),
                ledger_entry_count=0,
            )
        )
    return DriverEarnings(driver_profile_id=profile.id, totals_by_currency=totals)


async def list_driver_ledger_entries(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
    ledger_status: str | None,
    entry_type: str | None,
    currency: str | None,
) -> tuple[list[EarningsLedgerEntry], int]:
    profile, _ = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    filters = [
        EarningsLedgerEntry.driver_profile_id == profile.id,
        EarningsLedgerEntry.driver_user_id == user_id,
    ]
    if ledger_status is not None:
        filters.append(EarningsLedgerEntry.status == ledger_status)
    if entry_type is not None:
        filters.append(EarningsLedgerEntry.entry_type == entry_type)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(EarningsLedgerEntry.currency == normalized_currency)

    statement = select(EarningsLedgerEntry).where(*filters)
    count_statement = select(func.count()).select_from(EarningsLedgerEntry).where(*filters)
    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(EarningsLedgerEntry.occurred_at.desc(), EarningsLedgerEntry.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def advertiser_campaign_cost_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    currency: str | None,
    settings: Settings,
) -> CampaignCost:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    filters = [
        PayoutCalculation.campaign_id == campaign.id,
        PayoutCalculation.formula_version == settings.payout_formula_version,
    ]
    if start_at is not None:
        filters.append(PayoutCalculation.calculated_at >= start_at)
    if end_at is not None:
        filters.append(PayoutCalculation.calculated_at <= end_at)
    normalized_currency = validate_currency_code(currency)
    if normalized_currency is not None:
        filters.append(PayoutCalculation.currency == normalized_currency)

    result = await session.execute(
        select(
            PayoutCalculation.currency,
            func.coalesce(func.sum(PayoutCalculation.final_payout), 0),
            func.coalesce(func.sum(PayoutCalculation.gross_payout), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status
                            == PayoutCalculationStatus.CALCULATED.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status == PayoutCalculationStatus.BLOCKED.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayoutCalculation.status
                            == PayoutCalculationStatus.INSUFFICIENT_DATA.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.count(EarningsLedgerEntry.id),
        )
        .select_from(PayoutCalculation)
        .outerjoin(
            EarningsLedgerEntry,
            EarningsLedgerEntry.payout_calculation_id == PayoutCalculation.id,
        )
        .where(*filters)
        .group_by(PayoutCalculation.currency)
    )
    totals = [
        CampaignCurrencyCost(
            currency=row[0],
            final_payout_total=quantize_2(Decimal(str(row[1] or 0))),
            gross_payout_total=quantize_2(Decimal(str(row[2] or 0))),
            calculated_trip_count=int(row[3] or 0),
            blocked_trip_count=int(row[4] or 0),
            insufficient_data_trip_count=int(row[5] or 0),
            ledger_entry_count=int(row[6] or 0),
        )
        for row in result.all()
    ]
    if not totals:
        totals.append(
            CampaignCurrencyCost(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                final_payout_total=Decimal("0.00"),
                gross_payout_total=Decimal("0.00"),
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    return CampaignCost(
        campaign_id=campaign.id,
        formula_version=settings.payout_formula_version,
        totals_by_currency=totals,
        start_at=start_at,
        end_at=end_at,
    )
