# ruff: noqa: F401, F811

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from conftest import auth_headers, create_test_campaign, create_test_campaign_creative
from sqlalchemy import func, select, update
from starlette import status as http_status
from test_campaign_assignments import assignment_payload, create_assignment_ready_graph
from test_campaign_creatives import PASSWORD
from test_file_scanning import (
    advertiser_with_org,
    confirm_png,
    file_boundaries,
    scan_file,
)

from app.models.campaign import CampaignCreative
from app.models.stored_file import (
    FilePurpose,
    FileScanStatus,
    FileUploadIntent,
    StoredFile,
    UploadIntentStatus,
)
from app.schemas.campaigns import CreativeCreate
from app.services.campaigns import create_campaign_creative


def managed_payload(file_id: str, **changes):
    payload = {
        "name": "Managed exterior wrap",
        "creative_type": "image",
        "placement": "vehicle_exterior",
        "stored_file_id": file_id,
        "width_px": 1200,
        "height_px": 800,
        "status": "draft",
        "metadata": {"source": "managed-upload"},
    }
    payload.update(changes)
    return payload


def test_clean_managed_file_binding_derives_identity_and_same_retry_converges(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    advertiser, organization = advertiser_with_org(
        db_sessionmaker, "managed-creative@example.com"
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    stored = confirm_png(db_client, storage, advertiser.email)
    assert scan_file(db_sessionmaker, stored["id"], storage, scanner) == FileScanStatus.CLEAN
    url = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives"
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    first = db_client.post(url, headers=headers, json=managed_payload(stored["id"]))
    replay = db_client.post(url, headers=headers, json=managed_payload(stored["id"]))

    assert first.status_code == http_status.HTTP_201_CREATED
    assert replay.status_code == http_status.HTTP_201_CREATED
    assert replay.json()["id"] == first.json()["id"]
    assert first.json()["stored_file_id"] == stored["id"]
    assert first.json()["asset_source"] == "managed_file"
    assert first.json()["scan_status"] == "clean"
    assert first.json()["mime_type"] == "image/png"
    assert first.json()["checksum"] == stored["checksum_sha256"]
    assert first.json()["asset_url"] is None
    assert first.json()["status"] == "draft"

    changed = db_client.post(
        url,
        headers=headers,
        json=managed_payload(stored["id"], name="Changed replay"),
    )
    assert changed.status_code == http_status.HTTP_409_CONFLICT
    assert changed.json()["error"]["code"] == "CREATIVE_FILE_ALREADY_BOUND"

    type_change = db_client.patch(
        f"{url}/{first.json()['id']}",
        headers=headers,
        json={"creative_type": "video"},
    )
    assert type_change.status_code == http_status.HTTP_409_CONFLICT
    assert type_change.json()["error"]["code"] == "CREATIVE_TYPE_MISMATCH"


def test_pending_infected_cross_tenant_and_url_only_files_cannot_bind(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    owner_a, organization_a = advertiser_with_org(
        db_sessionmaker, "managed-owner-a@example.com"
    )
    owner_b, organization_b = advertiser_with_org(
        db_sessionmaker, "managed-owner-b@example.com"
    )
    campaign_a = create_test_campaign(
        db_sessionmaker,
        organization_id=organization_a.id,
        created_by_user_id=owner_a.id,
    )
    campaign_b = create_test_campaign(
        db_sessionmaker,
        organization_id=organization_b.id,
        created_by_user_id=owner_b.id,
    )
    pending = confirm_png(db_client, storage, owner_a.email)
    infected = confirm_png(db_client, storage, owner_b.email)
    scanner.infected_with = "Eicar-Test-Signature"
    assert scan_file(db_sessionmaker, infected["id"], storage, scanner) == FileScanStatus.INFECTED

    headers_a = auth_headers(db_client, owner_a.email, PASSWORD)
    pending_response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign_a.id}/creatives",
        headers=headers_a,
        json=managed_payload(pending["id"]),
    )
    cross_tenant = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign_a.id}/creatives",
        headers=headers_a,
        json=managed_payload(infected["id"]),
    )
    url_only = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign_a.id}/creatives",
        headers=headers_a,
        json={
            "name": "Legacy bypass",
            "creative_type": "image",
            "placement": "vehicle_exterior",
            "asset_url": "https://example.com/bypass.png",
            "status": "draft",
        },
    )
    ready_claim = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign_b.id}/creatives",
        headers=auth_headers(db_client, owner_b.email, PASSWORD),
        json=managed_payload(infected["id"], status="ready"),
    )

    assert pending_response.status_code == http_status.HTTP_409_CONFLICT
    assert pending_response.json()["error"]["code"] == "CREATIVE_FILE_NOT_CLEARED"
    assert cross_tenant.status_code == http_status.HTTP_404_NOT_FOUND
    assert cross_tenant.json()["error"]["code"] == "STORED_FILE_NOT_FOUND"
    assert url_only.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert ready_claim.status_code == http_status.HTTP_409_CONFLICT
    assert ready_claim.json()["error"]["code"] == "CREATIVE_READY_REQUIRES_REVIEW"


