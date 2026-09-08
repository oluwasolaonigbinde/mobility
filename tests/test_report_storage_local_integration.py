"""Opt-in real MinIO proof for immutable generated report objects."""

import asyncio
import hashlib
import os
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import boto3
import pytest
from botocore.config import Config
from conftest import auth_headers
from sqlalchemy import select
from test_advertiser_reports import PASSWORD
from test_file_kyc_lifecycle import _create_terminal_submission
from test_kyc import _seed_driver_authority
from test_kyc_retention_authority import migrated_kyc_factory as migrated_kyc_factory
from test_report_issuances import issue_run, request_issuance, run_worker

from app.adapters.storage import StorageObjectConflict, StorageObjectNotFound, StorageUnavailable
from app.adapters.storage.s3 import S3StorageProvider
from app.core.errors import AppError
from app.models.kyc import DriverKycSubmission
from app.models.report_issuance import (
    ReportIssuance,
    ReportPublicationIntent,
    ReportPublicationState,
    ReportPublicationWrite,
)
from app.models.stored_file import StoredFile, StoredObjectDeletion
from app.services import report_issuances as report_issuance_service
from app.services.file_kyc_lifecycle import purge_terminal_file_kyc
from app.services.stored_object_deletions import process_stored_object_deletions

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REPORT_STORAGE_LOCAL_INTEGRATION") != "1",
    reason="real local MinIO report-storage integration was not requested",
)


@pytest.mark.parametrize("versioning", [False, True])
def test_minio_kyc_delete_reply_loss_recovers_without_restoring_payload(
    migrated_kyc_factory, settings, versioning
):
    factory = migrated_kyc_factory
    admin, driver, _, bank_id, files = _seed_driver_authority(factory, suffix="minio-retention")
    endpoint = os.environ["REPORT_STORAGE_ENDPOINT_URL"]
    bucket = f"correction-retention-{uuid4().hex}"

    class LostDeleteReply(S3StorageProvider):
        failed = False

        async def delete_all_versions(self, object_key):
            await super().delete_all_versions(object_key)
            if not self.failed:
                self.failed = True
                raise StorageUnavailable("synthetic lost delete reply")

    provider = LostDeleteReply(
        endpoint_url=endpoint,
        public_endpoint_url=endpoint,
        region="us-east-1",
        bucket=bucket,
        access_key_id=os.environ["REPORT_STORAGE_ACCESS_KEY_ID"],
        secret_access_key=os.environ["REPORT_STORAGE_SECRET_ACCESS_KEY"],
    )
    provider._client.create_bucket(Bucket=bucket)

    if versioning:
        provider._client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )

    async def run():
        now = datetime.now(UTC)
        async with factory() as session:
            for file in await session.scalars(select(StoredFile)):
                provider._client.put_object(
                    Bucket=bucket, Key=file.storage_key, Body=b"old synthetic"
                )
                provider._client.put_object(Bucket=bucket, Key=file.storage_key, Body=b"synthetic")
            submission = await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
                settings=settings,
            )
            identity = submission.id
            await session.commit()
            with pytest.raises(AppError) as failed:
                await purge_terminal_file_kyc(
                    session,
                    storage=provider,
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="synthetic_minio_retention",
                    now=now,
                )
            assert failed.value.code == "FILE_STORAGE_UNAVAILABLE"
            await session.rollback()
        async with factory() as session:
            shell = await session.get(DriverKycSubmission, identity)
            assert shell.purged_at is not None and shell.encrypted_nin is None
            assert set(await session.scalars(select(StoredObjectDeletion.state))) == {"pending"}
        assert await process_stored_object_deletions(factory, storage=provider, limit=10) == 1
        async with factory() as session:
            receipts = list(await session.scalars(select(StoredObjectDeletion)))
            assert len(receipts) == 3
            assert {row.state for row in receipts} == {"completed"}
            assert sorted(row.attempts for row in receipts) == [1, 1, 2]
            for row in receipts:
                assert provider._exact_versions(row.storage_key) == []
                with pytest.raises(StorageObjectNotFound):
                    await provider.stat(row.storage_key)
            for file in await session.scalars(select(StoredFile)):
                await provider.stat(file.storage_key)
            assert len(list(await session.scalars(select(StoredFile)))) == 3

    try:
        asyncio.run(run())
    finally:
        versions = provider._client.list_object_versions(Bucket=bucket)
        for obj in [*versions.get("Versions", []), *versions.get("DeleteMarkers", [])]:
            provider._client.delete_object(
                Bucket=bucket, Key=obj["Key"], VersionId=obj["VersionId"]
            )
        for obj in provider._client.list_objects_v2(Bucket=bucket).get("Contents", []):
            provider._client.delete_object(Bucket=bucket, Key=obj["Key"])
        provider._client.delete_bucket(Bucket=bucket)


