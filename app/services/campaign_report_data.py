"""Company-scoped D118 facts; one terminal-trip cohort feeds every output."""

import base64
import io
import json
from datetime import UTC, timedelta
from decimal import Decimal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.core.errors import AppError
from app.models.campaign import CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.stored_file import FilePurpose, FileScanStatus, StoredFile
from app.models.trip import LocationPing
from app.services.campaign_lifecycle import campaign_display_status
from app.services.campaign_report_rendering import MAX_ARTIFACT_BYTES, RENDERER_VERSION
from app.services.disclosure import DisclosureQuery, _canonical_hash, record_disclosure
from app.services.heatmaps import report_area_trip_cell_counts

LAGOS = ZoneInfo("Africa/Lagos")
ZERO = Decimal("0.00")
# Technical work limits for private preview decoding, not campaign policy.
MAX_REPORT_ARTWORK = 64
MAX_ARTWORK_SOURCE_BYTES = 4 * MAX_ARTIFACT_BYTES
MAX_ARTWORK_PIXELS = 40_000_000


def report_too_large():
    return AppError(
        "REPORT_TOO_LARGE", "Choose fewer campaigns or a shorter reporting period", status_code=422
    )


def check_snapshot_size(value, *, prior_bytes=0):
    size = len(json.dumps(value, ensure_ascii=True).encode())
    if prior_bytes + size > MAX_ARTIFACT_BYTES:
        raise report_too_large()
    return size


def _creative_query(campaign_ids):
    approved = aliased(CampaignCreative)
    has_approved = (
        select(approved.id)
        .where(
            approved.campaign_id == CampaignCreative.campaign_id,
            approved.status == "approved",
            approved.stored_file_id.is_not(None),
        )
        .correlate(CampaignCreative)
        .exists()
    )
    return select(CampaignCreative).where(
        CampaignCreative.campaign_id.in_(campaign_ids),
        CampaignCreative.status != "archived",
        CampaignCreative.stored_file_id.is_not(None),
        or_(CampaignCreative.status == "approved", ~has_approved),
    )


async def preflight_artwork(session, campaigns):
    rows = (
        await session.execute(
            _creative_query([campaign.id for campaign in campaigns])
            .with_only_columns(CampaignCreative.id, StoredFile.size_bytes)
            .join(StoredFile, StoredFile.id == CampaignCreative.stored_file_id)
            .limit(MAX_REPORT_ARTWORK + 1)
        )
    ).all()
    if len(rows) > MAX_REPORT_ARTWORK or sum(size for _, size in rows) > MAX_ARTWORK_SOURCE_BYTES:
        raise report_too_large()
    return {"pixels": MAX_ARTWORK_PIXELS, "snapshot_bytes": 0}


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _display_date(value):
    return aware(value).astimezone(LAGOS).strftime("%d %b %Y %H:%M WAT") if value else "Not set"


def verified_driving(cohort):
    trips = {trip.id: trip for trip in cohort.trips}
    rows = [
        row
        for row in cohort.analytics
        if row.status == "computed" and (row.distance_m > 0 or row.moving_seconds > 0)
    ]
    known = {row.trip_session_id for row in cohort.analytics if row.status == "computed"}
    incomplete = any(trip.id not in known for trip in cohort.trips)
    cars = {row.vehicle_id for row in rows}
    withheld = (incomplete and not rows) or 0 < len(cars) < 3
    return trips, rows, cars, withheld


def _artwork_preview_path(public_origin, file_id):
    origin = public_origin.strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            origin = ""
    except ValueError:
        origin = ""
    return f"{origin}/api/advertiser/reports/artwork/{file_id}"


