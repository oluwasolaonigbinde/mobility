"""D71 fixtures represent already-issued files, without resurrecting S9 writers."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from report_fixtures import DAY_1, create_report_fixture
from sqlalchemy import select

from app.models.campaign_assignment import CampaignActivationEvent, CampaignAssignment
from app.models.measurement import MeasurementRun, MeasurementRunProofBinding
from app.models.report_issuance import ReportArtifact, ReportIssuance
from app.models.stored_file import StoredFile
from app.services.audit import create_audit_event
from app.services.report_integrity import canonical_sha256


def seed_legacy_issued_report(maker, storage, *, identity_tag="legacy-issued"):
    admin, advertiser, campaign = create_report_fixture(maker, identity_tag=identity_tag)

    async def seed():
        async with maker() as session:
            manifests = {
                "input_manifest": {
                    "period": {
                        "start_at": DAY_1.isoformat(),
                        "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
                    }
                },
                "result_manifest": {"title": "Previously issued campaign report"},
                "proof_manifest": {"historical": True},
                "report_snapshot": {"schema_version": "retired-renderer"},
            }
            digests = {
                name + "_sha256": canonical_sha256(value) for name, value in manifests.items()
            }
            run = MeasurementRun(
                id=uuid4(),
                organization_id=campaign.organization_id,
                campaign_id=campaign.id,
                created_by_user_id=admin.id,
                client_request_id=uuid4(),
                request_fingerprint="a" * 64,
                test_only=True,
                formula_version="retired-formula",
                method_revision="retired-method",
                period_start_at=DAY_1,
                period_end_at=DAY_1 + timedelta(days=1),
                **manifests,
                **digests,
            )
            session.add(run)
            await session.flush()
            event = await session.scalar(
                select(CampaignActivationEvent)
                .join(
                    CampaignAssignment,
                    CampaignAssignment.id == CampaignActivationEvent.assignment_id,
                )
                .where(CampaignAssignment.campaign_id == campaign.id)
            )
            facts = event.event_metadata["activation_snapshot"]
            session.add(
                MeasurementRunProofBinding(
                    measurement_run_id=run.id,
                    assignment_id=event.assignment_id,
                    activation_event_id=event.id,
                    creative_id=UUID(facts["creative_id"]),
                    installation_evidence_submission_id=UUID(
                        facts["installation_evidence_submission_id"]
                    ),
                    activation_snapshot_sha256=event.event_metadata["activation_snapshot_sha256"],
                    binding_fingerprint="b" * 64,
                )
            )
            frozen = {"historical": "already issued, never regenerated"}
            issuance = ReportIssuance(
                id=uuid4(),
                organization_id=campaign.organization_id,
                campaign_id=campaign.id,
                measurement_run_id=run.id,
                requested_by_user_id=advertiser.id,
                client_request_id=uuid4(),
                request_fingerprint="c" * 64,
                version=1,
                snapshot=frozen,
                snapshot_sha256=canonical_sha256(frozen),
                authority_fingerprint="d" * 64,
                schema_version="retired-export",
                renderer_version="retired-renderer",
                method_revision="retired-method",
                synthetic=True,
                status="ready",
                ready_at=datetime.now(UTC),
                **digests,
            )
            session.add(issuance)
            await session.flush()
            for kind, mime, content in (
                ("csv", "text/csv", b"Previously issued,unchanged\n"),
                ("pdf", "application/pdf", b"%PDF-1.4\nPreviously issued bytes\n%%EOF\n"),
            ):
                checksum = hashlib.sha256(content).hexdigest()
                key = f"reports/{campaign.organization_id}/{issuance.id}/legacy.{kind}"
                await storage.put(
                    object_key=key, content_type=mime, data=content, checksum_sha256=checksum
                )
                file = StoredFile(
                    id=uuid4(),
                    organization_id=campaign.organization_id,
                    uploader_user_id=advertiser.id,
                    purpose="report_export",
                    original_filename=f"legacy.{kind}",
                    storage_key=key,
                    content_type=mime,
                    actual_content_type=mime,
                    size_bytes=len(content),
                    checksum_sha256=checksum,
                    scan_status="clean",
                    scanned_at=datetime.now(UTC),
                )
                session.add(file)
                await session.flush()
                session.add(
                    ReportArtifact(
                        report_issuance_id=issuance.id,
                        stored_file_id=file.id,
                        format=kind,
                        content_type=mime,
                        size_bytes=len(content),
                        checksum_sha256=checksum,
                        renderer_version="retired-renderer",
                    )
                )
            for kind, identity, actor in (
                ("measurement_run", run.id, admin.id),
                ("report_issuance", issuance.id, advertiser.id),
            ):
                await create_audit_event(
                    session,
                    actor_user_id=actor,
                    action=f"historical.{kind}.issued",
                    entity_type=kind,
                    entity_id=str(identity),
                    metadata={"fixture": True},
                )
            await session.commit()
            return run, issuance

    run, issuance = asyncio.run(seed())
    return admin, advertiser, campaign, run, issuance
