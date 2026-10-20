"""Durable weekly/end obligations over the existing immutable report pipeline."""

import logging
from datetime import UTC, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_cancellation import CampaignCancellation
from app.models.report_schedule import ReportSchedule, ReportScheduleCursor
from app.schemas.measurement import MeasurementRunCreate
from app.schemas.report_issuances import ReportIssuanceCreate
from app.services.measurement import issue_measurement_run
from app.services.payout_rule_serialization import database_clock
from app.services.report_authorization import REPORT_ACTOR_ID
from app.services.report_issuances import request_report_issuance

logger = logging.getLogger(__name__)

WEEK = timedelta(days=7)
ELIGIBLE = ("active", "paused", "completed", "cancelled")


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
    return end


def next_due_window(start, end, now, existing):
    if start >= end:
        return None
    due = start + WEEK
    while due < end and due <= now:
        if due not in existing:
            return due, "weekly"
        due += WEEK
    if end <= now and end not in existing:
        return end, "final"
    return None


async def discover_report_obligations(session, *, limit):
    await session.execute(
        insert(ReportScheduleCursor)
        .values(name="campaigns")
        .on_conflict_do_nothing(index_elements=[ReportScheduleCursor.name])
    )
    cursor = await session.scalar(
        select(ReportScheduleCursor)
        .where(ReportScheduleCursor.name == "campaigns")
        .with_for_update()
    )
    query = (
        select(Campaign)
        .where(
            Campaign.status.in_(ELIGIBLE),
            Campaign.start_at.is_not(None),
            Campaign.end_at.is_not(None),
        )
        .order_by(Campaign.id)
        .limit(limit)
    )
    rows = list(
        await session.scalars(
            query.where(Campaign.id > cursor.campaign_id) if cursor.campaign_id else query
        )
    )
    if not rows and cursor.campaign_id:
        cursor.campaign_id = None
        rows = list(await session.scalars(query))
    now = await database_clock(session)
    created = 0
    for campaign in rows:
        end = await report_cutoff(session, campaign)
        if end is None:
            continue
        known = set(
            aware(value)
            for value in await session.scalars(
                select(ReportSchedule.period_end_at).where(
                    ReportSchedule.campaign_id == campaign.id,
                    ReportSchedule.period_start_at == campaign.start_at,
                )
            )
        )
        due = next_due_window(aware(campaign.start_at), end, now, known)
        if due:
            await session.execute(
                insert(ReportSchedule)
                .values(
                    id=uuid4(),
                    campaign_id=campaign.id,
                    period_start_at=campaign.start_at,
                    period_end_at=due[0],
                    kind=due[1],
                    measurement_request_id=uuid4(),
                    issuance_request_id=uuid4(),
                )
                .on_conflict_do_nothing(constraint="uq_report_schedule_window")
            )
            created += 1
    if rows:
        cursor.campaign_id = rows[-1].id
    await session.flush()
    return created


async def prepare_report(
    session,
    *,
    actor_user_id,
    campaign_id,
    start,
    end,
    measurement_request_id,
    issuance_request_id,
    settings,
):
    run = await issue_measurement_run(
        session,
        actor_user_id=actor_user_id,
        payload=MeasurementRunCreate(
            campaign_id=campaign_id,
            client_request_id=measurement_request_id,
            period_start_at=start,
            period_end_at=end,
        ),
        settings=settings,
    )
    issuance = await request_report_issuance(
        session,
        actor_user_id=actor_user_id,
        measurement_run_id=run.id,
        payload=ReportIssuanceCreate(client_request_id=issuance_request_id),
        settings=settings,
        admin=True,
    )
    return run, issuance


async def sweep_scheduled_reports(ctx):
    settings, maker = ctx["settings"], ctx["sessionmaker"]
    async with maker() as session:
        discovered = await discover_report_obligations(
            session, limit=settings.worker_sweep_batch_size
        )
        await session.commit()
    async with maker() as session:
        now = await database_clock(session)
        ids = list(
            await session.scalars(
                select(ReportSchedule.id)
                .where(ReportSchedule.state != "complete", ReportSchedule.next_attempt_at <= now)
                .order_by(ReportSchedule.next_attempt_at, ReportSchedule.id)
                .limit(settings.worker_sweep_batch_size)
            )
        )
    queued = failed = 0
    for identity in ids:
        async with maker() as session:
            now = await database_clock(session)
            obligation = await session.scalar(
                select(ReportSchedule)
                .where(
                    ReportSchedule.id == identity,
                    ReportSchedule.state != "complete",
                    ReportSchedule.next_attempt_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            if obligation is None:
                continue
            obligation.attempts += 1
            try:
                async with session.begin_nested():
                    run, issuance = await prepare_report(
                        session,
                        actor_user_id=REPORT_ACTOR_ID,
                        campaign_id=obligation.campaign_id,
                        start=obligation.period_start_at,
                        end=obligation.period_end_at,
                        measurement_request_id=obligation.measurement_request_id,
                        issuance_request_id=obligation.issuance_request_id,
                        settings=settings,
                    )
                    obligation.measurement_run_id, obligation.report_issuance_id = (
                        run.id,
                        issuance.id,
                    )
                    obligation.state, obligation.error_code = "complete", None
                queued += 1
            except Exception as error:
                if not isinstance(error, AppError):
                    logger.warning(
                        "job=sweep_report_schedules schedule=%s error=%s",
                        obligation.id,
                        type(error).__name__,
                    )
                obligation.state = "error"
                obligation.error_code = (
                    error.code if isinstance(error, AppError) else "REPORT_PREPARATION_FAILED"
                )
                obligation.next_attempt_at = now + timedelta(
                    minutes=settings.worker_sweep_interval_minutes
                )
                failed += 1
            await session.commit()
    return {"discovered": discovered, "queued": queued, "failed": failed}


async def rerun_campaign_report(session, *, actor_user_id: UUID, campaign_id: UUID, settings):
    from app.services.admin_authorization import require_active_admin
    from app.services.payout_rule_serialization import acquire_campaign_terms_lock

    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    end = await report_cutoff(session, campaign)
    now = await database_clock(session)
    if campaign.start_at is None or end is None or min(now, end) <= aware(campaign.start_at):
        raise AppError(
            "REPORT_PERIOD_UNAVAILABLE",
            "This campaign has no completed reporting period yet",
            status_code=409,
        )
    start = aware(campaign.start_at)
    if now < end and now - start >= WEEK:
        end = start + ((now - start) // WEEK) * WEEK
    else:
        end = min(now, end)
    _, issuance = await prepare_report(
        session,
        actor_user_id=actor_user_id,
        campaign_id=campaign_id,
        start=start,
        end=end,
        measurement_request_id=uuid4(),
        issuance_request_id=uuid4(),
        settings=settings,
    )
    return issuance
