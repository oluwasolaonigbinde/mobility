import asyncio
from uuid import uuid4

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_creative,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select
from test_driver_applications import enable_registration
from test_kyc import NIN, PASSWORD, _payload, _seed_driver_authority
from test_measurement_runs import create_measurement_graph, issue_payload
from test_stored_files import FakeStorageProvider

from app.adapters.storage import ObjectMetadata
from app.api.v1.dependencies import get_storage_provider
from app.models.audit import AuditEvent
from app.models.driver_application import DriverApplication, DriverApplicationStatus
from app.models.stored_file import FileScanStatus, FileUploadIntent, StoredFile
from app.models.user import User


def test_campaign_artwork_discovery_requires_existing_parent_and_preserves_pagination(
    db_client, db_sessionmaker
):
    admin = create_test_user(db_sessionmaker, email="artwork-ops@example.test", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker, email="artwork-owner@example.test", role="advertiser", password=PASSWORD
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=advertiser.id
    )
    other = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=advertiser.id
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    path = f"/api/v1/admin/campaigns/{campaign.id}/creatives"
    missing = db_client.get(f"/api/v1/admin/campaigns/{uuid4()}/creatives", headers=headers)
    assert missing.status_code == 404
    empty = db_client.get(path, headers=headers)
    assert empty.status_code == 200 and empty.json()["total"] == 0
    created = [
        create_test_campaign_creative(db_sessionmaker, campaign_id=campaign.id) for _ in range(3)
    ]
    create_test_campaign_creative(db_sessionmaker, campaign_id=other.id)
    first = db_client.get(path, headers=headers, params={"limit": 2}).json()
    later = db_client.get(path, headers=headers, params={"limit": 2, "offset": 2}).json()
    assert first["total"] == later["total"] == 3
    assert len(first["items"]) == 2 and len(later["items"]) == 1
    assert {item["id"] for item in first["items"] + later["items"]} == {
        str(row.id) for row in created
    }
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in later["items"]})
    assert db_client.get(path, headers=headers, params={"offset": 3}).json()["total"] == 3
    assert (
        db_client.get(path, headers=auth_headers(db_client, advertiser.email, PASSWORD)).status_code
        == 403
    )


def test_named_search_reaches_beyond_first_hundred_and_matches_literal_context(
    db_client, db_sessionmaker
):
    admin = create_test_user(db_sessionmaker, email="queue-admin@example.test", password=PASSWORD)

    async def seed():
        async with db_sessionmaker() as session:
            session.add_all(
                [
                    User(
                        email=f"operator-{i}@example.test",
                        full_name=f"Queue Person {i:03}",
                        password_hash=admin.password_hash,
                        role="driver",
                        status="active",
                        phone="+2349911223344",
                    )
                    for i in range(103)
                ]
            )
            await session.commit()

    asyncio.run(seed())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    first = db_client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"q": "Queue Person", "role": "driver", "limit": 100},
    ).json()
    later = db_client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"q": "Queue Person", "role": "driver", "limit": 100, "offset": 100},
    ).json()
    assert first["total"] == later["total"] == 103
    assert len(first["items"]) == 100 and len(later["items"]) == 3
    assert not ({r["id"] for r in first["items"]} & {r["id"] for r in later["items"]})
    for query in ("%", "+2349911223344", "not-present"):
        result = db_client.get("/api/v1/admin/users", headers=headers, params={"q": query}).json()
        assert result["total"] == 0 and result["items"] == []
    assert (
        db_client.get("/api/v1/admin/users", headers=headers, params={"q": "x" * 121}).status_code
        == 422
    )


