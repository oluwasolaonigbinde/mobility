"""One D118 report request, frozen once; issued files are never regenerated."""

from datetime import datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import cast, func, literal, select, text, union_all
from sqlalchemy.dialects.postgresql import JSONB

from app.core.errors import AppError
from app.core.outbox_enqueue import pending_job
from app.models.campaign import Campaign
from app.models.campaign_report import CampaignReport
from app.models.measurement import MeasurementRun
from app.models.report_issuance import ReportArtifact, ReportIssuance
from app.models.stored_file import FilePurpose, StoredFile
from app.schemas.campaign_reports import (
    CampaignReportCampaignRead,
    CampaignReportList,
    CampaignReportRead,
)
from app.schemas.report_issuances import ReportArtifactDownloadRead
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.campaign_report_data import (
    LAGOS,
    aware,
    build_report_snapshot,
    check_snapshot_size,
    preflight_artwork,
)
from app.services.campaign_report_rendering import MAX_ARTIFACT_BYTES
from app.services.campaigns import get_required_advertiser_context
from app.services.disclosure import _canonical_hash, lock_trip_disclosure_snapshot
from app.services.fraud_holds import lock_fraud_reconciliation_gate
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock
from app.services.report_issuances import _authorize_scope, _issued_snapshot_is_intact
from app.services.stored_files import _issue_download


def not_found():
    return AppError("CAMPAIGN_REPORT_NOT_FOUND", "Report was not found", status_code=404)


async def _request_lock(session, actor_id, request_id):
    key = int(_canonical_hash(f"campaign-report:{actor_id}:{request_id}")[:16], 16)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": key if key < 2**63 else key - 2**64}
    )


async def authorize_report(session, *, report, actor_user_id, admin):
    campaigns = report.snapshot.get("campaigns", [])
    if not campaigns or _canonical_hash(report.snapshot) != report.snapshot_sha256:
        raise not_found()
    for item in sorted(campaigns, key=lambda item: item["id"]):
        actor = await _authorize_scope(
            session,
            actor_user_id=actor_user_id,
            organization_id=report.organization_id,
            campaign_id=UUID(item["id"]),
            write=False,
        )
        if admin != (actor.role == "admin"):
            raise not_found()
    return report


def report_read(report):
    snapshot = report.snapshot
    return CampaignReportRead(
        id=report.id,
        kind=report.kind,
        status=report.status,
        start_date=snapshot["start_date"],
        end_date=snapshot["end_date"],
        campaigns=[
            CampaignReportCampaignRead(id=item["id"], name=item["name"])
            for item in snapshot["campaigns"]
        ],
        version=report.version,
        created_at=report.created_at,
        ready_at=report.ready_at,
        error="Report could not be prepared. Re-run it or ask Terrax for help."
        if report.status == "failed"
        else None,
    )


async def get_report(session, *, report_id, actor_user_id, admin):
    report = await session.get(CampaignReport, report_id)
    if report is None:
        raise not_found()
    return await authorize_report(session, report=report, actor_user_id=actor_user_id, admin=admin)


