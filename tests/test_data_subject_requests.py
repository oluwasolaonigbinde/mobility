import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import func, select
from starlette import status
from test_stored_files import FakeStorageProvider

from app.adapters.storage import ObjectMetadata
from app.api.v1.dependencies import get_storage_provider
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.data_subject_request import (
    DataSubjectDisposition,
    DataSubjectLocation,
    DataSubjectLocationAssessment,
    DataSubjectRequestType,
)
from app.models.stored_file import FileUploadIntent, StoredFile, UploadIntentStatus
from app.models.user import UserRole
from app.services.data_subject_requests import (
    complete_data_subject_request,
    create_data_subject_request,
    record_location_assessment,
    verify_data_subject_identity,
)


def test_admin_access_request_inventories_and_closes_all_locations(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="dsr-admin@example.test", role=UserRole.ADMIN
    )
    other_admin = create_test_user(
        db_sessionmaker, email="dsr-other-admin@example.test", role=UserRole.ADMIN
    )
    subject = create_test_user(
        db_sessionmaker, email="dsr-subject@example.test", role=UserRole.DRIVER
    )
    headers = auth_headers(db_client, admin.email)
    payload = {
        "subject_user_id": str(subject.id),
        "request_type": "access",
        "client_request_id": str(uuid4()),
        "requested_at": datetime.now(UTC).isoformat(),
    }
    opened = db_client.post("/api/v1/admin/privacy/dsr-requests", json=payload, headers=headers)
    assert opened.status_code == status.HTTP_201_CREATED
    request_id = opened.json()["id"]
    retry = db_client.post("/api/v1/admin/privacy/dsr-requests", json=payload, headers=headers)
    assert retry.status_code == status.HTTP_201_CREATED
    assert retry.json()["id"] == request_id
    changed_retry = db_client.post(
        "/api/v1/admin/privacy/dsr-requests",
        json={**payload, "request_type": "rectification"},
        headers=headers,
    )
    assert changed_retry.status_code == status.HTTP_409_CONFLICT
    assert changed_retry.json()["error"]["code"] == "DSR_REQUEST_REPLAY_CONFLICT"

    verified = db_client.post(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/verify-identity",
        headers=headers,
    )
    assert verified.status_code == status.HTTP_200_OK
    inventory = db_client.get(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/inventory", headers=headers
    )
    assert inventory.status_code == status.HTTP_200_OK
    assert inventory.json()["database"]["account_identity"] == 1
    assert inventory.json()["object_storage"] == {
        "stored_files": 0,
        "upload_intents": 0,
        "objects_verified": 0,
        "pending_objects_verified": 0,
    }
    assert "email" not in str(inventory.json()).lower()

    locations = list(DataSubjectLocation)
    for location in locations:
        assessment = {
            "disposition": (
                "provided" if location is DataSubjectLocation.DATABASE else "not_found"
            ),
            "evidence_reference": f"SYNTHETIC-ACCESS-{location.value}",
            "external_record_count": (
                0
                if location
                not in {DataSubjectLocation.DATABASE, DataSubjectLocation.OBJECT_STORAGE}
                else None
            ),
            "client_request_id": str(uuid4()),
        }
        response = db_client.post(
            f"/api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location.value}",
            json=assessment,
            headers=headers,
        )
        assert response.status_code == status.HTTP_201_CREATED, response.json()
        if location is DataSubjectLocation.DATABASE:
            exact_retry = db_client.post(
                f"/api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location.value}",
                json=assessment,
                headers=headers,
            )
            assert exact_retry.status_code == status.HTTP_201_CREATED
            assert exact_retry.json()["id"] == response.json()["id"]
            changed_assessment = db_client.post(
                f"/api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location.value}",
                json={**assessment, "evidence_reference": "SYNTHETIC-CHANGED"},
                headers=headers,
            )
            assert changed_assessment.status_code == status.HTTP_409_CONFLICT
            assert changed_assessment.json()["error"]["code"] == "DSR_ASSESSMENT_CONFLICT"
            cross_actor_retry = db_client.post(
                f"/api/v1/admin/privacy/dsr-requests/{request_id}/locations/{location.value}",
                json=assessment,
                headers=auth_headers(db_client, other_admin.email),
            )
            assert cross_actor_retry.status_code == status.HTTP_409_CONFLICT
            assert cross_actor_retry.json()["error"]["code"] == "DSR_ASSESSMENT_CONFLICT"

    completed = db_client.post(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/complete", headers=headers
    )
    assert completed.status_code == status.HTTP_200_OK
    assert completed.json()["status"] == "completed"

    async def assert_evidence() -> None:
        async with db_sessionmaker() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(DataSubjectLocationAssessment)
                )
                == 6
            )
            audits = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == request_id,
                        AuditEvent.action.like("privacy.dsr.%"),
                    )
                )
            )
            assert {event.action for event in audits} == {
                "privacy.dsr.opened",
                "privacy.dsr.identity_verified",
                "privacy.dsr.inventory_read",
                "privacy.dsr.location_assessed",
                "privacy.dsr.completed",
            }
            assert all("email" not in str(event.event_metadata).lower() for event in audits)
            assert all(str(subject.id) not in str(event.event_metadata) for event in audits)

    asyncio.run(assert_evidence())


