import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_kyc import NIN, PASSWORD, _seed_driver_authority
from test_stored_files import FakeStorageProvider

from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.storage import StorageUnavailable
from app.api.v1.dependencies import get_storage_provider
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.kyc import DriverKycDocument, DriverKycSubmission, KycSubmissionStatus
from app.models.stored_file import StoredFile
from app.services.file_kyc_lifecycle import purge_terminal_file_kyc
from app.services.kyc import submit_driver_kyc


async def _create_terminal_submission(
    session,
    *,
    driver_id,
    bank_id,
    files,
    now,
) -> DriverKycSubmission:
    view = await submit_driver_kyc(
        session,
        actor_user_id=driver_id,
        client_request_id=uuid4(),
        nin=NIN,
        bank_account_version_id=bank_id,
        document_file_ids={
            name: files[name]
            for name in ("driver_license", "driver_photo", "signed_agreement")
        },
        crypto=EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1),
    )
    view.submission.status = KycSubmissionStatus.REJECTED
    view.submission.created_at = now - timedelta(days=31)
    await session.flush()
    return view.submission


def test_file_kyc_retention_is_dry_run_first_audited_and_removes_terminal_objects(
    db_sessionmaker,
) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="retention"
    )
    storage = FakeStorageProvider()
    now = datetime.now(UTC)

    async def exercise():
        async with db_sessionmaker() as session:
            submission = await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
            )
            await session.commit()
            submission_id = submission.id
        async with db_sessionmaker() as session:
            planned = await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=True,
                actor_user_id=admin.id,
                reason="synthetic_retention_review",
                now=now,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            assert await session.get(DriverKycSubmission, submission_id) is not None
            executed = await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=False,
                actor_user_id=admin.id,
                reason="synthetic_retention_execution",
                now=now,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            submission_count = int(
                await session.scalar(select(func.count(DriverKycSubmission.id))) or 0
            )
            document_count = int(
                await session.scalar(select(func.count(DriverKycDocument.id))) or 0
            )
            actions = list((await session.scalars(select(AuditEvent.action))).all())
        return planned, executed, submission_count, document_count, actions

    planned, executed, submission_count, document_count, actions = asyncio.run(exercise())
    assert planned.dry_run is True
    assert planned.eligible_submissions == 1
    assert planned.purged_submissions == planned.purged_files == 0
    assert executed.purged_submissions == 1
    assert executed.purged_files == 3
    assert submission_count == document_count == 0
    assert len(storage.deleted) == 3
    assert "file_kyc.retention_dry_run" in actions
    assert "file_kyc.retention_executed" in actions


def test_shared_files_survive_old_rejected_version_and_missing_policy_fails_closed(
    db_sessionmaker,
) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="retention-shared"
    )
    storage = FakeStorageProvider()
    now = datetime.now(UTC)

    async def exercise():
        async with db_sessionmaker() as session:
            await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
            )
            await submit_driver_kyc(
                session,
                actor_user_id=driver.id,
                client_request_id=uuid4(),
                nin="10987654321",
                bank_account_version_id=bank_id,
                document_file_ids={
                    name: files[name]
                    for name in ("driver_license", "driver_photo", "signed_agreement")
                },
                crypto=EnvelopeCryptoProvider(
                    keys={1: bytes(range(32))}, active_key_version=1
                ),
            )
            await session.commit()
        async with db_sessionmaker() as session:
            unavailable = await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=None,
                limit=10,
                dry_run=True,
                actor_user_id=admin.id,
                reason="policy_readiness_check",
                now=now,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as raised:
                await purge_terminal_file_kyc(
                    session,
                    storage=storage,
                    retention_days=None,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="unsafe_missing_policy",
                    now=now,
                )
            assert raised.value.code == "FILE_KYC_RETENTION_POLICY_REQUIRED"
            await session.rollback()
        async with db_sessionmaker() as session:
            executed = await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=False,
                actor_user_id=admin.id,
                reason="synthetic_shared_file_retention",
                now=now,
            )
            await session.commit()
            remaining_files = int(await session.scalar(select(func.count(StoredFile.id))) or 0)
            remaining_submissions = int(
                await session.scalar(select(func.count(DriverKycSubmission.id))) or 0
            )
        return unavailable, executed, remaining_files, remaining_submissions

    unavailable, executed, remaining_files, remaining_submissions = asyncio.run(exercise())
    assert unavailable.policy_configured is False
    assert executed.purged_submissions == 1
    assert executed.purged_files == 0
    assert remaining_files == 6
    assert remaining_submissions == 1
    assert storage.deleted == []


def test_storage_outage_rolls_back_all_file_kyc_retention_rows(db_sessionmaker) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="retention-outage"
    )
    storage = FakeStorageProvider()
    storage.unavailable = True
    now = datetime.now(UTC)

    async def exercise() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as raised:
                await purge_terminal_file_kyc(
                    session,
                    storage=storage,
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="synthetic_outage_probe",
                    now=now,
                )
            assert raised.value.code == "FILE_STORAGE_UNAVAILABLE"
            await session.rollback()
        async with db_sessionmaker() as session:
            submissions = int(
                await session.scalar(select(func.count(DriverKycSubmission.id))) or 0
            )
            documents = int(
                await session.scalar(select(func.count(DriverKycDocument.id))) or 0
            )
            return submissions, documents

    assert asyncio.run(exercise()) == (1, 3)


