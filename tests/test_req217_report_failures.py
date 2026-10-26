"""D118: missing evidence and a broken campaign never become false results."""

import asyncio
import hashlib
import importlib.util
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import auth_headers, create_test_campaign_creative, create_test_campaign_zone
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_heatmaps import add_ping_batch
from test_req217_reports import PASSWORD, driving_trip, owner_graph
from test_stored_files import FakeStorageProvider

from app.adapters.storage import ObjectMetadata, StorageUnavailable
from app.api.v1.dependencies import get_storage_provider
from app.models.audit import AuditEvent
from app.models.campaign import CampaignCreative, CreativeStatus
from app.models.campaign_report import CampaignReport
from app.models.report_issuance import ReportArtifact
from app.models.stored_file import FileUploadIntent, StoredFile
from app.models.user import User
from app.services.campaign_report_data import _areas
from app.services.campaign_report_delivery import (
    _claim,
    _failed,
    _pair,
    _put_pair,
    _ready,
    publish_campaign_report,
)
from app.services.campaign_report_rendering import render_campaign_csv
from app.services.report_authorization import (
    REPORT_ACTOR_EMAIL,
    REPORT_ACTOR_ID,
    REPORT_ACTOR_NAME,
    REPORT_ACTOR_PASSWORD,
)
from app.services.report_cohorts import select_report_cohort


@pytest.mark.parametrize("gps", ["missing", "partial", "outside", "inside"])
def test_area_zero_requires_complete_retained_gps(db_sessionmaker, settings, gps):
    owner, _, campaign = owner_graph(db_sessionmaker, f"area-{gps}")
    create_test_campaign_zone(db_sessionmaker, campaign_id=campaign.id, created_by_user_id=owner.id)
    end = datetime(2020, 1, 2, 10, tzinfo=UTC)
    for index in range(3):
        trip = driving_trip(
            db_sessionmaker, campaign=campaign, suffix=f"{gps}-{index}", ended_at=end
        )
        if gps != "missing":
            lat, lon = (6.50, 3.40) if gps == "inside" else (8.05, 5.05)
            points = [(trip.started_at + timedelta(minutes=5), lat, lon)]
            if gps != "partial":
                points.append((trip.started_at + timedelta(minutes=6), lat, lon))
            add_ping_batch(
                db_sessionmaker,
                trip_id=trip.id,
                points=points,
                idempotency_key=f"area-source-{index}",
            )

    async def exercise():
        async with db_sessionmaker() as session:
            cohort = await select_report_cohort(
                session,
                campaign_id=campaign.id,
                start_at=end - timedelta(days=1),
                end_at=end + timedelta(hours=1),
                terminal_period=True,
                include_money=False,
                settings=settings,
            )
            result = await _areas(
                session,
                campaign=campaign,
                cohort=cohort,
                driving=list(cohort.analytics),
                settings=settings,
                unknown=False,
            )
            assert len(result) == 1
            expected = None if gps in {"missing", "partial"} else (3 if gps == "inside" else 0)
            assert result[0]["vehicle_count"] == result[0]["trip_count"] == expected
            expected_views = (
                None if expected is None else ("75.0000" if gps == "inside" else "0.0000")
            )
            assert result[0]["estimated_views"] == expected_views

    asyncio.run(exercise())


def test_scheduler_failure_isolated_from_other_company_and_expired_hint_recovery(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
):
    import app.services.campaign_reports as reports
    from app.services.report_scheduling import sweep_scheduled_reports

    broken_owner, _, broken = owner_graph(db_sessionmaker, "broken-schedule")
    _, _, healthy = owner_graph(db_sessionmaker, "healthy-schedule")
    response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=auth_headers(db_client, broken_owner.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
            "campaign_id": str(broken.id),
        },
    )
    assert response.status_code == 202, response.text
    expired_id = UUID(response.json()["id"])
    original = reports.build_report_snapshot

    async def unavailable(*args, **kwargs):
        if kwargs["campaigns"][0].id == broken.id:
            raise StorageUnavailable("synthetic unavailable artwork")
        return await original(*args, **kwargs)

    monkeypatch.setattr(reports, "build_report_snapshot", unavailable)
    recovered = []

    def hint(session, kind, identity):
        recovered.append((kind, identity))
        session.info.setdefault("outbox_jobs", set()).add((kind, identity))

    monkeypatch.setattr("app.services.report_scheduling.pending_job", hint)

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(
                User(
                    id=REPORT_ACTOR_ID,
                    email=REPORT_ACTOR_EMAIL,
                    full_name=REPORT_ACTOR_NAME,
                    password_hash=REPORT_ACTOR_PASSWORD,
                    role="admin",
                    status="disabled",
                )
            )
            expired = await session.get(CampaignReport, expired_id)
            expired.processing_token = uuid4()
            expired.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        assert (
            await sweep_scheduled_reports(
                {
                    "sessionmaker": db_sessionmaker,
                    "settings": settings,
                    "storage": FakeStorageProvider(),
                }
            )
            == 1
        )
        assert ("generate_campaign_report", expired_id) in recovered
        async with db_sessionmaker() as session:
            rows = list(await session.scalars(select(CampaignReport)))
            assert any(row.campaign_id == healthy.id and row.kind == "weekly" for row in rows)
            assert not any(row.campaign_id == broken.id and row.kind == "weekly" for row in rows)
            failure = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "campaign_report.preparation_failed")
            )
            assert failure is not None and failure.entity_id == str(broken.id)
            assert "synthetic unavailable artwork" not in str(failure.event_metadata)

    asyncio.run(exercise())


