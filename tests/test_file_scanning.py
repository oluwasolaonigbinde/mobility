import asyncio
from collections.abc import AsyncIterable
from uuid import UUID

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import select
from test_stored_files import PASSWORD, FakeStorageProvider, upload_payload

from app.adapters.scanner import MalwareScanResult, ScannerUnavailable
from app.adapters.storage import ObjectMetadata
from app.api.v1.dependencies import get_storage_provider
from app.jobs import file_scanning as file_scanning_jobs
from app.models.audit import AuditEvent
from app.models.organization import MembershipRole
from app.models.stored_file import FileScanStatus, StoredFile
from app.models.user import UserRole
from app.services.stored_files import scan_stored_file


class FakeScanner:
    def __init__(self) -> None:
        self.infected_with: str | None = None
        self.unavailable = False
        self.calls = 0

    async def scan(self, chunks: AsyncIterable[bytes]) -> MalwareScanResult:
        self.calls += 1
        if self.unavailable:
            raise ScannerUnavailable("scanner unavailable")
        async for _chunk in chunks:
            pass
        if self.infected_with is not None:
            return MalwareScanResult.infected(self.infected_with)
        return MalwareScanResult.clean()


@pytest.fixture
def file_boundaries(db_client):
    storage = FakeStorageProvider()
    scanner = FakeScanner()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    yield storage, scanner
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def advertiser_with_org(db_sessionmaker, email: str):
    user = create_test_user(
        db_sessionmaker,
        email=email,
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=user.id,
        membership_role=MembershipRole.OWNER,
    )
    return user, organization