def test_legacy_url_creative_remains_readable_but_has_no_managed_authority(
    db_client, db_sessionmaker
) -> None:
    advertiser, organization = advertiser_with_org(
        db_sessionmaker, "legacy-creative-read@example.com"
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    legacy = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        asset_url="https://legacy.example.com/wrap.png",
    )

    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{legacy.id}",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["asset_url"] == "https://legacy.example.com/wrap.png"
    assert response.json()["asset_source"] == "legacy_url"
    assert response.json()["stored_file_id"] is None
    assert response.json()["scan_status"] is None


def test_legacy_ready_url_cannot_authorize_a_new_offer(db_client, db_sessionmaker) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    creative_id = campaign.campaign_metadata["_test_creative_id"]

    async def make_legacy() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                update(CampaignCreative)
                .where(CampaignCreative.id == UUID(creative_id))
                .values(stored_file_id=None, asset_url="https://legacy.example/wrap.png")
            )
            await session.commit()

    asyncio.run(make_legacy())
    response = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=assignment_payload(campaign, profile, vehicle),
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "MANAGED_CLEAN_CREATIVE_REQUIRED"


def test_concurrent_same_file_create_converges_on_postgres(postgis_db_sessionmaker) -> None:
    advertiser, organization = advertiser_with_org(
        postgis_db_sessionmaker, "managed-race@example.com"
    )
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    stored_file_id = uuid4()

    async def seed_file() -> None:
        async with postgis_db_sessionmaker() as session:
            intent = FileUploadIntent(
                organization_id=organization.id,
                uploader_user_id=advertiser.id,
                client_request_id=uuid4(),
                request_fingerprint="b" * 64,
                purpose=FilePurpose.CREATIVE.value,
                original_filename="race.png",
                declared_content_type="image/png",
                declared_size_bytes=128,
                declared_sha256="a" * 64,
                object_key=f"test-intents/{stored_file_id}",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                status=UploadIntentStatus.CONFIRMED.value,
            )
            session.add(intent)
            await session.flush()
            session.add(
                StoredFile(
                    id=stored_file_id,
                    upload_intent_id=intent.id,
                    organization_id=organization.id,
                    uploader_user_id=advertiser.id,
                    purpose=FilePurpose.CREATIVE.value,
                    original_filename="race.png",
                    storage_key=f"test-files/{stored_file_id}",
                    content_type="image/png",
                    size_bytes=128,
                    checksum_sha256="a" * 64,
                    scan_status=FileScanStatus.CLEAN.value,
                    actual_content_type="image/png",
                    scan_attempts=1,
                    scanned_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(seed_file())

    async def bind_concurrently() -> tuple[list[tuple[UUID, bool]], int]:
        start = asyncio.Event()

        async def bind() -> tuple[UUID, bool]:
            async with postgis_db_sessionmaker() as session:
                await start.wait()
                creative, created = await create_campaign_creative(
                    session,
                    user_id=advertiser.id,
                    campaign_id=campaign.id,
                    payload=CreativeCreate(**managed_payload(str(stored_file_id))),
                )
                await session.commit()
                return creative.id, created

        first = asyncio.create_task(bind())
        second = asyncio.create_task(bind())
        start.set()
        results = await asyncio.gather(first, second)
        async with postgis_db_sessionmaker() as session:
            count = await session.scalar(
                select(func.count()).select_from(CampaignCreative).where(
                    CampaignCreative.stored_file_id == stored_file_id
                )
            )
        return results, int(count or 0)

    results, count = asyncio.run(bind_concurrently())
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    assert count == 1
