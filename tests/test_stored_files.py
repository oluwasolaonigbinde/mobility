import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import func, select

from app.adapters.storage import (
    ObjectMetadata,
    PresignedGet,
    PresignedPost,
    StorageObjectConflict,
    StorageObjectNotFound,
    StorageProvider,
    StorageUnavailable,
)
from app.api.v1.dependencies import get_storage_provider
from app.models.audit import AuditEvent
from app.models.organization import MembershipRole
from app.models.stored_file import FileUploadIntent, StoredFile
from app.models.user import UserRole
from app.services.stored_files import purge_expired_upload_intents

PASSWORD = "long-secure-password"


class FakeStorageProvider(StorageProvider):
    def __init__(self) -> None:
        self.objects: dict[str, ObjectMetadata] = {}
        self.contents: dict[str, bytes] = {}
        self.presigned: list[dict[str, object]] = []
        self.presigned_gets: list[dict[str, object]] = []
        self.deleted: list[str] = []
        self.unavailable = False

    async def presign_post(
        self,
        *,
        object_key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        expires_in_seconds: int,
    ) -> PresignedPost:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        request = {
            "object_key": object_key,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "checksum_sha256": checksum_sha256,
            "expires_in_seconds": expires_in_seconds,
        }
        self.presigned.append(request)
        return PresignedPost(
            url="http://storage.test/cardvert-private",
            fields={
                "key": object_key,
                "Content-Type": content_type,
                "x-amz-meta-sha256": checksum_sha256,
            },
        )

    async def stat(self, object_key: str) -> ObjectMetadata:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        try:
            return self.objects[object_key]
        except KeyError:
            raise StorageObjectNotFound(object_key) from None

    async def put(
        self,
        *,
        object_key: str,
        content_type: str,
        data: bytes,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        observed_hash = hashlib.sha256(data).hexdigest()
        if observed_hash != checksum_sha256:
            raise StorageObjectConflict("checksum mismatch")
        existing = self.objects.get(object_key)
        if existing is not None:
            if (
                existing.content_type != content_type
                or existing.size_bytes != len(data)
                or existing.checksum_sha256 != checksum_sha256
                or self.contents.get(object_key) != data
            ):
                raise StorageObjectConflict("immutable object mismatch")
            return existing
        metadata = ObjectMetadata(
            object_key=object_key,
            size_bytes=len(data),
            content_type=content_type,
            checksum_sha256=checksum_sha256,
        )
        self.objects[object_key] = metadata
        self.contents[object_key] = data
        return metadata

    async def stream(self, object_key: str):
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        try:
            yield self.contents[object_key]
        except KeyError:
            raise StorageObjectNotFound(object_key) from None

    async def presign_get(self, *, object_key: str, expires_in_seconds: int) -> PresignedGet:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        self.presigned_gets.append(
            {"object_key": object_key, "expires_in_seconds": expires_in_seconds}
        )
        return PresignedGet(
            url="http://storage.test/private-download",
            expires_in_seconds=expires_in_seconds,
        )

    async def promote(self, *, source_key: str, destination_key: str) -> ObjectMetadata:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        if destination_key in self.objects:
            self.objects.pop(source_key, None)
            self.contents.pop(source_key, None)
            return self.objects[destination_key]
        try:
            metadata = self.objects.pop(source_key)
        except KeyError:
            raise StorageObjectNotFound(source_key) from None
        promoted = replace(metadata, object_key=destination_key)
        self.objects[destination_key] = promoted
        if source_key in self.contents:
            self.contents[destination_key] = self.contents.pop(source_key)
        return promoted

    async def delete(self, object_key: str) -> None:
        if self.unavailable:
            raise StorageUnavailable("storage is unavailable")
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)
        self.contents.pop(object_key, None)


@pytest.fixture
def storage(db_client):
    provider = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: provider
    yield provider
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def advertiser_with_org(db_sessionmaker, email: str, *, role=MembershipRole.OWNER):
    user = create_test_user(
        db_sessionmaker,
        email=email,
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=user.id,
        membership_role=role,
    )
    return user, organization


def upload_payload(**changes):
    payload = {
        "client_request_id": "8ec6bdcc-65f1-47aa-a5d9-659f53b270c2",
        "purpose": "creative",
        "filename": "campaign-art.png",
        "content_type": "image/png",
        "size_bytes": 68,
        "sha256": "a" * 64,
    }
    payload.update(changes)
    return payload


def create_upload(db_client, email: str, payload=None):
    return db_client.post(
        "/api/v1/advertiser/files/uploads",
        headers=auth_headers(db_client, email, PASSWORD),
        json=payload or upload_payload(),
    )


