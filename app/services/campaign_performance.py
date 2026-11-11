"""D160 area-page projection from the shared released cells."""

from datetime import timedelta

from app.schemas.reports import CampaignPerformanceArea, CampaignPerformanceRead
from app.services.disclosure import load_cells, midnight

PERFORMANCE_POLICY = "campaign-performance-d160-v1"
UNCERTAINTY = "Views are estimates of potential contacts, not measured people or guaranteed views."


async def live_campaign_performance(session, *, campaign, settings, now):
    from app.services.campaign_report_data import _areas, verified_driving

    lower = midnight(campaign.start_at or now)
    end = midnight(now)
    # Include the prior Sunday only once its whole week is closed.
    end -= timedelta(days=end.weekday())
    areas = []
    hidden = False
    if lower < end:
        cohort, days = await load_cells(
            session, campaign_id=campaign.id, start=lower, end=end, settings=settings, now=now
        )
        hidden = any(day.status != "released" for day in days)
        _, driving, _, _ = verified_driving(cohort)
        areas = await _areas(
            session,
            campaign=campaign,
            cohort=cohort,
            driving=driving,
            settings=settings,
            days=days,
            start=lower,
            end=end,
        )
    return CampaignPerformanceRead(
        campaign_id=campaign.id,
        areas=[
            CampaignPerformanceArea(
                area_id=a["id"],
                name=a["name"],
                trip_count=a["trip_count"],
                modelled_potential_contacts=a["estimated_views"],
            )
            for a in areas
        ],
        completeness="Some days hidden." if hidden else "",
        uncertainty=UNCERTAINTY,
    )
