import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from test_driver_person_payee_onboarding import (
    _application,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)
from test_stored_files import FakeStorageProvider

from app.adapters.storage import ObjectMetadata
from app.core.errors import AppError
from app.models.driver_application import DriverApplication
from app.models.stored_file import FilePurpose, FileUploadIntent, StoredFile, StoredObjectDeletion
from app.services.kyc import _require_files
from app.services.stored_object_deletions import (
    delete_stored_object,
    ensure_stored_object_deletion,
    process_stored_object_deletions,
)


def migration():
    path = Path(__file__).parents[1] / "alembic/versions/0102_driver_agreement_acceptance.py"
    spec = importlib.util.spec_from_file_location("agreement_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("shared", [False, True])
def test_migration_retires_private_objects_retryably_without_fabricating_consent(
    postgis_db_client, postgis_db_sessionmaker, settings, shared
):
    client, sessions = postgis_db_client, postgis_db_sessionmaker
    token, _ = _register(client, sessions, settings, suffix="retirement")
    application = _application(sessions, email="person-payee-retirement@example.com")
    files = _seed_clean_kyc_files(sessions, email=application.email)
    response = client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(token, files, client),
    )
    assert response.status_code == 201, response.text
    unused = _seed_clean_kyc_files(sessions, email=application.email)
    file_id = files["driver_license"] if shared else unused["driver_license"]
    storage = FakeStorageProvider()

    async def run():
        async with sessions() as session:
            stored = await session.get(StoredFile, file_id)
            upload = await session.get(FileUploadIntent, stored.upload_intent_id)
            keys = {stored.storage_key, upload.object_key}
            for key in keys:
                storage.objects[key] = ObjectMetadata(
                    key, stored.size_bytes, stored.content_type, stored.checksum_sha256
                )
            await session.execute(
                text(
                    "ALTER TABLE driver_kyc_documents DROP CONSTRAINT ck_driver_kyc_documents_type"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE driver_kyc_documents ADD CONSTRAINT ck_driver_kyc_documents_type "
                    "CHECK (document_type IN ('driver_license','driver_photo','signed_agreement'))"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO driver_kyc_documents "
                    "(id,submission_id,stored_file_id,document_type) "
                    "VALUES (:id,:submission,:file,'signed_agreement')"
                ),
                {
                    "id": uuid4(),
                    "submission": UUID(response.json()["submission_id"]),
                    "file": file_id,
                },
            )
            for table, fields in {
                "driver_applications": ("agreement_version", "agreement_accepted_at"),
                "driver_kyc_submissions": (
                    "agreement_version",
                    "agreement_accepted_at",
                    "agreement_acceptance_requested",
                    "bank_check_receipt_sha256",
                    "bank_name_confirmed",
                ),
            }.items():
                for field in fields:
                    await session.execute(text(f"ALTER TABLE {table} DROP COLUMN {field}"))
            connection = await session.connection()

            def upgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration().upgrade()

            await connection.run_sync(upgrade)
            await session.commit()
        async with sessions() as session:
            actual = await session.get(DriverApplication, application.id)
            assert actual.agreement_version is actual.agreement_accepted_at is None
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM driver_kyc_documents "
                        "WHERE document_type='signed_agreement'"
                    )
                )
                == 0
            )
            intents = list(await session.scalars(select(StoredObjectDeletion)))
            assert len(intents) == (0 if shared else 2)
            if shared:
                assert await session.get(StoredFile, file_id) is not None
                assert keys <= storage.objects.keys()
                return
            assert {i.subject_user_id for i in intents} == {application.user_id}
            assert {i.storage_key for i in intents} == keys
        storage.unavailable = True
        with pytest.raises(AppError, match="Private file storage"):
            await process_stored_object_deletions(sessions, storage=storage, limit=2)
        assert keys <= storage.objects.keys()
        storage.unavailable = False
        assert await process_stored_object_deletions(sessions, storage=storage, limit=2) == 2
        assert not keys.intersection(storage.objects)
        async with sessions() as session:
            intents = list(await session.scalars(select(StoredObjectDeletion)))
            assert all(
                i.state == "completed" and i.subject_user_id == application.user_id for i in intents
            )
            assert await session.get(StoredFile, file_id) is None

    asyncio.run(run())


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