def confirm_png(db_client, storage: FakeStorageProvider, email: str) -> dict:
    content = b"\x89PNG\r\n\x1a\n" + b"scan-safe-content" * 4
    import hashlib

    payload = upload_payload(size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    created = db_client.post(
        "/api/v1/advertiser/files/uploads",
        headers=auth_headers(db_client, email, PASSWORD),
        json=payload,
    ).json()
    object_key = created["upload"]["fields"]["key"]
    storage.objects[object_key] = ObjectMetadata(
        object_key=object_key,
        size_bytes=len(content),
        content_type="image/png",
        checksum_sha256=payload["sha256"],
    )
    storage.contents[object_key] = content
    response = db_client.post(
        f"/api/v1/advertiser/files/uploads/{created['upload_id']}/confirm",
        headers=auth_headers(db_client, email, PASSWORD),
    )
    assert response.status_code == 201
    return response.json()


def scan_file(db_sessionmaker, file_id: str, storage, scanner):
    async def run():
        async with db_sessionmaker() as session:
            result = await scan_stored_file(
                session,
                file_id=UUID(file_id),
                storage=storage,
                scanner=scanner,
            )
            await session.commit()
            return result

    return asyncio.run(run())


def test_clean_exact_file_can_receive_short_lived_audited_private_read(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    advertiser, organization = advertiser_with_org(db_sessionmaker, "scan-clean@example.com")
    stored = confirm_png(db_client, storage, advertiser.email)

    outcome = scan_file(db_sessionmaker, stored["id"], storage, scanner)
    assert outcome == FileScanStatus.CLEAN
    assert scanner.calls == 1

    response = db_client.post(
        f"/api/v1/advertiser/files/{stored['id']}/download",
        headers={
            **auth_headers(db_client, advertiser.email, PASSWORD),
            "X-Request-ID": "file-read-request-1",
        },
        json={"purpose": "campaign_preview", "reason": "Review before submission"},
    )

    assert response.status_code == 200
    assert response.json()["url"].startswith("http://storage.test/private-download")
    assert response.json()["expires_in_seconds"] <= 60
    assert storage.presigned_gets == [
        {
            "object_key": storage.presigned_gets[0]["object_key"],
            "expires_in_seconds": response.json()["expires_in_seconds"],
        }
    ]

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            file = await session.get(StoredFile, UUID(stored["id"]))
            assert file is not None
            assert file.scan_status == FileScanStatus.CLEAN
            assert file.actual_content_type == "image/png"
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "stored_file.read")
            )
            assert audit is not None
            assert audit.actor_user_id == advertiser.id
            assert audit.event_metadata == {
                "organization_id": str(organization.id),
                "file_purpose": "creative",
                "access_purpose": "campaign_preview",
                "reason": "Review before submission",
                "request_id": "file-read-request-1",
            }

    asyncio.run(inspect())


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("infected", FileScanStatus.INFECTED),
        ("spoofed", FileScanStatus.REJECTED),
        ("size", FileScanStatus.REJECTED),
        ("outage", FileScanStatus.ERROR),
    ],
)
def test_unsafe_or_unavailable_scan_never_allows_download(
    db_client, db_sessionmaker, file_boundaries, mode, expected_status
) -> None:
    storage, scanner = file_boundaries
    advertiser, _ = advertiser_with_org(db_sessionmaker, f"scan-{mode}@example.com")
    stored = confirm_png(db_client, storage, advertiser.email)
    managed_key = next(key for key in storage.contents if key.startswith("managed/"))
    if mode == "infected":
        scanner.infected_with = "Eicar-Test-Signature"
    elif mode == "spoofed":
        storage.contents[managed_key] = b"%PDF-1.7" + storage.contents[managed_key][8:]
    elif mode == "size":
        storage.contents[managed_key] += b"x"
    else:
        scanner.unavailable = True

    assert scan_file(db_sessionmaker, stored["id"], storage, scanner) == expected_status
    denied = db_client.post(
        f"/api/v1/advertiser/files/{stored['id']}/download",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={"purpose": "campaign_preview", "reason": "Review before submission"},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "STORED_FILE_NOT_CLEARED"


def test_scan_and_read_replays_converge_and_cross_tenant_is_hidden(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    owner_a, _ = advertiser_with_org(db_sessionmaker, "scan-tenant-a@example.com")
    owner_b, _ = advertiser_with_org(db_sessionmaker, "scan-tenant-b@example.com")
    stored = confirm_png(db_client, storage, owner_a.email)

    assert scan_file(db_sessionmaker, stored["id"], storage, scanner) == FileScanStatus.CLEAN
    assert scan_file(db_sessionmaker, stored["id"], storage, scanner) == FileScanStatus.CLEAN
    assert scanner.calls == 1
    hidden = db_client.post(
        f"/api/v1/advertiser/files/{stored['id']}/download",
        headers=auth_headers(db_client, owner_b.email, PASSWORD),
        json={"purpose": "campaign_preview", "reason": "Review before submission"},
    )
    assert hidden.status_code == 404
    wrong_purpose = db_client.post(
        f"/api/v1/advertiser/files/{stored['id']}/download",
        headers=auth_headers(db_client, owner_a.email, PASSWORD),
        json={"purpose": "security_review", "reason": "Investigate scanner history"},
    )
    assert wrong_purpose.status_code == 403
    assert wrong_purpose.json()["error"]["code"] == "FILE_ACCESS_PURPOSE_FORBIDDEN"


def test_active_admin_read_is_purpose_scoped_and_inactive_admin_fails_in_service(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    advertiser, _ = advertiser_with_org(db_sessionmaker, "scan-admin-file@example.com")
    admin = create_test_user(
        db_sessionmaker,
        email="scan-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    stored = confirm_png(db_client, storage, advertiser.email)
    assert scan_file(db_sessionmaker, stored["id"], storage, scanner) == FileScanStatus.CLEAN
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)

    response = db_client.post(
        f"/api/v1/admin/files/{stored['id']}/download",
        headers=admin_headers,
        json={"purpose": "security_review", "reason": "Investigate scanner alert history"},
    )
    assert response.status_code == 200
    wrong_purpose = db_client.post(
        f"/api/v1/admin/files/{stored['id']}/download",
        headers=admin_headers,
        json={"purpose": "campaign_preview", "reason": "Preview campaign creative"},
    )
    assert wrong_purpose.status_code == 403

    async def disable() -> None:
        async with db_sessionmaker() as session:
            user = await session.get(type(admin), admin.id)
            assert user is not None
            user.status = "disabled"
            await session.commit()

    asyncio.run(disable())
    denied = db_client.post(
        f"/api/v1/admin/files/{stored['id']}/download",
        headers=admin_headers,
        json={"purpose": "security_review", "reason": "Investigate scanner alert history"},
    )
    assert denied.status_code == 403


def test_scan_worker_selects_and_commits_pending_file(
    db_client,
    db_sessionmaker,
    settings,
    file_boundaries,
    monkeypatch,
) -> None:
    storage, scanner = file_boundaries
    advertiser, _ = advertiser_with_org(db_sessionmaker, "scan-worker@example.com")
    stored = confirm_png(db_client, storage, advertiser.email)
    monkeypatch.setattr(file_scanning_jobs, "build_storage_provider", lambda _settings: storage)
    monkeypatch.setattr(file_scanning_jobs, "build_malware_scanner", lambda _settings: scanner)

    result = asyncio.run(
        file_scanning_jobs.scan_pending_files(
            {"settings": settings, "sessionmaker": db_sessionmaker}
        )
    )

    assert result == {"selected": 1, "clean": 1, "unsafe": 0, "failed": 0}

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            file = await session.get(StoredFile, UUID(stored["id"]))
            assert file is not None and file.scan_status == FileScanStatus.CLEAN

    asyncio.run(inspect())
