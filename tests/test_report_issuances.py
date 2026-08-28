import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_advertiser_reports import PASSWORD
from test_measurement_runs import create_measurement_graph, issue_payload
from test_stored_files import FakeStorageProvider

from app.adapters.storage import StorageUnavailable
from app.api.v1.dependencies import get_storage_provider
from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.models.organization import (
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.models.report_issuance import ReportArtifact, ReportIssuance
from app.models.stored_file import StoredFile
from app.models.user import UserRole
from app.schemas.measurement import MeasurementRunCreate
from app.schemas.report_issuances import ReportIssuanceCreate
from app.services import report_issuances as report_issuance_service
from app.services.measurement import issue_measurement_run
from app.services.report_issuances import request_report_issuance, sweep_report_issuances


class ReportStorage(FakeStorageProvider):
    def __init__(self) -> None:
        super().__init__()
        self.fail_pdf_once = False

    async def put(self, **kwargs):
        if self.fail_pdf_once and str(kwargs["object_key"]).endswith(".pdf"):
            self.fail_pdf_once = False
            raise StorageUnavailable("synthetic write failure")
        return await super().put(**kwargs)


@pytest.fixture
def report_storage(db_client):
    provider = ReportStorage()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: provider
    yield provider
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def issue_run(db_client, db_sessionmaker, *, roi: bool = False, test_only: bool = True):
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    payload = issue_payload(campaign.id)
    payload["test_only"] = test_only
    if roi:
        payload["mode"] = "roi_enabled"
        payload["roi"] = {
            "attributed_revenue": "2400.00",
            "approved_cost_basis": "1200.00",
            "currency": "NGN",
            "conversion_provenance": "SYNTHETIC_TEST_ONLY conversion fixture",
            "revenue_provenance": "SYNTHETIC_TEST_ONLY revenue fixture",
            "reporting_cutoff": payload["period_end_at"],
            "synthetic": True,
            "method": {
                "revision": "synthetic-roi-v1",
                "approval_reference": "SYNTHETIC_TEST_ONLY",
                "attribution_rule": "Synthetic conversion belongs to the fixture campaign.",
                "attribution_window": "Synthetic one-day fixture window.",
                "cost_basis": "Frozen driver campaign cost in NGN.",
                "exclusions": "No synthetic exclusions.",
                "corrections": "Reissue on changed fixture input.",
                "late_data": "Late fixture data requires reissue.",
            },
        }
    response = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=payload,
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert response.status_code == 201, response.text
    return admin, advertiser, campaign, response.json()


def request_issuance(db_client, advertiser, run_id, *, request_id=None, reissue_of_id=None):
    return db_client.post(
        f"/api/v1/advertiser/measurement-runs/{run_id}/report-issuances",
        json={
            "client_request_id": str(request_id or uuid4()),
            "reissue_of_id": str(reissue_of_id) if reissue_of_id else None,
        },
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )


def run_worker(db_sessionmaker, settings, storage) -> int:
    return asyncio.run(
        sweep_report_issuances(
            {"sessionmaker": db_sessionmaker, "settings": settings, "storage": storage}
        )
    )


def test_performance_issuance_replay_worker_download_and_tamper_fail_closed(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    request_id = uuid4()

    first = request_issuance(db_client, advertiser, run["id"], request_id=request_id)
    replay = request_issuance(db_client, advertiser, run["id"], request_id=request_id)
    assert first.status_code == 202, first.text
    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert first.json()["status"] == "queued"
    assert first.json()["artifacts"] == []

    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    ready = db_client.get(
        f"/api/v1/advertiser/report-issuances/{first.json()['id']}", headers=headers
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready"
    assert [item["format"] for item in ready.json()["artifacts"]] == ["csv", "pdf"]
    assert all("/" not in item["filename"] for item in ready.json()["artifacts"])

    contents = list(report_storage.contents.values())
    csv_content = next(content for content in contents if content.startswith(b"section,"))
    pdf_content = next(content for content in contents if content.startswith(b"%PDF-1.4"))
    assert b"roi" not in csv_content.lower()
    assert b"roi" not in pdf_content.lower()
    assert first.json()["id"].encode() in csv_content
    assert first.json()["id"].encode() in pdf_content
    assert b"campaign-performance-export-v1" in csv_content
    assert b"campaign-report-renderer-v1" in pdf_content
    for source_group in run["input_manifest"]["sources"].values():
        for source in source_group:
            assert str(source["trip_session_id"]).encode() not in csv_content
            assert str(source["trip_session_id"]).encode() not in pdf_content

    for artifact_format in ("csv", "pdf"):
        download = db_client.post(
            f"/api/v1/advertiser/report-issuances/{first.json()['id']}"
            f"/artifacts/{artifact_format}/download",
            json={"reason": "Download the approved campaign analysis"},
            headers=headers,
        )
        assert download.status_code == 200, download.text
        assert download.json()["url"] == "http://storage.test/private-download"
        assert download.json()["filename"].endswith(f".{artifact_format}")

    pdf_key = next(key for key in report_storage.objects if key.endswith(".pdf"))
    report_storage.objects[pdf_key] = report_storage.objects[pdf_key].__class__(
        object_key=pdf_key,
        size_bytes=report_storage.objects[pdf_key].size_bytes,
        content_type="application/pdf",
        checksum_sha256="f" * 64,
    )
    tampered = db_client.post(
        f"/api/v1/advertiser/report-issuances/{first.json()['id']}/artifacts/pdf/download",
        json={"reason": "Download the approved campaign analysis"},
        headers=headers,
    )
    assert tampered.status_code == 409
    assert tampered.json()["error"]["code"] == "STORED_FILE_OBJECT_MISMATCH"


def test_approved_non_synthetic_configuration_journey_rechecks_revoked_authority(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    approved_settings = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_disclosure_live_authorized": True,
            "privacy_legal_approval_reference": "approved-legal-fixture-v1",
            "privacy_disclosure_config_reference": "approved-disclosure-fixture-v1",
            "privacy_query_history_retention_reference": "approved-retention-fixture-v1",
            "measurement_live_issuance_authorized": True,
            "measurement_report_method_reference": "measurement-contract-v1",
        }
    )
    db_client.app.dependency_overrides[get_settings] = lambda: approved_settings
    _, advertiser, _, run = issue_run(
        db_client,
        db_sessionmaker,
        test_only=False,
    )
    assert run["test_only"] is False

    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    issuance = request_issuance(db_client, advertiser, run["id"])
    assert issuance.status_code == 202, issuance.text
    assert issuance.json()["synthetic"] is False
    assert run_worker(db_sessionmaker, approved_settings, report_storage) == 1

    status_response = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=headers,
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] == "ready"
    download = db_client.post(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}/artifacts/csv/download",
        json={"reason": "Download the approved campaign analysis"},
        headers=headers,
    )
    assert download.status_code == 200, download.text

    revoked_settings = approved_settings.model_copy(
        update={"measurement_live_issuance_authorized": False}
    )
    db_client.app.dependency_overrides[get_settings] = lambda: revoked_settings
    hidden_status = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=headers,
    )
    hidden_download = db_client.post(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}/artifacts/csv/download",
        json={"reason": "Download the approved campaign analysis"},
        headers=headers,
    )
    assert hidden_status.status_code == 404
    assert hidden_download.status_code == 404


