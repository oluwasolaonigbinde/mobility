import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
from app.models.report_issuance import (
    ReportArtifact,
    ReportIssuance,
    ReportIssuanceStatus,
    ReportPublicationIntent,
    ReportPublicationState,
)
from app.models.stored_file import StoredFile
from app.models.user import UserRole
from app.schemas.measurement import MeasurementRunCreate
from app.schemas.report_issuances import ReportIssuanceCreate
from app.services import report_issuances as report_issuance_service
from app.services.measurement import issue_measurement_run
from app.services.report_issuances import (
    request_report_issuance,
    sweep_report_issuances,
    sweep_report_publications,
)


def rendered_pdf_bytes(content: bytes) -> bytes:
    """Reassemble a bounded PDF's drawn text so wrapped disclosure lines are searchable."""
    lines = [
        line.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\")
        for line in re.findall(rb"\((.*)\) Tj", content)
    ]
    return b" ".join(lines)


class ReportStorage(FakeStorageProvider):
    def __init__(self) -> None:
        super().__init__()
        self.fail_pdf_once = False
        # When set, delete silently does nothing, standing in for a provider that accepts
        # a delete the object survives (object-lock retention, a denied policy, a bug).
        self.ignore_deletes = False
        # Awaited after a successful write so a test can simulate what a real publisher
        # cannot see: the world changing between its object write and its commit.
        self.after_put = None

    async def delete(self, object_key: str) -> None:
        if self.ignore_deletes:
            self.deleted.append(object_key)
            return
        await super().delete(object_key)

    async def put(self, **kwargs):
        object_key = str(kwargs["object_key"])
        if self.fail_pdf_once and object_key.endswith(".pdf"):
            self.fail_pdf_once = False
            raise StorageUnavailable("synthetic write failure")
        observed = await super().put(**kwargs)
        if self.after_put is not None:
            await self.after_put(object_key)
        return observed


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


def run_publication_cleanup(db_sessionmaker, settings, storage) -> int:
    return asyncio.run(
        sweep_report_publications(db_sessionmaker, storage=storage, settings=settings)
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
    from app.services.measurement import (
        DENSITY_PARAMETER_CALIBRATION,
        DENSITY_PARAMETER_SOURCE,
        VERIFIED_MOVEMENT_CAVEAT,
    )

    frozen_metrics = {metric["id"]: metric for metric in run["result_manifest"]["metrics"]}
    density_profile = frozen_metrics["modelled_potential_contacts"]["density_provenance"][
        "profiles"
    ][0]
    for fact in (
        VERIFIED_MOVEMENT_CAVEAT.encode(),
        DENSITY_PARAMETER_SOURCE.encode(),
        DENSITY_PARAMETER_CALIBRATION.encode(),
        density_profile["value_fingerprint"].encode(),
        density_profile["traffic_density_per_km"].encode(),
        b"completed trips covered",
    ):
        # The wrapped PDF is searched through its drawn text, not its raw bytes.
        assert fact in b" ".join(csv_content.split()), fact
        assert fact in rendered_pdf_bytes(pdf_content), fact
    movement = frozen_metrics["verified_vehicle_movement"]["completeness"]
    assert movement["denominator_trip_count"] >= movement["covered_trip_count"]
    assert movement["suppressed"] is False
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
    pdf_content = next(
        content for content in report_storage.contents.values() if content.startswith(b"%PDF-1.4")
    )
    frozen_roi = run["result_manifest"]["roi"]
    disclosed = {
        **frozen_roi["method"],
        **frozen_roi["provenance"],
        "method_revision": frozen_roi["method_revision"],
    }
    contract = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "measurement-methodology.json").read_text()
    )
    for field in contract["roi_gate"]["required_disclosure"]:
        value = str(disclosed[field]).encode()
        assert value in b" ".join(csv_content.split()), field
        assert value in rendered_pdf_bytes(pdf_content), field

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