def test_expired_publisher_cannot_finalize_and_retry_adopts_exact_keys(
    db_client,
    db_sessionmaker,
    monkeypatch,
):
    owner, _, campaign = owner_graph(db_sessionmaker, "expired-publisher")
    response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=auth_headers(db_client, owner.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
            "campaign_id": str(campaign.id),
        },
    )
    assert response.status_code == 202, response.text
    identity = UUID(response.json()["id"])
    storage = FakeStorageProvider()

    async def exercise():
        report, token = await _claim(db_sessionmaker, identity)
        pair = _pair(report)
        await _put_pair(storage, pair)
        async with db_sessionmaker() as session:
            row = await session.get(CampaignReport, identity)
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        frozen = dict(storage.contents)
        assert (
            await _failed(
                db_sessionmaker,
                report_id=identity,
                token=token,
                error=StorageUnavailable("expired callback"),
            )
            == "skipped"
        )
        assert (
            await _ready(
                db_sessionmaker, report_id=identity, token=token, artifacts=pair, storage=storage
            )
            == "skipped"
        )
        async with db_sessionmaker() as session:
            assert not list(await session.scalars(select(ReportArtifact)))
            row = await session.get(CampaignReport, identity)
            assert row.status == "queued" and row.processing_token == token

        # Expiry while verifying storage cannot use an earlier clock reading.
        _, fresh_token = await _claim(db_sessionmaker, identity)
        clock_reads = iter([datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=5)])

        async def verification_clock(_session):
            return next(clock_reads)

        with monkeypatch.context() as patch:
            patch.setattr(
                "app.services.campaign_report_delivery.database_clock", verification_clock
            )
            assert (
                await _ready(
                    db_sessionmaker,
                    report_id=identity,
                    token=fresh_token,
                    artifacts=pair,
                    storage=storage,
                )
                == "skipped"
            )
        async with db_sessionmaker() as session:
            assert not list(await session.scalars(select(ReportArtifact)))
            row = await session.get(CampaignReport, identity)
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=identity, storage=storage)
            == "ready"
        )
        assert frozen == storage.contents
        async with db_sessionmaker() as session:
            # This fixture creates metadata in its own PostgreSQL schema.
            # Install the migration's real guard before testing raw SQL bypasses.
            def install_guard(connection):
                spec = importlib.util.spec_from_file_location(
                    "campaign_report_migration", Path("alembic/versions/0116_campaign_reports.py")
                )
                revision = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(revision)
                with Operations.context(MigrationContext.configure(connection)):
                    revision.install_immutable_guard()

            connection = await session.connection()
            await connection.run_sync(install_guard)
            await session.commit()
            with pytest.raises(DBAPIError, match="immutable"):
                await session.execute(
                    text("UPDATE campaign_reports SET snapshot='{}'::jsonb WHERE id=:id"),
                    {"id": identity},
                )
            await session.rollback()
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(
                    text("DELETE FROM campaign_reports WHERE id=:id"), {"id": identity}
                )
            await session.rollback()

    asyncio.run(exercise())


