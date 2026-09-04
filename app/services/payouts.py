import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Text as SQLText
from sqlalchemy import and_, case, cast, false, func, or_, select, text, update
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
    AssignmentRuleBinding,
    CampaignPayoutRule,
    CampaignPayoutRuleRevision,
    CampaignPayoutRuleStatus,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCalculationStatus,
)
from app.models.trip import LocationPing, TripSession, TripSessionStatus
from app.models.trip_analytics import (
    FraudFlagSeverity,
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.schemas.payouts import (
    CampaignPayoutRuleCreate,
    CampaignPayoutRuleRevisionCreate,
    CampaignPayoutRuleUpdate,
)
from app.services.campaign_cancellations import campaign_financial_cutoff
from app.services.campaigns import get_advertiser_campaign
from app.services.drivers import get_required_driver_profile_with_user_by_user_id
from app.services.fraud_holds import fraud_hold_counts
from app.services.impressions import (
    ensure_current_estimate_source,
    get_authoritative_estimate_for_trip,
    impression_estimate_stale,
    impression_output_fingerprint,
    quantize_2,
    quantize_4,
)
from app.services.payout_debt import driver_money_balance, record_reversal_obligation
from app.services.payout_eligibility import (
    D22_ROLLING_CONFIRMATION_WINDOWS,
    D22_ROLLING_MAX_DISPLACEMENT_M,
    D22_ROLLING_RELEASE_WINDOWS,
    D22_ROLLING_STRIDE_SECONDS,
    D22_ROLLING_WINDOW_SECONDS,
    STATIONARY_POLICY_V1,
    EligibilityParams,
    EligibilityPing,
    classify_session,
)
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
    database_clock,
)
from app.services.provenance import stable_source_fingerprint
from app.services.trip_analytics import (
    analytics_not_found,
    analytics_output_fingerprint,
    ensure_current_analytics_formula,
    ensure_postgis,
)
from app.services.trip_evidence import verify_manifest_receipt
from app.services.trips import trip_not_found

logger = logging.getLogger(__name__)

DECIMAL_2 = Decimal("0.01")
ZERO = Decimal("0")
PAYOUT_V1 = "payout_v1"
PAYOUT_V2 = "payout_v2"
PAYOUT_V3 = "payout_v3"
PAYOUT_FORMULA_VERSIONS = frozenset({PAYOUT_V1, PAYOUT_V2})
# Classified in-service by name (MNY-06A) — the FND-07 shared classifier in
# app/db/integrity.py is a reserved surface and stays untouched.
RULE_REVISION_UNIQUE_CONSTRAINTS = (
    "uq_campaign_payout_rule_revisions_campaign_number",
    "uq_campaign_payout_rule_revisions_campaign_effective",
)
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
        "rolling_window_seconds",
        "rolling_stride_seconds",
        "rolling_max_displacement_m",
        "rolling_confirmation_windows",
        "rolling_release_windows",
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


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def payout_time_bounds(
    session: AsyncSession,
    *,
    trip: TripSession,
    window_end_at: datetime | None,
) -> tuple[datetime, datetime | None, datetime | None]:
    """Return the economic trip end, effective campaign end and frozen cutoff."""
    cutoff = await campaign_financial_cutoff(session, trip.campaign_id)
    trip_end = _aware_utc(trip.ended_at)
    economic_end = min(trip_end, cutoff) if cutoff is not None else trip_end
    economic_end = max(_aware_utc(trip.started_at), economic_end)
    effective_window_end = window_end_at
    if cutoff is not None and (
        effective_window_end is None or cutoff < _aware_utc(effective_window_end)
    ):
        effective_window_end = cutoff
    return economic_end, effective_window_end, cutoff


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
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


async def require_paycap_predecessors_processed(
    session: AsyncSession,
    *,
    trip: TripSession,
    lagos_days: list[date],
) -> None:
    """Refuse arrival-order allocation while an earlier overlapping trip is unresolved.

    Callers hold every listed day lock. A calculation of any status or formula
    is authoritative for ordering purposes; the shared-cap reader separately
    decides whether that authority consumes payable seconds.
    """
    overlap_clauses = []
    for day in lagos_days:
        day_start_utc, day_end_utc = lagos_day_utc_range(day)
        overlap_clauses.append(
            and_(
                TripSession.started_at < day_end_utc,
                func.coalesce(TripSession.ended_at, TripSession.started_at) >= day_start_utc,
            )
        )
    calculation_exists = (
        select(PayoutCalculation.id)
        .where(PayoutCalculation.trip_session_id == TripSession.id)
        .correlate(TripSession)
        .exists()
    )
    predecessor = await session.scalar(
        select(TripSession.id)
        .where(
            TripSession.driver_profile_id == trip.driver_profile_id,
            TripSession.campaign_id == trip.campaign_id,
            TripSession.status == TripSessionStatus.SEALED.value,
            TripSession.ended_at.is_not(None),
            or_(
                TripSession.started_at < trip.started_at,
                and_(
                    TripSession.started_at == trip.started_at,
                    TripSession.id < trip.id,
                ),
            ),
            or_(*overlap_clauses),
            ~calculation_exists,
        )
        .order_by(TripSession.started_at, TripSession.id)
        .limit(1)
    )
    if predecessor is not None:
        raise AppError(
            "PAYOUT_DAY_PREDECESSOR_UNPROCESSED",
            "An earlier trip overlapping this payout day must be processed first",
            status_code=status.HTTP_409_CONFLICT,
            details={"predecessor_trip_id": str(predecessor)},
        )