def test_mid_batch_storage_outage_is_idempotently_recoverable(db_sessionmaker) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="retention-mid-batch"
    )
    storage = FakeStorageProvider()
    now = datetime.now(UTC)

    async def exercise() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
            )
            await session.commit()

        original_delete = storage.delete
        calls = 0

        async def fail_second_delete(object_key: str) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StorageUnavailable("synthetic mid-batch outage")
            await original_delete(object_key)

        storage.delete = fail_second_delete  # type: ignore[method-assign]
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as raised:
                await purge_terminal_file_kyc(
                    session,
                    storage=storage,
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="synthetic_mid_batch_outage",
                    now=now,
                )
            assert raised.value.code == "FILE_STORAGE_UNAVAILABLE"
            await session.rollback()

        storage.delete = original_delete  # type: ignore[method-assign]
        async with db_sessionmaker() as session:
            retried = await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=False,
                actor_user_id=admin.id,
                reason="synthetic_mid_batch_retry",
                now=now,
            )
            await session.commit()
        return retried.purged_submissions, retried.purged_files

    assert asyncio.run(exercise()) == (1, 3)
    assert len(set(storage.deleted)) == 3


def test_admin_retention_endpoint_is_dry_run_first_and_policy_gated(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    admin, driver, _, _, _ = _seed_driver_authority(db_sessionmaker, suffix="retention-api")
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    headers = auth_headers(db_client, admin.email, PASSWORD)
    driver_auth = auth_headers(db_client, driver.email, PASSWORD)
    configured = settings.model_copy(update={"file_kyc_retention_days": 30})

    try:
        db_client.app.dependency_overrides[get_settings] = lambda: configured
        planned = db_client.post(
            "/api/v1/admin/operations/file-kyc-retention",
            headers=headers,
            json={"dry_run": True, "reason": "synthetic_api_retention_review"},
        )
        forbidden = db_client.post(
            "/api/v1/admin/operations/file-kyc-retention",
            headers=driver_auth,
            json={"dry_run": True, "reason": "synthetic_api_retention_review"},
        )
        db_client.app.dependency_overrides[get_settings] = lambda: settings.model_copy(
            update={"file_kyc_retention_days": None}
        )
        unsafe = db_client.post(
            "/api/v1/admin/operations/file-kyc-retention",
            headers=headers,
            json={"dry_run": False, "reason": "unsafe_api_retention_execution"},
        )
    finally:
        db_client.app.dependency_overrides.pop(get_storage_provider, None)
        db_client.app.dependency_overrides.pop(get_settings, None)

    assert planned.status_code == 200, planned.text
    assert planned.json()["policy_configured"] is True
    assert planned.json()["dry_run"] is True
    assert forbidden.status_code == 403
    assert unsafe.status_code == 409
    assert unsafe.json()["error"]["code"] == "FILE_KYC_RETENTION_POLICY_REQUIRED"


def test_postgres_retention_lock_prevents_concurrent_double_purge(
    postgis_db_sessionmaker,
) -> None:
    sessionmaker = postgis_db_sessionmaker
    admin, driver, _, bank_id, files = _seed_driver_authority(
        sessionmaker, suffix="retention-pg-lock"
    )
    storage = FakeStorageProvider()
    now = datetime.now(UTC)

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()
        original_delete = storage.delete
        first_delete = True

        async def blocking_delete(object_key: str) -> None:
            nonlocal first_delete
            if first_delete:
                first_delete = False
                entered.set()
                await release.wait()
            await original_delete(object_key)

        storage.delete = blocking_delete  # type: ignore[method-assign]
        async with sessionmaker() as seed_session:
            await _create_terminal_submission(
                seed_session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
            )
            await seed_session.commit()

        async def first_run():
            async with sessionmaker() as session:
                result = await purge_terminal_file_kyc(
                    session,
                    storage=storage,
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="synthetic_pg_retention_first",
                    now=now,
                )
                await session.commit()
                return result

        first_task = asyncio.create_task(first_run())
        await entered.wait()
        async with sessionmaker() as second_session:
            second = await purge_terminal_file_kyc(
                second_session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=False,
                actor_user_id=admin.id,
                reason="synthetic_pg_retention_second",
                now=now,
            )
            await second_session.commit()
        release.set()
        first = await first_task
        async with sessionmaker() as session:
            remaining = int(
                await session.scalar(select(func.count(DriverKycSubmission.id))) or 0
            )
            executions = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "file_kyc.retention_executed"
                    )
                )
                or 0
            )
        return first, second, remaining, executions

    first, second, remaining, executions = asyncio.run(exercise())
    assert first.lock_acquired is True
    assert first.purged_submissions == 1
    assert second.lock_acquired is False
    assert second.purged_submissions == 0
    assert remaining == 0
    assert executions == 1
    assert len(storage.deleted) == 3