def test_expired_third_worker_claim_terminalizes_without_a_fourth_attempt(
    db_client, db_sessionmaker, settings, report_storage, monkeypatch
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance = request_issuance(db_client, advertiser, run["id"])
    issuance_id = UUID(issuance.json()["id"])

    async def simulate_worker_crash(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(
        report_issuance_service,
        "_generate_and_publish",
        simulate_worker_crash,
    )

    async def expire_claim(expected_attempt: int) -> None:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            assert row.status == "processing"
            assert row.worker_attempts == expected_attempt
            assert row.processing_token is not None
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    for attempt in range(1, 4):
        assert run_worker(db_sessionmaker, settings, report_storage) == 1
        asyncio.run(expire_claim(attempt))

    assert run_worker(db_sessionmaker, settings, report_storage) == 0

    async def terminal_state() -> tuple[ReportIssuance, list[AuditEvent]]:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "report_issuance",
                        AuditEvent.entity_id == str(issuance_id),
                        AuditEvent.action.in_(
                            {
                                "report_issuance.worker_claimed",
                                "report_issuance.failed",
                            }
                        ),
                    )
                )
            )
            return row, events

    failed, events = asyncio.run(terminal_state())
    assert failed.status == "failed"
    assert failed.worker_attempts == 3
    assert failed.processing_token is None
    assert failed.lease_expires_at is None
    assert failed.next_attempt_at is None
    assert failed.ready_at is None
    assert failed.last_error_code == "worker_lease_expired"

    claimed = [event for event in events if event.action == "report_issuance.worker_claimed"]
    terminal = [event for event in events if event.action == "report_issuance.failed"]
    assert sorted(event.event_metadata["attempt"] for event in claimed) == [1, 2, 3]
    assert len(terminal) == 1
    assert terminal[0].event_metadata == {
        "attempt": 3,
        "error_code": "worker_lease_expired",
    }


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
    hidden_parent = db_client.get(
        f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "REPORT_ISSUANCE_NOT_FOUND"
    assert hidden_parent.status_code == 404
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


def test_changed_authority_and_requester_can_discover_only_the_current_reissue_parent(
    db_client, db_sessionmaker, settings
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
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker, test_only=False)
    no_current = db_client.get(
        f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert no_current.status_code == 200
    assert no_current.json() is None
    first = request_issuance(db_client, advertiser, run["id"])
    assert first.status_code == 202, first.text

    async def mark_ready() -> None:
        async with db_sessionmaker() as session:
            issuance = await session.get(ReportIssuance, UUID(first.json()["id"]))
            assert issuance is not None
            issuance.status = "ready"
            issuance.ready_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(mark_ready())

    successor = create_test_user(
        db_sessionmaker,
        email="report-successor@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    viewer = create_test_user(
        db_sessionmaker,
        email="report-parent-viewer@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    outsider = create_test_user(
        db_sessionmaker,
        email="report-parent-outsider@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=outsider.id)

    async def add_memberships() -> None:
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    OrganizationMembership(
                        organization_id=UUID(run["organization_id"]),
                        user_id=successor.id,
                        role=MembershipRole.MANAGER,
                        status=MembershipStatus.ACTIVE,
                    ),
                    OrganizationMembership(
                        organization_id=UUID(run["organization_id"]),
                        user_id=viewer.id,
                        role=MembershipRole.VIEWER,
                        status=MembershipStatus.ACTIVE,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(add_memberships())
    changed_settings = approved_settings.model_copy(
        update={"privacy_legal_approval_reference": "approved-successor-authority-v2"}
    )
    db_client.app.dependency_overrides[get_settings] = lambda: changed_settings
    successor_headers = auth_headers(db_client, successor.email, PASSWORD)

    hidden_status = db_client.get(
        f"/api/v1/advertiser/report-issuances/{first.json()['id']}",
        headers=successor_headers,
    )
    assert hidden_status.status_code == 404

    current = db_client.get(
        f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
        headers=successor_headers,
    )
    assert current.status_code == 200, current.text
    assert current.json() == {
        "id": first.json()["id"],
        "measurement_run_id": run["id"],
        "version": 1,
        "status": "ready",
    }

    reissue = request_issuance(
        db_client,
        successor,
        run["id"],
        reissue_of_id=current.json()["id"],
    )
    assert reissue.status_code == 202, reissue.text
    assert reissue.json()["version"] == 2
    assert reissue.json()["reissue_of_id"] == first.json()["id"]

    async def mark_failed() -> None:
        async with db_sessionmaker() as session:
            issuance = await session.get(ReportIssuance, UUID(reissue.json()["id"]))
            assert issuance is not None
            issuance.status = "failed"
            issuance.last_error_code = "storage_unavailable"
            await session.commit()

    asyncio.run(mark_failed())
    failed_parent = db_client.get(
        f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert failed_parent.status_code == 200
    assert failed_parent.json()["id"] == reissue.json()["id"]
    assert failed_parent.json()["status"] == "failed"
    recovered = request_issuance(
        db_client,
        advertiser,
        run["id"],
        reissue_of_id=failed_parent.json()["id"],
    )
    assert recovered.status_code == 202, recovered.text
    assert recovered.json()["version"] == 3

    for hidden_user in (viewer, outsider):
        hidden_parent = db_client.get(
            f"/api/v1/advertiser/measurement-runs/{run['id']}/report-issuances",
            headers=auth_headers(db_client, hidden_user.email, PASSWORD),
        )
        assert hidden_parent.status_code == 404


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


def test_concurrent_identical_reissues_converge_on_postgres(
    postgis_db_sessionmaker, settings
) -> None:
    admin, advertiser, campaign = create_measurement_graph(postgis_db_sessionmaker)

    async def create_parent() -> tuple[UUID, UUID]:
        async with postgis_db_sessionmaker() as session:
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=MeasurementRunCreate.model_validate(issue_payload(campaign.id)),
                settings=settings,
            )
            parent = await request_report_issuance(
                session,
                actor_user_id=advertiser.id,
                measurement_run_id=run.id,
                payload=ReportIssuanceCreate(client_request_id=uuid4()),
                settings=settings,
                admin=False,
            )
            parent.status = "failed"
            parent.last_error_code = "storage_unavailable"
            await session.commit()
            return run.id, parent.id

    run_id, parent_id = asyncio.run(create_parent())
    payload = ReportIssuanceCreate(client_request_id=uuid4(), reissue_of_id=parent_id)

    async def request_once() -> UUID:
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

    async def run_both() -> tuple[UUID, UUID]:
        first, second = await asyncio.gather(request_once(), request_once())
        return first, second

    first_id, second_id = asyncio.run(run_both())
    assert first_id == second_id

    async def versions() -> list[int]:
        async with postgis_db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(ReportIssuance.version)
                    .where(ReportIssuance.measurement_run_id == run_id)
                    .order_by(ReportIssuance.version)
                )
            )

    assert asyncio.run(versions()) == [1, 2]


def test_expired_earlier_claim_retries_successfully_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance = request_issuance(postgis_db_client, advertiser, run["id"])
    issuance_id = UUID(issuance.json()["id"])

    async def expire_first_claim() -> None:
        async with postgis_db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            row.status = "processing"
            row.worker_attempts = 1
            row.processing_token = uuid4()
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_first_claim())
    storage = ReportStorage()
    assert run_worker(postgis_db_sessionmaker, settings, storage) == 1

    async def completed_state() -> tuple[ReportIssuance, list[AuditEvent]]:
        async with postgis_db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "report_issuance",
                        AuditEvent.entity_id == str(issuance_id),
                        AuditEvent.action.in_(
                            {
                                "report_issuance.worker_claimed",
                                "report_issuance.ready",
                                "report_issuance.failed",
                            }
                        ),
                    )
                )
            )
            return row, events

    ready, events = asyncio.run(completed_state())
    assert ready.status == "ready"
    assert ready.worker_attempts == 2
    assert ready.processing_token is None
    assert ready.lease_expires_at is None
    assert ready.next_attempt_at is None
    assert ready.last_error_code is None
    assert len(storage.objects) == 2
    assert [
        event.event_metadata["attempt"]
        for event in events
        if event.action == "report_issuance.worker_claimed"
    ] == [2]
    assert len([event for event in events if event.action == "report_issuance.ready"]) == 1
    assert not [event for event in events if event.action == "report_issuance.failed"]