async def create_report(
    session,
    *,
    actor_user_id,
    campaigns,
    request_id,
    request_fingerprint,
    start,
    end,
    kind,
    settings,
    storage,
    now,
    rerun_of=None,
):
    """Called only after current company/operator scope is established."""
    # Same ordering as disclosure and money writers: gate before parent rows.
    await lock_fraud_reconciliation_gate(session, exclusive=True)
    if not campaigns:
        raise AppError(
            "REPORT_NO_CAMPAIGNS", "There are no campaigns to report on", status_code=409
        )
    # Bound work before expanding zero-filled daily data or decoding artwork.
    # This is a report memory limit, not a campaign-duration or client policy.
    if (end - start).days * len(campaigns) > MAX_ARTIFACT_BYTES // 1024:
        raise AppError(
            "REPORT_TOO_LARGE",
            "Choose fewer campaigns or a shorter reporting period",
            status_code=422,
        )
    await _request_lock(session, actor_user_id, request_id)
    organization_id = campaigns[0].organization_id
    for campaign in sorted(campaigns, key=lambda row: str(row.id)):
        await acquire_campaign_terms_lock(session, campaign.id)
        await _authorize_scope(
            session,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            write=True,
        )
    replay = await session.scalar(
        select(CampaignReport).where(
            CampaignReport.requested_by_user_id == actor_user_id,
            CampaignReport.client_request_id == request_id,
        )
    )
    if replay:
        if replay.request_fingerprint != request_fingerprint:
            raise AppError(
                "REPORT_REQUEST_CONFLICT",
                "This request was already used for another report",
                status_code=409,
            )
        return replay
    budget = await preflight_artwork(session, campaigns)
    for campaign in campaigns:
        await lock_trip_disclosure_snapshot(
            session, tenant_id=organization_id, campaign_id=campaign.id
        )
    snapshot = await build_report_snapshot(
        session,
        campaigns=campaigns,
        actor_user_id=actor_user_id,
        start=start,
        end=end,
        settings=settings,
        storage=storage,
        now=now,
        budget=budget,
    )
    check_snapshot_size(snapshot)
    version = 1
    campaign_id = campaigns[0].id if len(campaigns) == 1 else None
    if rerun_of is not None:
        version = 1 + int(
            await session.scalar(
                select(func.max(CampaignReport.version)).where(
                    CampaignReport.campaign_id == campaign_id,
                    CampaignReport.kind == kind,
                    CampaignReport.period_end_at == end,
                )
            )
            or 0
        )
    report = CampaignReport(
        id=uuid4(),
        organization_id=organization_id,
        campaign_id=campaign_id,
        requested_by_user_id=actor_user_id,
        client_request_id=request_id,
        request_fingerprint=request_fingerprint,
        kind=kind,
        version=version,
        rerun_of_id=rerun_of.id if rerun_of else None,
        period_start_at=start,
        period_end_at=end,
        snapshot=snapshot,
        snapshot_sha256=_canonical_hash(snapshot),
        status="queued",
        attempts=0,
        next_attempt_at=now,
    )
    session.add(report)
    await session.flush()
    pending_job(session, "generate_campaign_report", report.id)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="campaign_report.rerun" if rerun_of else "campaign_report.requested",
        entity_type="campaign_report",
        entity_id=str(report.id),
        metadata={
            "kind": kind,
            "version": version,
            "start_date": snapshot["start_date"],
            "end_date": snapshot["end_date"],
        },
    )
    return report


async def request_advertiser_report(session, *, actor_user_id, payload, settings, storage):
    await lock_fraud_reconciliation_gate(session, exclusive=True)
    organization, _ = await get_required_advertiser_context(
        session, actor_user_id, require_write=True
    )
    await _request_lock(session, actor_user_id, payload.client_request_id)
    fingerprint = _canonical_hash(payload.model_dump(mode="json"))
    replay = await session.scalar(
        select(CampaignReport).where(
            CampaignReport.requested_by_user_id == actor_user_id,
            CampaignReport.client_request_id == payload.client_request_id,
        )
    )
    if replay:
        await authorize_report(session, report=replay, actor_user_id=actor_user_id, admin=False)
        if replay.request_fingerprint != fingerprint:
            raise AppError(
                "REPORT_REQUEST_CONFLICT",
                "This request was already used for another report",
                status_code=409,
            )
        return replay
    query = (
        select(Campaign).where(Campaign.organization_id == organization.id).order_by(Campaign.id)
    )
    if payload.campaign_id is not None:
        query = query.where(Campaign.id == payload.campaign_id)
    campaigns = list(await session.scalars(query))
    if payload.campaign_id is not None and not campaigns:
        raise not_found()
    now = await database_clock(session)
    if payload.end_date > now.astimezone(LAGOS).date():
        raise AppError(
            "REPORT_PERIOD_INVALID", "Choose an end date on or before today", status_code=422
        )
    start = datetime.combine(payload.start_date, time.min, LAGOS)
    end = datetime.combine(payload.end_date + timedelta(days=1), time.min, LAGOS)
    return await create_report(
        session,
        actor_user_id=actor_user_id,
        campaigns=campaigns,
        request_id=payload.client_request_id,
        request_fingerprint=fingerprint,
        start=start,
        end=end,
        kind="custom",
        settings=settings,
        storage=storage,
        now=now,
    )


