from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.impression import ImpressionEstimate
from app.models.payout import PayoutCalculation
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

    @property
    def trip_ids(self) -> tuple[UUID, ...]:
        return tuple(trip.id for trip in self.trips)


async def select_report_cohort(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    settings: Settings,
) -> ReportCohort:
    """Freeze report membership from trip start time, never derivative timestamps."""
    trip_filters = [TripSession.campaign_id == campaign_id]
    if start_at is not None:
        trip_filters.append(TripSession.started_at >= start_at)
    if end_at is not None:
        trip_filters.append(TripSession.started_at < end_at)
    trips = tuple(
        (
            await session.scalars(
                select(TripSession)
                .where(*trip_filters)
                .order_by(TripSession.started_at, TripSession.id)
            )
        ).all()
    )
    trip_ids = tuple(trip.id for trip in trips)
    if not trip_ids:
        return ReportCohort(trips=(), analytics=(), impressions=(), payouts=())
    trip_order = {trip.id: (trip.started_at, str(trip.id)) for trip in trips}

    analytics = list(
        (
            await session.scalars(
                select(TripAnalytics).where(TripAnalytics.trip_session_id.in_(trip_ids))
            )
        ).all()
    )
    estimates = list(
        (
            await session.scalars(
                select(ImpressionEstimate).where(
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
                select(PayoutCalculation).where(
                    PayoutCalculation.trip_session_id.in_(trip_ids),
                    PayoutCalculation.id.in_(latest_payout_calculation_ids(trip_ids=trip_ids)),
                )
            )
        ).all()
    )

    def source_key(row: TripAnalytics | ImpressionEstimate | PayoutCalculation):
        return (*trip_order[row.trip_session_id], str(row.id))

    return ReportCohort(
        trips=trips,
        analytics=tuple(sorted(analytics, key=source_key)),
        impressions=tuple(sorted(estimates, key=source_key)),
        payouts=tuple(sorted(payouts, key=source_key)),
    )