def test_expired_final_claim_terminalizes_once_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance = request_issuance(postgis_db_client, advertiser, run["id"])
    issuance_id = UUID(issuance.json()["id"])

    async def expire_final_claim() -> None:
        async with postgis_db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            row.status = "processing"
            row.worker_attempts = 3
            row.processing_token = uuid4()
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_final_claim())
    storage = ReportStorage()

    async def run_concurrent_sweeps() -> list[int]:
        context = {
            "sessionmaker": postgis_db_sessionmaker,
            "settings": settings,
            "storage": storage,
        }
        return list(
            await asyncio.gather(
                sweep_report_issuances(context),
                sweep_report_issuances(context),
            )
        )

    assert asyncio.run(run_concurrent_sweeps()) == [0, 0]

    async def terminal_state() -> tuple[ReportIssuance, list[AuditEvent]]:
        async with postgis_db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "report_issuance",
                        AuditEvent.entity_id == str(issuance_id),
                        AuditEvent.action == "report_issuance.failed",
                    )
                )
            )
            return row, events

    failed, terminal_events = asyncio.run(terminal_state())
    assert failed.status == "failed"
    assert failed.worker_attempts == 3
    assert failed.processing_token is None
    assert failed.lease_expires_at is None
    assert failed.last_error_code == "worker_lease_expired"
    assert [event.event_metadata for event in terminal_events] == [
        {"attempt": 3, "error_code": "worker_lease_expired"}
    ]


@pytest.fixture
def deterministic_render(monkeypatch):
    """Isolate R51 publication mechanics from the SQLite timezone-naive renderer limit."""

    def csv(snapshot) -> bytes:
        return f"section,label\nissuance,{snapshot['issuance']['id']}\n".encode()

    def pdf(snapshot) -> bytes:
        return b"%PDF-1.4 " + str(snapshot["issuance"]["id"]).encode()

    monkeypatch.setattr(report_issuance_service, "render_report_csv", csv)
    monkeypatch.setattr(report_issuance_service, "render_report_pdf", pdf)