@pytest.mark.parametrize("limit", ["count", "bytes", "pixels"])
def test_report_artwork_work_is_bounded_before_more_decodes(
    db_client, db_sessionmaker, monkeypatch, limit
):
    owner, _, campaign = owner_graph(db_sessionmaker, f"artwork-budget-{limit}")
    image = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(image, format="PNG")
    data = image.getvalue()
    checksum = hashlib.sha256(data).hexdigest()
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
        checksum=checksum,
    )

    class CountReads(FakeStorageProvider):
        reads = 0

        async def stream(self, key):
            self.reads += 1
            yield data

    storage = CountReads()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage

    async def seed():
        async with db_sessionmaker() as session:
            file = await session.get(StoredFile, creative.stored_file_id)
            file.size_bytes = len(data)
            for index in range(64 if limit == "count" else 1):
                intent = FileUploadIntent(
                    organization_id=campaign.organization_id,
                    uploader_user_id=owner.id,
                    client_request_id=uuid4(),
                    request_fingerprint=checksum,
                    purpose="creative",
                    original_filename="preview.png",
                    declared_content_type="image/png",
                    declared_size_bytes=len(data),
                    declared_sha256=checksum,
                    object_key=f"budget-intent/{uuid4()}",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    status="confirmed",
                )
                session.add(intent)
                await session.flush()
                extra_file = StoredFile(
                    id=uuid4(),
                    upload_intent_id=intent.id,
                    organization_id=campaign.organization_id,
                    uploader_user_id=owner.id,
                    purpose="creative",
                    original_filename="preview.png",
                    storage_key=f"budget-test/{uuid4()}",
                    content_type="image/png",
                    actual_content_type="image/png",
                    size_bytes=len(data),
                    checksum_sha256=checksum,
                    scan_status="clean",
                    scan_attempts=1,
                    scanned_at=datetime.now(UTC),
                )
                session.add(extra_file)
                await session.flush()
                session.add(
                    CampaignCreative(
                        campaign_id=campaign.id,
                        name=f"Extra {index}",
                        creative_type="image",
                        placement="vehicle_exterior",
                        status="approved",
                        stored_file_id=extra_file.id,
                        mime_type="image/png",
                        checksum=checksum,
                    )
                )
            await session.commit()

    asyncio.run(seed())
    if limit == "bytes":
        monkeypatch.setattr("app.services.campaign_report_data.MAX_ARTWORK_SOURCE_BYTES", len(data))
    if limit == "pixels":
        monkeypatch.setattr("app.services.campaign_report_data.MAX_ARTWORK_PIXELS", 150)
    response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=auth_headers(db_client, owner.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "campaign_id": str(campaign.id),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REPORT_TOO_LARGE"
    assert storage.reads == (2 if limit == "pixels" else 0)

    async def no_partial_report():
        async with db_sessionmaker() as session:
            assert not list(await session.scalars(select(CampaignReport)))

    asyncio.run(no_partial_report())


@pytest.mark.parametrize("origin", ["", "https://cardvert.example.test"])
def test_pdf_artwork_reference_is_file_specific_owned_and_scan_gated(
    db_client, db_sessionmaker, settings, monkeypatch, origin
):
    owner, _, campaign = owner_graph(db_sessionmaker, f"pdf-reference-{bool(origin)}")
    other, _, _ = owner_graph(db_sessionmaker, f"pdf-other-{bool(origin)}")
    monkeypatch.setattr(settings, "public_origin", origin)
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_type="pdf",
        mime_type="application/pdf",
        creative_status=CreativeStatus.APPROVED,
    )
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage

    async def file_metadata():
        async with db_sessionmaker() as session:
            return await session.get(StoredFile, creative.stored_file_id)

    file = asyncio.run(file_metadata())
    storage.objects[file.storage_key] = ObjectMetadata(
        file.storage_key, file.size_bytes, file.content_type, file.checksum_sha256
    )
    headers = auth_headers(db_client, owner.email, PASSWORD)
    requested = db_client.post(
        "/api/v1/advertiser/reports",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "campaign_id": str(campaign.id),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
        },
    )
    assert requested.status_code == 202, requested.text
    expected = f"{origin}/api/advertiser/reports/artwork/{file.id}"

    async def frozen_reference():
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, requested.json()["id"])
            reference = report.snapshot["campaigns"][0]["creatives"][0]
            assert reference["content_type"] == "application/pdf"
            assert reference["preview_base64"] is None
            assert reference["preview_path"] == expected
            csv_text = render_campaign_csv(report.snapshot).decode("utf-8-sig")
            assert ("Preview link" if origin else "Preview app path") in csv_text
            assert expected in csv_text

    asyncio.run(frozen_reference())
    path = f"/api/v1/advertiser/files/{file.id}/download"
    body = {"purpose": "campaign_preview", "reason": "Report artwork preview"}
    assert db_client.post(path, headers=headers, json=body).status_code == 200
    assert (
        db_client.post(
            path, headers=auth_headers(db_client, other.email, PASSWORD), json=body
        ).status_code
        == 404
    )

    async def pending():
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, file.id)
            stored.scan_status = "pending"
            await session.commit()

    asyncio.run(pending())
    denied = db_client.post(path, headers=headers, json=body)
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "STORED_FILE_NOT_CLEARED"