def test_lost_response_replay_does_not_recompose_mutable_latest_projection(
    db_client, db_sessionmaker, report_storage, monkeypatch
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    request_id = uuid4()
    first = request_issuance(db_client, advertiser, run["id"], request_id=request_id)
    assert first.status_code == 202

    async def unexpected_recomposition(*args, **kwargs):
        raise AssertionError("an accepted request replay must use its frozen issuance")

    monkeypatch.setattr(
        report_issuance_service,
        "_compose_snapshot",
        unexpected_recomposition,
    )
    replay = request_issuance(db_client, advertiser, run["id"], request_id=request_id)
    changed = request_issuance(
        db_client,
        advertiser,
        run["id"],
        request_id=request_id,
        reissue_of_id=uuid4(),
    )
    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "REPORT_ISSUANCE_REQUEST_CONFLICT"


def test_roi_golden_reissue_and_changed_request_conflict(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker, roi=True)
    request_id = uuid4()
    first = request_issuance(db_client, advertiser, run["id"], request_id=request_id)
    assert first.status_code == 202, first.text

    changed = request_issuance(
        db_client,
        advertiser,
        run["id"],
        request_id=request_id,
        reissue_of_id=uuid4(),
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "REPORT_ISSUANCE_REQUEST_CONFLICT"
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    csv_content = next(
        content for content in report_storage.contents.values() if content.startswith(b"section,")
    )
    assert b"Return on investment" in csv_content
    assert b"synthetic-roi-v1" in csv_content
    assert b",100,percent," in csv_content

    reissue = request_issuance(
        db_client,
        advertiser,
        run["id"],
        reissue_of_id=first.json()["id"],
    )
    assert reissue.status_code == 202, reissue.text
    assert reissue.json()["version"] == 2
    assert reissue.json()["reissue_of_id"] == first.json()["id"]
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    async def counts() -> tuple[int, int, int]:
        async with db_sessionmaker() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(ReportIssuance)) or 0),
                int(await session.scalar(select(func.count()).select_from(ReportArtifact)) or 0),
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(StoredFile)
                        .where(StoredFile.purpose == "report_export")
                    )
                    or 0
                ),
            )

    assert asyncio.run(counts()) == (2, 4, 4)