async def read_generations(sessionmaker, issuance_id) -> list[ReportPublicationIntent]:
    async with sessionmaker() as session:
        return list(
            await session.scalars(
                select(ReportPublicationIntent)
                .where(ReportPublicationIntent.report_issuance_id == issuance_id)
                .order_by(ReportPublicationIntent.generation)
            )
        )


def generations(db_sessionmaker, issuance_id) -> list[ReportPublicationIntent]:
    return asyncio.run(read_generations(db_sessionmaker, issuance_id))


def artifact_count(db_sessionmaker) -> int:
    async def count() -> int:
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count()).select_from(ReportArtifact)) or 0)

    return asyncio.run(count())


def make_due(db_sessionmaker, issuance_id) -> None:
    async def due() -> None:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(due())


def test_crash_after_first_object_write_leaves_no_unregistered_orphan(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    report_storage.fail_pdf_once = True

    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    assert len(report_storage.objects) == 1
    assert artifact_count(db_sessionmaker) == 0

    crashed = generations(db_sessionmaker, issuance_id)
    assert [intent.generation for intent in crashed] == [1]
    assert crashed[0].state == ReportPublicationState.ABANDONED
    orphan_keys = {crashed[0].csv_object_key, crashed[0].pdf_object_key}
    assert set(report_storage.objects) <= orphan_keys

    run_worker(db_sessionmaker, settings, report_storage)
    assert report_storage.objects == {}
    assert sorted(report_storage.deleted) == sorted(orphan_keys)
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED

    # The tombstone is idempotent: a repeated cleanup claims and deletes nothing more.
    assert run_publication_cleanup(db_sessionmaker, settings, report_storage) == 0
    assert sorted(report_storage.deleted) == sorted(orphan_keys)


def test_retry_publishes_under_a_new_generation_and_new_keys(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    report_storage.fail_pdf_once = True
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    make_due(db_sessionmaker, issuance_id)
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    first, second = generations(db_sessionmaker, issuance_id)
    assert (first.generation, second.generation) == (1, 2)
    assert first.state == ReportPublicationState.CLEANED
    assert second.state == ReportPublicationState.COMPLETE
    assert {first.csv_object_key, first.pdf_object_key}.isdisjoint(
        {second.csv_object_key, second.pdf_object_key}
    )
    # The published key carries its intent, generation and content hash.
    assert f"/{second.id}/g2/" in second.csv_object_key
    assert second.csv_object_key.endswith(
        f"{hashlib.sha256(report_storage.contents[second.csv_object_key]).hexdigest()}.csv"
    )
    assert set(report_storage.objects) == {second.csv_object_key, second.pdf_object_key}

    async def stored_keys() -> set[str]:
        async with db_sessionmaker() as session:
            return set(
                await session.scalars(
                    select(StoredFile.storage_key).where(
                        StoredFile.purpose == "report_export",
                    )
                )
            )

    assert asyncio.run(stored_keys()) == {second.csv_object_key, second.pdf_object_key}


def test_expired_publisher_cannot_publish_and_its_objects_are_reclaimed(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    async def expire_publication_lease(object_key: str) -> None:
        if not object_key.endswith(".pdf"):
            return
        async with db_sessionmaker() as session:
            intent = await session.scalar(
                select(ReportPublicationIntent).where(
                    ReportPublicationIntent.report_issuance_id == issuance_id
                )
            )
            assert intent is not None
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    report_storage.after_put = expire_publication_lease
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    report_storage.after_put = None

    assert artifact_count(db_sessionmaker) == 0
    expired = generations(db_sessionmaker, issuance_id)[0]
    assert expired.state == ReportPublicationState.ABANDONED
    assert expired.last_error_code == "REPORT_PUBLICATION_LOST"

    async def issuance_state() -> tuple[str, str | None]:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            return row.status, row.last_error_code

    assert asyncio.run(issuance_state()) == ("queued", "REPORT_PUBLICATION_LOST")

    written = {expired.csv_object_key, expired.pdf_object_key}
    assert set(report_storage.objects) == written
    run_worker(db_sessionmaker, settings, report_storage)
    assert report_storage.objects == {}
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED


def test_abandoned_publisher_stops_before_writing_the_rest_of_the_pair(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    async def abandon_after_first_object(object_key: str) -> None:
        if not object_key.endswith(".csv"):
            return
        async with db_sessionmaker() as session:
            intent = await session.scalar(
                select(ReportPublicationIntent).where(
                    ReportPublicationIntent.report_issuance_id == issuance_id
                )
            )
            assert intent is not None
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    report_storage.after_put = abandon_after_first_object
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    report_storage.after_put = None

    # The publisher noticed it lost the fence and never wrote the second object.
    assert len(report_storage.objects) == 1
    assert artifact_count(db_sessionmaker) == 0
    stopped = generations(db_sessionmaker, issuance_id)[0]
    assert stopped.state == ReportPublicationState.ABANDONED
    assert next(iter(report_storage.objects)) == stopped.csv_object_key

    run_worker(db_sessionmaker, settings, report_storage)
    assert report_storage.objects == {}
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED


def test_processing_lease_lapses_exactly_at_its_instant_without_sleeping(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render, monkeypatch
) -> None:
    """TST-008: the reclaim boundary is pinned with an injected clock, not waited out.

    A sleeping test can only show that a lease expires *eventually*. Freezing the
    worker's database clock shows the exact instant it lapses: one microsecond
    earlier the holder still owns the issuance, and at the instant itself the
    sweep reclaims it.
    """
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    lease_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    async def strand_a_processing_lease() -> None:
        async with db_sessionmaker() as session:
            issuance = await session.get(ReportIssuance, issuance_id)
            assert issuance is not None
            issuance.status = ReportIssuanceStatus.PROCESSING
            issuance.processing_token = uuid4()
            issuance.lease_expires_at = lease_at
            issuance.next_attempt_at = None
            await session.commit()

    asyncio.run(strand_a_processing_lease())

    real_clock = report_issuance_service.database_clock

    def sweep_at(instant: datetime) -> int:
        async def frozen(session) -> datetime:
            return instant

        monkeypatch.setattr(report_issuance_service, "database_clock", frozen)
        try:
            return run_worker(db_sessionmaker, settings, report_storage)
        finally:
            # Restore only this patch: monkeypatch.undo() would also revert
            # deterministic_render.
            monkeypatch.setattr(report_issuance_service, "database_clock", real_clock)

    assert sweep_at(lease_at - timedelta(microseconds=1)) == 0
    assert asyncio.run(read_generations(db_sessionmaker, issuance_id)) == []

    assert sweep_at(lease_at) == 1
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.COMPLETE


def test_hard_crash_mid_publication_is_recovered_by_the_expired_generation_sweep(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render, monkeypatch
) -> None:
    """REP-006 requires recovery on DB rollback, not only on a caught exception.

    A SIGKILL, an OOM, or an IntegrityError at the finalize commit leaves a PUBLISHING
    generation with both objects written and no chance to run any except block. Only the
    expired-generation sweep can recover it.
    """
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    class Crash(BaseException):
        """Not an Exception: nothing in the publisher may catch it."""

    async def crash_before_finalizing(*args, **kwargs):
        raise Crash

    publish = report_issuance_service._complete_publication
    monkeypatch.setattr(report_issuance_service, "_complete_publication", crash_before_finalizing)
    with pytest.raises(Crash):
        run_worker(db_sessionmaker, settings, report_storage)
    # Restore only this patch: monkeypatch.undo() would also revert deterministic_render.
    monkeypatch.setattr(report_issuance_service, "_complete_publication", publish)

    stranded = generations(db_sessionmaker, issuance_id)[0]
    assert stranded.state == ReportPublicationState.PUBLISHING
    written = {stranded.csv_object_key, stranded.pdf_object_key}
    assert set(report_storage.objects) == written
    assert artifact_count(db_sessionmaker) == 0

    async def expire_publication_lease() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(ReportPublicationIntent, stranded.id)
            assert intent is not None
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_publication_lease())

    # One sweep retires the stranded generation and destroys its registered objects.
    assert run_publication_cleanup(db_sessionmaker, settings, report_storage) == 1

    recovered = generations(db_sessionmaker, issuance_id)[0]
    assert recovered.state == ReportPublicationState.CLEANED
    assert recovered.last_error_code is None
    assert report_storage.objects == {}
    assert sorted(report_storage.deleted) == sorted(written)

    async def abandon_reason() -> list[str]:
        async with db_sessionmaker() as session:
            return [
                event.event_metadata["error_code"]
                for event in await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "report_publication.abandoned",
                        AuditEvent.entity_id == str(issuance_id),
                    )
                )
            ]

    assert asyncio.run(abandon_reason()) == ["publication_lease_expired"]


def test_reclaiming_an_issuance_supersedes_its_still_leased_generation(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render, monkeypatch
) -> None:
    """The issuance claim is the outer authority, so correctness never rests on lease maths.

    The publication lease is taken after the issuance lease and therefore outlives it. A
    reclaimed issuance must still be able to register a fresh generation.
    """
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    class Crash(BaseException):
        pass

    async def crash_before_finalizing(*args, **kwargs):
        raise Crash

    publish = report_issuance_service._complete_publication
    monkeypatch.setattr(report_issuance_service, "_complete_publication", crash_before_finalizing)
    with pytest.raises(Crash):
        run_worker(db_sessionmaker, settings, report_storage)
    # Restore only this patch: monkeypatch.undo() would also revert deterministic_render.
    monkeypatch.setattr(report_issuance_service, "_complete_publication", publish)

    stranded = generations(db_sessionmaker, issuance_id)[0]
    assert stranded.state == ReportPublicationState.PUBLISHING
    assert stranded.lease_expires_at is not None

    # Expire only the ISSUANCE lease. The publication lease is still valid.
    async def expire_issuance_lease() -> None:
        async with db_sessionmaker() as session:
            row = await session.get(ReportIssuance, issuance_id)
            assert row is not None
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_issuance_lease())
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    first, second = generations(db_sessionmaker, issuance_id)
    assert first.last_error_code == "publication_claim_superseded"
    assert second.generation == 2
    assert second.state == ReportPublicationState.COMPLETE
    assert artifact_count(db_sessionmaker) == 2

    run_worker(db_sessionmaker, settings, report_storage)
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED
    assert set(report_storage.objects) == {second.csv_object_key, second.pdf_object_key}


