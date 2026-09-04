"""Opt-in real MinIO proof for immutable generated report objects."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import boto3
import pytest
from botocore.config import Config
from conftest import auth_headers
from sqlalchemy import select
from test_advertiser_reports import PASSWORD
from test_report_issuances import issue_run, request_issuance, run_worker

from app.adapters.storage import StorageObjectConflict, StorageObjectNotFound
from app.adapters.storage.s3 import S3StorageProvider
from app.models.report_issuance import (
    ReportIssuance,
    ReportPublicationIntent,
    ReportPublicationState,
)
from app.services import report_issuances as report_issuance_service

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


def test_minio_generation_scoped_cleanup_deletes_only_registered_keys() -> None:
    """The exact provider primitives R51 cleanup relies on, against a real object store."""
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
    intent = uuid4()
    prefix = f"integration/report-publication/{intent}"
    first_bytes = b"section,label,value\nmetric,Trip count,4\n"
    second_bytes = b"section,label,value\nmetric,Trip count,5\n"
    first_hash = hashlib.sha256(first_bytes).hexdigest()
    second_hash = hashlib.sha256(second_bytes).hexdigest()
    # Generation-unique keys carrying intent, generation and content hash.
    first_key = f"{prefix}/g1/{first_hash}.csv"
    second_key = f"{prefix}/g2/{second_hash}.csv"

    async def exercise() -> None:
        await provider.put(
            object_key=first_key,
            content_type="text/csv",
            data=first_bytes,
            checksum_sha256=first_hash,
        )
        await provider.put(
            object_key=second_key,
            content_type="text/csv",
            data=second_bytes,
            checksum_sha256=second_hash,
        )

        # Cleaning one abandoned generation must never reach the sibling generation.
        await provider.delete(first_key)
        with pytest.raises(StorageObjectNotFound):
            await provider.stat(first_key)
        assert (await provider.stat(second_key)).checksum_sha256 == second_hash

        # Deleting a registered key again is idempotent, so a re-claimed cleanup is safe.
        await provider.delete(first_key)
        with pytest.raises(StorageObjectNotFound):
            await provider.stat(first_key)

        # A late stale write is observable, which is what keeps a tombstone honest.
        await provider.put(
            object_key=first_key,
            content_type="text/csv",
            data=first_bytes,
            checksum_sha256=first_hash,
        )
        assert (await provider.stat(first_key)).checksum_sha256 == first_hash

    try:
        asyncio.run(exercise())
    finally:
        client.delete_object(Bucket=bucket, Key=first_key)
        client.delete_object(Bucket=bucket, Key=second_key)


def minio_provider(bucket: str) -> S3StorageProvider:
    endpoint = os.environ["REPORT_STORAGE_ENDPOINT_URL"]
    access_key = os.environ["REPORT_STORAGE_ACCESS_KEY_ID"]
    secret_key = os.environ["REPORT_STORAGE_SECRET_ACCESS_KEY"]
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
    return S3StorageProvider(
        endpoint_url=endpoint,
        public_endpoint_url=endpoint,
        region="us-east-1",
        bucket=bucket,
        access_key_id=access_key,
        secret_access_key=secret_key,
    )


def test_minio_publication_crash_is_recovered_and_reissued_end_to_end(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    """Real PostgreSQL, real MinIO, real renderer: a crashed publisher leaves no orphan."""
    bucket = os.environ.get("REPORT_STORAGE_BUCKET", "cardvert-report-integration")
    provider = minio_provider(bucket)
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    issuance_id = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    written: list[str] = []

    class Crash(BaseException):
        pass

    async def crash_before_finalizing(*args, **kwargs):
        raise Crash

    async def read_generations() -> list[ReportPublicationIntent]:
        async with postgis_db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(ReportPublicationIntent)
                    .where(ReportPublicationIntent.report_issuance_id == issuance_id)
                    .order_by(ReportPublicationIntent.generation)
                )
            )

    try:
        publish = report_issuance_service._complete_publication
        monkeypatch.setattr(
            report_issuance_service, "_complete_publication", crash_before_finalizing
        )
        with pytest.raises(Crash):
            run_worker(postgis_db_sessionmaker, settings, provider)
        monkeypatch.setattr(report_issuance_service, "_complete_publication", publish)

        stranded = asyncio.run(read_generations())[0]
        assert stranded.state == ReportPublicationState.PUBLISHING
        orphans = [stranded.csv_object_key, stranded.pdf_object_key]
        written.extend(orphans)
        # Both orphans really are in the bucket.
        for key in orphans:
            assert asyncio.run(provider.stat(key)).object_key == key

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
        assert run_worker(postgis_db_sessionmaker, settings, provider) == 1

        first, second = asyncio.run(read_generations())
        published = [second.csv_object_key, second.pdf_object_key]
        written.extend(published)
        assert first.state == ReportPublicationState.CLEANED
        assert second.state == ReportPublicationState.COMPLETE

        # The orphaned generation's objects are gone from the real bucket.
        for key in orphans:
            with pytest.raises(StorageObjectNotFound):
                asyncio.run(provider.stat(key))
        # The reissued generation's objects are present and intact.
        for key in published:
            observed = asyncio.run(provider.stat(key))
            assert observed.object_key == key
            assert key.endswith(f"{observed.checksum_sha256}.{key.rsplit('.', 1)[1]}")

        ready = postgis_db_client.get(
            f"/api/v1/advertiser/report-issuances/{issuance_id}",
            headers=auth_headers(postgis_db_client, advertiser.email, PASSWORD),
        )
        assert ready.status_code == 200, ready.text
        assert ready.json()["status"] == "ready"
    finally:
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["REPORT_STORAGE_ENDPOINT_URL"],
            region_name="us-east-1",
            aws_access_key_id=os.environ["REPORT_STORAGE_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["REPORT_STORAGE_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        for key in written:
            client.delete_object(Bucket=bucket, Key=key)
