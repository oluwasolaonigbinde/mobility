"""D90 coarse campaign facts and three-car report areas."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.errors import AppError
from app.schemas.reports import CampaignPerformanceRead

PERFORMANCE_POLICY = "campaign-performance-d90-v1"
UNCERTAINTY = "Views are estimates of potential contacts, not measured people or guaranteed views."
LAGOS = ZoneInfo("Africa/Lagos")


def performance_from_manifest(
    manifest: dict, *, campaign_id: UUID, labels: dict
) -> CampaignPerformanceRead:
    from app.services.measurement import _density_provenance, _qualifying_trip_ids

    ids = _qualifying_trip_ids(manifest)
    cohort = [row for row in manifest["cohort"] if row["trip_session_id"] in ids]
    analytics = [
        row
        for row in manifest["sources"]["trip_analytics"]
        if row["trip_session_id"] in ids and row["status"] == "computed"
    ]
    estimates = [
        row
        for row in manifest["sources"]["impression_estimates"]
        if row["trip_session_id"] in ids and row["status"] == "estimated"
    ]
    _, provenance = _density_provenance(estimates)
    views = (
        sum((Decimal(row["estimated_impressions"]) for row in estimates), Decimal(0))
        if provenance
        else None
    )
    areas = _area_projection(
        manifest, analytics=analytics, estimates=estimates, labels=labels, allow_contacts=provenance
    )
    return CampaignPerformanceRead(
        campaign_id=campaign_id,
        start_at=manifest["period"]["start_at"],
        end_at=manifest["period"]["end_at"],
        totals={
            "distance_m": str(sum((Decimal(row["distance_m"]) for row in analytics), Decimal(0))),
            "trip_count": len(ids),
            "driving_days": len(
                {
                    datetime.fromisoformat(row["terminal_at"]).astimezone(LAGOS).date()
                    for row in cohort
                }
            ),
            "estimated_views": str(views) if views is not None else None,
        },
        areas=areas,
        completeness=(
            "Distance and estimated views include available verified results; "
            "some completed trips may still be processing."
        ),
        uncertainty=UNCERTAINTY,
    )


def _area_projection(manifest, *, analytics, estimates, labels, allow_contacts):
    # D105: an area row needs at least three distinct cars; nothing else withholds it.
    authority = manifest.get("report_area_authority") or {}
    groups = defaultdict(list)
    trips = {row["trip_session_id"]: row["vehicle_id"] for row in analytics}
    for row in authority.get("rows", []):
        if row["trip_session_id"] in trips:
            if row["vehicle_id"] != trips[row["trip_session_id"]]:
                raise AppError(
                    "REPORT_AREA_AUTHORITY_INVALID",
                    "Area results could not be verified",
                    status_code=409,
                )
            groups[row["zone_id"]].append(row)
    _check_ping_totals(groups)
    impressions = {
        row["trip_session_id"]: Decimal(row["estimated_impressions"]) for row in estimates
    }
    result = []
    for area, rows in sorted(groups.items()):
        if area not in labels:
            raise AppError(
                "REPORT_AREA_AUTHORITY_INVALID",
                "Area results could not be verified",
                status_code=409,
            )
        members = {row["trip_session_id"] for row in rows}
        if len({trips[trip] for trip in members}) < 3:
            continue
        contacts = None
        if allow_contacts and members <= impressions.keys():
            # Report area allocation has no whole-hour
            # export window rule: report periods end at any cutoff.
            cells = defaultdict(Decimal)
            for row in rows:
                cells[(int(row["grid_x"]), int(row["grid_y"]))] += (
                    impressions[row["trip_session_id"]]
                    * Decimal(int(row["cell_ping_count"]))
                    / Decimal(int(row["total_ping_count"]))
                )
            contacts = str(
                sum((value.quantize(Decimal("0.0001")) for value in cells.values()), Decimal(0))
            )
        result.append(
            {
                "area_id": area,
                "name": labels[area],
                "trip_count": len(members),
                "modelled_potential_contacts": contacts,
            }
        )
    return result


def _check_ping_totals(groups):
    # Each trip's rows must agree on one positive ping total (frozen authority integrity).
    expected = {}
    for rows in groups.values():
        for row in rows:
            trip, total = row["trip_session_id"], row["total_ping_count"]
            if total <= 0 or expected.setdefault(trip, total) != total:
                raise AppError(
                    "REPORT_AREA_AUTHORITY_INVALID",
                    "Area results could not be verified",
                    status_code=409,
                )


async def live_campaign_performance(session, *, campaign, settings, now):
    from app.services.measurement import _density_provenance
    from app.services.report_cohorts import select_report_cohort

    cohort = (
        await select_report_cohort(
            session,
            campaign_id=campaign.id,
            start_at=campaign.start_at,
            end_at=now,
            settings=settings,
            terminal_period=True,
        )
    ).terminal_only(now)
    measured = [row for row in cohort.analytics if row.status == "computed"]
    estimates = [row for row in cohort.impressions if row.status == "estimated"]
    _, provenance = _density_provenance(
        [{"provenance": row.estimate_metadata} for row in estimates]
    )
    return CampaignPerformanceRead(
        campaign_id=campaign.id,
        start_at=campaign.start_at,
        end_at=now,
        totals={
            "distance_m": str(sum((row.distance_m for row in measured), Decimal(0))),
            "trip_count": len(cohort.trips),
            "driving_days": len({row.ended_at.astimezone(LAGOS).date() for row in cohort.trips}),
            "estimated_views": str(
                sum((row.estimated_impressions for row in estimates), Decimal(0))
            )
            if provenance
            else None,
        },
        areas=[],
        completeness=(
            "Current results include available verified trips. "
            "Area detail is released in reports when privacy permits."
        ),
        uncertainty=UNCERTAINTY,
    )