@pytest.mark.parametrize("versioning", [False, True])
def test_minio_cleanup_removes_every_exact_key_version_and_marker(versioning):
    bucket = f"correction-report-versions-{uuid4().hex}"
    provider = minio_provider(bucket)
    key = "managed/report/exact.csv"
    peer = key + ".peer"
    try:
        if versioning:
            provider._client.put_bucket_versioning(
                Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
            )
        for payload in (b"old private report", b"current private report"):
            provider._client.put_object(Bucket=bucket, Key=key, Body=payload)
        provider._client.put_object(Bucket=bucket, Key=peer, Body=b"preserve peer")
        if versioning:
            provider._client.delete_object(Bucket=bucket, Key=key)
            assert len(provider._exact_versions(key)) == 3
        asyncio.run(provider.delete_all_versions(key))
        assert provider._exact_versions(key) == []
        with pytest.raises(StorageObjectNotFound):
            asyncio.run(provider.stat(key))
        assert asyncio.run(provider.stat(peer)).size_bytes == len(b"preserve peer")
        asyncio.run(provider.delete_all_versions(key))
        assert provider._put_client.meta.config.retries["total_max_attempts"] == 1
    finally:
        provider._delete_all_versions_sync(key)
        provider._delete_all_versions_sync(peer)
        provider._client.delete_bucket(Bucket=bucket)


def test_minio_late_put_after_timeout_cannot_follow_a_terminal_cleanup(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch
):
    _, advertiser, _, run = issue_run(postgis_db_client, postgis_db_sessionmaker)
    identity = UUID(request_issuance(postgis_db_client, advertiser, run["id"]).json()["id"])
    bucket = f"correction-report-timeout-{uuid4().hex}"
    provider = minio_provider(bucket)
    original = provider._put_client.put_object
    release = threading.Event()
    thread = None
    provider_errors = []

    def lose_reply(**kwargs):
        nonlocal thread

        def finish_later():
            if not release.wait(timeout=30):
                provider_errors.append("synthetic release timed out")
                return
            try:
                original(**kwargs)
            except Exception as exc:
                provider_errors.append(type(exc).__name__)

        thread = threading.Thread(target=finish_later)
        thread.start()
        raise TimeoutError("synthetic response lost before server write completed")

    monkeypatch.setattr(provider._put_client, "put_object", lose_reply)

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            intent = await session.scalar(
                select(ReportPublicationIntent).where(
                    ReportPublicationIntent.report_issuance_id == identity
                )
            )
            receipt = await session.scalar(
                select(ReportPublicationWrite).where(
                    ReportPublicationWrite.publication_intent_id == intent.id
                )
            )
            assert receipt.state == "uncertain"
            assert intent.state == "abandoned"
            return intent

    try:
        assert run_worker(postgis_db_sessionmaker, settings, provider) == 1
        intent = asyncio.run(inspect())
        assert provider._exact_versions(intent.csv_object_key) == []
        assert (
            asyncio.run(
                report_issuance_service.sweep_report_publications(
                    postgis_db_sessionmaker,
                    storage=provider,
                    settings=settings,
                )
            )
            == 0
        )
        release.set()
        thread.join(timeout=10)
        assert not thread.is_alive() and provider_errors == []
        assert asyncio.run(provider.stat(intent.csv_object_key)).size_bytes > 0
        assert (
            asyncio.run(
                report_issuance_service.sweep_report_publications(
                    postgis_db_sessionmaker,
                    storage=provider,
                    settings=settings,
                )
            )
            == 0
        )
        asyncio.run(inspect())
    finally:
        release.set()
        if thread is not None:
            thread.join(timeout=10)
        for item in provider._client.list_objects_v2(Bucket=bucket).get("Contents", []):
            asyncio.run(provider.delete_all_versions(item["Key"]))
        provider._client.delete_bucket(Bucket=bucket)


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


