"""Publish one deterministic pair; queue retries adopt the same immutable keys."""

import hashlib
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.adapters.storage import StorageObjectConflict, StorageObjectNotFound, StorageUnavailable
from app.models.campaign_report import CampaignReport
from app.models.report_issuance import ReportArtifact
from app.models.stored_file import FilePurpose, FileScanStatus, StoredFile
from app.services.audit import create_audit_event
from app.services.campaign_report_data import aware
from app.services.campaign_report_rendering import (
    RENDERER_VERSION,
    render_campaign_csv,
    render_campaign_pdf,
)
from app.services.disclosure import _canonical_hash
from app.services.payout_rule_serialization import database_clock

# Retain the previous report worker's exact attempt/lease values (S9/D118).
REPORT_MAX_ATTEMPTS = 3
REPORT_LEASE_SECONDS = 120


async def _claim(maker, report_id):
    async with maker() as session:
        report = await session.scalar(
            select(CampaignReport).where(CampaignReport.id == report_id).with_for_update()
        )
        now = await database_clock(session)
        if report is None or report.status != "queued" or aware(report.next_attempt_at) > now:
            return None
        if report.lease_expires_at and aware(report.lease_expires_at) > now:
            return None
        if report.attempts >= REPORT_MAX_ATTEMPTS:
            report.status, report.error_code = "failed", "REPORT_ATTEMPTS_EXHAUSTED"
            report.processing_token = report.lease_expires_at = None
            await session.commit()
            return None
        report.attempts += 1
        report.processing_token = uuid4()
        report.lease_expires_at = now + timedelta(seconds=REPORT_LEASE_SECONDS)
        await session.commit()
        return report, report.processing_token


def _pair(report):
    if (
        _canonical_hash(report.snapshot) != report.snapshot_sha256
        or report.snapshot.get("schema_version") != RENDERER_VERSION
    ):
        raise ValueError("REPORT_SNAPSHOT_INVALID")
    artifacts = []
    for kind, mime, content in (
        ("csv", "text/csv", render_campaign_csv(report.snapshot)),
        ("pdf", "application/pdf", render_campaign_pdf(report.snapshot)),
    ):
        checksum = hashlib.sha256(content).hexdigest()
        period = f"{report.snapshot['start_date']}-{report.snapshot['end_date']}"
        filename = f"cardvert-{period}-{report.id}.{kind}"
        key = f"reports/{report.organization_id}/{report.id}/{checksum}.{kind}"
        artifacts.append(
            {
                "format": kind,
                "content_type": mime,
                "content": content,
                "checksum": checksum,
                "filename": filename,
                "key": key,
            }
        )
    return artifacts


def _matches(observed, artifact):
    return (
        observed.object_key == artifact["key"]
        and observed.content_type.lower() == artifact["content_type"]
        and observed.size_bytes == len(artifact["content"])
        and observed.checksum_sha256.lower() == artifact["checksum"]
    )


async def _put_pair(storage, artifacts):
    for artifact in artifacts:
        try:
            observed = await storage.stat(artifact["key"])
        except StorageObjectNotFound:
            observed = await storage.put(
                object_key=artifact["key"],
                content_type=artifact["content_type"],
                data=artifact["content"],
                checksum_sha256=artifact["checksum"],
            )
        if not _matches(observed, artifact):
            raise StorageObjectConflict("Report object metadata mismatch")


async def _ready(maker, *, report_id, token, artifacts, storage):
    async with maker() as session:
        report = await session.scalar(
            select(CampaignReport).where(CampaignReport.id == report_id).with_for_update()
        )
        now = await database_clock(session)
        if (
            report is None
            or report.status != "queued"
            or report.processing_token != token
            or report.lease_expires_at is None
            or aware(report.lease_expires_at) <= now
        ):
            return "skipped"
        for artifact in artifacts:
            if not _matches(await storage.stat(artifact["key"]), artifact):
                raise StorageObjectConflict("Report object metadata mismatch")
        if aware(report.lease_expires_at) <= await database_clock(session):
            return "skipped"
        for artifact in artifacts:
            file = StoredFile(
                id=uuid4(),
                upload_intent_id=None,
                organization_id=report.organization_id,
                subject_user_id=None,
                uploader_user_id=report.requested_by_user_id,
                purpose=FilePurpose.REPORT_EXPORT,
                original_filename=artifact["filename"],
                storage_key=artifact["key"],
                content_type=artifact["content_type"],
                actual_content_type=artifact["content_type"],
                size_bytes=len(artifact["content"]),
                checksum_sha256=artifact["checksum"],
                scan_status=FileScanStatus.CLEAN,
                scan_attempts=0,
                scanned_at=now,
            )
            session.add(file)
            await session.flush()
            session.add(
                ReportArtifact(
                    id=uuid4(),
                    report_issuance_id=None,
                    campaign_report_id=report.id,
                    stored_file_id=file.id,
                    format=artifact["format"],
                    content_type=artifact["content_type"],
                    size_bytes=len(artifact["content"]),
                    checksum_sha256=artifact["checksum"],
                    renderer_version=RENDERER_VERSION,
                )
            )
        lease_end = aware(report.lease_expires_at)
        report.status, report.ready_at, report.error_code = "ready", now, None
        report.processing_token = report.lease_expires_at = None
        await create_audit_event(
            session,
            actor_user_id=None,
            action="campaign_report.ready",
            entity_type="campaign_report",
            entity_id=str(report.id),
            metadata={"version": report.version, "snapshot_sha256": report.snapshot_sha256},
        )
        if lease_end <= await database_clock(session):
            await session.rollback()
            return "skipped"
        await session.commit()
        return "ready"


async def _failed(maker, *, report_id, token, error):
    async with maker() as session:
        report = await session.scalar(
            select(CampaignReport).where(CampaignReport.id == report_id).with_for_update()
        )
        now = await database_clock(session)
        if (
            report is None
            or report.status != "queued"
            or report.processing_token != token
            or report.lease_expires_at is None
            or aware(report.lease_expires_at) <= now
        ):
            return "skipped"
        lease_end = aware(report.lease_expires_at)
        transient = isinstance(error, StorageUnavailable)
        report.processing_token = report.lease_expires_at = None
        report.error_code = (
            "REPORT_STORAGE_UNAVAILABLE" if transient else "REPORT_PREPARATION_FAILED"
        )
        if transient and report.attempts < REPORT_MAX_ATTEMPTS:
            report.next_attempt_at = now + timedelta(seconds=REPORT_LEASE_SECONDS)
            result = "retry"
        else:
            report.status = "failed"
            result = "failed"
        await create_audit_event(
            session,
            actor_user_id=None,
            action="campaign_report.failed",
            entity_type="campaign_report",
            entity_id=str(report.id),
            metadata={"error_code": report.error_code, "error_class": type(error).__name__},
        )
        if lease_end <= await database_clock(session):
            await session.rollback()
            return "skipped"
        await session.commit()
        return result


async def publish_campaign_report(maker, *, report_id, storage):
    claimed = await _claim(maker, report_id)
    if claimed is None:
        return "skipped"
    report, token = claimed
    try:
        artifacts = _pair(report)
        await _put_pair(storage, artifacts)
        return await _ready(
            maker, report_id=report.id, token=token, artifacts=artifacts, storage=storage
        )
    except Exception as error:
        # Keys are deterministic from the durable frozen row, including after
        # an uncertain write. No cleanup races a late successful write. A retry
        # verifies/adopts the same bytes; no ready report enters this path.
        return await _failed(maker, report_id=report.id, token=token, error=error)