def test_finalize_rejects_a_corrupt_object_and_registers_no_partial_pair(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    async def corrupt_csv_after_pair(object_key: str) -> None:
        if not object_key.endswith(".pdf"):
            return
        csv_key = next(key for key in report_storage.objects if key.endswith(".csv"))
        existing = report_storage.objects[csv_key]
        report_storage.objects[csv_key] = existing.__class__(
            object_key=csv_key,
            size_bytes=existing.size_bytes,
            content_type=existing.content_type,
            checksum_sha256="c" * 64,
        )

    report_storage.after_put = corrupt_csv_after_pair
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    report_storage.after_put = None

    assert artifact_count(db_sessionmaker) == 0
    corrupted = generations(db_sessionmaker, issuance_id)[0]
    assert corrupted.state == ReportPublicationState.ABANDONED
    assert corrupted.last_error_code == "stored_object_conflict"


def test_finalize_rejects_a_missing_half_of_the_object_pair(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])

    async def drop_csv_after_pair(object_key: str) -> None:
        if not object_key.endswith(".pdf"):
            return
        csv_key = next(key for key in report_storage.objects if key.endswith(".csv"))
        report_storage.objects.pop(csv_key)
        report_storage.contents.pop(csv_key, None)

    report_storage.after_put = drop_csv_after_pair
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    report_storage.after_put = None

    assert artifact_count(db_sessionmaker) == 0
    dropped = generations(db_sessionmaker, issuance_id)[0]
    assert dropped.state == ReportPublicationState.ABANDONED
    # A vanished registered object is a configuration condition, never a transient outage.
    assert dropped.last_error_code == "stored_object_conflict"