def test_erasure_preserves_protected_history_without_approved_exception(
    db_sessionmaker,
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="erasure-admin@example.test", role=UserRole.ADMIN
    )
    subject = create_test_user(
        db_sessionmaker, email="erasure-subject@example.test", role=UserRole.DRIVER
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            session.add(
                AuditEvent(
                    actor_user_id=subject.id,
                    action="synthetic.subject.action",
                    entity_type="synthetic",
                    entity_id=str(subject.id),
                    event_metadata={},
                )
            )
            case = await create_data_subject_request(
                session,
                actor_user_id=admin.id,
                subject_user_id=subject.id,
                request_type=DataSubjectRequestType.ERASURE,
                client_request_id=uuid4(),
                requested_at=datetime.now(UTC),
            )
            await verify_data_subject_identity(
                session, actor_user_id=admin.id, request_id=case.id
            )
            await session.commit()
            request_id = case.id

        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as protected:
                await record_location_assessment(
                    session,
                    actor_user_id=admin.id,
                    request_id=request_id,
                    location=DataSubjectLocation.DATABASE,
                    disposition=DataSubjectDisposition.ERASED,
                    evidence_reference="SYNTHETIC-ERASURE-DB",
                    exception_reference=None,
                    external_record_count=None,
                    client_request_id=uuid4(),
                    approved_exception_references=set(),
                )
            assert protected.value.code == "DSR_RECORDS_REMAIN"
            with pytest.raises(AppError) as unapproved:
                await record_location_assessment(
                    session,
                    actor_user_id=admin.id,
                    request_id=request_id,
                    location=DataSubjectLocation.DATABASE,
                    disposition=DataSubjectDisposition.RETAINED_EXCEPTION,
                    evidence_reference="SYNTHETIC-ERASURE-DB",
                    exception_reference="SYNTHETIC-EXCEPTION",
                    external_record_count=None,
                    client_request_id=uuid4(),
                    approved_exception_references=set(),
                )
            assert unapproved.value.code == "DSR_EXCEPTION_NOT_APPROVED"
            retained = await record_location_assessment(
                session,
                actor_user_id=admin.id,
                request_id=request_id,
                location=DataSubjectLocation.DATABASE,
                disposition=DataSubjectDisposition.RETAINED_EXCEPTION,
                evidence_reference="SYNTHETIC-ERASURE-DB",
                exception_reference="SYNTHETIC-EXCEPTION",
                external_record_count=None,
                client_request_id=uuid4(),
                approved_exception_references={"SYNTHETIC-EXCEPTION"},
            )
            await session.commit()
            assert retained.data_class_counts["audit_event"] == 1
            protected_audit_id = await session.scalar(
                select(AuditEvent.id).where(AuditEvent.actor_user_id == subject.id)
            )
            assert protected_audit_id is not None
            assert await session.get(AuditEvent, protected_audit_id) is not None

    asyncio.run(run())


def test_non_admin_cannot_open_data_subject_request(db_client, db_sessionmaker) -> None:
    actor = create_test_user(
        db_sessionmaker, email="dsr-driver@example.test", role=UserRole.DRIVER
    )
    response = db_client.post(
        "/api/v1/admin/privacy/dsr-requests",
        headers=auth_headers(db_client, actor.email),
        json={
            "subject_user_id": str(actor.id),
            "request_type": "access",
            "client_request_id": str(uuid4()),
            "requested_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_completion_requires_every_store(db_sessionmaker) -> None:
    admin = create_test_user(
        db_sessionmaker, email="incomplete-admin@example.test", role=UserRole.ADMIN
    )
    subject = create_test_user(
        db_sessionmaker, email="incomplete-subject@example.test", role=UserRole.ADVERTISER
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            case = await create_data_subject_request(
                session,
                actor_user_id=admin.id,
                subject_user_id=subject.id,
                request_type=DataSubjectRequestType.ACCESS,
                client_request_id=uuid4(),
                requested_at=datetime.now(UTC),
            )
            await verify_data_subject_identity(
                session, actor_user_id=admin.id, request_id=case.id
            )
            with pytest.raises(AppError) as incomplete:
                await complete_data_subject_request(
                    session, actor_user_id=admin.id, request_id=case.id
                )
            assert incomplete.value.code == "DSR_LOCATIONS_INCOMPLETE"
            assert set(incomplete.value.details["missing_locations"]) == {
                location.value for location in DataSubjectLocation
            }

    asyncio.run(run())


@pytest.mark.parametrize(
    ("request_type", "database_disposition", "exception_reference"),
    [
        (
            DataSubjectRequestType.RECTIFICATION,
            DataSubjectDisposition.RECTIFIED,
            None,
        ),
        (
            DataSubjectRequestType.ERASURE,
            DataSubjectDisposition.RETAINED_EXCEPTION,
            "SYNTHETIC-ERASURE-EXCEPTION",
        ),
    ],
)
def test_rectification_and_erasure_manual_workflows_complete_with_explicit_evidence(
    db_sessionmaker,
    request_type: DataSubjectRequestType,
    database_disposition: DataSubjectDisposition,
    exception_reference: str | None,
) -> None:
    admin = create_test_user(
        db_sessionmaker,
        email=f"{request_type.value}-admin@example.test",
        role=UserRole.ADMIN,
    )
    subject = create_test_user(
        db_sessionmaker,
        email=f"{request_type.value}-subject@example.test",
        role=UserRole.DRIVER,
    )

    async def run() -> None:
        async with db_sessionmaker() as session:
            case = await create_data_subject_request(
                session,
                actor_user_id=admin.id,
                subject_user_id=subject.id,
                request_type=request_type,
                client_request_id=uuid4(),
                requested_at=datetime.now(UTC),
            )
            await verify_data_subject_identity(
                session, actor_user_id=admin.id, request_id=case.id
            )
            for location in DataSubjectLocation:
                disposition = DataSubjectDisposition.NOT_FOUND
                location_exception = None
                if location is DataSubjectLocation.DATABASE:
                    disposition = database_disposition
                    location_exception = exception_reference
                await record_location_assessment(
                    session,
                    actor_user_id=admin.id,
                    request_id=case.id,
                    location=location,
                    disposition=disposition,
                    evidence_reference=f"SYNTHETIC-{request_type.value}-{location.value}",
                    exception_reference=location_exception,
                    external_record_count=(
                        0
                        if location
                        not in {
                            DataSubjectLocation.DATABASE,
                            DataSubjectLocation.OBJECT_STORAGE,
                        }
                        else None
                    ),
                    client_request_id=uuid4(),
                    approved_exception_references=(
                        {exception_reference} if exception_reference else set()
                    ),
                    storage=FakeStorageProvider(),
                )
            completed = await complete_data_subject_request(
                session, actor_user_id=admin.id, request_id=case.id
            )
            await session.commit()
            assert completed.status == "completed"

    asyncio.run(run())


def test_object_inventory_checks_private_storage_and_fails_closed(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="storage-dsr-admin@example.test", role=UserRole.ADMIN
    )
    subject = create_test_user(
        db_sessionmaker, email="storage-dsr-subject@example.test", role=UserRole.DRIVER
    )
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage

    async def seed() -> None:
        async with db_sessionmaker() as session:
            intent = FileUploadIntent(
                subject_user_id=subject.id,
                uploader_user_id=admin.id,
                client_request_id=uuid4(),
                request_fingerprint="a" * 64,
                purpose="driver_kyc",
                original_filename="identity.png",
                declared_content_type="image/png",
                declared_size_bytes=3,
                declared_sha256="b" * 64,
                object_key=f"quarantine/{uuid4()}",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                status=UploadIntentStatus.CONFIRMED.value,
            )
            session.add(intent)
            await session.flush()
            session.add(
                StoredFile(
                    upload_intent_id=intent.id,
                    subject_user_id=subject.id,
                    uploader_user_id=admin.id,
                    purpose="driver_kyc",
                    original_filename="identity.png",
                    storage_key=f"managed/subject/{subject.id}/{intent.id}",
                    content_type="image/png",
                    size_bytes=3,
                    checksum_sha256="b" * 64,
                    scan_status="clean",
                )
            )
            await session.commit()

    asyncio.run(seed())
    headers = auth_headers(db_client, admin.email)
    opened = db_client.post(
        "/api/v1/admin/privacy/dsr-requests",
        headers=headers,
        json={
            "subject_user_id": str(subject.id),
            "request_type": "erasure",
            "client_request_id": str(uuid4()),
            "requested_at": datetime.now(UTC).isoformat(),
        },
    )
    request_id = opened.json()["id"]
    assert db_client.post(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/verify-identity",
        headers=headers,
    ).status_code == status.HTTP_200_OK

    storage.unavailable = True
    unavailable = db_client.get(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/inventory", headers=headers
    )
    assert unavailable.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert unavailable.json()["error"]["code"] == "DSR_STORAGE_UNAVAILABLE"

    storage.unavailable = False

    async def load_storage_key() -> tuple[str, str]:
        async with db_sessionmaker() as session:
            stored = await session.scalar(select(StoredFile))
            assert stored is not None
            return stored.storage_key, stored.checksum_sha256

    storage_key, checksum = asyncio.run(load_storage_key())
    storage.objects[storage_key] = ObjectMetadata(
        object_key=storage_key,
        size_bytes=3,
        content_type="image/png",
        checksum_sha256=checksum,
    )
    inventory = db_client.get(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/inventory", headers=headers
    )
    assert inventory.status_code == status.HTTP_200_OK
    assert inventory.json()["object_storage"]["objects_verified"] == 1

    erased = db_client.post(
        f"/api/v1/admin/privacy/dsr-requests/{request_id}/locations/object_storage",
        headers=headers,
        json={
            "disposition": "erased",
            "evidence_reference": "SYNTHETIC-OBJECT-ERASURE",
            "client_request_id": str(uuid4()),
        },
    )
    assert erased.status_code == status.HTTP_409_CONFLICT
    assert erased.json()["error"]["code"] == "DSR_RECORDS_REMAIN"
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def test_dsr_request_and_location_exact_races_converge(postgis_db_sessionmaker) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker, email="race-admin@example.test", role=UserRole.ADMIN
    )
    subject = create_test_user(
        postgis_db_sessionmaker, email="race-subject@example.test", role=UserRole.DRIVER
    )

    async def run() -> None:
        request_key = uuid4()
        requested_at = datetime.now(UTC)

        async def open_case():
            async with postgis_db_sessionmaker() as session:
                case = await create_data_subject_request(
                    session,
                    actor_user_id=admin.id,
                    subject_user_id=subject.id,
                    request_type=DataSubjectRequestType.ACCESS,
                    client_request_id=request_key,
                    requested_at=requested_at,
                )
                await session.commit()
                return case.id

        first_id, second_id = await asyncio.gather(open_case(), open_case())
        assert first_id == second_id
        async with postgis_db_sessionmaker() as session:
            await verify_data_subject_identity(
                session, actor_user_id=admin.id, request_id=first_id
            )
            await session.commit()

        assessment_key = uuid4()

        async def assess():
            async with postgis_db_sessionmaker() as session:
                row = await record_location_assessment(
                    session,
                    actor_user_id=admin.id,
                    request_id=first_id,
                    location=DataSubjectLocation.DATABASE,
                    disposition=DataSubjectDisposition.PROVIDED,
                    evidence_reference="SYNTHETIC-RACE-ACCESS",
                    exception_reference=None,
                    external_record_count=None,
                    client_request_id=assessment_key,
                    approved_exception_references=set(),
                )
                await session.commit()
                return row.id

        first_assessment, second_assessment = await asyncio.gather(assess(), assess())
        assert first_assessment == second_assessment
        async with postgis_db_sessionmaker() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(DataSubjectLocationAssessment)
                )
                == 1
            )

    asyncio.run(run())
