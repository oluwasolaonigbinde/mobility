"""Optional real MinIO + ClamAV upload-to-creative integration proof."""

import hashlib
import os

import httpx
import pytest
from conftest import auth_headers, create_test_campaign
from test_campaign_creatives import PASSWORD
from test_file_scanning import advertiser_with_org, scan_file

from app.adapters.scanner.clamav import ClamAVScanner
from app.adapters.storage.s3 import S3StorageProvider
from app.api.v1.dependencies import get_storage_provider
from app.models.stored_file import FileScanStatus


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_FILE_INTEGRATION") != "1",
    reason="real local MinIO/ClamAV integration was not requested",
)
def test_real_private_upload_scan_and_creative_binding(db_client, db_sessionmaker) -> None:
    storage = S3StorageProvider(
        endpoint_url=os.environ["LOCAL_MINIO_ENDPOINT"],
        public_endpoint_url=os.environ["LOCAL_MINIO_ENDPOINT"],
        region="us-east-1",
        bucket="cardvert-private",
        access_key_id=os.environ["LOCAL_MINIO_ACCESS_KEY"],
        secret_access_key=os.environ["LOCAL_MINIO_SECRET_KEY"],
    )
    scanner = ClamAVScanner(
        host=os.environ["LOCAL_CLAMAV_HOST"],
        port=3310,
        timeout_seconds=30,
    )
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    try:
        advertiser, organization = advertiser_with_org(
            db_sessionmaker, "real-managed-creative@example.com"
        )
        campaign = create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=advertiser.id,
        )
        content = b"\x89PNG\r\n\x1a\n" + b"real-local-managed-creative" * 4
        checksum = hashlib.sha256(content).hexdigest()
        headers = auth_headers(db_client, advertiser.email, PASSWORD)
        intent = db_client.post(
            "/api/v1/advertiser/files/uploads",
            headers=headers,
            json={
                "client_request_id": "00000000-0000-4000-8000-000000000051",
                "purpose": "creative",
                "filename": "real-wrap.png",
                "content_type": "image/png",
                "size_bytes": len(content),
                "sha256": checksum,
            },
        )
        assert intent.status_code == 201
        upload = intent.json()["upload"]
        uploaded = httpx.post(
            upload["url"],
            data=upload["fields"],
            files={"file": ("real-wrap.png", content, "image/png")},
        )
        assert uploaded.status_code in {200, 204}
        confirmed = db_client.post(
            f"/api/v1/advertiser/files/uploads/{intent.json()['upload_id']}/confirm",
            headers=headers,
        )
        assert confirmed.status_code == 201
        file_id = confirmed.json()["id"]
        assert scan_file(db_sessionmaker, file_id, storage, scanner) == FileScanStatus.CLEAN
        creative = db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
            headers=headers,
            json={
                "name": "Real local wrap",
                "creative_type": "image",
                "placement": "vehicle_exterior",
                "stored_file_id": file_id,
                "status": "draft",
            },
        )
        assert creative.status_code == 201
        assert creative.json()["stored_file_id"] == file_id
        assert creative.json()["scan_status"] == "clean"
        assert creative.json()["checksum"] == checksum
        assert creative.json()["asset_url"] is None
    finally:
        db_client.app.dependency_overrides.pop(get_storage_provider, None)