def test_partial_storage_failure_exposes_no_artifact_and_retry_recovers_pair(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance = request_issuance(db_client, advertiser, run["id"])
    report_storage.fail_pdf_once = True

    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    status_response = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"
    assert status_response.json()["artifacts"] == []

    async def make_due_and_count() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, UUID(issuance.json()["id"]))
            assert row is not None
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        async with db_sessionmaker() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(ReportArtifact)) or 0),
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(StoredFile)
                        .where(StoredFile.purpose == "report_export")
                    )
                    or 0
                ),
            )

    assert asyncio.run(make_due_and_count()) == (0, 0)
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    recovered = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert recovered.json()["status"] == "ready"
    assert recovered.json()["worker_attempts"] == 2
    assert len(recovered.json()["artifacts"]) == 2


def test_terminal_failure_can_only_recover_as_an_append_only_new_version(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance = request_issuance(db_client, advertiser, run["id"])

    async def mark_failed() -> None:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, UUID(issuance.json()["id"]))
            assert row is not None
            row.status = "failed"
            row.worker_attempts = 3
            row.last_error_code = "storage_unavailable"
            await session.commit()

    asyncio.run(mark_failed())
    reissue = request_issuance(
        db_client,
        advertiser,
        run["id"],
        reissue_of_id=issuance.json()["id"],
    )
    assert reissue.status_code == 202, reissue.text
    assert reissue.json()["version"] == 2
    assert reissue.json()["reissue_of_id"] == issuance.json()["id"]


def test_cross_tenant_viewer_revocation_and_gate_changes_fail_closed(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    outsider = create_test_user(
        db_sessionmaker,
        email="report-outsider@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=outsider.id)
    cross_tenant = request_issuance(db_client, outsider, run["id"])
    assert cross_tenant.status_code == 404

    viewer = create_test_user(
        db_sessionmaker,
        email="report-viewer@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    async def add_viewer() -> None:
        async with db_sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    organization_id=UUID(run["organization_id"]),
                    user_id=viewer.id,
                    role=MembershipRole.VIEWER,
                    status=MembershipStatus.ACTIVE,
                )
            )
            await session.commit()

    asyncio.run(add_viewer())
    forbidden = request_issuance(db_client, viewer, run["id"])
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "REPORT_ISSUANCE_ROLE_FORBIDDEN"

    issuance = request_issuance(db_client, advertiser, run["id"])
    assert issuance.status_code == 202
    viewer_status = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=auth_headers(db_client, viewer.email, PASSWORD),
    )
    assert viewer_status.status_code == 404
    blocked_settings = settings.model_copy(update={"privacy_disclosure_synthetic_test_mode": False})
    assert run_worker(db_sessionmaker, blocked_settings, report_storage) == 1

    async def inspect_failed_publication() -> tuple[str, int]:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, UUID(issuance.json()["id"]))
            count = int(await session.scalar(select(func.count()).select_from(ReportArtifact)) or 0)
            assert row is not None
            return row.status, count

    assert asyncio.run(inspect_failed_publication()) == ("queued", 0)

    db_client.app.dependency_overrides[get_settings] = lambda: blocked_settings
    hidden = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "REPORT_ISSUANCE_NOT_FOUND"
    db_client.app.dependency_overrides[get_settings] = lambda: settings

    async def revoke() -> None:
        async with db_sessionmaker() as session:
            membership = await session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == UUID(run["organization_id"]),
                    OrganizationMembership.user_id == advertiser.id,
                )
            )
            assert membership is not None
            membership.status = MembershipStatus.DISABLED
            await session.commit()

    asyncio.run(revoke())
    revoked = db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert revoked.status_code == 404


