"""Optional real MinIO + ClamAV upload-to-protected-KYC integration proof."""

import hashlib
import os
from uuid import uuid4

import httpx
import pytest
from conftest import auth_headers
from test_file_scanning import scan_file
from test_kyc import PASSWORD, _seed_driver_authority

from app.adapters.scanner.clamav import ClamAVScanner
from app.adapters.storage.s3 import S3StorageProvider
from app.api.v1.dependencies import get_storage_provider
from app.models.stored_file import FileScanStatus


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_FILE_INTEGRATION") != "1",
    reason="real local MinIO/ClamAV integration was not requested",
)
def test_real_private_upload_scan_and_protected_kyc_binding(
    db_client, db_sessionmaker
) -> None:
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
        _, driver, _, bank_id, _ = _seed_driver_authority(
            db_sessionmaker, suffix="real-local"
        )
        headers = auth_headers(db_client, driver.email, PASSWORD)
        file_ids: dict[str, str] = {}
        for index, document_type in enumerate(
            ("driver_license", "driver_photo", "signed_agreement"), start=1
        ):
            content = b"\x89PNG\r\n\x1a\n" + f"local-kyc-{index}".encode() * 8
            checksum = hashlib.sha256(content).hexdigest()
            intent = db_client.post(
                "/api/v1/driver/files/uploads",
                headers=headers,
                json={
                    "client_request_id": str(uuid4()),
                    "purpose": "driver_kyc",
                    "filename": f"{document_type}.png",
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
                files={"file": (f"{document_type}.png", content, "image/png")},
            )
            assert uploaded.status_code in {200, 204}
            confirmed = db_client.post(
                f"/api/v1/driver/files/uploads/{intent.json()['upload_id']}/confirm",
                headers=headers,
            )
            assert confirmed.status_code == 201
            file_id = confirmed.json()["id"]
            assert scan_file(db_sessionmaker, file_id, storage, scanner) == FileScanStatus.CLEAN
            file_ids[document_type] = file_id

        submitted = db_client.post(
            "/api/v1/driver/kyc/submissions",
            headers=headers,
            json={
                "client_request_id": str(uuid4()),
                "nin": "12345678901",
                "bank_account_version_id": str(bank_id),
                "driver_license_file_id": file_ids["driver_license"],
                "driver_photo_file_id": file_ids["driver_photo"],
                "signed_agreement_file_id": file_ids["signed_agreement"],
            },
        )
        assert submitted.status_code == 201
        assert submitted.json()["masked_nin"] == "*******8901"
        assert submitted.json()["status"] == "pending_review"
    finally:
        db_client.app.dependency_overrides.pop(get_storage_provider, None)
