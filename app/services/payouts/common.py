"""Payouts: common domain operations."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import overload
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.payout import (
    EarningsLedgerEntry,
    EarningsLedgerEntryType,
    PayoutCalculation,
)
from app.models.trip import TripSession, TripSessionStatus
from app.services.campaign_cancellations import campaign_financial_cutoff
from app.services.payout_eligibility import (
    EligibilityParams,
)

logger = logging.getLogger(__name__)


DECIMAL_2 = Decimal("0.01")


ZERO = Decimal("0")


PAYOUT_V4 = "payout_v4"


RULE_REVISION_UNIQUE_CONSTRAINTS = (
    "uq_campaign_payout_rule_revisions_campaign_number",
    "uq_campaign_payout_rule_revisions_campaign_effective",
)


LAGOS_TZ = ZoneInfo("Africa/Lagos")


PAYOUT_SOURCE_FIELDS = ("campaign_id", "assignment_id", "driver_profile_id", "vehicle_id")


PAYOUT_CALCULATION_CONSTRAINTS = frozenset({"uq_payout_calculations_trip_formula_rule"})


LEDGER_ENTRY_CONSTRAINTS = frozenset(
    {
        "uq_earnings_ledger_entries_payout_calculation_id",
        "uq_earnings_ledger_entries_trip_payout_per_trip",
    }
)


def quantize_ngn_half_up(value: Decimal) -> Decimal:
    """Quantize current daily-rate ledger amounts once to 2dp using HALF_UP."""
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
    assert trip.ended_at is not None
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
    abort would release it."""
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


@overload
def validate_currency_code(value: str | None, *, fallback: str) -> str: ...


@overload
def validate_currency_code(value: str | None, *, fallback: None = None) -> str | None: ...


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


RESOLVED_ELIGIBILITY_PARAM_KEYS = frozenset(EligibilityParams.__dataclass_fields__)