def test_a_surviving_object_is_never_recorded_as_a_cleaned_tombstone(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    """CLEANED is terminal, so it must never be written over an object that still exists."""
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    report_storage.fail_pdf_once = True
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    abandoned = generations(db_sessionmaker, issuance_id)[0]
    assert abandoned.state == ReportPublicationState.ABANDONED
    surviving = dict(report_storage.objects)
    assert surviving

    report_storage.ignore_deletes = True
    assert run_publication_cleanup(db_sessionmaker, settings, report_storage) == 0

    stuck = generations(db_sessionmaker, issuance_id)[0]
    assert stuck.state == ReportPublicationState.ABANDONED
    assert stuck.last_error_code == "publication_object_resurrected"
    assert report_storage.objects == surviving

    async def cleaned_events() -> int:
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "report_publication.cleaned")
                )
                or 0
            )

    assert asyncio.run(cleaned_events()) == 0

    # Once the provider really deletes, the next sweep completes the tombstone.
    report_storage.ignore_deletes = False
    assert run_publication_cleanup(db_sessionmaker, settings, report_storage) == 1
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED
    assert report_storage.objects == {}
    assert asyncio.run(cleaned_events()) == 1


def test_a_crashed_cleanup_worker_releases_its_claim_for_the_next_sweep(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    """A worker killed while holding a CLEANING claim must not strand the generation."""
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    report_storage.fail_pdf_once = True
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    abandoned = generations(db_sessionmaker, issuance_id)[0]
    registered = {abandoned.csv_object_key, abandoned.pdf_object_key}

    async def strand_as_expired_cleaning() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(ReportPublicationIntent, abandoned.id)
            assert intent is not None
            intent.state = ReportPublicationState.CLEANING
            intent.publisher_token = uuid4()
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(strand_as_expired_cleaning())

    # One sweep releases the dead claim and then completes the cleanup.
    assert run_publication_cleanup(db_sessionmaker, settings, report_storage) == 1
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.CLEANED
    assert report_storage.objects == {}
    assert set(report_storage.deleted) <= registered

    async def released_reason() -> list[str]:
        async with db_sessionmaker() as session:
            return [
                event.event_metadata["error_code"]
                for event in await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "report_publication.abandoned",
                        AuditEvent.entity_id == str(issuance_id),
                    )
                )
            ]

    assert "publication_cleanup_lease_expired" in asyncio.run(released_reason())