def test_report_audits_exclude_contents_urls_and_raw_errors(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance = request_issuance(db_client, advertiser, run["id"])
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    db_client.post(
        f"/api/v1/advertiser/report-issuances/{issuance.json()['id']}/artifacts/csv/download",
        json={"reason": "Download the approved campaign analysis"},
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            events = list(
                await session.scalars(select(AuditEvent).where(AuditEvent.action.like("report_%")))
            )
            serialized = str([event.event_metadata for event in events])
            assert "http://" not in serialized
            assert "csv_content" not in serialized
            assert "pdf_content" not in serialized
            assert "Traceback" not in serialized

    asyncio.run(inspect())


def test_admin_request_status_download_and_expired_lease_recovery(
    db_client, db_sessionmaker, settings, report_storage
) -> None:
    admin, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    created = db_client.post(
        f"/api/v1/admin/measurement-runs/{run['id']}/report-issuances",
        json={"client_request_id": str(uuid4())},
        headers=admin_headers,
    )
    assert created.status_code == 202, created.text

    async def expire_claim() -> None:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, UUID(created.json()["id"]))
            assert row is not None
            row.status = "processing"
            row.worker_attempts = 1
            row.processing_token = uuid4()
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_claim())
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    ready = db_client.get(
        f"/api/v1/admin/report-issuances/{created.json()['id']}", headers=admin_headers
    )
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["worker_attempts"] == 2
    download = db_client.post(
        f"/api/v1/admin/report-issuances/{created.json()['id']}/artifacts/pdf/download",
        json={"reason": "Review the issued campaign report evidence"},
        headers=admin_headers,
    )
    assert download.status_code == 200, download.text

    async def report_file_id() -> UUID:
        async with db_sessionmaker() as session:
            stored_file_id = await session.scalar(
                select(ReportArtifact.stored_file_id).where(
                    ReportArtifact.report_issuance_id == UUID(created.json()["id"]),
                    ReportArtifact.format == "pdf",
                )
            )
            assert stored_file_id is not None
            return stored_file_id

    file_id = asyncio.run(report_file_id())

    async def reject_linked_file_mutation() -> None:
        async with db_sessionmaker() as session:
            stored_file = await session.get(StoredFile, file_id)
            assert stored_file is not None
            stored_file.original_filename = "changed.pdf"
            with pytest.raises(ValueError, match="stored file is immutable"):
                await session.commit()
            await session.rollback()
        async with db_sessionmaker() as session:
            stored_file = await session.get(StoredFile, file_id)
            assert stored_file is not None
            await session.delete(stored_file)
            with pytest.raises(ValueError, match="stored file is immutable"):
                await session.commit()
            await session.rollback()

    asyncio.run(reject_linked_file_mutation())
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    generic_metadata = db_client.get(
        f"/api/v1/advertiser/files/{file_id}", headers=advertiser_headers
    )
    generic_advertiser_download = db_client.post(
        f"/api/v1/advertiser/files/{file_id}/download",
        json={"purpose": "campaign_preview", "reason": "Preview the campaign file"},
        headers=advertiser_headers,
    )
    generic_admin_download = db_client.post(
        f"/api/v1/admin/files/{file_id}/download",
        json={"purpose": "security_review", "reason": "Review private object integrity"},
        headers=admin_headers,
    )
    assert generic_metadata.status_code == 404
    assert generic_advertiser_download.status_code == 404
    assert generic_admin_download.status_code == 404

    wrong_surface = db_client.get(
        f"/api/v1/admin/report-issuances/{created.json()['id']}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert wrong_surface.status_code == 403


def test_concurrent_identical_requests_converge_on_postgres(
    postgis_db_sessionmaker, settings
) -> None:
    admin, advertiser, campaign = create_measurement_graph(postgis_db_sessionmaker)

    async def create_run():
        async with postgis_db_sessionmaker() as session:
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=MeasurementRunCreate.model_validate(issue_payload(campaign.id)),
                settings=settings,
            )
            await session.commit()
            return run.id

    run_id = asyncio.run(create_run())
    payload = ReportIssuanceCreate(client_request_id=uuid4())

    async def request_once():
        async with postgis_db_sessionmaker() as session:
            issuance = await request_report_issuance(
                session,
                actor_user_id=advertiser.id,
                measurement_run_id=run_id,
                payload=payload,
                settings=settings,
                admin=False,
            )
            await session.commit()
            return issuance.id

    async def run_both():
        return await asyncio.gather(request_once(), request_once())

    first_id, second_id = asyncio.run(run_both())
    assert first_id == second_id

    async def count() -> int:
        async with postgis_db_sessionmaker() as session:
            return int(await session.scalar(select(func.count()).select_from(ReportIssuance)) or 0)

    assert asyncio.run(count()) == 1