def test_measurement_discovery_is_named_paginated_authorized_and_does_not_issue(
    db_client, db_sessionmaker
):
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker, identity_tag="ops-list")
    headers = auth_headers(db_client, admin.email, PASSWORD)
    empty = db_client.get("/api/v1/admin/measurement-runs", headers=headers).json()
    assert empty["items"] == [] and empty["total"] == 0
    issued = db_client.post(
        "/api/v1/admin/measurement-runs", headers=headers, json=issue_payload(campaign.id)
    )
    assert issued.status_code == 201, issued.text
    page = db_client.get(
        "/api/v1/admin/measurement-runs", headers=headers, params={"q": campaign.name, "limit": 1}
    ).json()
    assert page["total"] == 1 and page["items"][0]["campaign_name"] == campaign.name
    assert page["items"][0]["reproducible"] is True
    assert page["items"][0]["report_status"] is None
    assert "result_manifest" not in page["items"][0]
    past = db_client.get(
        "/api/v1/admin/measurement-runs", headers=headers, params={"offset": 1}
    ).json()
    assert past["total"] == 1 and past["items"] == []
    denied = db_client.get(
        "/api/v1/admin/measurement-runs",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    assert denied.status_code == 403


def test_approval_reveal_denies_superseded_nin_without_read_audit(db_client, db_sessionmaker):
    admin, driver, _, bank, files = _seed_driver_authority(db_sessionmaker, suffix="ops-stale")
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    first = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=driver_headers, json=_payload(bank, files)
    ).json()
    second = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=driver_headers,
        json=_payload(bank, files, client_request_id=str(uuid4())),
    )
    assert second.status_code == 201, second.text
    headers = auth_headers(db_client, admin.email, PASSWORD)
    stale = db_client.post(
        f"/api/v1/admin/kyc/submissions/{first['id']}/nin/reveal",
        headers=headers,
        json={"purpose": "person_payee_approval"},
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "KYC_REVIEW_STALE"
    current = db_client.post(
        f"/api/v1/admin/kyc/submissions/{second.json()['id']}/nin/reveal",
        headers=headers,
        json={"purpose": "person_payee_approval"},
    )
    assert current.status_code == 200 and current.json()["nin"] == NIN
    assert current.headers["cache-control"] == "no-store"

    async def reads():
        async with db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.action == "admin.kyc.nin_read")
                )
            )

    assert [r.entity_id for r in asyncio.run(reads())] == [second.json()["id"]]


def test_driver_application_history_and_detail_serialize_terminal_rows_without_writes(
    db_client, db_sessionmaker, settings
):
    enable_registration(db_client, settings)
    for suffix in ("approved-history", "rejected-history"):
        response = db_client.post(
            "/api/v1/auth/register-driver",
            json={
                "email": f"{suffix}@example.test",
                "full_name": f"{suffix} driver",
            },
        )
        assert response.status_code == 202
    admin = create_test_user(
        db_sessionmaker,
        email="application-history-admin@example.test",
        password=PASSWORD,
    )

    async def make_terminal():
        async with db_sessionmaker() as session:
            rows = list(
                (
                    await session.scalars(
                        select(DriverApplication).order_by(DriverApplication.email)
                    )
                ).all()
            )
            rows[0].status = DriverApplicationStatus.APPROVED.value
            rows[1].status = DriverApplicationStatus.REJECTED.value
            await session.commit()

    async def snapshot():
        async with db_sessionmaker() as session:
            rows = list((await session.scalars(select(DriverApplication))).all())
            return {row.id: (row.status, row.created_at, row.updated_at) for row in rows}, int(
                await session.scalar(select(func.count(AuditEvent.id))) or 0
            )

    asyncio.run(make_terminal())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    before, audits_before = asyncio.run(snapshot())
    pending = db_client.get("/api/v1/admin/driver-applications", headers=headers)
    history = db_client.get(
        "/api/v1/admin/driver-applications", headers=headers, params={"history": True}
    )
    details = [
        db_client.get(f"/api/v1/admin/driver-applications/{application_id}", headers=headers)
        for application_id in before
    ]

    assert pending.status_code == 200
    assert pending.json()["items"] == [] and pending.json()["total"] == 0
    assert history.status_code == 200
    assert {item["status"] for item in history.json()["items"]} == {"approved", "rejected"}
    assert all(response.status_code == 200 for response in details)
    assert {response.json()["status"] for response in details} == {"approved", "rejected"}
    assert asyncio.run(snapshot()) == (before, audits_before)