def test_cleanup_spares_published_generations_and_unregistered_objects(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    assert run_worker(db_sessionmaker, settings, report_storage) == 1

    published = generations(db_sessionmaker, issuance_id)[0]
    assert published.state == ReportPublicationState.COMPLETE
    published_keys = {published.csv_object_key, published.pdf_object_key}

    unrelated_key = "managed/unrelated/reports/keep-me.csv"
    asyncio.run(
        report_storage.put(
            object_key=unrelated_key,
            content_type="text/csv",
            data=b"unrelated",
            checksum_sha256=hashlib.sha256(b"unrelated").hexdigest(),
        )
    )

    for _ in range(3):
        run_worker(db_sessionmaker, settings, report_storage)

    assert report_storage.deleted == []
    assert set(report_storage.objects) == published_keys | {unrelated_key}
    assert generations(db_sessionmaker, issuance_id)[0].state == ReportPublicationState.COMPLETE
    assert artifact_count(db_sessionmaker) == 2


def test_publication_generation_fences_are_enforced_by_the_database(
    db_client, db_sessionmaker, settings, report_storage, deterministic_render
) -> None:
    _, advertiser, _, run = issue_run(db_client, db_sessionmaker)
    issuance_id = UUID(request_issuance(db_client, advertiser, run["id"]).json()["id"])
    assert run_worker(db_sessionmaker, settings, report_storage) == 1
    published = generations(db_sessionmaker, issuance_id)[0]

    def live_intent(generation: int) -> ReportPublicationIntent:
        return ReportPublicationIntent(
            report_issuance_id=issuance_id,
            generation=generation,
            state=ReportPublicationState.PREPARED,
            csv_object_key=f"managed/fence/{generation}.csv",
            pdf_object_key=f"managed/fence/{generation}.pdf",
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )

    async def two_live_generations() -> None:
        async with db_sessionmaker() as session:
            session.add(live_intent(10))
            session.add(live_intent(11))
            await session.commit()

    with pytest.raises(IntegrityError):
        asyncio.run(two_live_generations())

    async def tombstone_cannot_be_published() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(ReportPublicationIntent, published.id)
            assert intent is not None
            intent.state = ReportPublicationState.CLEANED
            await session.commit()

    with pytest.raises(ValueError, match="state transition is invalid"):
        asyncio.run(tombstone_cannot_be_published())

    async def identity_is_immutable() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(ReportPublicationIntent, published.id)
            assert intent is not None
            intent.csv_object_key = "managed/rewritten.csv"
            await session.commit()

    with pytest.raises(ValueError, match="identity is immutable"):
        asyncio.run(identity_is_immutable())

    async def generations_are_append_only() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(ReportPublicationIntent, published.id)
            assert intent is not None
            await session.delete(intent)
            await session.commit()

    with pytest.raises(ValueError, match="append-only"):
        asyncio.run(generations_are_append_only())


def test_concurrent_sweeps_never_double_publish_or_delete_a_live_generation_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    """Two sweeps racing one queued issuance publish one pair and delete nothing.

    The one-live-generation fence itself is proven by the database in
    test_publication_generation_fences_are_enforced_by_the_database and in the 0082
    migration test; this covers the sweep-level outcome under real row locking.
    """
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance_id = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    storage = ReportStorage()

    async def race() -> list[int]:
        context = {
            "sessionmaker": postgis_db_sessionmaker,
            "settings": settings,
            "storage": storage,
        }
        return list(
            await asyncio.gather(
                sweep_report_issuances(context),
                sweep_report_issuances(context),
            )
        )

    assert sorted(asyncio.run(race())) == [0, 1]

    published = generations(postgis_db_sessionmaker, issuance_id)
    assert [intent.state for intent in published] == [ReportPublicationState.COMPLETE]
    assert artifact_count(postgis_db_sessionmaker) == 2
    assert set(storage.objects) == {
        published[0].csv_object_key,
        published[0].pdf_object_key,
    }
    assert storage.deleted == []


def test_concurrent_cleanup_sweeps_reclaim_an_abandoned_generation_once_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance_id = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    storage = ReportStorage()
    storage.fail_pdf_once = True
    assert run_worker(postgis_db_sessionmaker, settings, storage) == 1

    abandoned = generations(postgis_db_sessionmaker, issuance_id)[0]
    assert abandoned.state == ReportPublicationState.ABANDONED
    registered = {abandoned.csv_object_key, abandoned.pdf_object_key}

    async def race() -> list[int]:
        return list(
            await asyncio.gather(
                sweep_report_publications(
                    postgis_db_sessionmaker, storage=storage, settings=settings
                ),
                sweep_report_publications(
                    postgis_db_sessionmaker, storage=storage, settings=settings
                ),
            )
        )

    # A generation another worker already holds must be skipped, not waited on. Without
    # skip_locked this sweep would block on the held row until the holder commits.
    async def sweep_while_another_worker_holds_the_row() -> int:
        async with postgis_db_sessionmaker() as holder:
            held = await holder.scalar(
                select(ReportPublicationIntent)
                .where(ReportPublicationIntent.id == abandoned.id)
                .with_for_update()
            )
            assert held is not None
            try:
                return await asyncio.wait_for(
                    sweep_report_publications(
                        postgis_db_sessionmaker, storage=storage, settings=settings
                    ),
                    timeout=5,
                )
            finally:
                await holder.rollback()

    assert asyncio.run(sweep_while_another_worker_holds_the_row()) == 0
    assert generations(postgis_db_sessionmaker, issuance_id)[0].state == (
        ReportPublicationState.ABANDONED
    )
    assert storage.deleted == []

    assert sorted(asyncio.run(race())) == [0, 1]
    assert generations(postgis_db_sessionmaker, issuance_id)[0].state == (
        ReportPublicationState.CLEANED
    )
    assert storage.objects == {}
    assert set(storage.deleted) <= registered

    async def cleaned_events() -> list[dict]:
        async with postgis_db_sessionmaker() as session:
            return [
                event.event_metadata
                for event in await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "report_publication.cleaned",
                        AuditEvent.entity_id == str(issuance_id),
                    )
                )
            ]

    assert asyncio.run(cleaned_events()) == [{"generation": 1, "object_count": 2}]