async def list_reports(session, *, actor_user_id, admin, campaign_id, limit, offset):
    organization_id = None
    if admin:
        await require_active_admin(session, actor_user_id)
    else:
        organization, _ = await get_required_advertiser_context(session, actor_user_id)
        organization_id = organization.id
    current = select(CampaignReport)
    legacy = (
        select(ReportIssuance, MeasurementRun, Campaign)
        .join(
            MeasurementRun,
            MeasurementRun.id == ReportIssuance.measurement_run_id,
        )
        .join(Campaign, Campaign.id == ReportIssuance.campaign_id)
        .where(ReportIssuance.status == "ready")
    )
    if organization_id:
        current = current.where(CampaignReport.organization_id == organization_id)
        legacy = legacy.where(ReportIssuance.organization_id == organization_id)
    if campaign_id:
        # JSON containment covers an all-campaign custom report as well.
        current = current.where(
            cast(CampaignReport.snapshot, JSONB)["campaigns"].contains([{"id": str(campaign_id)}])
        )
        legacy = legacy.where(ReportIssuance.campaign_id == campaign_id)
    new_ids = current.with_only_columns(
        CampaignReport.id.label("id"),
        CampaignReport.created_at.label("created_at"),
        literal(False).label("legacy"),
        maintain_column_froms=True,
    )
    old_ids = legacy.with_only_columns(
        ReportIssuance.id.label("id"),
        ReportIssuance.created_at.label("created_at"),
        literal(True).label("legacy"),
        maintain_column_froms=True,
    )
    combined = union_all(new_ids, old_ids).subquery()
    total = int(await session.scalar(select(func.count()).select_from(combined)) or 0)
    page = (
        await session.execute(
            select(combined.c.id, combined.c.legacy)
            .order_by(combined.c.created_at.desc(), combined.c.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    reports = []
    for identity, legacy_row in page:
        try:
            result = await _listed_report(
                session,
                identity=identity,
                legacy=legacy_row,
                actor_user_id=actor_user_id,
                admin=admin,
            )
        except AppError as error:
            if error.status_code == 404:
                continue
            raise
        reports.append(result)
    return CampaignReportList(items=reports, total=total, limit=limit, offset=offset)


async def _listed_report(session, *, identity, legacy, actor_user_id, admin):
    if not legacy:
        report = await get_report(
            session, report_id=identity, actor_user_id=actor_user_id, admin=admin
        )
        return report_read(report)
    issued, run, campaign = (
        await session.execute(
            select(ReportIssuance, MeasurementRun, Campaign)
            .join(MeasurementRun, MeasurementRun.id == ReportIssuance.measurement_run_id)
            .join(Campaign, Campaign.id == ReportIssuance.campaign_id)
            .where(ReportIssuance.id == identity)
        )
    ).one()
    if not _issued_snapshot_is_intact(issued, run):
        raise not_found()
    actor = await _authorize_scope(
        session,
        actor_user_id=actor_user_id,
        organization_id=issued.organization_id,
        campaign_id=campaign.id,
        write=False,
    )
    if admin != (actor.role == "admin"):
        raise not_found()
    return CampaignReportRead(
        id=issued.id,
        kind="issued",
        status="ready",
        version=issued.version,
        legacy=True,
        start_date=aware(run.period_start_at).astimezone(LAGOS).date(),
        end_date=(aware(run.period_end_at) - timedelta(microseconds=1)).astimezone(LAGOS).date(),
        campaigns=[CampaignReportCampaignRead(id=campaign.id, name=campaign.name)],
        created_at=issued.created_at,
        ready_at=issued.ready_at,
    )


async def download_report(
    session,
    *,
    report_id,
    artifact_format,
    actor_user_id,
    admin,
    storage,
    settings,
    reason,
):
    report = await get_report(
        session, report_id=report_id, actor_user_id=actor_user_id, admin=admin
    )
    if report.status != "ready":
        raise AppError("REPORT_NOT_READY", "This report is not ready to download", status_code=409)
    artifact = await session.scalar(
        select(ReportArtifact).where(
            ReportArtifact.campaign_report_id == report.id,
            ReportArtifact.format == artifact_format,
        )
    )
    if artifact is None:
        raise not_found()
    file = await session.scalar(
        select(StoredFile).where(
            StoredFile.id == artifact.stored_file_id,
            StoredFile.organization_id == report.organization_id,
            StoredFile.purpose == FilePurpose.REPORT_EXPORT,
            StoredFile.checksum_sha256 == artifact.checksum_sha256,
            StoredFile.size_bytes == artifact.size_bytes,
            StoredFile.content_type == artifact.content_type,
        )
    )
    if file is None:
        raise not_found()
    download = await _issue_download(
        session,
        stored_file=file,
        actor_user_id=actor_user_id,
        access_purpose="report_download",
        reason=reason,
        storage=storage,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="campaign_report.downloaded",
        entity_type="campaign_report",
        entity_id=str(report.id),
        metadata={"format": artifact.format},
    )
    return ReportArtifactDownloadRead(
        url=download.url,
        expires_in_seconds=download.expires_in_seconds,
        filename=file.original_filename,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        checksum_sha256=file.checksum_sha256,
    )
