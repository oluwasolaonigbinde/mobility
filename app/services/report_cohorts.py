from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.impression import ImpressionEstimate
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.models.trip_analytics import TripAnalytics
from app.services.impressions import current_authoritative_estimates
from app.services.payouts import latest_payout_calculation_ids


@dataclass(frozen=True)
class ReportCohort:
    trips: tuple[TripSession, ...]
    analytics: tuple[TripAnalytics, ...]
    impressions: tuple[ImpressionEstimate, ...]
    payouts: tuple[PayoutCalculation, ...]

    ledger: tuple[EarningsLedgerEntry, ...] | None = None
    terminal_period: bool = False

    def terminal_only(self, end_at: datetime) -> "ReportCohort":
        def aware(value):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value

        trips = tuple(
            t
            for t in self.trips
            if t.status in {"ended", "sealed"}
            and t.ended_at is not None
            and aware(t.ended_at) < aware(end_at)
        )
        ids = {t.id for t in trips}
        return replace(
            self,
            trips=trips,
            analytics=tuple(r for r in self.analytics if r.trip_session_id in ids),
            impressions=tuple(r for r in self.impressions if r.trip_session_id in ids),
            payouts=tuple(r for r in self.payouts if r.trip_session_id in ids),
            ledger=tuple(r for r in self.ledger or () if r.trip_session_id in ids),
        )

    def final_cost(self, payout: PayoutCalculation) -> Decimal:
        if self.ledger is None:
            return payout.final_payout
        rows = [r for r in self.ledger if r.trip_session_id == payout.trip_session_id]
        if payout.status == "calculated" and not any(
            r.payout_calculation_id == payout.id for r in rows
        ):
            raise AppError(
                "MEASUREMENT_LEDGER_INCOMPLETE",
                "Calculated trip cost requires durable ledger authority",
                status_code=409,
            )
        if any(r.currency != payout.currency for r in rows):
            raise AppError(
                "MEASUREMENT_LEDGER_CURRENCY_CONFLICT",
                "Trip ledger currency does not match its calculation",
                status_code=409,
            )
        return sum(
            (economic_ledger_amount(r.entry_type, r.status, r.amount) for r in rows),
            Decimal("0.00"),
        )

    @property
    def trip_ids(self) -> tuple[UUID, ...]:
        return tuple(trip.id for trip in self.trips)


def economic_ledger_amount(entry_type: str, status: str, amount: Decimal) -> Decimal:
    if entry_type not in {"trip_payout", "adjustment", "reversal", "debt_remainder"}:
        raise ValueError("Unknown economic ledger entry type")
    if status not in {"pending", "available", "voided", "reversed", "paid"} or amount < 0:
        raise ValueError("Invalid economic ledger fact")
    if status == "voided" or entry_type == "debt_remainder":
        return Decimal("0.00")
    return -amount if entry_type == "reversal" else amount


async def select_report_cohort(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
    terminal_period: bool = False,
) -> ReportCohort:
    """Select terminal-period v2 membership or preserve legacy start-period selection."""
    trip_filters = [TripSession.campaign_id == campaign_id]
    if start_at is not None:
        trip_filters.append(
            or_(TripSession.ended_at >= start_at, TripSession.ended_at.is_(None))
            if terminal_period
            else TripSession.started_at >= start_at
        )
    if end_at is not None:
        trip_filters.append(TripSession.started_at < end_at)
    trips = tuple(
        (
            await session.scalars(
                select(TripSession)
                .where(*trip_filters)
                .order_by(TripSession.started_at, TripSession.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    trip_ids = tuple(trip.id for trip in trips)
    if not trip_ids:
        return ReportCohort(
            trips=(),
            analytics=(),
            impressions=(),
            payouts=(),
            ledger=() if terminal_period else None,
            terminal_period=terminal_period,
        )
    trip_order = {trip.id: (trip.started_at, str(trip.id)) for trip in trips}

    analytics = list(
        (
            await session.scalars(
                select(TripAnalytics)
                .where(TripAnalytics.trip_session_id.in_(trip_ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    estimates = list(
        (
            await session.scalars(
                select(ImpressionEstimate)
                .execution_options(populate_existing=True)
                .where(
                    ImpressionEstimate.trip_session_id.in_(trip_ids),
                    ImpressionEstimate.is_authoritative.is_(True),
                )
            )
        ).all()
    )
    estimates = await current_authoritative_estimates(session, estimates, settings=settings)
    payouts = list(
        (
            await session.scalars(
                select(PayoutCalculation)
                .execution_options(populate_existing=True)
                .where(
                    PayoutCalculation.trip_session_id.in_(trip_ids),
                    PayoutCalculation.id.in_(latest_payout_calculation_ids(trip_ids=trip_ids)),
                )
            )
        ).all()
    )

    ledger = None
    if terminal_period:
        ledger = tuple(
            (
                await session.scalars(
                    select(EarningsLedgerEntry)
                    .where(
                        EarningsLedgerEntry.trip_session_id.in_(trip_ids),
                        EarningsLedgerEntry.campaign_id == campaign_id,
                    )
                    .order_by(EarningsLedgerEntry.id)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    def source_key(row: TripAnalytics | ImpressionEstimate | PayoutCalculation):
        return (*trip_order[row.trip_session_id], str(row.id))

    return ReportCohort(
        trips=trips,
        ledger=ledger,
        terminal_period=terminal_period,
        analytics=tuple(sorted(analytics, key=source_key)),
        impressions=tuple(sorted(estimates, key=source_key)),
        payouts=tuple(sorted(payouts, key=source_key)),
    )