@dataclass(frozen=True)
class DriverCurrencyEarnings:
    currency: str
    pending_amount: Decimal
    available_amount: Decimal
    paid_amount: Decimal
    voided_amount: Decimal
    lifetime_earned_amount: Decimal
    released_available_amount: Decimal
    cash_paid_amount: Decimal
    carry_forward_debt_amount: Decimal
    batch_payable_amount: Decimal
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
    """Economic/provenance sign convention.

    A debt remainder is settlement provenance for an already-recorded source,
    never a second economic earning. Reversals are negative; a non-voided
    original remains economic even if allocation changes its settlement status
    to ``reversed``.
    """
    return case(
        (
            EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.DEBT_REMAINDER.value,
            0,
        ),
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


def invalid_rule_revision(message: str) -> AppError:
    return AppError(
        "INVALID_PAYOUT_RULE_REVISION",
        message,
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def rule_revision_conflict() -> AppError:
    return AppError(
        "PAYOUT_RULE_REVISION_CONFLICT",
        "A concurrent revision was created for this campaign; re-read the revision chain and retry",
        status_code=status.HTTP_409_CONFLICT,
    )


def rule_mutation_retired(fields: list[str]) -> AppError:
    return AppError(
        "PAYOUT_RULE_MUTATION_RETIRED",
        "payout_v2 rule values are immutable; create a payout-rule revision"
        " instead of editing the rule",
        status_code=status.HTTP_409_CONFLICT,
        details={"retired_fields": fields},
    )


def rule_revisions_exist() -> AppError:
    return AppError(
        "PAYOUT_RULE_REVISIONS_EXIST",
        "This campaign's payout values are governed by an immutable revision"
        " chain; create a new revision instead of a new rule",
        status_code=status.HTTP_409_CONFLICT,
    )


def payout_source_mismatch(mismatches: list[dict[str, str]]) -> AppError:
    return AppError(
        "PAYOUT_SOURCE_MISMATCH",
        "Trip, analytics, and impression estimate source fields must match",
        status_code=status.HTTP_400_BAD_REQUEST,
        details={"mismatches": mismatches},
    )


def recompute_requires_correction_order() -> AppError:
    """PR7: the direct execute path is retired — ALL retroactive recomputes
    execute only through an approved maker-checker correction order,
    regardless of delta sign."""
    return AppError(
        "RECOMPUTE_REQUIRES_CORRECTION_ORDER",
        "Direct day recompute is retired; project and execute an approved"
        " payout correction order instead",
        status_code=status.HTTP_409_CONFLICT,
    )


def correction_release_at_required() -> AppError:
    return AppError(
        "CORRECTION_RELEASE_AT_REQUIRED",
        "The projected correction contains positive deltas; execution requires"
        " an explicit release_at for the pending entries (Q22 — no default is"
        " invented)",
        status_code=status.HTTP_400_BAD_REQUEST,
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
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise AppError(
            "INVALID_CURRENCY",
            "Currency must be a 3-letter code",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized


def merge_payout_metadata(prefix: dict | None, authoritative: dict) -> dict:
    """Attach caller context without allowing it to replace payout evidence."""
    return {**(prefix or {}), **authoritative}


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
        field for field in V1_RULE_FIELDS if getattr(payload, field, None) is not None
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
        raise invalid_rule_values("daily_payable_hours_cap is required for payout_v2 rules (D4)")
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
        field for field in V2_RULE_FIELDS if getattr(payload, field, None) is not None
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


async def campaign_has_rule_revisions(session: AsyncSession, campaign_id: UUID) -> bool:
    revision_id = await session.scalar(
        select(CampaignPayoutRuleRevision.id)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
        .limit(1)
    )
    return revision_id is not None


async def create_campaign_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    created_by_user_id: UUID,
    payload: CampaignPayoutRuleCreate,
    settings: Settings,
) -> tuple[CampaignPayoutRule, CampaignPayoutRuleRevision | None]:
    await get_campaign(session, campaign_id)
    # PR3(a): once a campaign has an immutable revision chain, rule creation
    # (and with it deactivate_other_active_rules) is retired for it.
    if await campaign_has_rule_revisions(session, campaign_id):
        raise rule_revisions_exist()
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
    genesis = None
    if rule.formula_version == PAYOUT_V2 and rule.status == CampaignPayoutRuleStatus.ACTIVE.value:
        # PR3: a new campaign's governing rule and revision 1 are atomic —
        # the genesis snapshot of the campaign's payout_v3 value chain.
        genesis = CampaignPayoutRuleRevision(
            campaign_id=campaign_id,
            payout_rule_id=rule.id,
            revision_number=1,
            effective_from=rule.created_at,
            hourly_rate_naira=rule.hourly_rate_naira,
            premium_hourly_rate_naira=None,
            daily_payable_hours_cap=rule.daily_payable_hours_cap,
            currency=rule.currency,
            eligibility_params=rule.eligibility_params or {},
            formula_version=PAYOUT_V3,
            reason="genesis: initial payout_v2 rule values at rule creation",
            created_by_user_id=created_by_user_id,
        )
        session.add(genesis)
        await session.flush()
        await session.refresh(genesis)
    return rule, genesis


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
    other_model_fields = V1_RULE_FIELDS if rule.formula_version == PAYOUT_V2 else V2_RULE_FIELDS
    set_other_fields = sorted(
        field for field in other_model_fields if update_values.get(field) is not None
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
        # MNY-06A: v2 value mutation is retired — the append-only revision
        # chain is the only value-change path.
        retired_fields = sorted(
            field for field in V2_RULE_FIELDS | {"currency"} if field in update_values
        )
        if retired_fields:
            raise rule_mutation_retired(retired_fields)
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


def _is_rule_revision_unique_conflict(exc: IntegrityError) -> bool:
    message = str(exc.orig) if exc.orig is not None else str(exc)
    return any(name in message for name in RULE_REVISION_UNIQUE_CONSTRAINTS)


def _ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def latest_payout_rule_revision(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignPayoutRuleRevision | None:
    return await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
        .order_by(CampaignPayoutRuleRevision.revision_number.desc())
        .limit(1)
    )


async def create_payout_rule_revision(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
    payload: CampaignPayoutRuleRevisionCreate,
    actor_user_id: UUID,
) -> tuple[CampaignPayoutRuleRevision, CampaignPayoutRuleRevision | None]:
    """Append one immutable revision to the campaign's value chain (PR1).

    Guards: effective_from strictly after the latest revision's (no
    retro-insertion — retroactivity is MNY-06C's correction order) and not
    before the DB clock. A campaign-scoped authority lock serializes valid
    concurrent publications into successive, gap-free revision numbers and
    shares the same boundary as assignment acceptance. Returns (revision,
    previous) so the caller can audit full before/after values.
    """
    await acquire_campaign_terms_lock(session, campaign_id)
    db_now = await database_clock(session)
    rule = await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    if rule.formula_version != PAYOUT_V2:
        raise invalid_rule_revision(
            "payout-rule revisions extend the hourly (payout_v2) rule model;"
            f" this rule is {rule.formula_version}"
        )
    if rule.status != CampaignPayoutRuleStatus.ACTIVE.value:
        raise rule_inactive()
    validate_eligibility_params_overlay(payload.eligibility_params)

    latest = await latest_payout_rule_revision(session, campaign_id)
    if latest is not None and payload.effective_from <= _ensure_utc_aware(latest.effective_from):
        raise invalid_rule_revision(
            "effective_from must be strictly after the latest revision's"
            " effective_from; retroactive changes require a correction order"
        )
    if payload.effective_from < _ensure_utc_aware(db_now):
        raise invalid_rule_revision("effective_from must not be before the database clock")

    revision = CampaignPayoutRuleRevision(
        campaign_id=campaign_id,
        payout_rule_id=rule.id,
        revision_number=(latest.revision_number + 1) if latest is not None else 1,
        effective_from=payload.effective_from,
        hourly_rate_naira=payload.hourly_rate_naira,
        premium_hourly_rate_naira=payload.premium_hourly_rate_naira,
        daily_payable_hours_cap=payload.daily_payable_hours_cap,
        currency=rule.currency,
        eligibility_params=payload.eligibility_params,
        formula_version=PAYOUT_V3,
        reason=payload.reason,
        created_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(revision)
            await session.flush()
    except IntegrityError as exc:
        if _is_rule_revision_unique_conflict(exc):
            raise rule_revision_conflict() from exc
        raise
    await session.refresh(revision)
    return revision, latest


async def list_payout_rule_revisions(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[CampaignPayoutRuleRevision], int]:
    await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    total = await session.scalar(
        select(func.count())
        .select_from(CampaignPayoutRuleRevision)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
    )
    result = await session.execute(
        select(CampaignPayoutRuleRevision)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
        .order_by(CampaignPayoutRuleRevision.revision_number.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_trip_for_payout(
    session: AsyncSession, trip_id: UUID, settings: Settings
) -> TripSession:
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
    if trip.evidence_protocol_version == 2:
        if trip.evidence_manifest_verified_at is None or not verify_manifest_receipt(
            trip, settings
        ):
            raise AppError(
                "TRIP_EVIDENCE_NOT_VERIFIED",
                "Payout requires an authenticated v2 trip evidence manifest",
                status_code=status.HTTP_409_CONFLICT,
            )
    if trip.evidence_protocol_version == 1:
        existing_money = await session.scalar(
            select(PayoutCalculation.id)
            .where(PayoutCalculation.trip_session_id == trip.id)
            .limit(1)
        ) or await session.scalar(
            select(EarningsLedgerEntry.id)
            .where(EarningsLedgerEntry.trip_session_id == trip.id)
            .limit(1)
        )
        if existing_money is None:
            raise AppError(
                "LEGACY_TRIP_MONEY_ORIGINATION_PROHIBITED",
                "Legacy trip evidence cannot originate new money",
                status_code=status.HTTP_409_CONFLICT,
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
    estimate = await get_authoritative_estimate_for_trip(
        session,
        trip_id=trip_id,
        settings=settings,
        validate_source=False,
    )
    if estimate is None:
        raise impression_estimate_not_found()
    current = await get_authoritative_estimate_for_trip(
        session,
        trip_id=trip_id,
        settings=settings,
    )
    if current is None:
        raise impression_estimate_stale()
    return current


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
        if analytics_fingerprint != analytics_output_fingerprint(
            analytics
        ) or impression_fingerprint != impression_output_fingerprint(estimate):
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
    return effective_eligibility_params_overlay(settings, rule.eligibility_params)


def effective_eligibility_params_overlay(
    settings: Settings,
    overlay: dict | None,
) -> EligibilityParams:
    overlay = overlay or {}

    def value(key: str, fallback: float) -> float:
        raw = overlay.get(key, fallback)
        return float(raw)

    return EligibilityParams(
        stationary_radius_m=value(
            "stationary_radius_m", settings.payout_eligibility_stationary_radius_m
        ),
        stationary_window_seconds=int(
            value("stationary_window_min", settings.payout_eligibility_stationary_window_min) * 60
        ),
        stationary_grace_seconds=int(
            value("stationary_grace_min", settings.payout_eligibility_stationary_grace_min) * 60
        ),
        max_accuracy_m=value("max_accuracy_m", settings.payout_eligibility_max_accuracy_m),
        teleport_kmh=value("teleport_kmh", settings.payout_eligibility_teleport_kmh),
        max_ping_gap_seconds=int(
            value("max_ping_gap_seconds", settings.payout_eligibility_max_ping_gap_seconds)
        ),
        rolling_window_seconds=int(
            value(
                "rolling_window_seconds",
                D22_ROLLING_WINDOW_SECONDS,
            )
        ),
        rolling_stride_seconds=int(
            value(
                "rolling_stride_seconds",
                D22_ROLLING_STRIDE_SECONDS,
            )
        ),
        rolling_max_displacement_m=value(
            "rolling_max_displacement_m",
            D22_ROLLING_MAX_DISPLACEMENT_M,
        ),
        rolling_confirmation_windows=int(
            value(
                "rolling_confirmation_windows",
                D22_ROLLING_CONFIRMATION_WINDOWS,
            )
        ),
        rolling_release_windows=int(
            value(
                "rolling_release_windows",
                D22_ROLLING_RELEASE_WINDOWS,
            )
        ),
    )


RESOLVED_ELIGIBILITY_PARAM_KEYS = frozenset(EligibilityParams.__dataclass_fields__)


def frozen_eligibility_params(binding: AssignmentRuleBinding) -> EligibilityParams:
    """Read the complete acceptance-time classifier values, never Settings.

    Bindings created before migration 0021 cannot prove a complete snapshot;
    fail closed rather than silently filling their gaps from mutable runtime
    configuration.
    """
    if binding.stationary_policy_marker != STATIONARY_POLICY_V1:
        raise AppError(
            "PAYOUT_STATIONARY_POLICY_UNRESOLVED",
            "The payout_v3 assignment binding does not contain the approved"
            " stationary detector policy; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    snapshot = binding.resolved_eligibility_params or {}
    if set(snapshot) != RESOLVED_ELIGIBILITY_PARAM_KEYS:
        raise AppError(
            "PAYOUT_BINDING_INCOMPLETE",
            "The payout_v3 assignment binding does not contain a complete"
            " frozen eligibility snapshot; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    return EligibilityParams(
        stationary_radius_m=float(snapshot["stationary_radius_m"]),
        stationary_window_seconds=int(snapshot["stationary_window_seconds"]),
        stationary_grace_seconds=int(snapshot["stationary_grace_seconds"]),
        max_accuracy_m=float(snapshot["max_accuracy_m"]),
        teleport_kmh=float(snapshot["teleport_kmh"]),
        max_ping_gap_seconds=int(snapshot["max_ping_gap_seconds"]),
        rolling_window_seconds=int(snapshot["rolling_window_seconds"]),
        rolling_stride_seconds=int(snapshot["rolling_stride_seconds"]),
        rolling_max_displacement_m=float(snapshot["rolling_max_displacement_m"]),
        rolling_confirmation_windows=int(snapshot["rolling_confirmation_windows"]),
        rolling_release_windows=int(snapshot["rolling_release_windows"]),
    )


def validate_eligibility_params_overlay(overlay: dict | None) -> None:
    if overlay is None:
        return
    unknown = sorted(set(overlay) - ELIGIBILITY_PARAM_KEYS)
    if unknown:
        raise invalid_rule_values(f"Unknown eligibility_params keys: {', '.join(unknown)}")
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
    premium_zone_ids: list[UUID] | None = None,
    frozen_premium_zone_wkts: list[str] | None = None,
    frozen_exclusion_zone_wkts: list[str] | None = None,
    recorded_through: datetime | None = None,
) -> list[EligibilityPingRow]:
    """One PostGIS round trip: pings plus geofence/tier membership.

    payout_v2 keeps its target-minus-exclusion eligibility rule. payout_v3
    supplies immutable geometry snapshots: exclusion stays unpaid, target
    becomes premium, and valid time outside target earns base pay.
    """

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
    frozen_geography = (
        frozen_premium_zone_wkts is not None and frozen_exclusion_zone_wkts is not None
    )

    def frozen_zone_hit(wkts: list[str]):
        conditions = [
            func.ST_Intersects(func.ST_GeomFromText(wkt, 4326), LocationPing.geom) for wkt in wkts
        ]
        return or_(*conditions) if conditions else false()

    if frozen_geography:
        # D18/Q5 payout_v3: target geometry is a premium tier, not an
        # eligibility boundary. Valid time outside it earns base pay; only
        # the frozen exclusion area remains geographically unpaid.
        in_area = ~frozen_zone_hit(frozen_exclusion_zone_wkts or [])
        in_premium = frozen_zone_hit(frozen_premium_zone_wkts or [])
    else:
        in_area = and_(
            or_(~has_target_zones, zone_hit(CampaignZoneType.TARGET.value)),
            ~zone_hit(CampaignZoneType.EXCLUSION.value),
        )
    if not frozen_geography and premium_zone_ids:
        in_premium = (
            select(CampaignZone.id)
            .where(
                CampaignZone.id.in_(premium_zone_ids),
                func.ST_Intersects(CampaignZone.geom, LocationPing.geom),
            )
            .correlate(LocationPing)
            .exists()
        )
    elif not frozen_geography:
        in_premium = false()
    ping_filters = [LocationPing.trip_session_id == trip_id]
    if recorded_through is not None:
        ping_filters.append(LocationPing.recorded_at <= recorded_through)
    result = await session.execute(
        select(
            LocationPing.id,
            LocationPing.recorded_at,
            LocationPing.latitude,
            LocationPing.longitude,
            LocationPing.accuracy_m,
            in_area.label("in_area"),
            in_premium.label("in_premium"),
        )
        .where(*ping_filters)
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
                in_premium=bool(row.in_premium),
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
                {"id": row.id, "geom": row.geom_wkb, "updated_at": row.updated_at} for row in rows
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
            "eligibility_params": params.as_legacy_metadata(),
            "ping_set_fingerprint": ping_fingerprint,
            "zone_state_fingerprint": zone_fingerprint,
            "window_start_at": window_start_at,
            "window_end_at": window_end_at,
        }
    )


def v3_inputs_fingerprint(
    *,
    binding: AssignmentRuleBinding,
    params: EligibilityParams,
    ping_fingerprint: str,
    zone_fingerprint: str,
    window_start_at: datetime | None,
    window_end_at: datetime | None,
) -> str:
    """payout_v3 dispute-replay fingerprint (B2/Q6): extends the v2 inputs
    with every frozen binding — binding/revision ids, both tier rates, cap,
    the frozen premium zone set + geometry hash, the frozen eligibility
    overlay, and the fail-closed stationary policy marker (EXT-RM2-POLICY)."""
    return stable_source_fingerprint(
        {
            "formula_version": PAYOUT_V3,
            "binding_id": binding.id,
            "revision_id": binding.revision_id,
            "hourly_rate_naira": Decimal(binding.hourly_rate_naira),
            "premium_hourly_rate_naira": (
                Decimal(binding.premium_hourly_rate_naira)
                if binding.premium_hourly_rate_naira is not None
                else None
            ),
            "daily_payable_hours_cap": Decimal(binding.daily_payable_hours_cap),
            "eligibility_params": params.as_metadata(),
            "frozen_eligibility_params": binding.eligibility_params or {},
            "resolved_eligibility_params": binding.resolved_eligibility_params,
            "premium_zone_ids": list(binding.premium_zone_ids or []),
            "premium_zone_geometry_hash": binding.premium_zone_geometry_hash,
            "exclusion_zone_ids": list(binding.exclusion_zone_ids or []),
            "exclusion_zone_geometry_hash": binding.exclusion_zone_geometry_hash,
            "stationary_policy_marker": binding.stationary_policy_marker,
            "currency": binding.currency,
            "ping_set_fingerprint": ping_fingerprint,
            "zone_state_fingerprint": zone_fingerprint,
            "window_start_at": window_start_at,
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
    """Return authoritative accepted windows or fail closed for legacy v3."""
    if not binding.campaign_window_frozen:
        raise AppError(
            "PAYOUT_BINDING_WINDOW_NOT_FROZEN",
            "The payout binding predates the accepted campaign-window freeze; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    return binding.campaign_window_start_at, binding.campaign_window_end_at


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

    ONE shared D4 cap pool per driver/campaign/Lagos-day across engines
    (PR5): counts both payout_v2 and payout_v3 calculations' stored per-day
    allocations. Counts every trip that *overlaps* the day, charging each
    only the seconds its stored allocation assigns to that day (RM1) — a
    cross-midnight trip consumes each day's allowance separately. Per-trip
    MAX dedupes a trip calculated under two rules or engines (counted once,
    conservatively the larger); trips whose trip_payout entry is voided
    consume nothing. Callers hold that day's paycap advisory lock."""
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
            PayoutCalculation.id.label("calculation_id"),
            PayoutCalculation.trip_session_id.label("trip_id"),
            PayoutCalculation.formula_version.label("formula_version"),
            PayoutCalculation.status.label("calculation_status"),
            PayoutCalculation.payable_seconds_by_day.label("by_day"),
            PayoutCalculation.payable_seconds.label("payable"),
            TripSession.started_at.label("started_at"),
        )
        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
        .where(
            PayoutCalculation.driver_profile_id == driver_profile_id,
            PayoutCalculation.campaign_id == campaign_id,
            PayoutCalculation.formula_version.in_((PAYOUT_V2, PAYOUT_V3)),
            PayoutCalculation.status.in_(
                (
                    PayoutCalculationStatus.CALCULATED.value,
                    PayoutCalculationStatus.INSUFFICIENT_DATA.value,
                )
            ),
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
    calculation_authorities_by_trip: dict[UUID, set[tuple[str, str]]] = {}
    for row in rows.all():
        calculation_authorities_by_trip.setdefault(row.trip_id, set()).add(
            (str(row.calculation_id), row.formula_version)
        )
        if row.calculation_status == PayoutCalculationStatus.CALCULATED.value:
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
        if (
            metadata.get("payout_calculation_id"),
            metadata.get("formula_version"),
        ) not in calculation_authorities_by_trip.get(entry.trip_session_id, set()):
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
    return quantize_ngn_half_up(Decimal(payable_seconds) * hourly_rate / SECONDS_PER_HOUR)


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
        "blocked" if status_value == PayoutCalculationStatus.BLOCKED.value else "insufficient_data"
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
        (estimate.estimated_impressions / Decimal("1000")) * rule.estimated_impression_rate_per_1000
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
    # The shared hold snapshot covers open, acknowledged and confirmed. A
    # local/open-only predicate here would let the floor restore held pay.
    no_active_holds = all(count == 0 for count in counts.values())
    if (
        gross_payout > 0
        and no_active_holds
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
                "estimated_impression_rate_per_1000": str(rule.estimated_impression_rate_per_1000),
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
    economic_end, effective_window_end, _ = await payout_time_bounds(
        session, trip=trip, window_end_at=campaign.end_at
    )
    ping_rows = await load_eligibility_pings(
        session,
        trip_id=trip.id,
        campaign_id=trip.campaign_id,
        recorded_through=economic_end,
    )
    zone_state = await campaign_zone_state(session, trip.campaign_id)
    current = v2_inputs_fingerprint(
        rule=rule,
        params=params,
        ping_fingerprint=ping_set_fingerprint(ping_rows),
        zone_fingerprint=zone_state.fingerprint,
        window_start_at=campaign.start_at,
        window_end_at=effective_window_end,
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
    metadata_prefix: dict | None = None,
    now: datetime | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    ensure_postgis(session)
    calculated_at = now or utc_now()
    campaign = await get_campaign(session, trip.campaign_id)
    params = effective_eligibility_params(settings, rule)
    economic_end, effective_window_end, cutoff = await payout_time_bounds(
        session, trip=trip, window_end_at=campaign.end_at
    )
    ping_rows = await load_eligibility_pings(
        session,
        trip_id=trip.id,
        campaign_id=trip.campaign_id,
        recorded_through=economic_end,
    )
    breakdown = classify_session(
        session_started_at=trip.started_at,
        session_ended_at=economic_end,
        pings=[row.ping for row in ping_rows],
        window_start_at=campaign.start_at,
        window_end_at=effective_window_end,
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
        window_end_at=effective_window_end,
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
    await require_paycap_predecessors_processed(
        session,
        trip=trip,
        lagos_days=lagos_days,
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
        "eligibility_params": params.as_legacy_metadata(),
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
        "financial_cutoff_at": cutoff.isoformat() if cutoff is not None else None,
        "recorded_trip_end_at": _aware_utc(trip.ended_at).isoformat(),
    }
    payout_metadata = merge_payout_metadata(metadata_prefix, payout_metadata)

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
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation, metadata_prefix=metadata_prefix)
    return calculation, ledger, True


def price_tiered_payable_seconds(
    base_seconds: int,
    premium_seconds: int,
    base_rate: Decimal,
    premium_rate: Decimal,
) -> Decimal:
    """payout_v3 pricing: each payable second at its own tier rate, quantized
    exactly once to 2dp NGN with ROUND_HALF_UP per ledger amount (16.1)."""
    return quantize_ngn_half_up(
        (Decimal(base_seconds) * base_rate + Decimal(premium_seconds) * premium_rate)
        / SECONDS_PER_HOUR
    )


@dataclass(frozen=True)
class TierAmountComponents:
    base_amount: Decimal
    premium_amount: Decimal


def allocate_tier_amount_components(
    *,
    base_seconds: int,
    premium_seconds: int,
    base_rate: Decimal,
    premium_rate: Decimal,
    authoritative_total: Decimal,
) -> TierAmountComponents:
    """Split the once-quantized ledger total without creating a new total.

    Base receives its HALF_UP raw share and premium receives the residual.
    Empty tiers remain exactly zero. The two components therefore always sum
    to the authoritative payout/correction target, including half-kobo cases.
    """
    total = quantize_ngn_half_up(authoritative_total)
    if base_seconds <= 0:
        return TierAmountComponents(Decimal("0.00"), total)
    if premium_seconds <= 0:
        return TierAmountComponents(total, Decimal("0.00"))
    base_amount = quantize_ngn_half_up(Decimal(base_seconds) * base_rate / SECONDS_PER_HOUR)
    rounded_premium = quantize_ngn_half_up(
        Decimal(premium_seconds) * premium_rate / SECONDS_PER_HOUR
    )
    residual = total - base_amount - rounded_premium
    return TierAmountComponents(base_amount, quantize_2(rounded_premium + residual))


async def calculate_trip_payout_v3(
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
    """payout_v3 (MNY-06B): priced EXCLUSIVELY from the assignment's frozen
    acceptance-time binding — later revisions never reprice accepted work.

    Eligibility/exclusions run the unchanged v2 classifier; eligible slices
    additionally carry base|premium per the binding's frozen premium zone ids
    (PR11/PR14). Cap-before-price per Lagos day is preserved (RM1/D4) with
    CHRONOLOGICAL fill (PR4): the earliest eligible seconds consume the day's
    cap first, each second priced at its own tier rate; the cap pool is
    shared with payout_v2 (PR5). A NULL frozen premium rate prices premium
    slices at the base rate (no premium disclosed on the revision)."""
    ensure_postgis(session)
    calculated_at = now or utc_now()
    await get_campaign(session, trip.campaign_id)
    window_start_at, window_end_at = frozen_campaign_window(binding)
    economic_end, effective_window_end, cutoff = await payout_time_bounds(
        session, trip=trip, window_end_at=window_end_at
    )
    revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
    if revision is None or revision.currency != binding.currency:
        raise invalid_rule_values(
            "the frozen assignment binding must match its payout revision currency"
        )
    params = frozen_eligibility_params(binding)
    premium_zone_uuids = [UUID(str(zone_id)) for zone_id in binding.premium_zone_ids or []]
    ping_rows = await load_eligibility_pings(
        session,
        trip_id=trip.id,
        campaign_id=trip.campaign_id,
        premium_zone_ids=premium_zone_uuids,
        frozen_premium_zone_wkts=list(binding.premium_zone_geometry_wkts or []),
        frozen_exclusion_zone_wkts=list(binding.exclusion_zone_geometry_wkts or []),
        recorded_through=economic_end,
    )
    breakdown = classify_session(
        session_started_at=trip.started_at,
        session_ended_at=economic_end,
        pings=[row.ping for row in ping_rows],
        window_start_at=window_start_at,
        window_end_at=effective_window_end,
        params=params,
        stationary_policy_marker=binding.stationary_policy_marker,
    )
    pings_fingerprint = ping_set_fingerprint(ping_rows)
    inputs_fingerprint = v3_inputs_fingerprint(
        binding=binding,
        params=params,
        ping_fingerprint=pings_fingerprint,
        zone_fingerprint=(
            f"{binding.premium_zone_geometry_hash}:{binding.exclusion_zone_geometry_hash}"
        ),
        window_start_at=window_start_at,
        window_end_at=effective_window_end,
    )

    lagos_day = lagos_day_for(trip.started_at)
    day_keys = sorted(breakdown.eligible_seconds_by_day) or [lagos_day.isoformat()]
    lagos_days = [date.fromisoformat(key) for key in day_keys]
    # Same advisory-lock discipline as v2 (RM1): locks BEFORE reading cap
    # consumption, sorted day order, never inside a savepoint.
    for day in lagos_days:
        await acquire_paycap_lock(
            session, paycap_lock_key(trip.driver_profile_id, trip.campaign_id, day)
        )
    await require_paycap_predecessors_processed(
        session,
        trip=trip,
        lagos_days=lagos_days,
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

    cap_seconds = int(Decimal(binding.daily_payable_hours_cap) * SECONDS_PER_HOUR)
    consumed_by_day: dict[str, int] = {}
    for day in lagos_days:
        key = day.isoformat()
        consumed_by_day[key] = await day_consumed_payable_seconds(
            session,
            driver_profile_id=trip.driver_profile_id,
            campaign_id=trip.campaign_id,
            lagos_day=day,
            exclude_trip_id=trip.id,
        )
    payable_by_day_tier: dict[str, dict[str, int]] = {}
    if status_value == PayoutCalculationStatus.CALCULATED.value:
        # PR4: chronological fill within each Lagos day — slices arrive in
        # chronological order and each day's remaining cap is drawn down as
        # its earliest eligible seconds pass, whatever their tier.
        remaining_by_day = {key: max(0, cap_seconds - consumed_by_day[key]) for key in day_keys}
        for eligible_slice in breakdown.eligible_slices:
            take = min(eligible_slice.length, remaining_by_day[eligible_slice.day])
            if take <= 0:
                continue
            remaining_by_day[eligible_slice.day] -= take
            tiers = payable_by_day_tier.setdefault(eligible_slice.day, {"base": 0, "premium": 0})
            tiers["premium" if eligible_slice.premium else "base"] += take
    payable_by_day = {
        key: tiers["base"] + tiers["premium"] for key, tiers in payable_by_day_tier.items()
    }
    payable_seconds = sum(payable_by_day.values())
    base_seconds = sum(tiers["base"] for tiers in payable_by_day_tier.values())
    premium_seconds = sum(tiers["premium"] for tiers in payable_by_day_tier.values())
    consumed_before = sum(consumed_by_day.values())
    base_rate = Decimal(binding.hourly_rate_naira)
    premium_rate = (
        Decimal(binding.premium_hourly_rate_naira)
        if binding.premium_hourly_rate_naira is not None
        else base_rate
    )
    amount = price_tiered_payable_seconds(base_seconds, premium_seconds, base_rate, premium_rate)
    tier_amounts = allocate_tier_amount_components(
        base_seconds=base_seconds,
        premium_seconds=premium_seconds,
        base_rate=base_rate,
        premium_rate=premium_rate,
        authoritative_total=amount,
    )

    payout_metadata = {
        "formula_version": PAYOUT_V3,
        "payout_rule_id": str(revision.payout_rule_id),
        "binding": {
            "binding_id": str(binding.id),
            "revision_id": str(binding.revision_id),
            "currency": binding.currency,
            "bound_at": binding.bound_at.isoformat(),
            "campaign_window_start_at": (
                window_start_at.isoformat() if window_start_at is not None else None
            ),
            "campaign_window_end_at": (
                window_end_at.isoformat() if window_end_at is not None else None
            ),
            "premium_zone_ids": list(binding.premium_zone_ids or []),
            "premium_zone_geometry_hash": binding.premium_zone_geometry_hash,
            "exclusion_zone_ids": list(binding.exclusion_zone_ids or []),
            "exclusion_zone_geometry_hash": binding.exclusion_zone_geometry_hash,
            "stationary_policy_marker": binding.stationary_policy_marker,
            "eligibility_params": binding.eligibility_params or {},
            "resolved_eligibility_params": binding.resolved_eligibility_params,
        },
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
            # Per-day-per-tier allocation (PR4); the 0015 column keeps its
            # day -> seconds shape so the shared cap pool reads v2 and v3
            # rows uniformly (PR5).
            "payable_seconds_by_day_tier": payable_by_day_tier,
        },
        "rates": {
            "hourly_rate_naira": str(base_rate),
            "premium_hourly_rate_naira": (
                str(Decimal(binding.premium_hourly_rate_naira))
                if binding.premium_hourly_rate_naira is not None
                else None
            ),
        },
        "eligibility_params": params.as_metadata(),
        "zone_state": {
            "source": "assignment_binding",
            "premium_fingerprint": binding.premium_zone_geometry_hash,
            "exclusion_fingerprint": binding.exclusion_zone_geometry_hash,
        },
        "ping_set_fingerprint": pings_fingerprint,
        "teleport_incident_count": breakdown.teleport_incident_count,
        "stationary_detector": {
            **breakdown.stationary_detector_evidence,
            "policy_fingerprint": stable_source_fingerprint(
                {
                    "version": binding.stationary_policy_marker,
                    "params": params.as_metadata(),
                }
            ),
        },
        "components": {
            "eligible_seconds": breakdown.eligible_seconds,
            "eligible_seconds_by_day": breakdown.eligible_seconds_by_day,
            "excluded_seconds_by_reason": breakdown.excluded_seconds_by_reason,
            "payable_seconds": payable_seconds,
            "payable_seconds_by_day": payable_by_day,
            "payable_seconds_by_day_tier": payable_by_day_tier,
            "base_payable_seconds": base_seconds,
            "premium_payable_seconds": premium_seconds,
            "base_amount": str(tier_amounts.base_amount),
            "premium_amount": str(tier_amounts.premium_amount),
            "amount": str(amount),
        },
        "source_analytics_formula_version": analytics.formula_version,
        "source_analytics_computed_at": analytics.computed_at.isoformat(),
        "source_analytics_fingerprint": analytics_output_fingerprint(analytics),
        "source_impression_formula_version": estimate.formula_version,
        "source_impression_estimated_at": estimate.estimated_at.isoformat(),
        "source_impression_fingerprint": impression_output_fingerprint(estimate),
        "financial_cutoff_at": cutoff.isoformat() if cutoff is not None else None,
        "recorded_trip_end_at": _aware_utc(trip.ended_at).isoformat(),
    }
    payout_metadata = merge_payout_metadata(metadata_prefix, payout_metadata)

    calculation = PayoutCalculation(
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        impression_estimate_id=estimate.id,
        payout_rule_id=revision.payout_rule_id,
        assignment_id=analytics.assignment_id,
        campaign_id=analytics.campaign_id,
        driver_profile_id=analytics.driver_profile_id,
        vehicle_id=analytics.vehicle_id,
        formula_version=PAYOUT_V3,
        status=status_value,
        currency=binding.currency,
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
            formula_version=PAYOUT_V3,
            payout_rule_id=revision.payout_rule_id,
        )
        if existing is None:
            raise
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation, metadata_prefix=metadata_prefix)
    return calculation, ledger, True


async def v3_calculation_is_stale(
    session: AsyncSession,
    calculation: PayoutCalculation,
    *,
    trip: TripSession,
    settings: Settings,
) -> bool:
    """Detect input drift for a payout_v3 calculation without recomputing
    money: re-derive the inputs fingerprint from the frozen binding and the
    current ping set, and compare. Money is never auto-rewritten."""
    binding = await binding_for_assignment(session, trip.assignment_id)
    if binding is None or not binding.campaign_window_frozen:
        return True
    revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
    if revision is None or revision.currency != binding.currency:
        return True
    await get_campaign(session, trip.campaign_id)
    window_start_at, window_end_at = frozen_campaign_window(binding)
    economic_end, effective_window_end, _ = await payout_time_bounds(
        session, trip=trip, window_end_at=window_end_at
    )
    params = frozen_eligibility_params(binding)
    ping_rows = await load_eligibility_pings(
        session,
        trip_id=trip.id,
        campaign_id=trip.campaign_id,
        frozen_premium_zone_wkts=list(binding.premium_zone_geometry_wkts or []),
        frozen_exclusion_zone_wkts=list(binding.exclusion_zone_geometry_wkts or []),
        recorded_through=economic_end,
    )
    current = v3_inputs_fingerprint(
        binding=binding,
        params=params,
        ping_fingerprint=ping_set_fingerprint(ping_rows),
        zone_fingerprint=(
            f"{binding.premium_zone_geometry_hash}:{binding.exclusion_zone_geometry_hash}"
        ),
        window_start_at=window_start_at,
        window_end_at=effective_window_end,
    )
    return calculation.currency != binding.currency or calculation.inputs_fingerprint != current


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
    metadata_prefix: dict | None = None,
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
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
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
    values["payout_metadata"] = merge_payout_metadata(metadata_prefix, values["payout_metadata"])

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
        ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
        return existing, ledger, False
    await session.refresh(calculation)
    ledger = await ensure_ledger_entry(session, calculation, metadata_prefix=metadata_prefix)
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
    metadata_prefix: dict | None = None,
) -> tuple[PayoutCalculation, EarningsLedgerEntry | None, bool]:
    """Per-rule formula dispatch (D2/D8, Q4/Q5) + engine routing (MNY-06B).

    Engine routing rule: a sealed trip computes payout_v3 if and only if its
    assignment has an assignment_rule_bindings row (acceptance-time freeze);
    trips without a binding compute payout_v2/v1 exactly as before.

    Rule-less path reuses the trip's latest calculation across ALL formula
    versions (one calculation chain per trip: a campaign switched
    payout_v1 -> payout_v2 never re-pays history). Fresh computation happens
    only when no calculation exists, under the governing active rule's model.
    payout_v2/v3 rows are write-once: with strict_staleness (admin surface)
    input drift raises PAYOUT_CALCULATION_STALE to flag it; the worker passes
    strict_staleness=False and reuses (recompute-day is the corrective tool).
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
            elif existing.formula_version == PAYOUT_V3:
                if strict_staleness and await v3_calculation_is_stale(
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
            ledger = await ensure_ledger_entry(session, existing, metadata_prefix=metadata_prefix)
            return existing, ledger, False

    # Engine routing (MNY-06B): binding presence decides the engine. A bound
    # assignment's trips price from the frozen acceptance-time values only.
    binding = await binding_for_assignment(session, trip.assignment_id)
    if binding is not None:
        if payout_rule_id is not None:
            revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
            if payout_rule_id != revision.payout_rule_id:
                raise invalid_rule_values(
                    "this trip's assignment is bound to a payout revision;"
                    " an explicit rule must match the bound rule identity"
                )
            # Write-once holds on the explicit-rule surface (mirror of v2):
            # a trip already calculated under another rule/formula is never
            # given a second calculation — flag it instead.
            existing_any = await existing_payout_calculation_for_trip_any_formula(
                session, trip_id=trip.id
            )
            if existing_any is not None and not (
                existing_any.formula_version == PAYOUT_V3
                and existing_any.payout_rule_id == revision.payout_rule_id
            ):
                raise payout_calculation_stale()
        return await calculate_trip_payout_v3(
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
                existing_any.formula_version == PAYOUT_V2 and existing_any.payout_rule_id == rule.id
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
            metadata_prefix=metadata_prefix,
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
        metadata_prefix=metadata_prefix,
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
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PENDING.value,
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
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.AVAILABLE.value,
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
            func.coalesce(
                func.sum(
                    case(
                        (
                            EarningsLedgerEntry.status == EarningsLedgerEntryStatus.PAID.value,
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
                            != EarningsLedgerEntryStatus.VOIDED.value,
                            signed_amount,
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
        paid = quantize_2(Decimal(str(row[4] or 0)))
        balance = await driver_money_balance(
            session,
            driver_profile_id=profile.id,
            currency=row[0],
        )
        totals.append(
            DriverCurrencyEarnings(
                currency=row[0],
                pending_amount=pending,
                available_amount=available,
                paid_amount=paid,
                voided_amount=voided,
                lifetime_earned_amount=quantize_2(Decimal(str(row[5] or 0))),
                released_available_amount=balance.released_available,
                cash_paid_amount=balance.cash_paid,
                carry_forward_debt_amount=balance.carry_forward_debt,
                batch_payable_amount=balance.batch_payable,
                ledger_entry_count=int(row[6] or 0),
            )
        )
    if not totals:
        totals.append(
            DriverCurrencyEarnings(
                currency=validate_currency_code(currency, fallback=settings.default_currency),
                pending_amount=Decimal("0.00"),
                available_amount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                voided_amount=Decimal("0.00"),
                lifetime_earned_amount=Decimal("0.00"),
                released_available_amount=Decimal("0.00"),
                cash_paid_amount=Decimal("0.00"),
                carry_forward_debt_amount=Decimal("0.00"),
                batch_payable_amount=Decimal("0.00"),
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
                            PayoutCalculation.status == PayoutCalculationStatus.CALCULATED.value,
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
    payable_seconds: int
    payable_by_day: dict[str, int]
    payable_by_day_tier: dict[str, dict[str, int]] | None
    hourly_rate: Decimal
    premium_hourly_rate: Decimal | None
    cap_seconds: int
    voided: bool
    current_ping_fingerprint: str | None
    stored_inputs_fingerprint: str | None
    governing_values: dict
    stationary_detector_evidence: dict | None


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
    """The v2-vs-v3 mixed-day refusal is retired (PR6): the recompute core
    prices both engines under one shared cap pool. Only formula versions with
    no seconds-based repricing model (payout_v1) still refuse."""
    return AppError(
        "PAYOUT_DAY_UNSUPPORTED_FORMULA",
        "The day holds calculations without a seconds-based payout model"
        " (payout_v1); recompute supports payout_v2 and payout_v3 only",
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


async def compute_payout_day_targets(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    driver_profile_id: UUID,
    lagos_date: date,
    settings: Settings,
) -> DayComputation:
    """PR6 v3-aware recompute core, shared by dry-run projection and execution.

    Re-runs one driver/campaign/Lagos-day under the same advisory lock as the
    pipeline and returns per-trip targets WITHOUT writing anything: payout_v2
    trips reprice from the governing rule row (existing recompute logic
    preserved) and payout_v3 trips from each trip's FROZEN acceptance-time
    binding — later revisions never reprice accepted work. The D4 cap is ONE
    shared chronological pool across both engines (PR4/PR5): trips consume it
    in start order against their own governing cap, and within a payout_v3
    trip the day's eligible slices fill chronologically, each second priced at
    its own tier. Calculations are never edited; a run with unchanged inputs
    targets exactly the posted position.
    """
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
    if any(
        calculation.formula_version not in (PAYOUT_V2, PAYOUT_V3)
        for calculation in latest_calculations
    ):
        raise payout_day_unsupported_formula()
    currencies = {calculation.currency for calculation in latest_calculations}
    if len(currencies) > 1:
        raise payout_day_currency_mismatch()
    day_currency = next(iter(currencies), None)

    rule: CampaignPayoutRule | None = None
    v2_params = None
    if any(calculation.formula_version == PAYOUT_V2 for calculation in latest_calculations):
        rule = await resolve_payout_rule(session, campaign_id=campaign_id, payout_rule_id=None)
        if rule.formula_version != PAYOUT_V2:
            raise invalid_rule_values(
                "recompute-day requires the governing rule to be payout_v2 for"
                " the day's payout_v2 calculations"
            )
        if rule.currency != day_currency:
            raise payout_day_currency_mismatch()
        v2_params = effective_eligibility_params(settings, rule)

    zone_state = await campaign_zone_state(session, campaign_id)

    consumed = 0  # ONE shared chronological cap pool across engines (PR5).
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
        formula_version = calculation.formula_version

        binding: AssignmentRuleBinding | None = None
        if formula_version == PAYOUT_V3:
            binding = await binding_for_assignment(session, trip.assignment_id)
            if binding is None:
                raise AppError(
                    "PAYOUT_BINDING_NOT_FOUND",
                    "A payout_v3 calculation exists but its assignment has no"
                    " frozen rule binding; resolve manually",
                    status_code=status.HTTP_409_CONFLICT,
                )
            revision = await session.get(CampaignPayoutRuleRevision, binding.revision_id)
            if (
                revision is None
                or revision.currency != binding.currency
                or calculation.currency != binding.currency
            ):
                raise payout_day_currency_mismatch()
            window_start_at, window_end_at = frozen_campaign_window(binding)
            trip_cap_seconds = int(Decimal(binding.daily_payable_hours_cap) * SECONDS_PER_HOUR)
            hourly_rate = Decimal(binding.hourly_rate_naira)
            premium_hourly_rate = (
                Decimal(binding.premium_hourly_rate_naira)
                if binding.premium_hourly_rate_naira is not None
                else None
            )
            v3_params = frozen_eligibility_params(binding)
            governing_values = {
                "engine": PAYOUT_V3,
                "binding_id": binding.id,
                "revision_id": binding.revision_id,
                "hourly_rate_naira": hourly_rate,
                "premium_hourly_rate_naira": premium_hourly_rate,
                "daily_payable_hours_cap": Decimal(binding.daily_payable_hours_cap),
                # Complete resolved values frozen at acceptance. Runtime
                # Settings never participate in payout_v3 replay.
                "eligibility_params": v3_params.as_metadata(),
                "frozen_eligibility_params": binding.eligibility_params or {},
                "resolved_eligibility_params": binding.resolved_eligibility_params,
                "premium_zone_ids": list(binding.premium_zone_ids or []),
                "premium_zone_geometry_hash": binding.premium_zone_geometry_hash,
                "exclusion_zone_ids": list(binding.exclusion_zone_ids or []),
                "exclusion_zone_geometry_hash": binding.exclusion_zone_geometry_hash,
                "stationary_policy_marker": binding.stationary_policy_marker,
                "campaign_window_start_at": window_start_at,
                "campaign_window_end_at": window_end_at,
                "currency": binding.currency,
            }
        else:
            trip_cap_seconds = daily_cap_seconds(rule)
            hourly_rate = Decimal(rule.hourly_rate_naira)
            premium_hourly_rate = None
            governing_values = {
                "engine": PAYOUT_V2,
                "payout_rule_id": rule.id,
                "hourly_rate_naira": hourly_rate,
                "daily_payable_hours_cap": Decimal(rule.daily_payable_hours_cap),
                "eligibility_params": v2_params.as_legacy_metadata(),
                "currency": rule.currency,
            }

        contract_window_end = (
            window_end_at if formula_version == PAYOUT_V3 else campaign.end_at
        )
        economic_end, effective_window_end, financial_cutoff = await payout_time_bounds(
            session, trip=trip, window_end_at=contract_window_end
        )
        governing_values["financial_cutoff_at"] = (
            financial_cutoff.isoformat() if financial_cutoff is not None else None
        )

        ping_fingerprint: str | None = None
        payable_by_day_tier: dict[str, dict[str, int]] | None = None
        stationary_detector_evidence: dict | None = None
        # blocked stays 0 (fraud posture, S2); insufficient_data is priced
        # from a fresh classification — the admin escape hatch for trips whose
        # analytics healed after the write-once calculation (D9).
        if voided or calculation.status == PayoutCalculationStatus.BLOCKED.value:
            eligible_seconds = 0
            excluded_seconds_by_reason: dict[str, int] = {}
            payable_seconds = 0
            payable_by_day: dict[str, int] = {}
            if formula_version == PAYOUT_V3:
                payable_by_day_tier = {}
            target_amount = Decimal("0.00")
        elif formula_version == PAYOUT_V2:
            ping_rows = await load_eligibility_pings(
                session,
                trip_id=trip.id,
                campaign_id=campaign_id,
                recorded_through=economic_end,
            )
            ping_fingerprint = ping_set_fingerprint(ping_rows)
            breakdown = classify_session(
                session_started_at=trip.started_at,
                session_ended_at=economic_end,
                pings=[row.ping for row in ping_rows],
                window_start_at=campaign.start_at,
                window_end_at=effective_window_end,
                params=v2_params,
            )
            eligible_seconds = breakdown.eligible_seconds
            excluded_seconds_by_reason = breakdown.excluded_seconds_by_reason
            # Re-allocate only the day being recomputed; the trip's seconds on
            # any other Lagos day keep their stored allocation, because those
            # days' caps are not being re-run under this lock (RM1). A prior
            # true-up's breakdown supersedes the calculation row for those
            # days (same chain as day_consumed_payable_seconds).
            day_eligible = breakdown.eligible_seconds_by_day.get(day_key, 0)
            day_payable = max(0, min(day_eligible, trip_cap_seconds - consumed))
            consumed += day_payable
            prior_breakdown = await _latest_recompute_breakdown(
                session,
                trip.id,
                payout_calculation_id=calculation.id,
                formula_version=formula_version,
            )
            if (
                prior_breakdown is not None
                and prior_breakdown.get("payable_seconds_by_day") is not None
            ):
                stored_by_day = prior_breakdown["payable_seconds_by_day"]
            else:
                stored_by_day = calculation.payable_seconds_by_day
            other_days = {
                key: int(value) for key, value in (stored_by_day or {}).items() if key != day_key
            }
            payable_by_day = dict(other_days)
            if day_payable > 0:
                payable_by_day[day_key] = day_payable
            payable_seconds = sum(payable_by_day.values())
            target_amount = price_payable_seconds(payable_seconds, hourly_rate)
        else:
            premium_zone_uuids = [UUID(str(zone_id)) for zone_id in binding.premium_zone_ids or []]
            ping_rows = await load_eligibility_pings(
                session,
                trip_id=trip.id,
                campaign_id=campaign_id,
                premium_zone_ids=premium_zone_uuids,
                frozen_premium_zone_wkts=list(binding.premium_zone_geometry_wkts or []),
                frozen_exclusion_zone_wkts=list(binding.exclusion_zone_geometry_wkts or []),
                recorded_through=economic_end,
            )
            ping_fingerprint = ping_set_fingerprint(ping_rows)
            breakdown = classify_session(
                session_started_at=trip.started_at,
                session_ended_at=economic_end,
                pings=[row.ping for row in ping_rows],
                window_start_at=window_start_at,
                window_end_at=effective_window_end,
                params=v3_params,
                stationary_policy_marker=binding.stationary_policy_marker,
            )
            stationary_detector_evidence = {
                **breakdown.stationary_detector_evidence,
                "policy_fingerprint": stable_source_fingerprint(
                    {
                        "version": binding.stationary_policy_marker,
                        "params": v3_params.as_metadata(),
                    }
                ),
            }
            eligible_seconds = breakdown.eligible_seconds
            excluded_seconds_by_reason = breakdown.excluded_seconds_by_reason
            # PR4 chronological fill of the recomputed day only: the trip's
            # earliest eligible seconds on this day draw the shared pool
            # first, whatever their tier.
            remaining = max(0, trip_cap_seconds - consumed)
            day_tiers = {"base": 0, "premium": 0}
            for eligible_slice in breakdown.eligible_slices:
                if eligible_slice.day != day_key:
                    continue
                take = min(eligible_slice.length, remaining)
                if take <= 0:
                    continue
                remaining -= take
                consumed += take
                day_tiers["premium" if eligible_slice.premium else "base"] += take
            # Other Lagos days keep their stored per-tier allocation — their
            # caps are not re-run under this day's lock (RM1). A prior
            # true-up's breakdown supersedes the calculation metadata (same
            # chain as day_consumed_payable_seconds).
            prior_breakdown = await _latest_recompute_breakdown(
                session,
                trip.id,
                payout_calculation_id=calculation.id,
                formula_version=formula_version,
            )
            if (
                prior_breakdown is not None
                and prior_breakdown.get("payable_seconds_by_day_tier") is not None
            ):
                stored_tiers = prior_breakdown["payable_seconds_by_day_tier"]
            else:
                stored_tiers = ((calculation.payout_metadata or {}).get("cap") or {}).get(
                    "payable_seconds_by_day_tier"
                ) or {}
            payable_by_day_tier = {
                key: {
                    "base": int(value.get("base", 0) or 0),
                    "premium": int(value.get("premium", 0) or 0),
                }
                for key, value in stored_tiers.items()
                if key != day_key
            }
            if day_tiers["base"] + day_tiers["premium"] > 0:
                payable_by_day_tier[day_key] = day_tiers
            payable_by_day = {
                key: tiers["base"] + tiers["premium"] for key, tiers in payable_by_day_tier.items()
            }
            payable_seconds = sum(payable_by_day.values())
            base_seconds = sum(tiers["base"] for tiers in payable_by_day_tier.values())
            premium_seconds = sum(tiers["premium"] for tiers in payable_by_day_tier.values())
            target_amount = price_tiered_payable_seconds(
                base_seconds,
                premium_seconds,
                hourly_rate,
                premium_hourly_rate if premium_hourly_rate is not None else hourly_rate,
            )

        posted = await _posted_amount_for_trip(
            session,
            trip_session_id=trip.id,
            driver_profile_id=driver_profile_id,
            currency=calculation.currency,
        )
        delta = quantize_2(target_amount - posted)
        targets.append(
            DayTripTarget(
                trip_session_id=trip.id,
                vehicle_id=trip.vehicle_id,
                payout_calculation_id=calculation.id,
                formula_version=formula_version,
                currency=calculation.currency,
                previous_posted_amount=posted,
                target_amount=target_amount,
                delta_amount=delta,
                eligible_seconds=eligible_seconds,
                excluded_seconds_by_reason=excluded_seconds_by_reason,
                payable_seconds=payable_seconds,
                payable_by_day=payable_by_day,
                payable_by_day_tier=payable_by_day_tier,
                hourly_rate=hourly_rate,
                premium_hourly_rate=premium_hourly_rate,
                cap_seconds=trip_cap_seconds,
                voided=voided,
                current_ping_fingerprint=ping_fingerprint,
                stored_inputs_fingerprint=calculation.inputs_fingerprint,
                governing_values=governing_values,
                stationary_detector_evidence=stationary_detector_evidence,
            )
        )

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


async def write_day_differentials(
    session: AsyncSession,
    *,
    computation: DayComputation,
    request_metadata: dict,
    recompute_at: datetime,
    correction_order_id: UUID | None = None,
    release_at: datetime | None = None,
) -> RecomputeDayOutcome:
    """Execution mode of the PR6 core: posts append-only differential entries
    for the computation's nonzero deltas — adjustment for upward deltas (freed
    cap), positive reversal for downward deltas (netted negative in
    summaries). Under a correction order (MNY-06C), positive deltas post as
    PENDING with the order's own release_at (Q22); negative deltas keep the
    reversal semantics — carry-forward debt when a reversal exceeds the
    balance is MNY-11A's scope and is deliberately NOT implemented here.
    Calculations are never edited; running twice with unchanged inputs posts
    nothing.
    """
    campaign_id = computation.campaign_id
    driver_profile_id = computation.driver_profile_id
    lagos_date = computation.lagos_date
    profile = await session.get(DriverProfile, driver_profile_id)
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
                "payable_seconds": target.payable_seconds,
                "payable_seconds_by_day": target.payable_by_day,
                "hourly_rate_naira": str(target.hourly_rate),
                "cap_seconds": target.cap_seconds,
                "target_amount": str(target.target_amount),
                "previous_posted_amount": str(target.previous_posted_amount),
                "delta_amount": str(delta),
            }
            if target.payable_by_day_tier is not None:
                base_seconds = sum(
                    int(tiers.get("base", 0) or 0) for tiers in target.payable_by_day_tier.values()
                )
                premium_seconds = sum(
                    int(tiers.get("premium", 0) or 0)
                    for tiers in target.payable_by_day_tier.values()
                )
                tier_amounts = allocate_tier_amount_components(
                    base_seconds=base_seconds,
                    premium_seconds=premium_seconds,
                    base_rate=target.hourly_rate,
                    premium_rate=target.premium_hourly_rate or target.hourly_rate,
                    authoritative_total=target.target_amount,
                )
                breakdown_metadata["payable_seconds_by_day_tier"] = target.payable_by_day_tier
                breakdown_metadata["base_payable_seconds"] = base_seconds
                breakdown_metadata["premium_payable_seconds"] = premium_seconds
                breakdown_metadata["base_amount"] = str(tier_amounts.base_amount)
                breakdown_metadata["premium_amount"] = str(tier_amounts.premium_amount)
                breakdown_metadata["premium_hourly_rate_naira"] = (
                    str(target.premium_hourly_rate)
                    if target.premium_hourly_rate is not None
                    else None
                )
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
            if target.formula_version == PAYOUT_V3:
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
                await record_reversal_obligation(session, reversal_entry=entry)
        outcomes.append(
            RecomputeDayTripOutcome(
                trip_session_id=target.trip_session_id,
                payout_calculation_id=target.payout_calculation_id,
                previous_posted_amount=target.previous_posted_amount,
                target_amount=target.target_amount,
                delta_amount=delta,
                eligible_seconds=target.eligible_seconds,
                payable_seconds=target.payable_seconds,
                entry=entry,
                voided=target.voided,
            )
        )

    return RecomputeDayOutcome(
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        lagos_date=lagos_date,
        cap_seconds=max((target.cap_seconds for target in computation.trips), default=0),
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
    return await write_day_differentials(
        session,
        computation=computation,
        request_metadata=request_metadata,
        recompute_at=recompute_at,
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
    base_payable_seconds: int | None
    premium_payable_seconds: int | None
    base_hourly_rate: Decimal | None
    premium_hourly_rate: Decimal | None
    base_amount: Decimal | None
    premium_amount: Decimal | None
    superseded_by_recompute: bool
    entries: list[EarningsLedgerEntry]
    lagos_day: date | None
    cap_seconds: int | None
    day_payable_seconds: int | None


def _tier_breakdown_from_stored_metadata(
    source: dict,
    *,
    fallback_rates: dict | None = None,
) -> tuple[int, int, Decimal, Decimal | None, Decimal, Decimal] | None:
    """Parse one durable payout_v3 explanation without live recalculation.

    Legacy B2 rows may lack component amounts. Their safe compatibility path
    uses only the stored tier seconds, frozen rates and stored target amount,
    through the same residual allocator now used at write time.
    """
    tiers_by_day = source.get("payable_seconds_by_day_tier")
    rates = fallback_rates or {}
    base_rate_raw = source.get("hourly_rate_naira", rates.get("hourly_rate_naira"))
    premium_rate_raw = source.get(
        "premium_hourly_rate_naira", rates.get("premium_hourly_rate_naira")
    )
    total_raw = source.get("target_amount", source.get("amount"))
    if not isinstance(tiers_by_day, dict) or base_rate_raw is None or total_raw is None:
        return None
    try:
        tier_sums = {"base": 0, "premium": 0}
        for value in tiers_by_day.values():
            if not isinstance(value, dict):
                return None
            for key in tier_sums:
                seconds = int(value.get(key, 0) or 0)
                if seconds < 0:
                    return None
                tier_sums[key] += seconds
        base_seconds = int(
            source.get(
                "base_payable_seconds",
                tier_sums["base"],
            )
        )
        premium_seconds = int(
            source.get(
                "premium_payable_seconds",
                tier_sums["premium"],
            )
        )
        if (
            base_seconds < 0
            or premium_seconds < 0
            or base_seconds != tier_sums["base"]
            or premium_seconds != tier_sums["premium"]
        ):
            return None
        base_rate = Decimal(str(base_rate_raw))
        premium_rate = Decimal(str(premium_rate_raw)) if premium_rate_raw is not None else None
        total = Decimal(str(total_raw))
        if base_rate < 0 or (premium_rate is not None and premium_rate < 0) or total < 0:
            return None
        if source.get("base_amount") is not None and source.get("premium_amount") is not None:
            base_amount = Decimal(str(source["base_amount"]))
            premium_amount = Decimal(str(source["premium_amount"]))
            if base_amount < 0 or premium_amount < 0:
                return None
        else:
            allocated = allocate_tier_amount_components(
                base_seconds=base_seconds,
                premium_seconds=premium_seconds,
                base_rate=base_rate,
                premium_rate=premium_rate or base_rate,
                authoritative_total=total,
            )
            base_amount = allocated.base_amount
            premium_amount = allocated.premium_amount
    except (ArithmeticError, TypeError, ValueError):
        return None
    if quantize_2(base_amount + premium_amount) != quantize_2(total):
        return None
    return (
        base_seconds,
        premium_seconds,
        base_rate,
        premium_rate,
        base_amount,
        premium_amount,
    )


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
        if (
            entry.status == EarningsLedgerEntryStatus.VOIDED.value
            or entry.entry_type == EarningsLedgerEntryType.DEBT_REMAINDER.value
        ):
            continue
        if entry.entry_type == EarningsLedgerEntryType.REVERSAL.value:
            amount -= entry.amount
        else:
            amount += entry.amount
    amount = quantize_2(amount)
    original_trip_payout_voided = any(
        entry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value
        and entry.status == EarningsLedgerEntryStatus.VOIDED.value
        for entry in entries
    )

    formula_version = calculation.formula_version if calculation else PAYOUT_V1
    eligible_seconds: int | None = None
    excluded: dict[str, int] | None = None
    hourly_rate: Decimal | None = None
    capped_seconds: int | None = None
    base_payable_seconds: int | None = None
    premium_payable_seconds: int | None = None
    base_hourly_rate: Decimal | None = None
    premium_hourly_rate: Decimal | None = None
    base_amount: Decimal | None = None
    premium_amount: Decimal | None = None
    lagos_day_value: date | None = None
    cap_seconds: int | None = None
    day_payable_seconds: int | None = None
    superseded = False

    if calculation is not None and calculation.formula_version in (PAYOUT_V2, PAYOUT_V3):
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

        if calculation.formula_version == PAYOUT_V3 and not original_trip_payout_voided:
            components = metadata.get("components") or {}
            tier = _tier_breakdown_from_stored_metadata(components, fallback_rates=rates)
            if tier is not None:
                (
                    base_payable_seconds,
                    premium_payable_seconds,
                    base_hourly_rate,
                    premium_hourly_rate,
                    base_amount,
                    premium_amount,
                ) = tier
                hourly_rate = base_hourly_rate

        authoritative_recompute_entries: list[
            tuple[EarningsLedgerEntry, tuple[int | None, dict[str, int] | None]]
        ] = []
        for entry in entries:
            entry_metadata = entry.ledger_metadata or {}
            stored = entry_metadata.get("breakdown")
            if (
                entry.status == EarningsLedgerEntryStatus.VOIDED.value
                or entry.entry_type
                not in (
                    EarningsLedgerEntryType.ADJUSTMENT.value,
                    EarningsLedgerEntryType.REVERSAL.value,
                )
                or not entry_metadata.get("recompute_day")
                or entry_metadata.get("payout_calculation_id") != str(calculation.id)
                or entry_metadata.get("formula_version") != calculation.formula_version
                or not isinstance(stored, dict)
            ):
                continue
            if calculation.formula_version == PAYOUT_V3 and (
                _tier_breakdown_from_stored_metadata(stored) is None
            ):
                continue
            # The newest otherwise-authoritative recompute remains the
            # provenance boundary even when its explanation pair is malformed.
            # Falling through to an older correction (or the original
            # calculation) would re-expose stale driver reasons.
            explanation = _recompute_explanation_from_stored_metadata(stored) or (None, None)
            authoritative_recompute_entries.append((entry, explanation))

        if authoritative_recompute_entries:
            superseded = True
            newest, (eligible_seconds, excluded) = authoritative_recompute_entries[-1]
            stored = (newest.ledger_metadata or {}).get("breakdown") or {}
            if stored.get("payable_seconds") is not None:
                capped_seconds = int(stored["payable_seconds"])
            if stored.get("hourly_rate_naira") is not None:
                hourly_rate = Decimal(str(stored["hourly_rate_naira"]))
            if stored.get("cap_seconds") is not None:
                cap_seconds = int(stored["cap_seconds"])
            if calculation.formula_version == PAYOUT_V3:
                tier = _tier_breakdown_from_stored_metadata(stored)
                if tier is not None:
                    (
                        base_payable_seconds,
                        premium_payable_seconds,
                        base_hourly_rate,
                        premium_hourly_rate,
                        base_amount,
                        premium_amount,
                    ) = tier
                    hourly_rate = base_hourly_rate

        if lagos_day_value is not None:
            day_payable_seconds = await day_consumed_payable_seconds(
                session,
                driver_profile_id=profile.id,
                campaign_id=trip.campaign_id,
                lagos_day=lagos_day_value,
            )

    # Tier components explain the authoritative posted balance, not a stale
    # calculation target. If later ledger voiding makes those disagree, hide
    # the tier explanation and leave the entries as the visible authority.
    if (
        base_amount is not None
        and premium_amount is not None
        and quantize_2(base_amount + premium_amount) != amount
    ):
        base_payable_seconds = None
        premium_payable_seconds = None
        base_hourly_rate = None
        premium_hourly_rate = None
        base_amount = None
        premium_amount = None

    return DriverTripBreakdown(
        trip_session_id=trip.id,
        formula_version=formula_version,
        currency=currency,
        amount=amount,
        eligible_seconds=eligible_seconds,
        excluded_seconds_by_reason=excluded,
        hourly_rate=hourly_rate,
        capped_seconds=capped_seconds,
        base_payable_seconds=base_payable_seconds,
        premium_payable_seconds=premium_payable_seconds,
        base_hourly_rate=base_hourly_rate,
        premium_hourly_rate=premium_hourly_rate,
        base_amount=base_amount,
        premium_amount=premium_amount,
        superseded_by_recompute=superseded,
        entries=entries,
        lagos_day=lagos_day_value,
        cap_seconds=cap_seconds,
        day_payable_seconds=day_payable_seconds,
    )
