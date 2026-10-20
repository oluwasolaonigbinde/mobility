import asyncio

import pytest
from test_driver_person_payee_onboarding import (
    _application,
    _register,
    _seed_clean_kyc_files,
)
from test_stored_files import FakeStorageProvider

from app.core.errors import AppError
from app.models.stored_file import FilePurpose, StoredFile, StoredObjectDeletion
from app.services.kyc import _require_files
from app.services.stored_object_deletions import (
    delete_stored_object,
    ensure_stored_object_deletion,
)


def test_agreement_migration_is_reachable_from_the_real_alembic_chain(monkeypatch):
    from database_helpers import (
        configured_postgres_url,
        create_database_from_url,
        drop_database,
        fetch_all,
        upgrade_to,
    )

    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, "head", monkeypatch)
        columns = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    url,
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='driver_kyc_submissions'",
                )
            )
        }
        assert {
            "agreement_version",
            "agreement_accepted_at",
            "agreement_acceptance_requested",
            "bank_check_receipt_sha256",
            "bank_name_confirmed",
        } <= columns
        assert asyncio.run(fetch_all(url, "SELECT version_num FROM alembic_version")) == [
            ("0111_fix_daily_pay_policy",)
        ]
    finally:
        asyncio.run(drop_database(url))


def test_retirement_serializes_attachment_and_denies_provider_deleted_gap(
    postgis_db_client, postgis_db_sessionmaker, settings
):
    client, sessions = postgis_db_client, postgis_db_sessionmaker
    _register(client, sessions, settings, suffix="retire-race")
    application = _application(sessions, email="person-payee-retire-race@example.com")
    files = _seed_clean_kyc_files(sessions, email=application.email)

    async def run():
        started, release, attaching = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Storage(FakeStorageProvider):
            async def delete_all_versions(self, key):
                started.set()
                await release.wait()
                await super().delete_all_versions(key)

        storage = Storage()
        async with sessions() as session:
            stored = await session.get(StoredFile, files["driver_license"])
            intent = await ensure_stored_object_deletion(
                session,
                storage_key=stored.storage_key,
                object_checksum_sha256=stored.checksum_sha256,
                reason="agreement_replaced",
                owner_type="retired_driver_agreement",
                owner_id=stored.id,
                organization_id=None,
                subject_user_id=application.user_id,
                stored_file_id=stored.id,
                upload_intent_id=stored.upload_intent_id,
            )
            intent_id = intent.id
            await session.commit()

        async def remove():
            async with sessions() as session:
                intent = await session.get(StoredObjectDeletion, intent_id)
                await delete_stored_object(session, intent=intent, storage=storage)

        async def attach():
            async with sessions() as session:
                attaching.set()
                with pytest.raises(AppError) as error:
                    await _require_files(
                        session,
                        file_ids=files,
                        actor_user_id=application.user_id,
                        purpose=FilePurpose.DRIVER_KYC,
                    )
                assert error.value.code == "KYC_DOCUMENT_NOT_CLEARED"

        deleting = asyncio.create_task(remove())
        await started.wait()
        attachment = asyncio.create_task(attach())
        await attaching.wait()
        release.set()
        await asyncio.gather(deleting, attachment)
        async with sessions() as session:
            assert await session.get(StoredFile, files["driver_license"]) is not None
            assert (await session.get(StoredObjectDeletion, intent_id)).state == "provider_deleted"
        # Attachment remains denied after provider commit and before finalization.
        await attach()

    asyncio.run(run())
