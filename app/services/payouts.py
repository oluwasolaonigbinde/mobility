import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Text as SQLText
from sqlalchemy import and_, case, cast, false, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import is_expected_uniqueness_conflict
from app.models.campaign import Campaign
from app.models.campaign_zone import CampaignZone
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
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.models.trip import LocationPing, TripSession, TripSessionStatus
from app.models.trip_analytics import (
    TripAnalytics,
    TripAnalyticsStatus,
)
from app.schemas.payouts import (
    CampaignPayoutV4RevisionCreate,
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
)
from app.services.payout_debt import driver_money_balance, record_reversal_obligation
from app.services.payout_eligibility import (
    D39_STOP_OVERLAY,
    METRES_PER_MILE,
    STATIONARY_POLICY_D39,
    EligibilityParams,
    EligibilityPing,
    classify_session,
    credited_distance_m_by_day,
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
# D39 daily rate for reaching a daily distance target. Created only through
# the audited v4 revision path, never through the rule-create API.
PAYOUT_V4 = "payout_v4"
SHORTFALL_PROPORTIONAL = "proportional"
SHORTFALL_PER_MILE_DEDUCTION = "per_mile_deduction"
SHORTFALL_STRATEGIES = frozenset({SHORTFALL_PROPORTIONAL, SHORTFALL_PER_MILE_DEDUCTION})
# Classified in-service by name (MNY-06A) — the FND-07 shared classifier in
# app/db/integrity.py is a reserved surface and stays untouched.
RULE_REVISION_UNIQUE_CONSTRAINTS = (
    "uq_campaign_payout_rule_revisions_campaign_number",
    "uq_campaign_payout_rule_revisions_campaign_effective",
)
LAGOS_TZ = ZoneInfo("Africa/Lagos")
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
    """Daily-rate money quantization: 2dp NGN, ROUND_HALF_UP, applied exactly
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
                func.coalesce(TripSession.ended_at, TripSession.started_at) > day_start_utc,
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
            TripSession.status.in_([TripSessionStatus.ENDED.value, TripSessionStatus.SEALED.value]),
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


def rule_not_found() -> AppError:
    return AppError(
        "PAYOUT_RULE_NOT_FOUND",
        "Payout rule was not found",
        status_code=status.HTTP_404_NOT_FOUND,
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


def payout_v4_policy_unavailable() -> AppError:
    # D39 Q1-Q3 (shortfall formula and minimum, which miles count, the cap and
    # the full-day amount) are still open with the client. Until the owner
    # switches publishing on, nothing is written.
    return AppError(
        "PAYOUT_V4_POLICY_UNAVAILABLE",
        "Daily-rate pay is not switched on yet",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
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


async def publish_payout_v4_revision(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    payload: CampaignPayoutV4RevisionCreate,
    actor_user_id: UUID,
    settings: Settings,
) -> tuple[
    CampaignPayoutRuleRevision, CampaignPayoutRuleRevision | None, CampaignPayoutRule | None
]:
    """Append one audited daily-rate (payout_v4, D39) revision.

    Fails closed before any lock or write while PAYOUT_V4_PUBLISHING_ENABLED is
    off. A campaign without an active rule gets a rate-less payout_v4 rule in
    the same transaction. Revisions serialize with acceptance under the campaign
    terms lock. The stop rule is fixed by the server.
    Returns (revision, previous, created_rule).
    """
    # An unknown campaign is 404 whether or not publishing is on.
    await get_campaign(session, campaign_id)
    if not settings.payout_v4_publishing_enabled:
        raise payout_v4_policy_unavailable()
    await acquire_campaign_terms_lock(session, campaign_id)
    db_now = await database_clock(session)
    campaign = await get_campaign(session, campaign_id)
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.campaign_id == campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
    )
    if rule is not None and rule.formula_version != PAYOUT_V4:
        raise invalid_rule_revision(
            f"this campaign is governed by a {rule.formula_version} rule; a daily-rate"
            " revision cannot extend it"
        )
    latest = await latest_payout_rule_revision(session, campaign_id)
    if latest is not None and payload.effective_from <= _ensure_utc_aware(latest.effective_from):
        raise invalid_rule_revision(
            "effective_from must be strictly after the latest revision's"
            " effective_from; retroactive changes require a correction order"
        )
    if payload.effective_from < _ensure_utc_aware(db_now):
        raise invalid_rule_revision("effective_from must not be before the database clock")

    created_rule = None
    if rule is None:
        rule = CampaignPayoutRule(
            campaign_id=campaign_id,
            created_by_user_id=actor_user_id,
            formula_version=PAYOUT_V4,
            status=CampaignPayoutRuleStatus.ACTIVE.value,
            currency=validate_currency_code(campaign.currency),
            rule_metadata={},
        )
        session.add(rule)
        await session.flush()
        await session.refresh(rule)
        created_rule = rule

    revision = CampaignPayoutRuleRevision(
        campaign_id=campaign_id,
        payout_rule_id=rule.id,
        revision_number=(latest.revision_number + 1) if latest is not None else 1,
        effective_from=payload.effective_from,
        daily_rate_naira=payload.daily_rate_naira,
        daily_target_miles=payload.daily_target_miles,
        shortfall_strategy=payload.shortfall_strategy,
        deduction_per_mile_naira=payload.deduction_per_mile_naira,
        minimum_miles=payload.minimum_miles,
        outside_area_weight=payload.outside_area_weight,
        currency=rule.currency,
        eligibility_params=dict(D39_STOP_OVERLAY),
        formula_version=PAYOUT_V4,
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
    return revision, latest, created_rule


async def list_payout_rule_revisions(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
    limit: int,
    offset: int,
    effective_before: datetime | None = None,
) -> tuple[list[CampaignPayoutRuleRevision], int]:
    await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    conditions = [CampaignPayoutRuleRevision.campaign_id == campaign_id]
    if effective_before is not None:
        conditions.append(CampaignPayoutRuleRevision.effective_from <= effective_before)
    total = await session.scalar(
        select(func.count()).select_from(CampaignPayoutRuleRevision).where(*conditions)
    )
    result = await session.execute(
        select(CampaignPayoutRuleRevision)
        .where(*conditions)
        .order_by(
            CampaignPayoutRuleRevision.effective_from.desc(),
            CampaignPayoutRuleRevision.revision_number.desc(),
        )
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
    # batches inside the grace window, and write-once payouts must never
    # fingerprint an incomplete ping set. This also covers the admin
    # recompute endpoints — corrections only ever reprice sealed trips.
    if trip.status != TripSessionStatus.SEALED.value or trip.ended_at is None:
        raise AppError(
            "TRIP_NOT_SEALED",
            "Payout can only be calculated for sealed trips",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if trip.evidence_manifest_verified_at is None or not verify_manifest_receipt(trip, settings):
        raise AppError(
            "TRIP_EVIDENCE_NOT_VERIFIED",
            "Payout requires an authenticated v2 trip evidence manifest",
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


@dataclass(frozen=True)
class EligibilityPingRow:
    id: UUID
    ping: EligibilityPing


@dataclass(frozen=True)
class CampaignZoneState:
    fingerprint: str
    zone_count: int
    max_updated_at: datetime | None


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
    )


RESOLVED_ELIGIBILITY_PARAM_KEYS = frozenset(EligibilityParams.__dataclass_fields__)


def frozen_eligibility_params(binding: AssignmentRuleBinding) -> EligibilityParams:
    """Read the complete acceptance-time classifier values, never Settings.

    Bindings created before migration 0021 cannot prove a complete snapshot;
    fail closed rather than silently filling their gaps from mutable runtime
    configuration.
    """
    expected_marker = STATIONARY_POLICY_D39
    if binding.stationary_policy_marker != expected_marker:
        raise AppError(
            "PAYOUT_STATIONARY_POLICY_UNRESOLVED",
            f"The {binding.formula_version} assignment binding does not contain the approved"
            " stationary detector policy; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    snapshot = binding.resolved_eligibility_params or {}
    if set(snapshot) != RESOLVED_ELIGIBILITY_PARAM_KEYS:
        raise AppError(
            "PAYOUT_BINDING_INCOMPLETE",
            "The daily-rate assignment binding does not contain a complete"
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
    frozen_premium_zone_wkts: list[str],
    frozen_exclusion_zone_wkts: list[str],
    recorded_through: datetime | None = None,
) -> list[EligibilityPingRow]:
    """Read signed trip pings against the frozen accepted service area."""

    def frozen_zone_hit(wkts: list[str]):
        conditions = [
            func.ST_Intersects(func.ST_GeomFromText(wkt, 4326), LocationPing.geom) for wkt in wkts
        ]
        return or_(*conditions) if conditions else false()

    in_area = ~frozen_zone_hit(frozen_exclusion_zone_wkts)
    in_premium = frozen_zone_hit(frozen_premium_zone_wkts)
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


@dataclass(frozen=True)
class DailyRateTerms:
    """The payout_v4 pay terms frozen on a binding (all client values, D39)."""

    daily_rate_naira: Decimal
    daily_target_miles: Decimal
    shortfall_strategy: str
    deduction_per_mile_naira: Decimal | None
    minimum_miles: Decimal
    outside_area_weight: Decimal

    def as_metadata(self) -> dict[str, str | None]:
        return {
            "daily_rate_naira": str(self.daily_rate_naira),
            "daily_target_miles": str(self.daily_target_miles),
            "shortfall_strategy": self.shortfall_strategy,
            "deduction_per_mile_naira": (
                str(self.deduction_per_mile_naira)
                if self.deduction_per_mile_naira is not None
                else None
            ),
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
        or binding.shortfall_strategy not in SHORTFALL_STRATEGIES
        or (binding.shortfall_strategy == SHORTFALL_PER_MILE_DEDUCTION)
        != (binding.deduction_per_mile_naira is not None)
    ):
        raise AppError(
            "PAYOUT_BINDING_INCOMPLETE",
            "The payout_v4 assignment binding does not contain complete daily-rate"
            " terms; resolve manually",
            status_code=status.HTTP_409_CONFLICT,
        )
    return DailyRateTerms(
        daily_rate_naira=Decimal(binding.daily_rate_naira),
        daily_target_miles=Decimal(binding.daily_target_miles),
        shortfall_strategy=binding.shortfall_strategy,
        deduction_per_mile_naira=(
            Decimal(binding.deduction_per_mile_naira)
            if binding.deduction_per_mile_naira is not None
            else None
        ),
        minimum_miles=Decimal(binding.minimum_miles),
        outside_area_weight=Decimal(binding.outside_area_weight),
    )


def _half_up_naira(value: Fraction) -> Decimal:
    """Exact 2dp NGN ROUND_HALF_UP of a non-negative fraction."""
    cents = math.floor(value * 100 + Fraction(1, 2))
    return (Decimal(cents) / 100).quantize(DECIMAL_2)


def day_pay_naira(distance_m: int, terms: DailyRateTerms) -> Decimal:
    """D(d): a day's pay for ``distance_m`` whole credited metres (payout_v4).

    D(0) = 0; below the minimum distance nothing is paid; at or above the
    target the day rate is paid and never more (one full day's rate per
    driver per campaign day). Short of the target: ``proportional`` pays
    rate x miles / target; ``per_mile_deduction`` pays rate minus the
    deduction for each missing mile, floored at 0. D is non-decreasing, so a
    day's per-trip increments are never negative and sum to D(day total).
    The per-mile form jumps from D(0) to rate - deduction x target just above
    zero; the client's minimum-distance answer (Q1) decides whether that jump
    is intended.
    """
    if distance_m <= 0:
        return Decimal("0.00")
    miles = Fraction(distance_m) / Fraction(METRES_PER_MILE)
    if miles < Fraction(terms.minimum_miles):
        return Decimal("0.00")
    rate = Fraction(terms.daily_rate_naira)
    target = Fraction(terms.daily_target_miles)
    if miles >= target:
        return _half_up_naira(rate)
    if terms.shortfall_strategy == SHORTFALL_PROPORTIONAL:
        return _half_up_naira(rate * miles / target)
    deduction = Fraction(terms.deduction_per_mile_naira)
    return _half_up_naira(max(Fraction(0), rate - deduction * (target - miles)))


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


@dataclass(frozen=True)
class DailyRateClassification:
    """One trip classified under its frozen payout_v4 binding (no writes)."""

    terms: DailyRateTerms
    params: EligibilityParams
    governing_values: dict
    breakdown: object
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
) -> tuple[list[tuple[PayoutCalculation, datetime, str]], int]:
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

    statement = (
        select(PayoutCalculation, TripSession.started_at, Campaign.name)
        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
        .join(Campaign, Campaign.id == PayoutCalculation.campaign_id)
    )
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
    return [(row[0], row[1], row[2]) for row in result.all()], int(total or 0)


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
                            EarningsLedgerEntry.status != EarningsLedgerEntryStatus.VOIDED.value,
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
    # Sum the stored calculation amounts for this campaign.
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
        formula_version=governing_rule or PAYOUT_V4,
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
                await record_reversal_obligation(session, reversal_entry=entry)
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