def test_driver_uploads_are_subject_scoped_and_role_purpose_bound(
    db_client, db_sessionmaker, storage
) -> None:
    first = create_test_user(
        db_sessionmaker,
        email="driver-files-a@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    second = create_test_user(
        db_sessionmaker,
        email="driver-files-b@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=first.id)
    create_test_driver_profile(db_sessionmaker, user_id=second.id)
    payload = upload_payload(purpose="driver_kyc", filename="12345678901-licence.png")

    created = db_client.post(
        "/api/v1/driver/files/uploads",
        headers=auth_headers(db_client, first.email, PASSWORD),
        json=payload,
    )
    forbidden = db_client.post(
        "/api/v1/driver/files/uploads",
        headers=auth_headers(db_client, first.email, PASSWORD),
        json=upload_payload(client_request_id="0342e450-fb55-451d-9676-a28fdd284192"),
    )

    assert created.status_code == 201
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FILE_PURPOSE_FORBIDDEN"
    key = created.json()["upload"]["fields"]["key"]
    assert key.startswith(f"unconfirmed/subject/{first.id}/")
    storage.objects[key] = ObjectMetadata(
        object_key=key,
        size_bytes=68,
        content_type="image/png",
        checksum_sha256="a" * 64,
    )

    cross_subject = db_client.post(
        f"/api/v1/driver/files/uploads/{created.json()['upload_id']}/confirm",
        headers=auth_headers(db_client, second.email, PASSWORD),
    )
    confirmed = db_client.post(
        f"/api/v1/driver/files/uploads/{created.json()['upload_id']}/confirm",
        headers=auth_headers(db_client, first.email, PASSWORD),
    )

    assert cross_subject.status_code == 404
    assert confirmed.status_code == 201
    assert confirmed.json()["organization_id"] is None
    assert confirmed.json()["subject_user_id"] == str(first.id)
    assert confirmed.json()["purpose"] == "driver_kyc"
    assert confirmed.json()["original_filename"] == "driver-kyc.png"
    assert "12345678901" not in str(confirmed.json())

    async def inspect_sensitive_filename() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(FileUploadIntent, UUID(created.json()["upload_id"]))
            assert intent is not None and intent.original_filename == "driver-kyc.png"

    asyncio.run(inspect_sensitive_filename())


def test_presigned_post_is_private_condition_bound_and_same_retry_converges(
    db_client, db_sessionmaker, storage
) -> None:
    _, organization = advertiser_with_org(db_sessionmaker, "upload-owner@example.com")

    first = create_upload(db_client, "upload-owner@example.com")
    replay = create_upload(db_client, "upload-owner@example.com")

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["upload_id"] == first.json()["upload_id"]
    object_key = first.json()["upload"]["fields"]["key"]
    assert replay.json()["upload"]["fields"]["key"] == object_key
    assert object_key.startswith(f"unconfirmed/{organization.id}/")
    assert "object_key" not in first.json()
    assert first.json()["upload"]["url"].startswith("http://storage.test/")
    assert first.json()["upload"]["fields"] == {
        "key": object_key,
        "Content-Type": "image/png",
        "x-amz-meta-sha256": "a" * 64,
    }
    assert storage.presigned[-1]["size_bytes"] == 68

    async def inspect_audit() -> None:
        async with db_sessionmaker() as session:
            audits = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action == "stored_file.upload_requested"
                        )
                    )
                ).all()
            )
            assert len(audits) == 1
            assert "filename" not in audits[0].event_metadata

    asyncio.run(inspect_audit())

    changed = create_upload(
        db_client,
        "upload-owner@example.com",
        upload_payload(filename="changed.png"),
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "FILE_UPLOAD_RETRY_CONFLICT"


def test_confirmation_promotes_exact_object_once_and_keeps_it_private(
    db_client, db_sessionmaker, storage
) -> None:
    advertiser, organization = advertiser_with_org(db_sessionmaker, "confirm-owner@example.com")
    created = create_upload(db_client, advertiser.email).json()
    object_key = created["upload"]["fields"]["key"]
    storage.objects[object_key] = ObjectMetadata(
        object_key=object_key,
        size_bytes=68,
        content_type="image/png",
        checksum_sha256="a" * 64,
    )

    first = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )
    replay = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    body = first.json()
    assert body["organization_id"] == str(organization.id)
    assert body["scan_status"] == "pending"
    assert "url" not in body and "bucket" not in body and "storage_key" not in body
    managed_key = next(iter(storage.objects))
    assert managed_key.startswith(f"managed/{organization.id}/")

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(StoredFile)) == 1
            intent = await session.get(FileUploadIntent, UUID(created["upload_id"]))
            assert intent is not None and intent.status == "confirmed"
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "stored_file.confirmed")
            )
            assert audit is not None
            assert "filename" not in audit.event_metadata

    asyncio.run(inspect())


