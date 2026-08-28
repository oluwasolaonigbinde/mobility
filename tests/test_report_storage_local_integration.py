"""Opt-in real MinIO proof for immutable generated report objects."""

import asyncio
import hashlib
import os
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config

from app.adapters.storage import StorageObjectConflict
from app.adapters.storage.s3 import S3StorageProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REPORT_STORAGE_LOCAL_INTEGRATION") != "1",
    reason="real local MinIO report-storage integration was not requested",
)


def test_minio_generated_report_put_is_idempotent_and_no_overwrite() -> None:
    endpoint = os.environ["REPORT_STORAGE_ENDPOINT_URL"]
    access_key = os.environ["REPORT_STORAGE_ACCESS_KEY_ID"]
    secret_key = os.environ["REPORT_STORAGE_SECRET_ACCESS_KEY"]
    bucket = os.environ.get("REPORT_STORAGE_BUCKET", "cardvert-report-integration")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)

    provider = S3StorageProvider(
        endpoint_url=endpoint,
        public_endpoint_url=endpoint,
        region="us-east-1",
        bucket=bucket,
        access_key_id=access_key,
        secret_access_key=secret_key,
    )
    prefix = f"integration/report-issuance/{uuid4()}"
    replay_key = f"{prefix}/replay.csv"
    race_key = f"{prefix}/race.pdf"
    first_bytes = b"section,label,value\nmetric,Trip count,4\n"
    changed_bytes = b"section,label,value\nmetric,Trip count,5\n"
    first_hash = hashlib.sha256(first_bytes).hexdigest()
    changed_hash = hashlib.sha256(changed_bytes).hexdigest()

    async def exercise() -> None:
        first = await provider.put(
            object_key=replay_key,
            content_type="text/csv",
            data=first_bytes,
            checksum_sha256=first_hash,
        )
        replay = await provider.put(
            object_key=replay_key,
            content_type="text/csv",
            data=first_bytes,
            checksum_sha256=first_hash,
        )
        assert first == replay
        with pytest.raises(StorageObjectConflict):
            await provider.put(
                object_key=replay_key,
                content_type="text/csv",
                data=changed_bytes,
                checksum_sha256=changed_hash,
            )

        raced = await asyncio.gather(
            provider.put(
                object_key=race_key,
                content_type="application/pdf",
                data=first_bytes,
                checksum_sha256=first_hash,
            ),
            provider.put(
                object_key=race_key,
                content_type="application/pdf",
                data=changed_bytes,
                checksum_sha256=changed_hash,
            ),
            return_exceptions=True,
        )
        assert sum(not isinstance(result, Exception) for result in raced) == 1
        assert sum(isinstance(result, StorageObjectConflict) for result in raced) == 1
        observed = await provider.stat(race_key)
        assert observed.checksum_sha256 in {first_hash, changed_hash}

    try:
        asyncio.run(exercise())
    finally:
        client.delete_object(Bucket=bucket, Key=replay_key)
        client.delete_object(Bucket=bucket, Key=race_key)