@pytest.mark.parametrize("lost_copy_reply", [False, True])
def test_minio_upload_confirmation_recovers_copy_and_database_failure(
    postgis_db_sessionmaker, settings, monkeypatch, lost_copy_reply
):
    from sqlalchemy import func
    from test_stored_files import advertiser_with_org, upload_payload

    from app.core.errors import AppError
    from app.models.stored_file import StoredFile
    from app.schemas.stored_files import FileUploadCreate
    from app.services.stored_files import confirm_advertiser_upload, create_advertiser_upload_intent

    actor, _ = advertiser_with_org(postgis_db_sessionmaker, "minio-upload-fault@example.com")
    bucket = f"correction-upload-{uuid4().hex}"
    provider = minio_provider(bucket)
    content = b"synthetic protected promotion boundary"
    checksum = hashlib.sha256(content).hexdigest()
    original_copy = provider._client.copy_object

    def copy_then_lose_reply(**kwargs):
        original_copy(**kwargs)
        raise TimeoutError("synthetic copy response loss")

    if lost_copy_reply:
        monkeypatch.setattr(provider._client, "copy_object", copy_then_lose_reply)

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            intent, _ = await create_advertiser_upload_intent(
                session,
                actor_user_id=actor.id,
                payload=FileUploadCreate(
                    **upload_payload(sha256=checksum, size_bytes=len(content))
                ),
                storage=provider,
                settings=settings,
            )
            await session.commit()
            source, identity = intent.object_key, intent.id
        await provider.put(
            object_key=source, content_type="image/png", data=content, checksum_sha256=checksum
        )
        async with postgis_db_sessionmaker() as session:
            if lost_copy_reply:
                with pytest.raises(AppError) as failure:
                    await confirm_advertiser_upload(
                        session,
                        actor_user_id=actor.id,
                        upload_id=identity,
                        storage=provider,
                        settings=settings,
                    )
                assert failure.value.code == "FILE_STORAGE_UNAVAILABLE"
            else:
                await confirm_advertiser_upload(
                    session,
                    actor_user_id=actor.id,
                    upload_id=identity,
                    storage=provider,
                    settings=settings,
                )
            await session.rollback()
        assert (await provider.stat(source)).checksum_sha256 == checksum
        await provider.delete(source)
        async with postgis_db_sessionmaker() as session:
            recovered = await confirm_advertiser_upload(
                session,
                actor_user_id=actor.id,
                upload_id=identity,
                storage=provider,
                settings=settings,
            )
            await session.commit()
            assert recovered.checksum_sha256 == checksum
            assert recovered.scan_status == "pending"
            assert await session.scalar(select(func.count()).select_from(StoredFile)) == 1
            observed = b"".join([chunk async for chunk in provider.stream(recovered.storage_key)])
            assert observed == content

    try:
        asyncio.run(exercise())
    finally:
        for item in provider._client.list_objects_v2(Bucket=bucket).get("Contents", []):
            provider._client.delete_object(Bucket=bucket, Key=item["Key"])
        provider._client.delete_bucket(Bucket=bucket)


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