def test_cleanup_never_claims_a_live_generation_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance_id = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    storage = ReportStorage()

    class Crash(BaseException):
        pass

    async def crash_before_finalizing(*args, **kwargs):
        raise Crash

    publish = report_issuance_service._complete_publication
    monkeypatch.setattr(report_issuance_service, "_complete_publication", crash_before_finalizing)
    with pytest.raises(Crash):
        run_worker(postgis_db_sessionmaker, settings, storage)
    monkeypatch.setattr(report_issuance_service, "_complete_publication", publish)

    live = generations(postgis_db_sessionmaker, issuance_id)[0]
    assert live.state == ReportPublicationState.PUBLISHING
    written = {live.csv_object_key, live.pdf_object_key}
    assert set(storage.objects) == written

    # Its publication lease is still valid, so cleanup must leave it and its objects alone.
    for _ in range(3):
        assert run_publication_cleanup(postgis_db_sessionmaker, settings, storage) == 0
    assert generations(postgis_db_sessionmaker, issuance_id)[0].state == (
        ReportPublicationState.PUBLISHING
    )
    assert storage.deleted == []
    assert set(storage.objects) == written


def test_crashed_publication_is_reclaimed_and_reissued_end_to_end_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    """Full recovery against real PostgreSQL and the real renderer, no stubs."""
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance_id = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    storage = ReportStorage()

    class Crash(BaseException):
        pass

    async def crash_before_finalizing(*args, **kwargs):
        raise Crash

    publish = report_issuance_service._complete_publication
    monkeypatch.setattr(report_issuance_service, "_complete_publication", crash_before_finalizing)
    with pytest.raises(Crash):
        run_worker(postgis_db_sessionmaker, settings, storage)
    monkeypatch.setattr(report_issuance_service, "_complete_publication", publish)

    stranded = generations(postgis_db_sessionmaker, issuance_id)[0]
    orphans = {stranded.csv_object_key, stranded.pdf_object_key}

    async def expire_both_leases() -> None:
        async with postgis_db_sessionmaker() as session:
            issuance = await session.get(ReportIssuance, issuance_id)
            assert issuance is not None
            issuance.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            intent = await session.get(ReportPublicationIntent, stranded.id)
            assert intent is not None
            intent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_both_leases())

    # One sweep reclaims the issuance, destroys the orphaned generation and republishes.
    assert run_worker(postgis_db_sessionmaker, settings, storage) == 1

    first, second = generations(postgis_db_sessionmaker, issuance_id)
    assert first.state == ReportPublicationState.CLEANED
    assert second.state == ReportPublicationState.COMPLETE
    assert orphans.isdisjoint({second.csv_object_key, second.pdf_object_key})
    assert set(storage.objects) == {second.csv_object_key, second.pdf_object_key}
    assert sorted(storage.deleted) == sorted(orphans)
    assert artifact_count(postgis_db_sessionmaker) == 2

    # The surviving objects are the real rendered report, downloadable by its owner.
    csv_bytes = storage.contents[second.csv_object_key]
    assert csv_bytes.startswith(b"section,")
    assert storage.contents[second.pdf_object_key].startswith(b"%PDF-1.4")
    ready = postgis_db_client.get(
        f"/api/v1/advertiser/report-issuances/{issuance_id}",
        headers=auth_headers(postgis_db_client, advertiser.email, PASSWORD),
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready"
    assert [item["format"] for item in ready.json()["artifacts"]] == ["csv", "pdf"]