def _clone_clean_file(db_sessionmaker, file_id):
    async def clone():
        async with db_sessionmaker() as session:
            source = await session.get(StoredFile, file_id)
            assert source is not None
            intent = FileUploadIntent(
                organization_id=source.organization_id,
                subject_user_id=source.subject_user_id,
                uploader_user_id=source.uploader_user_id,
                client_request_id=uuid4(),
                request_fingerprint=uuid4().hex * 2,
                purpose=source.purpose,
                original_filename=source.original_filename,
                declared_content_type=source.content_type,
                declared_size_bytes=source.size_bytes,
                declared_sha256=source.checksum_sha256,
                object_key=f"unconfirmed/subject/{source.subject_user_id}/{uuid4()}",
                expires_at=source.created_at,
                status="confirmed",
            )
            session.add(intent)
            await session.flush()
            replacement = StoredFile(
                upload_intent_id=intent.id,
                organization_id=source.organization_id,
                subject_user_id=source.subject_user_id,
                uploader_user_id=source.uploader_user_id,
                purpose=source.purpose,
                original_filename=source.original_filename,
                storage_key=f"managed/subject/{source.subject_user_id}/{intent.id}",
                content_type=source.content_type,
                size_bytes=source.size_bytes,
                checksum_sha256=source.checksum_sha256,
                scan_status=FileScanStatus.CLEAN,
            )
            session.add(replacement)
            await session.commit()
            return replacement.id

    return asyncio.run(clone())


def _seed_download_object(db_sessionmaker, storage, file_id):
    async def seed():
        async with db_sessionmaker() as session:
            stored_file = await session.get(StoredFile, file_id)
            assert stored_file is not None
            storage.objects[stored_file.storage_key] = ObjectMetadata(
                object_key=stored_file.storage_key,
                size_bytes=stored_file.size_bytes,
                content_type=stored_file.actual_content_type or stored_file.content_type,
                checksum_sha256=stored_file.checksum_sha256,
            )

    asyncio.run(seed())


def _stored_file_reads(db_sessionmaker):
    async def reads():
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(AuditEvent).where(AuditEvent.action == "stored_file.read")
                    )
                ).all()
            )

    return asyncio.run(reads())


def test_kyc_download_uses_current_person_file_authority_not_reason_text(
    db_client, db_sessionmaker
):
    admin, driver, _, bank, files = _seed_driver_authority(
        db_sessionmaker, suffix="ops-person-file-stale"
    )
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    first = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=driver_headers, json=_payload(bank, files)
    )
    assert first.status_code == 201
    stale_file_id = files["driver_license"]
    current_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    unlinked_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    current_files = files | {"driver_license": current_file_id}
    current = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=driver_headers,
        json=_payload(bank, current_files, client_request_id=str(uuid4())),
    )
    assert current.status_code == 201
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    _seed_download_object(db_sessionmaker, storage, stale_file_id)
    _seed_download_object(db_sessionmaker, storage, current_file_id)
    _seed_download_object(db_sessionmaker, storage, unlinked_file_id)
    headers = auth_headers(db_client, admin.email, PASSWORD)

    stale = db_client.post(
        f"/api/v1/admin/files/{stale_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review applicant identity evidence"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "KYC_REVIEW_STALE"
    assert storage.presigned_gets == []
    assert _stored_file_reads(db_sessionmaker) == []

    unlinked = db_client.post(
        f"/api/v1/admin/files/{unlinked_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review applicant identity evidence"},
    )
    assert unlinked.status_code == 409
    assert unlinked.json()["error"]["code"] == "KYC_REVIEW_STALE"
    assert storage.presigned_gets == []
    assert _stored_file_reads(db_sessionmaker) == []

    linked = db_client.post(
        f"/api/v1/admin/files/{current_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review applicant identity evidence"},
    )
    assert linked.status_code == 200
    assert linked.headers["cache-control"] == "no-store"
    assert len(storage.presigned_gets) == 1
    assert [row.entity_id for row in _stored_file_reads(db_sessionmaker)] == [str(current_file_id)]

    for purpose in ("security_review", "incident_response"):
        historical = db_client.post(
            f"/api/v1/admin/files/{stale_file_id}/download",
            headers=headers,
            json={"purpose": purpose, "reason": "Investigate historical evidence integrity"},
        )
        assert historical.status_code == 200