@pytest.mark.parametrize(
    ("metadata_change", "error_code"),
    [
        ({"size_bytes": 69}, "FILE_UPLOAD_SIZE_MISMATCH"),
        ({"content_type": "text/html"}, "FILE_UPLOAD_TYPE_MISMATCH"),
        ({"checksum_sha256": "b" * 64}, "FILE_UPLOAD_CHECKSUM_MISMATCH"),
    ],
)
def test_confirmation_rejects_server_observed_mismatch_without_creating_file(
    db_client, db_sessionmaker, storage, metadata_change, error_code
) -> None:
    advertiser, _ = advertiser_with_org(
        db_sessionmaker, f"mismatch-{error_code.lower()}@example.com"
    )
    created = create_upload(db_client, advertiser.email).json()
    object_key = created["upload"]["fields"]["key"]
    expected = {
        "object_key": object_key,
        "size_bytes": 68,
        "content_type": "image/png",
        "checksum_sha256": "a" * 64,
    }
    expected.update(metadata_change)
    storage.objects[object_key] = ObjectMetadata(**expected)

    response = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == error_code

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(StoredFile)) == 0

    asyncio.run(inspect())


def test_upload_expiry_cross_tenant_and_viewer_fail_closed(
    db_client, db_sessionmaker, storage
) -> None:
    owner_a, _ = advertiser_with_org(db_sessionmaker, "tenant-a@example.com")
    owner_b, _ = advertiser_with_org(db_sessionmaker, "tenant-b@example.com")
    advertiser_with_org(
        db_sessionmaker,
        "viewer-upload@example.com",
        role=MembershipRole.VIEWER,
    )
    created = create_upload(db_client, owner_a.email).json()
    object_key = created["upload"]["fields"]["key"]
    storage.objects[object_key] = ObjectMetadata(
        object_key=object_key,
        size_bytes=68,
        content_type="image/png",
        checksum_sha256="a" * 64,
    )

    cross_tenant = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, owner_b.email, PASSWORD),
    )
    viewer = create_upload(db_client, "viewer-upload@example.com")

    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "FILE_UPLOAD_NOT_FOUND"
    assert viewer.status_code == 403
    assert viewer.json()["error"]["code"] == "ORGANIZATION_WRITE_FORBIDDEN"

    async def expire() -> None:
        async with db_sessionmaker() as session:
            intent = await session.get(FileUploadIntent, UUID(created["upload_id"]))
            assert intent is not None
            intent.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    expired = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, owner_a.email, PASSWORD),
    )
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "FILE_UPLOAD_EXPIRED"


def test_orphan_cleanup_deletes_both_possible_keys_and_is_retry_safe(
    db_sessionmaker, storage
) -> None:
    advertiser, organization = advertiser_with_org(db_sessionmaker, "cleanup-upload@example.com")

    async def scenario() -> None:
        intent_id = None
        async with db_sessionmaker() as session:
            intent = FileUploadIntent(
                organization_id=organization.id,
                uploader_user_id=advertiser.id,
                client_request_id=UUID("b4c293d9-3698-4096-a82a-6c01f24b204a"),
                request_fingerprint="f" * 64,
                purpose="creative",
                original_filename="old.png",
                declared_content_type="image/png",
                declared_size_bytes=68,
                declared_sha256="a" * 64,
                object_key=f"unconfirmed/{organization.id}/orphan",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
                status="pending",
            )
            session.add(intent)
            await session.commit()
            intent_id = intent.id
        assert intent_id is not None
        managed_key = f"managed/{organization.id}/{intent_id}"
        storage.objects[managed_key] = ObjectMetadata(
            object_key=managed_key,
            size_bytes=68,
            content_type="image/png",
            checksum_sha256="a" * 64,
        )

        async with db_sessionmaker() as session:
            assert await purge_expired_upload_intents(session, storage=storage, limit=10) == 1
            await session.commit()
        async with db_sessionmaker() as session:
            assert await purge_expired_upload_intents(session, storage=storage, limit=10) == 0
            intent = await session.get(FileUploadIntent, intent_id)
            assert intent is not None and intent.status == "expired"
        assert storage.deleted == [
            f"unconfirmed/{organization.id}/orphan",
            managed_key,
        ]

    asyncio.run(scenario())


def test_storage_outage_creates_no_intent(db_client, db_sessionmaker, storage) -> None:
    advertiser_with_org(db_sessionmaker, "storage-down@example.com")
    storage.unavailable = True

    response = create_upload(db_client, "storage-down@example.com")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FILE_STORAGE_UNAVAILABLE"

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(FileUploadIntent)) == 0

    asyncio.run(inspect())