async def _preview(session, *, creative, organization_id, storage, budget, public_origin):
    file = await session.scalar(
        select(StoredFile)
        .where(
            StoredFile.id == creative.stored_file_id,
            StoredFile.organization_id == organization_id,
            StoredFile.purpose == FilePurpose.CREATIVE,
            StoredFile.scan_status == FileScanStatus.CLEAN,
        )
        .with_for_update()
    )
    if file is None:
        return None
    mime = file.actual_content_type or file.content_type
    result = {
        "id": str(creative.id),
        "file_id": str(file.id),
        "label": creative.name,
        "content_type": mime,
        "preview_path": _artwork_preview_path(public_origin, file.id),
        "preview_base64": None,
    }
    if mime == "application/pdf":
        return result
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        return None
    data = bytearray()
    async for chunk in storage.stream(file.storage_key):
        data.extend(chunk)
        if len(data) > 20 * 1024 * 1024:
            raise AppError(
                "REPORT_ARTWORK_UNAVAILABLE", "Artwork preview is too large", status_code=409
            )
    import hashlib

    if len(data) != file.size_bytes or hashlib.sha256(data).hexdigest() != file.checksum_sha256:
        raise AppError(
            "REPORT_ARTWORK_UNAVAILABLE", "Artwork preview could not be verified", status_code=409
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("Artwork dimensions exceed the preview boundary")
            pixels = image.width * image.height
            if pixels > budget["pixels"]:
                raise report_too_large()
            budget["pixels"] -= pixels
            image = image.convert("RGB")
            image.thumbnail((660, 405))
            canvas = Image.new("RGB", (660, 405), "white")
            canvas.paste(image, ((660 - image.width) // 2, (405 - image.height) // 2))
            output = io.BytesIO()
            canvas.save(output, format="JPEG", quality=80)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise AppError(
            "REPORT_ARTWORK_UNAVAILABLE", "Artwork preview could not be prepared", status_code=409
        ) from None
    result["preview_base64"] = base64.b64encode(output.getvalue()).decode()
    return result


async def _creatives(session, *, campaign, storage, budget, public_origin):
    rows = list(
        await session.scalars(
            _creative_query([campaign.id])
            .order_by(CampaignCreative.created_at, CampaignCreative.id)
            .limit(MAX_REPORT_ARTWORK + 1)
        )
    )
    result = []
    if len(rows) > MAX_REPORT_ARTWORK:
        raise report_too_large()
    for creative in rows:
        preview = await _preview(
            session,
            creative=creative,
            organization_id=campaign.organization_id,
            storage=storage,
            budget=budget,
            public_origin=public_origin,
        )
        if preview:
            result.append(preview)
            check_snapshot_size(result, prior_bytes=budget["snapshot_bytes"])
    return result


async def _deployed_cars(session, *, campaign, start, end):
    assignments = list(
        await session.scalars(
            select(CampaignAssignment).where(
                CampaignAssignment.campaign_id == campaign.id,
                CampaignAssignment.activated_at.is_not(None),
                CampaignAssignment.activated_at < end,
            )
        )
    )
    cars = {
        row.vehicle_id
        for row in assignments
        if all(
            value is None or aware(value) > start
            for value in (row.deactivated_at, row.cancelled_at)
        )
    }
    return None if 0 < len(cars) < 3 else len(cars)


async def _areas(session, *, campaign, cohort, driving, settings, days, start, end):
    """Sum only complete, closed weeks with safe exact trip-membership partitions."""
    zones = list(
        await session.scalars(
            select(CampaignZone)
            .where(CampaignZone.campaign_id == campaign.id, CampaignZone.zone_type == "target")
            .order_by(CampaignZone.name, CampaignZone.id)
        )
    )
    result = {
        str(z.id): {"id": str(z.id), "name": z.name, "trip_count": 0, "estimated_views": Decimal(0)}
        for z in zones
    }
    statuses = {d.date: d.status for d in days}
    estimates = {
        str(r.trip_session_id): r.estimated_impressions
        for r in cohort.impressions
        if r.status == "estimated"
    }
    week = start.astimezone(LAGOS)
    released_weeks = 0
    while week.weekday() != 0:
        week += timedelta(days=1)
    while week + timedelta(days=7) <= end:
        week_days = [week.date() + timedelta(days=i) for i in range(7)]
        if any(statuses.get(d) in {None, "not_ready"} for d in week_days):
            week += timedelta(days=7)
            continue
        released = {d for d in week_days if statuses[d] == "released"}
        trips = [t for t in cohort.trips if aware(t.ended_at).astimezone(LAGOS).date() in released]
        ids = {t.id for t in trips}
        rows = [r for r in driving if r.trip_session_id in ids]
        selected = {r.trip_session_id for r in rows}
        trips = [t for t in trips if t.id in selected]
        cells_by_zone = {}
        week_trips = [
            t for t in cohort.trips if aware(t.ended_at).astimezone(LAGOS).date() in week_days
        ]
        week_ids = {t.id for t in week_trips}
        retained = dict(
            (
                await session.execute(
                    select(LocationPing.trip_session_id, func.count())
                    .where(LocationPing.trip_session_id.in_(week_ids))
                    .group_by(LocationPing.trip_session_id)
                )
            ).all()
        )
        unknown = any(
            retained.get(r.trip_session_id, 0) < r.ping_count
            for r in cohort.analytics
            if r.trip_session_id in week_ids
        )
        if trips:
            lower = min(aware(t.started_at) for t in trips) - timedelta(
                seconds=settings.location_ping_start_skew_seconds
            )
            upper = max(aware(t.ended_at) for t in trips) + timedelta(
                seconds=settings.location_ping_end_skew_seconds, microseconds=1
            )
            for z in zones:
                cells_by_zone[str(z.id)] = await report_area_trip_cell_counts(
                    session,
                    trip_ids=list(selected),
                    zone_id=z.id,
                    resolution_m=settings.privacy_min_resolution_m,
                    window_start_at=lower,
                    window_end_at=upper,
                )
        from app.services.disclosure import area_week_figures

        figures = None if unknown else area_week_figures(trips, cells_by_zone, estimates)
        if figures is not None:
            released_weeks += 1
            for zone, item in result.items():
                values = figures.get(zone, {"trip_count": 0, "estimated_views": Decimal(0)})
                item["trip_count"] += values["trip_count"]
                if item["estimated_views"] is None or values["estimated_views"] is None:
                    item["estimated_views"] = None
                else:
                    item["estimated_views"] += values["estimated_views"]
        week += timedelta(days=7)
    if not released_weeks:
        return []
    return [
        {
            **item,
            "estimated_views": str(item["estimated_views"])
            if item["estimated_views"] is not None
            else None,
        }
        for item in result.values()
    ]


async def _campaign_snapshot(session, *, campaign, start, end, settings, storage, now, budget):
    lower = max(start, aware(campaign.start_at)) if campaign.start_at else start
    campaign_end = await report_campaign_end(session, campaign)
    upper = min(end, campaign_end, now) if campaign_end else min(end, now)
    from app.services.disclosure import load_cells, released_totals

    cohort, daily = await load_cells(
        session, campaign_id=campaign.id, start=start, end=end, settings=settings, now=now
    )
    _, rows, _, _ = verified_driving(cohort)
    measured = released_totals(daily)
    views = measured.pop("estimated_views")
    measured = {k: str(v) if isinstance(v, Decimal) else v for k, v in measured.items()}
    measured["cars_deployed"] = (
        (await _deployed_cars(session, campaign=campaign, start=lower, end=upper))
        if lower < upper
        else 0
    )
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "status": campaign_display_status(campaign.status, campaign.end_at, now=now),
        "start_at": _display_date(campaign.start_at),
        "end_at": _display_date(campaign_end),
        "overlap_start": lower.astimezone(LAGOS).date().isoformat() if lower < upper else None,
        "overlap_end": upper.astimezone(LAGOS).date().isoformat() if lower < upper else None,
        "measured": measured,
        "estimates": {"views": str(views) if views is not None else None},
        "daily": [row.model_dump(mode="json") for row in daily],
        "areas": await _areas(
            session,
            campaign=campaign,
            cohort=cohort,
            driving=rows,
            settings=settings,
            days=daily,
            start=start,
            end=end,
        ),
        "creatives": await _creatives(
            session,
            campaign=campaign,
            storage=storage,
            budget=budget,
            public_origin=settings.public_origin,
        ),
        "note": "Some days hidden." if any(d.status != "released" for d in daily) else "",
        "areas_label": "Full weeks only",
    }


async def report_campaign_end(session, campaign):
    end = aware(campaign.end_at) if campaign.end_at else None
    if campaign.status == "cancelled":
        from app.services.campaign_cancellations import campaign_financial_cutoff

        cutoff = await campaign_financial_cutoff(session, campaign.id)
        if cutoff is None:
            raise AppError(
                "REPORT_SOURCE_INVALID", "Campaign end could not be verified", status_code=409
            )
        end = min(end, cutoff) if end else cutoff
    return end


async def build_report_snapshot(
    session,
    *,
    campaigns,
    actor_user_id,
    start,
    end,
    settings,
    storage,
    now,
    budget,
):
    items = []
    for campaign in campaigns:
        item = await _campaign_snapshot(
            session,
            campaign=campaign,
            start=start,
            end=end,
            settings=settings,
            storage=storage,
            now=now,
            budget=budget,
        )
        # Every disclosed count is empty or meets the independently checked floor.
        safe = all(
            value is None or value == 0 or value >= 3
            for value in (
                item["measured"]["cars_deployed"],
                *(row["vehicle_count"] for row in item["daily"]),
            )
        )
        await record_disclosure(
            session,
            settings=settings,
            query=DisclosureQuery(
                route_id="advertiser.campaign.report",
                principal_id=actor_user_id,
                tenant_id=campaign.organization_id,
                campaign_id=campaign.id,
                start_at=start,
                end_at=end,
                filters={"method": RENDERER_VERSION},
            ),
            has_releasable_cells=safe,
            result_hash=_canonical_hash(item),
            commit_served=False,
        )
        items.append(item)
        budget["snapshot_bytes"] = check_snapshot_size(items)
    return {
        "schema_version": RENDERER_VERSION,
        "generated_at": now.astimezone(LAGOS).isoformat(),
        "start_date": start.astimezone(LAGOS).date().isoformat(),
        "end_date": (end - timedelta(microseconds=1)).astimezone(LAGOS).date().isoformat(),
        "timezone": "Africa/Lagos",
        "campaigns": items,
    }