def test_kyc_download_uses_current_vehicle_file_authority_not_reason_text(
    db_client, db_sessionmaker
):
    admin, driver, profile, _, files = _seed_driver_authority(
        db_sessionmaker, suffix="ops-vehicle-file-stale"
    )
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    payload = {
        "client_request_id": str(uuid4()),
        "registration_file_id": str(files["registration"]),
        "insurance_file_id": str(files["insurance"]),
        "vehicle_photo_file_id": str(files["vehicle_photo"]),
    }
    path = f"/api/v1/driver/vehicles/{vehicle.id}/evidence-submissions"
    first = db_client.post(path, headers=driver_headers, json=payload)
    assert first.status_code == 201
    stale_file_id = files["registration"]
    current_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    unlinked_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    current = db_client.post(
        path,
        headers=driver_headers,
        json=payload
        | {
            "client_request_id": str(uuid4()),
            "registration_file_id": str(current_file_id),
        },
    )
    assert current.status_code == 201
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    _seed_download_object(db_sessionmaker, storage, stale_file_id)
    _seed_download_object(db_sessionmaker, storage, current_file_id)
    _seed_download_object(db_sessionmaker, storage, unlinked_file_id)
    headers = auth_headers(db_client, admin.email, PASSWORD)

    stale = db_client.post(
        f"/api/v1/admin/files/{stale_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review vehicle identity evidence"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "KYC_REVIEW_STALE"
    assert storage.presigned_gets == []
    assert _stored_file_reads(db_sessionmaker) == []

    unlinked = db_client.post(
        f"/api/v1/admin/files/{unlinked_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review vehicle identity evidence"},
    )
    assert unlinked.status_code == 409
    assert unlinked.json()["error"]["code"] == "KYC_REVIEW_STALE"
    assert storage.presigned_gets == []
    assert _stored_file_reads(db_sessionmaker) == []

    linked = db_client.post(
        f"/api/v1/admin/files/{current_file_id}/download",
        headers=headers,
        json={"purpose": "kyc_review", "reason": "Review vehicle identity evidence"},
    )
    assert linked.status_code == 200
    assert linked.headers["cache-control"] == "no-store"
    assert len(storage.presigned_gets) == 1
    assert [row.entity_id for row in _stored_file_reads(db_sessionmaker)] == [str(current_file_id)]


def test_kyc_review_download_service_denies_stale_and_unlinked_person_files(
    db_client, db_sessionmaker, settings
):
    from app.core.errors import AppError
    from app.services.stored_files import issue_admin_file_download

    admin, driver, _, bank, files = _seed_driver_authority(
        db_sessionmaker, suffix="ops-person-file-service"
    )
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    first = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=driver_headers, json=_payload(bank, files)
    )
    assert first.status_code == 201
    stale_file_id = files["driver_license"]
    current_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    unlinked_file_id = _clone_clean_file(db_sessionmaker, stale_file_id)
    current = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=driver_headers,
        json=_payload(
            bank, files | {"driver_license": current_file_id}, client_request_id=str(uuid4())
        ),
    )
    assert current.status_code == 201
    storage = FakeStorageProvider()
    for file_id in (stale_file_id, current_file_id, unlinked_file_id):
        _seed_download_object(db_sessionmaker, storage, file_id)

    async def download(file_id, purpose="kyc_review"):
        async with db_sessionmaker() as session:
            try:
                await issue_admin_file_download(
                    session,
                    actor_user_id=admin.id,
                    file_id=file_id,
                    access_purpose=purpose,
                    reason="Review applicant identity evidence",
                    storage=storage,
                    settings=settings,
                )
            except AppError as error:
                await session.rollback()
                return error.code
            await session.commit()
            return "issued"

    assert asyncio.run(download(stale_file_id)) == "KYC_REVIEW_STALE"
    assert asyncio.run(download(unlinked_file_id)) == "KYC_REVIEW_STALE"
    assert storage.presigned_gets == []
    assert _stored_file_reads(db_sessionmaker) == []
    assert asyncio.run(download(current_file_id)) == "issued"
    assert len(storage.presigned_gets) == 1
    assert asyncio.run(download(stale_file_id, purpose="security_review")) == "issued"
