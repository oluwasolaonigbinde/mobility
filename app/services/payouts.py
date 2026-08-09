import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Text as SQLText
from sqlalchemy import and_, case, cast, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.campaign import Campaign
from app.models.campaign_zone import CampaignZone, CampaignZoneType
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
from app.models.trip import LocationPing, TripSession, TripSessionStatus
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
from app.services.payout_eligibility import (
    EligibilityParams,
    EligibilityPing,
    classify_session,
)
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import (
    analytics_not_found,
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
    ensure_postgis,
)
from app.services.trips import trip_not_found

logger = logging.getLogger(__name__)

DECIMAL_2 = Decimal("0.01")
ZERO = Decimal("0")
PAYOUT_V1 = "payout_v1"
PAYOUT_V2 = "payout_v2"
PAYOUT_FORMULA_VERSIONS = frozenset({PAYOUT_V1, PAYOUT_V2})
LAGOS_TZ = ZoneInfo("Africa/Lagos")
SECONDS_PER_HOUR = Decimal("3600")
V2_RULE_FIELDS = {"hourly_rate_naira", "daily_payable_hours_cap", "eligibility_params"}
V1_RULE_FIELDS = {
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "max_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
}
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
    "hourly_rate_naira",
    "daily_payable_hours_cap",
}
ELIGIBILITY_PARAM_KEYS = frozenset(
    {
        "stationary_radius_m",
        "stationary_window_min",
        "stationary_grace_min",
        "max_accuracy_m",
        "teleport_kmh",
        "max_ping_gap_seconds",
    }
)
PAYOUT_SOURCE_FIELDS = ("campaign_id", "assignment_id", "driver_profile_id", "vehicle_id")
PAYOUT_CALCULATION_CONSTRAINTS = frozenset({"uq_payout_calculations_trip_formula_rule"})
LEDGER_ENTRY_CONSTRAINTS = frozenset(
    {
        "uq_earnings_ledger_entries_payout_calculation_id",
        "uq_earnings_ledger_entries_trip_payout_per_trip",
    }
)


def quantize_ngn_half_up(value: Decimal) -> Decimal:
    """payout_v2 money quantization: 2dp NGN, ROUND_HALF_UP, applied exactly
    once per ledger amount. v1 keeps quantize_2 (context default HALF_EVEN) —
    frozen history, never converge the two."""
    return value.quantize(DECIMAL_2, rounding=ROUND_HALF_UP)


