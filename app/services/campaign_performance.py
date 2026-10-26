"""Coarse advertiser campaign facts; shared terminal-trip authority with D118 reports."""

from datetime import datetime
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

from app.schemas.reports import (
    CampaignPerformanceArea,
    CampaignPerformanceRead,
    CampaignPerformanceTotals,
)
from app.services.report_cohorts import ReportCohort, select_report_cohort

PERFORMANCE_POLICY = "campaign-performance-d118-v2"
UNCERTAINTY = "Views are estimates of potential contacts, not measured people or guaranteed views."
LAGOS = ZoneInfo("Africa/Lagos")


async def live_campaign_performance(
    session, *, campaign, settings, now, start_at=None, end_at=None
):
    from app.services.campaign_report_data import (
        _areas,
        aware,
        verified_driving,
    )

    lower = start_at or campaign.start_at
    upper = min(aware(end_at or now), aware(now))
    cohort = ReportCohort((), (), (), (), terminal_period=True)
    if lower is None or aware(lower) < upper:
        cohort = await select_report_cohort(
            session,
            campaign_id=campaign.id,
            start_at=lower,
            end_at=upper,
            settings=settings,
            terminal_period=True,
            include_money=False,
        )
    trips, measured, cars, hidden = verified_driving(cohort)
    estimates = {
        row.trip_session_id: row for row in cohort.impressions if row.status == "estimated"
    }
    areas = await _areas(
        session,
        campaign=campaign,
        cohort=cohort,
        driving=measured,
        settings=settings,
        unknown=hidden and not measured,
    )
    return CampaignPerformanceRead(
        campaign_id=campaign.id,
        start_at=lower,
        end_at=upper,
        totals=CampaignPerformanceTotals.model_validate(
            {
                "distance_m": None
                if hidden
                else str(sum((row.distance_m for row in measured), Decimal(0))),
                "trip_count": None if hidden else len(measured),
                "driving_days": None
                if hidden
                else len(
                    {
                        aware(cast(datetime, trips[row.trip_session_id].ended_at))
                        .astimezone(LAGOS)
                        .date()
                        for row in measured
                    }
                ),
                "estimated_views": str(
                    sum(
                        (estimates[row.trip_session_id].estimated_impressions for row in measured),
                        Decimal(0),
                    )
                )
                if not hidden and all(row.trip_session_id in estimates for row in measured)
                else None,
            }
        ),
        areas=[
            CampaignPerformanceArea.model_validate(
                {
                    "area_id": row["id"],
                    "name": row["name"],
                    "trip_count": row["trip_count"],
                    "modelled_potential_contacts": row["estimated_views"],
                }
            )
            for row in areas
            if row["vehicle_count"] and row["vehicle_count"] >= 3
        ],
        completeness="Available verified results only. Some trips may still be processing. "
        "Withheld results need at least three cars; they are not zero.",
        uncertainty=UNCERTAINTY,
    )
