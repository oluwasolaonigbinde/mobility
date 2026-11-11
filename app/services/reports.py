from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.reports import DailyMetricItem, DailyMetricsResponse
from app.services.campaigns import get_advertiser_campaign
from app.services.disclosure import (
    lock_trip_disclosure_snapshot,
    require_governed_advertiser_output,
)
from app.services.report_cohorts import ReportCohort

ZERO_2 = Decimal("0.00")


LAGOS = ZoneInfo("Africa/Lagos")


def campaign_daily_series(
    cohort: ReportCohort, *, start_day: date, end_day: date, now, blocked_days=frozenset()
):
    """One Nigeria-day calculation for reports and the owned seven-day read (D118).

    Only verified driving contributes. A suppressed day contains no counts or
    amounts; an empty day has zero measured driving and zero estimated views.
    """
    from app.services.disclosure import after_day, trip_final

    trips = {trip.id: trip for trip in cohort.trips if trip.ended_at is not None}
    by_day = defaultdict(list)
    source_days = defaultdict(list)
    analytics = {row.trip_session_id: row for row in cohort.analytics}
    for trip in trips.values():
        ended = trip.ended_at
        assert ended is not None  # The terminal-trip map excludes open trips.
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=UTC)
        source_days[ended.astimezone(LAGOS).date()].append(trip)
    estimates = {r.trip_session_id: r for r in cohort.impressions if r.status == "estimated"}
    for row in cohort.analytics:
        trip = trips.get(row.trip_session_id)
        if (
            trip is not None
            and row.status == "computed"
            and (row.distance_m > 0 or row.moving_seconds > 0)
        ):
            ended = trip.ended_at
            assert ended is not None
            if ended.tzinfo is None:
                ended = ended.replace(tzinfo=UTC)
            by_day[ended.astimezone(LAGOS).date()].append(row)
    items = []
    day = start_day
    while day <= end_day:
        rows = by_day[day]
        cars = {row.vehicle_id for row in rows}
        closed = (
            now >= after_day(datetime.combine(day, time.min, LAGOS))
            and day not in blocked_days
            and all(trip_final(t, analytics.get(t.id)) for t in source_days[day])
        )
        status = (
            "not_ready" if not closed else "not_enough_cars" if 0 < len(cars) < 3 else "released"
        )
        suppressed = status != "released"
        estimate_rows = [
            estimates[r.trip_session_id] for r in rows if r.trip_session_id in estimates
        ]
        items.append(
            DailyMetricItem(
                date=day,
                vehicle_count=None if suppressed else len(cars),
                trip_count=None if suppressed else len(rows),
                distance_m=None if suppressed else sum((r.distance_m for r in rows), ZERO_2),
                driving_seconds=None if suppressed else sum(r.moving_seconds for r in rows),
                estimated_impressions=(
                    None
                    if suppressed or len(estimate_rows) != len(rows)
                    else sum((r.estimated_impressions for r in estimate_rows), ZERO_2)
                ),
                status=status,
            )
        )
        day += timedelta(days=1)
    return items


async def daily_metrics_for_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
    offset: int,
    settings: Settings,
    record_history: bool = True,
) -> DailyMetricsResponse:
    from app.services.disclosure import DisclosureQuery, _canonical_hash, record_disclosure
    from app.services.payout_rule_serialization import database_clock

    organization_id = await require_governed_advertiser_output(
        session,
        settings=settings,
        route_id="advertiser.campaign.daily_metrics",
        user_id=user_id,
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(session, tenant_id=organization_id, campaign_id=campaign.id)
    now = await database_clock(session)
    today = now.astimezone(LAGOS).date()
    from app.services.disclosure import load_cells, validate_window

    validate_window(start_at, end_at)
    last_day = (end_at - timedelta(microseconds=1)).astimezone(LAGOS).date() if end_at else today
    first_day = start_at.astimezone(LAGOS).date() if start_at else last_day - timedelta(days=6)
    start = start_at or datetime.combine(first_day, time.min, LAGOS)
    end = end_at or datetime.combine(last_day + timedelta(days=1), time.min, LAGOS)
    validate_window(start, end)
    total = (last_day - first_day).days + 1
    page_start = first_day + timedelta(days=min(offset, total))
    page_end = min(last_day, page_start + timedelta(days=limit - 1))
    series = []
    if offset < total:
        _, series = await load_cells(
            session,
            campaign_id=campaign.id,
            start=datetime.combine(page_start, time.min, LAGOS),
            end=datetime.combine(page_end + timedelta(days=1), time.min, LAGOS),
            settings=settings,
            now=now,
        )
    result = DailyMetricsResponse(
        campaign_id=campaign.id,
        start_at=start,
        end_at=end,
        items=series,
        total=total,
        limit=limit,
        offset=offset,
    )
    if record_history:
        # Placeholders disclose no contributor facts. Every nonzero measured day
        # was independently checked; an empty day is the client-requested zero.
        safe = all(
            (
                (row.status != "released")
                and all(
                    value is None
                    for value in (
                        row.vehicle_count,
                        row.trip_count,
                        row.distance_m,
                        row.driving_seconds,
                        row.estimated_impressions,
                    )
                )
            )
            or (
                row.status == "released"
                and row.vehicle_count is not None
                and (row.vehicle_count == 0 or row.vehicle_count >= 3)
            )
            for row in result.items
        )
        await record_disclosure(
            session,
            settings=settings,
            query=DisclosureQuery(
                route_id="advertiser.campaign.daily_metrics",
                principal_id=user_id,
                tenant_id=organization_id,
                campaign_id=campaign.id,
                start_at=start,
                end_at=end,
                filters={"limit": limit, "offset": offset},
            ),
            has_releasable_cells=safe,
            result_hash=_canonical_hash(result.model_dump(mode="json")),
        )
    return result


async def advertiser_campaign_report(session, *, user_id, campaign_id, settings):
    from app.services.campaign_performance import PERFORMANCE_POLICY, live_campaign_performance
    from app.services.disclosure import DisclosureQuery, _canonical_hash, record_disclosure
    from app.services.payout_rule_serialization import database_clock

    organization_id = await require_governed_advertiser_output(
        session, settings=settings, route_id="advertiser.campaign.performance", user_id=user_id
    )
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await lock_trip_disclosure_snapshot(session, tenant_id=organization_id, campaign_id=campaign_id)
    result = await live_campaign_performance(
        session,
        campaign=campaign,
        settings=settings,
        now=await database_clock(session),
    )
    await record_disclosure(
        session,
        query=DisclosureQuery(
            route_id="advertiser.campaign.performance",
            principal_id=user_id,
            tenant_id=organization_id,
            campaign_id=campaign_id,
            start_at=None,
            end_at=None,
            filters={"policy": PERFORMANCE_POLICY},
        ),
        settings=settings,
        has_releasable_cells=True,
        result_hash=_canonical_hash(result.model_dump(mode="json")),
    )
    return result