def lagos_day_for(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(LAGOS_TZ).date()


def lagos_day_utc_range(day: date) -> tuple[datetime, datetime]:
    day_start = datetime.combine(day, time.min, tzinfo=LAGOS_TZ)
    return day_start.astimezone(UTC), (day_start + timedelta(days=1)).astimezone(UTC)


def paycap_lock_key(driver_profile_id: UUID, campaign_id: UUID, lagos_date: date) -> int:
    digest = hashlib.sha256(
        f"paycap:{driver_profile_id}:{campaign_id}:{lagos_date}".encode()
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def acquire_paycap_lock(session: AsyncSession, lock_key: int) -> None:
    """Transaction-scoped advisory lock for the read-remaining-cap -> write
    critical section. Must never be taken inside begin_nested(): a savepoint
    abort would release it. No-op outside PostgreSQL."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
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
    ledger_net_total: Decimal
    calculated_trip_count: int
    blocked_trip_count: int
    insufficient_data_trip_count: int
    ledger_entry_count: int


@dataclass(frozen=True)
class CampaignCost:
    campaign_id: UUID
    formula_version: str
    formula_versions: list[str]
    totals_by_currency: list[CampaignCurrencyCost]
    start_at: datetime | None
    end_at: datetime | None


def signed_ledger_amount_expression():
    """Ledger sign convention (architecture 16.2, next-steps ledger block):
    every amount is stored positive; balance computations net reversal-typed
    entries as negative; adjustments are ordinary positive earnings."""
    return case(
        (
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.REVERSAL.value,
            -EarningsLedgerEntry.amount,
        ),
        else_=EarningsLedgerEntry.amount,
    )


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


def create_rule_v2_values(
    payload: CampaignPayoutRuleCreate,
    settings: Settings,
) -> dict:
    set_v1_fields = sorted(
        field
        for field in V1_RULE_FIELDS
        if getattr(payload, field, None) is not None
    )
    if set_v1_fields:
        raise invalid_rule_values(
            f"payout_v2 rules must not set v1 fields: {', '.join(set_v1_fields)}"
        )
    hourly_rate = payload.hourly_rate_naira
    if hourly_rate is None:
        default_rate = Decimal(str(settings.payout_default_hourly_rate_ngn))
        if default_rate > 0:
            hourly_rate = default_rate
        else:
            raise invalid_rule_values("hourly_rate_naira is required for payout_v2 rules")
    if payload.daily_payable_hours_cap is None:
        raise invalid_rule_values(
            "daily_payable_hours_cap is required for payout_v2 rules (D4)"
        )
    validate_eligibility_params_overlay(payload.eligibility_params)
    return {
        "formula_version": PAYOUT_V2,
        "status": payload.status.value,
        "currency": validate_currency_code(payload.currency, fallback=settings.default_currency),
        "hourly_rate_naira": Decimal(hourly_rate),
        "daily_payable_hours_cap": Decimal(payload.daily_payable_hours_cap),
        "eligibility_params": payload.eligibility_params,
        "rule_metadata": payload.metadata,
    }


def create_rule_values(
    payload: CampaignPayoutRuleCreate,
    settings: Settings,
) -> dict:
    formula_version = payload.formula_version or settings.payout_formula_version
    if formula_version not in PAYOUT_FORMULA_VERSIONS:
        raise invalid_rule_values(
            "formula_version must be one of: " + ", ".join(sorted(PAYOUT_FORMULA_VERSIONS))
        )
    if formula_version == PAYOUT_V2:
        return create_rule_v2_values(payload, settings)
    set_v2_fields = sorted(
        field
        for field in V2_RULE_FIELDS
        if getattr(payload, field, None) is not None
    )
    if set_v2_fields:
        raise invalid_rule_values(
            f"payout_v1 rules must not set v2 fields: {', '.join(set_v2_fields)}"
        )
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
    # A rule row's model is immutable (P6): reject the other model's fields.
    other_model_fields = (
        V1_RULE_FIELDS if rule.formula_version == PAYOUT_V2 else V2_RULE_FIELDS
    )
    set_other_fields = sorted(
        field
        for field in other_model_fields
        if update_values.get(field) is not None
    )
    if set_other_fields:
        raise invalid_rule_values(
            f"{rule.formula_version} rules must not set: {', '.join(set_other_fields)}"
        )
    changed_fields = list(update_values)
    metadata_update = update_values.pop("metadata", None) if "metadata" in update_values else None
    if "status" in update_values and update_values["status"] is not None:
        update_values["status"] = update_values["status"].value
    if rule.formula_version == PAYOUT_V2:
        if "eligibility_params" in update_values:
            validate_eligibility_params_overlay(update_values["eligibility_params"])
    else:
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
    # Money is sealed-only (RM3): an `ended` trip may still be receiving late
    # batches inside the grace window, and write-once payout_v2 must never
    # fingerprint an incomplete ping set. This also covers the admin
    # recompute endpoints — corrections only ever reprice sealed trips.
    if trip.status != TripSessionStatus.SEALED.value or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_SEALED",
            "Payout can only be calculated for sealed trips",
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


@dataclass(frozen=True)
class EligibilityPingRow:
    id: UUID
    ping: EligibilityPing


@dataclass(frozen=True)
class CampaignZoneState:
    fingerprint: str
    zone_count: int
    max_updated_at: datetime | None


def effective_eligibility_params(
    settings: Settings,
    rule: CampaignPayoutRule,
) -> EligibilityParams:
    overlay = rule.eligibility_params or {}
    def value(key: str, fallback: float) -> float:
        raw = overlay.get(key, fallback)
        return float(raw)

    return EligibilityParams(
        stationary_radius_m=value(
            "stationary_radius_m", settings.payout_eligibility_stationary_radius_m
        ),
        stationary_window_seconds=int(
            value("stationary_window_min", settings.payout_eligibility_stationary_window_min)
            * 60
        ),
        stationary_grace_seconds=int(
            value("stationary_grace_min", settings.payout_eligibility_stationary_grace_min)
            * 60
        ),
        max_accuracy_m=value("max_accuracy_m", settings.payout_eligibility_max_accuracy_m),
        teleport_kmh=value("teleport_kmh", settings.payout_eligibility_teleport_kmh),
        max_ping_gap_seconds=int(
            value("max_ping_gap_seconds", settings.payout_eligibility_max_ping_gap_seconds)
        ),
    )


def validate_eligibility_params_overlay(overlay: dict | None) -> None:
    if overlay is None:
        return
    unknown = sorted(set(overlay) - ELIGIBILITY_PARAM_KEYS)
    if unknown:
        raise invalid_rule_values(
            f"Unknown eligibility_params keys: {', '.join(unknown)}"
        )
    for key, raw in overlay.items():
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise invalid_rule_values(f"eligibility_params.{key} must be a number")
        minimum = 0 if key == "stationary_grace_min" else 0.000001
        if raw < minimum:
            raise invalid_rule_values(
                f"eligibility_params.{key} must be "
                + ("non-negative" if key == "stationary_grace_min" else "positive")
            )


async def load_eligibility_pings(
    session: AsyncSession,
    *,
    trip_id: UUID,
    campaign_id: UUID,
) -> list[EligibilityPingRow]:
    """One PostGIS round trip: pings in analytics order plus geofence
    membership. In-area = inside a target zone (or the campaign has no target
    zones at all) and never inside an exclusion zone; bonus zones play no role
    in payout_v2 eligibility (Q5, decisions-log)."""

    def zone_hit(zone_type: str):
        return (
            select(CampaignZone.id)
            .where(
                CampaignZone.campaign_id == campaign_id,
                CampaignZone.zone_type == zone_type,
                func.ST_Intersects(CampaignZone.geom, LocationPing.geom),
            )
            .correlate(LocationPing)
            .exists()
        )

    has_target_zones = (
        select(CampaignZone.id)
        .where(
            CampaignZone.campaign_id == campaign_id,
            CampaignZone.zone_type == CampaignZoneType.TARGET.value,
        )
        .exists()
    )
    in_area = and_(
        or_(~has_target_zones, zone_hit(CampaignZoneType.TARGET.value)),
        ~zone_hit(CampaignZoneType.EXCLUSION.value),
    )
    result = await session.execute(
        select(
            LocationPing.id,
            LocationPing.recorded_at,
            LocationPing.latitude,
            LocationPing.longitude,
            LocationPing.accuracy_m,
            in_area.label("in_area"),
        )
        .where(LocationPing.trip_session_id == trip_id)
        .order_by(
            LocationPing.recorded_at,
            LocationPing.sequence_number.asc().nullslast(),
            LocationPing.created_at,
            LocationPing.id,
        )
    )
    return [
        EligibilityPingRow(
            id=row.id,
            ping=EligibilityPing(
                recorded_at=row.recorded_at,
                latitude=row.latitude,
                longitude=row.longitude,
                accuracy_m=row.accuracy_m,
                in_area=bool(row.in_area),
            ),
        )
        for row in result.all()
    ]


async def campaign_zone_state(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignZoneState:
    result = await session.execute(
        select(
            CampaignZone.id,
            cast(CampaignZone.geom, SQLText).label("geom_wkb"),
            CampaignZone.updated_at,
        )
        .where(CampaignZone.campaign_id == campaign_id)
        .order_by(CampaignZone.id)
    )
    rows = result.all()
    fingerprint = stable_source_fingerprint(
        {
            "zones": [
                {"id": row.id, "geom": row.geom_wkb, "updated_at": row.updated_at}
                for row in rows
            ]
        }
    )
    max_updated_at = max((row.updated_at for row in rows), default=None)
    return CampaignZoneState(
        fingerprint=fingerprint,
        zone_count=len(rows),
        max_updated_at=max_updated_at,
    )


def ping_set_fingerprint(rows: list[EligibilityPingRow]) -> str:
    return stable_source_fingerprint({"ping_ids": [row.id for row in rows]})


def v2_inputs_fingerprint(
    *,
    rule: CampaignPayoutRule,
    params: EligibilityParams,
    ping_fingerprint: str,
    zone_fingerprint: str,
    window_start_at: datetime | None,
    window_end_at: datetime | None,
) -> str:
    return stable_source_fingerprint(
        {
            "formula_version": PAYOUT_V2,
            "hourly_rate_naira": Decimal(rule.hourly_rate_naira),
            "daily_payable_hours_cap": Decimal(rule.daily_payable_hours_cap),
            "eligibility_params": params.as_metadata(),
            "ping_set_fingerprint": ping_fingerprint,
            "zone_state_fingerprint": zone_fingerprint,
            "window_start_at": window_start_at,
            "window_end_at": window_end_at,
        }
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


def day_allocation_seconds(
    by_day: dict | None,
    payable_seconds: int | None,
    trip_started_at: datetime,
    day_key: str,
) -> int:
    """Seconds a calculation charges to one Lagos day.

    Reads the stored per-day allocation (RM1). Rows written before 0015 have
    no allocation map: they charged the whole trip to its start day, so that
    is what they consume — never re-derive them, the audited recompute-day
    tool is the only corrective path (D9)."""
    if by_day:
        return int(by_day.get(day_key, 0) or 0)
    if payable_seconds and lagos_day_for(trip_started_at).isoformat() == day_key:
        return int(payable_seconds)
    return 0


async def day_consumed_payable_seconds(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    campaign_id: UUID,
    lagos_day: date,
    exclude_trip_id: UUID | None = None,
) -> int:
    """Payable seconds already allocated for the driver/campaign/Lagos-day.

    Counts every trip that *overlaps* the day, charging each only the seconds
    its stored allocation assigns to that day (RM1) — a cross-midnight trip
    consumes each day's allowance separately. Per-trip MAX dedupes a trip
    calculated under two v2 rule rows (counted once, conservatively the
    larger); trips whose trip_payout entry is voided consume nothing. Callers
    hold that day's paycap advisory lock."""
    day_key = lagos_day.isoformat()
    day_start_utc, day_end_utc = lagos_day_utc_range(lagos_day)
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
    per_trip = (
        select(
            PayoutCalculation.trip_session_id.label("trip_id"),
            PayoutCalculation.payable_seconds_by_day.label("by_day"),
            PayoutCalculation.payable_seconds.label("payable"),
            TripSession.started_at.label("started_at"),
        )
        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
        .where(
            PayoutCalculation.driver_profile_id == driver_profile_id,
            PayoutCalculation.campaign_id == campaign_id,
            PayoutCalculation.formula_version == PAYOUT_V2,
            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
            # Overlap, not start-day containment: a trip that began yesterday
            # can still consume today's cap (RM1).
            TripSession.started_at < day_end_utc,
            func.coalesce(TripSession.ended_at, TripSession.started_at) >= day_start_utc,
            ~voided_trip_payout,
        )
    )
    if exclude_trip_id is not None:
        per_trip = per_trip.where(PayoutCalculation.trip_session_id != exclude_trip_id)
    rows = await session.execute(per_trip)
    consumed_by_trip: dict[UUID, int] = {}
    for row in rows.all():
        seconds = day_allocation_seconds(row.by_day, row.payable, row.started_at, day_key)
        consumed_by_trip[row.trip_id] = max(consumed_by_trip.get(row.trip_id, 0), seconds)

    # A recompute-day true-up supersedes the calculation's figure: the latest
    # non-voided differential entry stores the day's authoritative
    # payable_seconds for its trip (calculations are write-once).
    recompute_entries = await session.execute(
        select(EarningsLedgerEntry, TripSession.started_at.label("trip_started_at"))
        .join(TripSession, TripSession.id == EarningsLedgerEntry.trip_session_id)
        .where(
            EarningsLedgerEntry.driver_profile_id == driver_profile_id,
            EarningsLedgerEntry.campaign_id == campaign_id,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
            EarningsLedgerEntry.entry_type.in_(
                (
                    EarningsLedgerEntryType.ADJUSTMENT.value,
                    EarningsLedgerEntryType.REVERSAL.value,
                )
            ),
            TripSession.started_at < day_end_utc,
            func.coalesce(TripSession.ended_at, TripSession.started_at) >= day_start_utc,
        )
        .order_by(
            EarningsLedgerEntry.occurred_at,
            EarningsLedgerEntry.created_at,
            EarningsLedgerEntry.id,
        )
    )
    for entry, trip_started_at in recompute_entries.all():
        if exclude_trip_id is not None and entry.trip_session_id == exclude_trip_id:
            continue
        metadata = entry.ledger_metadata or {}
        if not metadata.get("recompute_day"):
            continue
        breakdown_meta = metadata.get("breakdown") or {}
        by_day = breakdown_meta.get("payable_seconds_by_day")
        payable = breakdown_meta.get("payable_seconds")
        if by_day is not None:
            consumed_by_trip[entry.trip_session_id] = int(by_day.get(day_key, 0) or 0)
        elif payable is not None and lagos_day_for(trip_started_at).isoformat() == day_key:
            # Pre-RM1 differential: a whole-trip figure, which could only ever
            # have been charged to the trip's own start day.
            consumed_by_trip[entry.trip_session_id] = int(payable)
    return sum(consumed_by_trip.values())


def daily_cap_seconds(rule: CampaignPayoutRule) -> int:
    return int(Decimal(rule.daily_payable_hours_cap) * SECONDS_PER_HOUR)


def price_payable_seconds(payable_seconds: int, hourly_rate: Decimal) -> Decimal:
    """Price once per ledger amount: rate x integer seconds / 3600, quantized
    exactly once to 2dp NGN with ROUND_HALF_UP (frozen into payout_v2)."""
    return quantize_ngn_half_up(
        Decimal(payable_seconds) * hourly_rate / SECONDS_PER_HOUR
    )


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
    # Min-floor loophole closed with v2 (architecture 17, decisions-log): the
    # floor lifts only trips with no open fraud flags (extend to `confirmed`
    # when S2 adds that status).
    no_open_flags = all(count == 0 for count in counts.values())
    if (
        gross_payout > 0
        and no_open_flags
        and Decimal("0") < final_payout < rule.min_payout_per_trip
    ):
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


async def v2_calculation_is_stale(
    session: AsyncSession,
    calculation: PayoutCalculation,
    *,
    trip: TripSession,
    settings: Settings,
) -> bool:
    """Detect input drift for a payout_v2 calculation without recomputing
    money: re-derive the inputs fingerprint from the current rule row, zone
    state, settings, and ping set, and compare. Money is never auto-rewritten
    (write-once; the audited admin recompute-day is the corrective tool)."""
    rule = await session.get(CampaignPayoutRule, calculation.payout_rule_id)
    if rule is None or rule.formula_version != PAYOUT_V2:
        return True
    campaign = await get_campaign(session, trip.campaign_id)
    params = effective_eligibility_params(settings, rule)
    ping_rows = await load_eligibility_pings(
        session, trip_id=trip.id, campaign_id=trip.campaign_id
    )
    zone_state = await campaign_zone_state(session, trip.campaign_id)
    current = v2_inputs_fingerprint(
        rule=rule,
        params=params,
        ping_fingerprint=ping_set_fingerprint(ping_rows),
        zone_fingerprint=zone_state.fingerprint,
        window_start_at=campaign.start_at,
        window_end_at=campaign.end_at,
    )
    return calculation.inputs_fingerprint != current


async def calculate_trip_payout_v2(
    session: AsyncSession,
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    rule: CampaignPayoutRule,
    counts: dict[str, int],
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    ensure_postgis(session)
    calculated_at = now or utc_now()
    campaign = await get_campaign(session, trip.campaign_id)
    params = effective_eligibility_params(settings, rule)
    ping_rows = await load_eligibility_pings(
        session, trip_id=trip.id, campaign_id=trip.campaign_id
    )
    breakdown = classify_session(
        session_started_at=trip.started_at,
        session_ended_at=trip.ended_at,
        pings=[row.ping for row in ping_rows],
        window_start_at=campaign.start_at,
        window_end_at=campaign.end_at,
        params=params,
    )
    zone_state = await campaign_zone_state(session, trip.campaign_id)
    pings_fingerprint = ping_set_fingerprint(ping_rows)
    inputs_fingerprint = v2_inputs_fingerprint(
        rule=rule,
        params=params,
        ping_fingerprint=pings_fingerprint,
        zone_fingerprint=zone_state.fingerprint,
        window_start_at=campaign.start_at,
        window_end_at=campaign.end_at,
    )

    lagos_day = lagos_day_for(trip.started_at)
    # Every Lagos day the trip's eligible time touches (RM1): a cross-midnight
    # trip charges each day's own cap. Sorted so concurrent workers always take
    # the locks in the same order and cannot deadlock.
    day_keys = sorted(breakdown.eligible_seconds_by_day) or [lagos_day.isoformat()]
    lagos_days = [date.fromisoformat(key) for key in day_keys]
    # Advisory locks BEFORE reading cap consumption; never inside a savepoint.
    for day in lagos_days:
        await acquire_paycap_lock(
            session, paycap_lock_key(trip.driver_profile_id, trip.campaign_id, day)
        )

    if (
        analytics.status == TripAnalyticsStatus.INSUFFICIENT_DATA.value
        or estimate.status == ImpressionEstimateStatus.INSUFFICIENT_DATA.value
    ):
        status_value = PayoutCalculationStatus.INSUFFICIENT_DATA.value
    elif (
        analytics.status == TripAnalyticsStatus.BLOCKED.value
        or estimate.status == ImpressionEstimateStatus.EXCLUDED.value
    ):
        status_value = PayoutCalculationStatus.BLOCKED.value
    else:
        status_value = PayoutCalculationStatus.CALCULATED.value

    cap_seconds = daily_cap_seconds(rule)
    consumed_by_day: dict[str, int] = {}
    payable_by_day: dict[str, int] = {}
    for day in lagos_days:
        key = day.isoformat()
        consumed_by_day[key] = await day_consumed_payable_seconds(
            session,
            driver_profile_id=trip.driver_profile_id,
            campaign_id=trip.campaign_id,
            lagos_day=day,
            exclude_trip_id=trip.id,
        )
    if status_value == PayoutCalculationStatus.CALCULATED.value:
        # Cap before pricing, in integer seconds, independently per Lagos day.
        for key in day_keys:
            allotted = max(
                0,
                min(
                    breakdown.eligible_seconds_by_day.get(key, 0),
                    cap_seconds - consumed_by_day[key],
                ),
            )
            if allotted > 0:
                payable_by_day[key] = allotted
    payable_seconds = sum(payable_by_day.values())
    consumed_before = sum(consumed_by_day.values())
    hourly_rate = Decimal(rule.hourly_rate_naira)
    amount = price_payable_seconds(payable_seconds, hourly_rate)

    payout_metadata = {
        "formula_version": PAYOUT_V2,
        "payout_rule_id": str(rule.id),
        "source_analytics_id": str(analytics.id),
        "source_impression_estimate_id": str(estimate.id),
        "fraud_flag_counts": counts,
        "request_metadata": metadata,
        "lagos_day": lagos_day.isoformat(),
        "lagos_days": day_keys,
        "cap": {
            "cap_seconds": cap_seconds,
            "consumed_before_seconds": consumed_before,
            "payable_seconds": payable_seconds,
            "consumed_before_seconds_by_day": consumed_by_day,
            "payable_seconds_by_day": payable_by_day,
        },
        "rates": {"hourly_rate_naira": str(hourly_rate)},
        "eligibility_params": params.as_metadata(),
        "zone_state": {
            "fingerprint": zone_state.fingerprint,
            "zone_count": zone_state.zone_count,
            "max_updated_at": (
                zone_state.max_updated_at.isoformat()
                if zone_state.max_updated_at is not None
                else None
            ),
        },
        "ping_set_fingerprint": pings_fingerprint,
        "teleport_incident_count": breakdown.teleport_incident_count,
        "components": {
            "eligible_seconds": breakdown.eligible_seconds,
            "eligible_seconds_by_day": breakdown.eligible_seconds_by_day,
            "excluded_seconds_by_reason": breakdown.excluded_seconds_by_reason,
            "payable_seconds": payable_seconds,
            "payable_seconds_by_day": payable_by_day,
            "amount": str(amount),
        },
        "source_analytics_formula_version": analytics.formula_version,
        "source_analytics_computed_at": analytics.computed_at.isoformat(),
        "source_analytics_fingerprint": analytics_output_fingerprint(analytics),
        "source_impression_formula_version": estimate.formula_version,
        "source_impression_estimated_at": estimate.estimated_at.isoformat(),
        "source_impression_fingerprint": impression_output_fingerprint(estimate),
    }

    calculation = PayoutCalculation(
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        impression_estimate_id=estimate.id,
        payout_rule_id=rule.id,
        assignment_id=analytics.assignment_id,
        campaign_id=analytics.campaign_id,
        driver_profile_id=analytics.driver_profile_id,
        vehicle_id=analytics.vehicle_id,
        formula_version=PAYOUT_V2,
        status=status_value,
        currency=rule.currency,
        gross_payout=amount,
        final_payout=amount,
        eligible_seconds=breakdown.eligible_seconds,
        payable_seconds=payable_seconds,
        payable_seconds_by_day=payable_by_day,
        excluded_seconds_by_reason=breakdown.excluded_seconds_by_reason,
        inputs_fingerprint=inputs_fingerprint,
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
            formula_version=PAYOUT_V2,
            payout_rule_id=rule.id,
        )
        if existing is None:
            raise
        ledger = await ensure_ledger_entry(session, existing)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation)
    return calculation, ledger, True


async def _calculate_trip_payout_v1(
    session: AsyncSession,
    *,
    trip: TripSession,
    analytics: TripAnalytics,
    estimate: ImpressionEstimate,
    rule: CampaignPayoutRule,
    counts: dict[str, int],
    metadata: dict,
    formula_version: str,
    now: datetime | None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    existing = await existing_payout_calculation(
        session,
        trip_id=trip.id,
        formula_version=formula_version,
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
        formula_version=formula_version,
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
            formula_version=formula_version,
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


async def calculate_trip_payout(
    session: AsyncSession,
    *,
    trip_id: UUID,
    payout_rule_id: UUID | None,
    metadata: dict,
    settings: Settings,
    now: datetime | None = None,
    strict_staleness: bool = True,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    """Per-rule formula dispatch (D2/D8, Q4/Q5).

    Rule-less path reuses the trip's latest calculation across ALL formula
    versions (one calculation chain per trip: a campaign switched
    payout_v1 -> payout_v2 never re-pays history). Fresh computation happens
    only when no calculation exists, under the governing active rule's model.
    payout_v2 rows are write-once: with strict_staleness (admin surface) input
    drift raises PAYOUT_CALCULATION_STALE to flag it; the worker passes
    strict_staleness=False and reuses (recompute-day is the corrective tool).
    """
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
        existing = await existing_payout_calculation_for_trip_any_formula(
            session,
            trip_id=trip.id,
        )
        if existing is not None:
            if existing.formula_version == PAYOUT_V2:
                if strict_staleness and await v2_calculation_is_stale(
                    session, existing, trip=trip, settings=settings
                ):
                    raise payout_calculation_stale()
            else:
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

    if rule.formula_version == PAYOUT_V2:
        if payout_rule_id is not None:
            # Write-once holds on the explicit-rule surface too: a trip
            # already calculated under another rule/formula is never given a
            # second v2 calculation — flag it instead (recompute-day corrects).
            existing_any = await existing_payout_calculation_for_trip_any_formula(
                session, trip_id=trip.id
            )
            if existing_any is not None and not (
                existing_any.formula_version == PAYOUT_V2
                and existing_any.payout_rule_id == rule.id
            ):
                raise payout_calculation_stale()
        return await calculate_trip_payout_v2(
            session,
            trip=trip,
            analytics=analytics,
            estimate=estimate,
            rule=rule,
            counts=counts,
            metadata=metadata,
            settings=settings,
            now=now,
        )
    return await _calculate_trip_payout_v1(
        session,
        trip=trip,
        analytics=analytics,
        estimate=estimate,
        rule=rule,
        counts=counts,
        metadata=metadata,
        formula_version=rule.formula_version,
        now=now,
    )


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

    signed_amount = signed_ledger_amount_expression()
    result = await session.execute(
        select(
            EarningsLedgerEntry.currency,
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status
                            == EarningsLedgerEntryStatus.PENDING.value,
                            signed_amount,
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
                            signed_amount,
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
    # Formula-agnostic: a campaign may hold payout_v1 history and payout_v2
    # rows side by side; reports render whichever version a row carries (16.1),
    # and each trip counts once (its latest calculation).
    filters = [
        PayoutCalculation.campaign_id == campaign.id,
        PayoutCalculation.id.in_(latest_payout_calculation_ids(campaign_id=campaign.id)),
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
    # Reversal netting lives in a separate ledger aggregate: adjustment and
    # reversal entries carry no payout_calculation_id, so the calc join above
    # can never see them. Note the ranges differ deliberately: calc aggregates
    # window on calculated_at (when cost was computed), the ledger net on
    # occurred_at (when money was posted).
    ledger_filters = [EarningsLedgerEntry.campaign_id == campaign.id]
    if start_at is not None:
        ledger_filters.append(EarningsLedgerEntry.occurred_at >= start_at)
    if end_at is not None:
        ledger_filters.append(EarningsLedgerEntry.occurred_at <= end_at)
    if normalized_currency is not None:
        ledger_filters.append(EarningsLedgerEntry.currency == normalized_currency)
    ledger_result = await session.execute(
        select(
            EarningsLedgerEntry.currency,
            func.coalesce(func.sum(signed_ledger_amount_expression()), 0),
        )
        .where(
            *ledger_filters,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
        .group_by(EarningsLedgerEntry.currency)
    )
    ledger_net_by_currency = {
        row[0]: quantize_2(Decimal(str(row[1] or 0))) for row in ledger_result.all()
    }

    formula_rows = await session.execute(
        select(PayoutCalculation.formula_version)
        .where(PayoutCalculation.campaign_id == campaign.id)
        .distinct()
        .order_by(PayoutCalculation.formula_version)
    )
    formula_versions = [row[0] for row in formula_rows.all()]
    governing_rule = await session.scalar(
        select(CampaignPayoutRule.formula_version)
        .where(
            CampaignPayoutRule.campaign_id == campaign.id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
        .order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(1)
    )

    totals = [
        CampaignCurrencyCost(
            currency=row[0],
            final_payout_total=quantize_2(Decimal(str(row[1] or 0))),
            gross_payout_total=quantize_2(Decimal(str(row[2] or 0))),
            ledger_net_total=ledger_net_by_currency.pop(row[0], Decimal("0.00")),
            calculated_trip_count=int(row[3] or 0),
            blocked_trip_count=int(row[4] or 0),
            insufficient_data_trip_count=int(row[5] or 0),
            ledger_entry_count=int(row[6] or 0),
        )
        for row in result.all()
    ]
    for leftover_currency, net_total in sorted(ledger_net_by_currency.items()):
        totals.append(
            CampaignCurrencyCost(
                currency=leftover_currency,
                final_payout_total=Decimal("0.00"),
                gross_payout_total=Decimal("0.00"),
                ledger_net_total=net_total,
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    if not totals:
        totals.append(
            CampaignCurrencyCost(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                final_payout_total=Decimal("0.00"),
                gross_payout_total=Decimal("0.00"),
                ledger_net_total=Decimal("0.00"),
                calculated_trip_count=0,
                blocked_trip_count=0,
                insufficient_data_trip_count=0,
                ledger_entry_count=0,
            )
        )
    return CampaignCost(
        campaign_id=campaign.id,
        formula_version=governing_rule or PAYOUT_V1,
        formula_versions=formula_versions,
        totals_by_currency=totals,
        start_at=start_at,
        end_at=end_at,
    )


@dataclass(frozen=True)
class RecomputeDayTripOutcome:
    trip_session_id: UUID
    payout_calculation_id: UUID | None
    previous_posted_amount: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    eligible_seconds: int
    payable_seconds: int
    entry: EarningsLedgerEntry | None
    voided: bool


@dataclass(frozen=True)
class RecomputeDayOutcome:
    campaign_id: UUID
    driver_profile_id: UUID
    lagos_date: date
    cap_seconds: int
    trips: list[RecomputeDayTripOutcome]
    adjustment_count: int
    reversal_count: int


def payout_day_mixed_formulas() -> AppError:
    return AppError(
        "PAYOUT_DAY_MIXED_FORMULAS",
        "The day holds calculations under both payout models; resolve manually",
        status_code=status.HTTP_409_CONFLICT,
    )


async def _posted_amount_for_trip(
    session: AsyncSession,
    *,
    trip_session_id: UUID,
    driver_profile_id: UUID,
    currency: str,
) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(signed_ledger_amount_expression()), 0)).where(
            EarningsLedgerEntry.trip_session_id == trip_session_id,
            EarningsLedgerEntry.driver_profile_id == driver_profile_id,
            EarningsLedgerEntry.currency == currency,
            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
        )
    )
    return quantize_2(Decimal(str(total or 0)))


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
    """Admin day true-up (16.1 amendment, next-steps S1 decision 6).

    Re-runs the Lagos day's cap allocation for one driver/campaign under the
    same advisory lock as the pipeline and posts append-only differential
    entries: adjustment for upward deltas (freed cap), positive reversal for
    downward deltas (netted negative in summaries). Calculations are never
    edited; running twice with unchanged inputs posts nothing.
    """
    ensure_postgis(session)
    recompute_at = now or utc_now()
    rule = await resolve_payout_rule(session, campaign_id=campaign_id, payout_rule_id=None)
    if rule.formula_version != PAYOUT_V2:
        raise invalid_rule_values(
            "recompute-day applies only to campaigns governed by a payout_v2 rule"
        )
    profile = await session.get(DriverProfile, driver_profile_id)
    if profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    campaign = await get_campaign(session, campaign_id)
    params = effective_eligibility_params(settings, rule)
    day_range = lagos_day_utc_range(lagos_date)

    await acquire_paycap_lock(
        session, paycap_lock_key(driver_profile_id, campaign_id, lagos_date)
    )

    trips_result = await session.execute(
        select(TripSession)
        .where(
            TripSession.campaign_id == campaign_id,
            TripSession.driver_profile_id == driver_profile_id,
            # Sealed trips are the ones that hold money; `ended` (pre-seal)
            # trips are included defensively — they have no calculations yet,
            # but excluding them here must never be the thing that frees cap.
            TripSession.status.in_(
                [TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value]
            ),
            TripSession.ended_at.is_not(None),
            # Overlap, not start-day containment (RM1): a trip that began the
            # previous evening can hold part of this day's cap.
            TripSession.started_at < day_range[1],
            TripSession.ended_at >= day_range[0],
        )
        .order_by(TripSession.started_at, TripSession.id)
    )
    trips = list(trips_result.scalars().all())
    trip_ids = [trip.id for trip in trips]

    calculations_by_trip: dict[UUID, PayoutCalculation] = {}
    if trip_ids:
        calc_result = await session.execute(
            select(PayoutCalculation)
            .where(PayoutCalculation.trip_session_id.in_(trip_ids))
            .order_by(PayoutCalculation.calculated_at, PayoutCalculation.id)
        )
        for calculation in calc_result.scalars().all():
            if calculation.formula_version != PAYOUT_V2:
                raise payout_day_mixed_formulas()
            if calculation.currency != rule.currency:
                # A currency drift would zero the posted-position sum and
                # double-pay the day; refuse instead of true-ing up.
                raise AppError(
                    "PAYOUT_DAY_CURRENCY_MISMATCH",
                    "The day's calculations and the governing rule use "
                    "different currencies; resolve manually",
                    status_code=status.HTTP_409_CONFLICT,
                )
            calculations_by_trip[calculation.trip_session_id] = calculation

    cap_seconds = daily_cap_seconds(rule)
    hourly_rate = Decimal(rule.hourly_rate_naira)
    cap_remaining = cap_seconds
    day_key = lagos_date.isoformat()
    outcomes: list[RecomputeDayTripOutcome] = []
    adjustment_count = 0
    reversal_count = 0
    recompute_run_id = str(
        UUID(bytes=hashlib.sha256(
            f"recompute:{campaign_id}:{driver_profile_id}:{lagos_date}:"
            f"{recompute_at.isoformat()}".encode()
        ).digest()[:16])
    )

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
        # blocked stays 0 (fraud posture, S2); insufficient_data is priced
        # from a fresh classification — the admin escape hatch for trips whose
        # analytics healed after the write-once calculation (D9).
        if voided or calculation.status == PayoutCalculationStatus.BLOCKED.value:
            eligible_seconds = 0
            payable_seconds = 0
            payable_by_day: dict[str, int] = {}
            target_amount = Decimal("0.00")
        else:
            ping_rows = await load_eligibility_pings(
                session, trip_id=trip.id, campaign_id=campaign_id
            )
            breakdown = classify_session(
                session_started_at=trip.started_at,
                session_ended_at=trip.ended_at,
                pings=[row.ping for row in ping_rows],
                window_start_at=campaign.start_at,
                window_end_at=campaign.end_at,
                params=params,
            )
            eligible_seconds = breakdown.eligible_seconds
            # Re-allocate only the day being recomputed; the trip's seconds on
            # any other Lagos day keep their stored allocation, because those
            # days' caps are not being re-run under this lock (RM1).
            day_eligible = breakdown.eligible_seconds_by_day.get(day_key, 0)
            day_payable = max(0, min(day_eligible, cap_remaining))
            cap_remaining -= day_payable
            other_days = {
                key: int(value)
                for key, value in (calculation.payable_seconds_by_day or {}).items()
                if key != day_key
            }
            payable_by_day = dict(other_days)
            if day_payable > 0:
                payable_by_day[day_key] = day_payable
            payable_seconds = sum(payable_by_day.values())
            target_amount = price_payable_seconds(payable_seconds, hourly_rate)

        posted = await _posted_amount_for_trip(
            session,
            trip_session_id=trip.id,
            driver_profile_id=driver_profile_id,
            currency=rule.currency,
        )
        delta = quantize_2(target_amount - posted)
        entry: EarningsLedgerEntry | None = None
        if delta != 0:
            entry_type = (
                EarningsLedgerEntryType.ADJUSTMENT.value
                if delta > 0
                else EarningsLedgerEntryType.REVERSAL.value
            )
            inherited_status = (
                trip_payout_entry.status
                if trip_payout_entry is not None
                and trip_payout_entry.status != EarningsLedgerEntryStatus.VOIDED.value
                else EarningsLedgerEntryStatus.PENDING.value
            )
            entry = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=driver_profile_id,
                driver_user_id=profile.user_id,
                campaign_id=campaign_id,
                trip_session_id=trip.id,
                vehicle_id=trip.vehicle_id,
                entry_type=entry_type,
                status=inherited_status,
                amount=abs(delta),
                currency=rule.currency,
                description=(
                    "Day true-up adjustment"
                    if delta > 0
                    else "Day true-up reversal"
                ),
                occurred_at=recompute_at,
                ledger_metadata={
                    "recompute_day": True,
                    "recompute_run_id": recompute_run_id,
                    "lagos_day": lagos_date.isoformat(),
                    "payout_calculation_id": str(calculation.id),
                    "formula_version": PAYOUT_V2,
                    "breakdown": {
                        "eligible_seconds": eligible_seconds,
                        "payable_seconds": payable_seconds,
                        "payable_seconds_by_day": payable_by_day,
                        "hourly_rate_naira": str(hourly_rate),
                        "cap_seconds": cap_seconds,
                        "target_amount": str(target_amount),
                        "previous_posted_amount": str(posted),
                        "delta_amount": str(delta),
                    },
                    "request_metadata": request_metadata,
                },
            )
            session.add(entry)
            await session.flush()
            if delta > 0:
                adjustment_count += 1
            else:
                reversal_count += 1
        outcomes.append(
            RecomputeDayTripOutcome(
                trip_session_id=trip.id,
                payout_calculation_id=calculation.id,
                previous_posted_amount=posted,
                target_amount=target_amount,
                delta_amount=delta,
                eligible_seconds=eligible_seconds,
                payable_seconds=payable_seconds,
                entry=entry,
                voided=voided,
            )
        )

    return RecomputeDayOutcome(
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        lagos_date=lagos_date,
        cap_seconds=cap_seconds,
        trips=outcomes,
        adjustment_count=adjustment_count,
        reversal_count=reversal_count,
    )


@dataclass(frozen=True)
class DriverTripBreakdown:
    trip_session_id: UUID
    formula_version: str
    currency: str
    amount: Decimal
    eligible_seconds: int | None
    excluded_seconds_by_reason: dict[str, int] | None
    hourly_rate: Decimal | None
    capped_seconds: int | None
    superseded_by_recompute: bool
    entries: list[EarningsLedgerEntry]
    lagos_day: date | None
    cap_seconds: int | None
    day_payable_seconds: int | None


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
        .order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.created_at,
                  EarningsLedgerEntry.id)
    )
    entries = list(entries_result.scalars().all())
    calculation = await existing_payout_calculation_for_trip_any_formula(
        session, trip_id=trip.id
    )
    if calculation is None and not entries:
        raise payout_calculation_not_found()

    currency = (
        calculation.currency
        if calculation is not None
        else entries[0].currency
    )
    amount = Decimal("0.00")
    for entry in entries:
        if entry.status == EarningsLedgerEntryStatus.VOIDED.value:
            continue
        if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value:
            amount -= entry.amount
        else:
            amount += entry.amount
    amount = quantize_2(amount)

    formula_version = calculation.formula_version if calculation else PAYOUT_V1
    eligible_seconds: int | None = None
    excluded: dict[str, int] | None = None
    hourly_rate: Decimal | None = None
    capped_seconds: int | None = None
    lagos_day_value: date | None = None
    cap_seconds: int | None = None
    day_payable_seconds: int | None = None
    superseded = False

    if calculation is not None and calculation.formula_version == PAYOUT_V2:
        eligible_seconds = calculation.eligible_seconds
        excluded = calculation.excluded_seconds_by_reason or {}
        capped_seconds = calculation.payable_seconds
        metadata = calculation.payout_metadata or {}
        rates = metadata.get("rates") or {}
        if rates.get("hourly_rate_naira") is not None:
            hourly_rate = Decimal(str(rates["hourly_rate_naira"]))
        cap_metadata = metadata.get("cap") or {}
        cap_seconds = cap_metadata.get("cap_seconds")
        if metadata.get("lagos_day"):
            lagos_day_value = date.fromisoformat(metadata["lagos_day"])

        recompute_entries = [
            entry
            for entry in entries
            if (entry.ledger_metadata or {}).get("recompute_day")
            and entry.status != EarningsLedgerEntryStatus.VOIDED.value
        ]
        if recompute_entries:
            superseded = True
            newest = recompute_entries[-1]
            stored = (newest.ledger_metadata or {}).get("breakdown") or {}
            if stored.get("eligible_seconds") is not None:
                eligible_seconds = int(stored["eligible_seconds"])
            if stored.get("payable_seconds") is not None:
                capped_seconds = int(stored["payable_seconds"])
            if stored.get("hourly_rate_naira") is not None:
                hourly_rate = Decimal(str(stored["hourly_rate_naira"]))
            if stored.get("cap_seconds") is not None:
                cap_seconds = int(stored["cap_seconds"])

        if lagos_day_value is not None:
            day_payable_seconds = await day_consumed_payable_seconds(
                session,
                driver_profile_id=profile.id,
                campaign_id=trip.campaign_id,
                lagos_day=lagos_day_value,
            )

    return DriverTripBreakdown(
        trip_session_id=trip.id,
        formula_version=formula_version,
        currency=currency,
        amount=amount,
        eligible_seconds=eligible_seconds,
        excluded_seconds_by_reason=excluded,
        hourly_rate=hourly_rate,
        capped_seconds=capped_seconds,
        superseded_by_recompute=superseded,
        entries=entries,
        lagos_day=lagos_day_value,
        cap_seconds=cap_seconds,
        day_payable_seconds=day_payable_seconds,
    )
