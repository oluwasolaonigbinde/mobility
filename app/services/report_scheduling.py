"""D118: weekly and final reports use the same request and publisher."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.adapters.storage import StorageError
from app.core.errors import AppError
from app.core.outbox_enqueue import pending_job
from app.models.campaign import Campaign
from app.models.campaign_cancellation import CampaignCancellation
from app.models.campaign_report import CampaignReport
from app.models.report_schedule import ReportScheduleCursor
from app.services.audit import create_audit_event
from app.services.campaign_report_data import aware
from app.services.campaign_reports import _request_lock, create_report
from app.services.disclosure import _canonical_hash, after_day, load_cells, midnight
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.report_authorization import REPORT_ACTOR_ID, require_report_operator

WEEK = timedelta(days=7)
ELIGIBLE = ("active", "paused", "cancelled")


async def report_cutoff(session, campaign):
    if campaign.end_at is None:
        return None
    end = aware(campaign.end_at)
    if campaign.status == "cancelled":
        cutoff = await session.scalar(
            select(CampaignCancellation.cutoff_at).where(
                CampaignCancellation.campaign_id == campaign.id
            )
        )
        if cutoff is None:
            return None
        end = min(end, aware(cutoff))
    return after_day(end)


def next_due_window(start, end, now, existing):
    start = midnight(start)
    existing = {midnight(value) for value in existing}
    if start >= end:
        return None
    due = start + WEEK
    while due < end and due <= now:
        if due not in existing:
            return due, "weekly"
        due += WEEK
    return (end, "final") if end <= now and end not in existing else None


def latest_due_window(start, end, now):
    start = midnight(start)
    if start >= end or now < min(start + WEEK, end):
        return None
    if end <= now:
        return end, "final"
    weeks = (now - start) // WEEK
    return start + weeks * WEEK, "weekly"


async def rerun_campaign_report(
    session, *, actor_user_id, campaign_id, request_id, settings, storage
):
    await require_report_operator(session, actor_user_id)
    await _request_lock(session, actor_user_id, request_id)
    fingerprint = _canonical_hash({"campaign_id": str(campaign_id), "action": "rerun"})
    replay = await session.scalar(
        select(CampaignReport).where(
            CampaignReport.requested_by_user_id == actor_user_id,
            CampaignReport.client_request_id == request_id,
        )
    )
    if replay:
        if replay.request_fingerprint != fingerprint:
            raise AppError(
                "REPORT_REQUEST_CONFLICT",
                "This request was already used for another report",
                status_code=409,
            )
        return replay
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.get(Campaign, campaign_id, populate_existing=True)
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    now = await database_clock(session)
    end = await report_cutoff(session, campaign)
    due = (
        latest_due_window(aware(campaign.start_at), end, now) if campaign.start_at and end else None
    )
    if campaign.status not in ELIGIBLE or due is None:
        raise AppError(
            "REPORT_NOT_DUE", "The first weekly or final report is not due yet", status_code=409
        )
    _, days = await load_cells(
        session,
        campaign_id=campaign.id,
        start=midnight(campaign.start_at),
        end=due[0],
        settings=settings,
        now=now,
    )
    if any(d.status == "not_ready" for d in days):
        raise AppError("REPORT_NOT_DUE", "Daily figures are not ready yet", status_code=409)
    prior = await session.scalar(
        select(CampaignReport)
        .where(
            CampaignReport.campaign_id == campaign.id,
            CampaignReport.kind == due[1],
            CampaignReport.period_end_at >= due[0],
            CampaignReport.period_end_at < due[0] + timedelta(days=1),
        )
        .order_by(CampaignReport.version.desc())
        .limit(1)
    )
    return await create_report(
        session,
        actor_user_id=actor_user_id,
        campaigns=[campaign],
        request_id=request_id,
        request_fingerprint=fingerprint,
        start=midnight(campaign.start_at),
        end=due[0],
        kind=due[1],
        settings=settings,
        storage=storage,
        now=now,
        rerun_of=prior,
    )


async def _discover_campaign_report(session, *, campaign_id, settings, storage) -> int:
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await session.get(Campaign, campaign_id, populate_existing=True)
    if campaign is None:
        return 0
    end = await report_cutoff(session, campaign)
    if end is None or campaign.status not in ELIGIBLE:
        return 0
    now = await database_clock(session)
    known = {
        aware(value)
        for value in await session.scalars(
            select(CampaignReport.period_end_at).where(
                CampaignReport.campaign_id == campaign.id,
                CampaignReport.kind.in_(("weekly", "final")),
            )
        )
    }
    due = next_due_window(aware(campaign.start_at), end, now, known)
    if not due:
        return 0
    _, days = await load_cells(
        session,
        campaign_id=campaign.id,
        start=midnight(campaign.start_at),
        end=due[0],
        settings=settings,
        now=now,
    )
    if any(d.status == "not_ready" for d in days):
        return 0
    request_id = uuid4()
    try:
        async with session.begin_nested():
            await create_report(
                session,
                actor_user_id=REPORT_ACTOR_ID,
                campaigns=[campaign],
                request_id=request_id,
                request_fingerprint=_canonical_hash(str(request_id)),
                start=midnight(campaign.start_at),
                end=due[0],
                kind=due[1],
                settings=settings,
                storage=storage,
                now=now,
            )
    except (AppError, StorageError) as error:
        await create_audit_event(
            session,
            actor_user_id=REPORT_ACTOR_ID,
            action="campaign_report.preparation_failed",
            entity_type="campaign",
            entity_id=str(campaign_id),
            metadata={"error_code": getattr(error, "code", "REPORT_STORAGE_UNAVAILABLE")},
        )
        return 0
    return 1


async def discover_reports(session, *, settings, storage, limit):
    """Commit once per campaign so a report build holds only its own campaign key."""
    await require_report_operator(session, REPORT_ACTOR_ID)
    await session.execute(
        insert(ReportScheduleCursor)
        .values(name="campaigns")
        .on_conflict_do_nothing(index_elements=[ReportScheduleCursor.name])
    )
    cursor_id = await session.scalar(
        select(ReportScheduleCursor.campaign_id).where(ReportScheduleCursor.name == "campaigns")
    )
    query = (
        select(Campaign.id)
        .where(
            Campaign.status.in_(ELIGIBLE),
            Campaign.start_at.is_not(None),
            Campaign.end_at.is_not(None),
        )
        .order_by(Campaign.id)
        .limit(limit)
    )
    campaign_ids = list(
        await session.scalars(query.where(Campaign.id > cursor_id) if cursor_id else query)
    )
    if not campaign_ids and cursor_id:
        campaign_ids = list(await session.scalars(query))
    await session.commit()
    created = 0
    for campaign_id in campaign_ids:
        created += await _discover_campaign_report(
            session, campaign_id=campaign_id, settings=settings, storage=storage
        )
        # Duplicate reports are excluded by the campaign key and the known
        # periods it guards, so a concurrent sweep only repeats a no-op.
        await session.execute(
            update(ReportScheduleCursor)
            .where(ReportScheduleCursor.name == "campaigns")
            .values(campaign_id=campaign_id)
        )
        await session.commit()
    return created


async def sweep_scheduled_reports(ctx):
    settings, maker = ctx["settings"], ctx["sessionmaker"]
    # Lost queue hints and expired leases recover even when discovery is blocked.
    async with maker() as session:
        now = await database_clock(session)
        ids = await session.scalars(
            select(CampaignReport.id)
            .where(
                CampaignReport.status == "queued",
                CampaignReport.next_attempt_at <= now,
                (CampaignReport.lease_expires_at.is_(None))
                | (CampaignReport.lease_expires_at <= now),
            )
            .order_by(CampaignReport.next_attempt_at, CampaignReport.id)
            .limit(settings.worker_sweep_batch_size)
        )
        for identity in ids:
            pending_job(session, "generate_campaign_report", identity)
        await session.commit()
    async with maker() as session:
        count = await discover_reports(
            session,
            settings=settings,
            storage=ctx["storage"],
            limit=settings.worker_sweep_batch_size,
        )
        await session.commit()
        return count
