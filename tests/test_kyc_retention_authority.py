import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import create_test_vehicle
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_file_kyc_lifecycle import _create_terminal_submission
from test_kyc import NIN, _seed_driver_authority
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)
from test_stored_files import FakeStorageProvider

from app.adapters.crypto import AssociatedData, EnvelopeCryptoProvider
from app.api.v1.kyc import _driver_response, _vehicle_response
from app.core.errors import AppError
from app.db.base import Base
from app.models.kyc import (
    DriverKycDocument,
    DriverKycReviewDecision,
    DriverKycSubmission,
    VehicleEvidenceDocument,
    VehicleEvidenceReviewDecision,
    VehicleEvidenceSubmission,
)
from app.models.stored_file import StoredFile, StoredObjectDeletion
from app.services.audit import create_audit_event
from app.services.file_kyc_lifecycle import purge_terminal_file_kyc
from app.services.kyc import (
    DriverKycView,
    VehicleEvidenceView,
    reveal_driver_nin,
    rewrap_driver_nin,
    submit_vehicle_evidence,
)
from app.services.stored_object_deletions import (
    delete_stored_object,
    ensure_stored_object_deletion,
    process_stored_object_deletions,
)


@pytest.fixture
def migrated_kyc_factory(monkeypatch, request):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        upgrade_to(url, getattr(request, "param", "head"), monkeypatch)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        asyncio.run(engine.dispose())
        asyncio.run(drop_database(url))


@pytest.mark.parametrize("kind", ["driver", "vehicle"])
def test_kyc_review_identity_and_durable_payload_purge_precede_every_provider_delete(
    migrated_kyc_factory, settings, kind, monkeypatch
):
    factory = migrated_kyc_factory
    admin, driver, profile, bank_id, files = _seed_driver_authority(factory, suffix=f"purge-{kind}")
    vehicle = create_test_vehicle(factory, driver_profile_id=profile.id)
    now = datetime.now(UTC)
    model, documents, decisions = (
        (DriverKycSubmission, DriverKycDocument, DriverKycReviewDecision)
        if kind == "driver"
        else (VehicleEvidenceSubmission, VehicleEvidenceDocument, VehicleEvidenceReviewDecision)
    )

    async def run():
        async with factory() as session:
            if kind == "driver":
                submission = await _create_terminal_submission(
                    session,
                    driver_id=driver.id,
                    bank_id=bank_id,
                    files=files,
                    now=now,
                    settings=settings,
                )
                facts = dict(identity_match_confirmed=False, bank_account_match_confirmed=False)
            else:
                view = await submit_vehicle_evidence(
                    session,
                    actor_user_id=driver.id,
                    vehicle_id=vehicle.id,
                    client_request_id=uuid4(),
                    document_file_ids={
                        key: files[key] for key in ("registration", "insurance", "vehicle_photo")
                    },
                    settings=settings,
                )
                submission = view.submission
                submission.status = "rejected"
                submission.created_at = now - timedelta(days=31)
                facts = dict(
                    sequence=1,
                    owner_match_confirmed=False,
                    vehicle_identity_confirmed=False,
                    roadworthy_confirmed=False,
                    pilot_car_confirmed=False,
                    valid_until=None,
                )
            decision = decisions(
                submission_id=submission.id,
                client_request_id=uuid4(),
                request_fingerprint="a" * 64,
                decision="rejected",
                reason_code="missing_evidence",
                documents_readable_confirmed=False,
                decided_by_user_id=admin.id,
                **facts,
            )
            session.add(decision)
            await session.commit()
            identity, decision_id, version = submission.id, decision.id, submission.version
            original_decision = {
                column.name: getattr(decision, column.name)
                for column in decisions.__table__.columns
            }

        async def forbidden(sql, **params):
            async with factory() as session:
                with pytest.raises(DBAPIError):
                    await session.execute(text(sql), {"id": identity, **params})
                    await session.commit()

        clear_payload = (
            "encrypted_nin=NULL, encryption_algorithm=NULL, encryption_key_version=NULL, "
            "nin_last_four=NULL"
            if kind == "driver"
            else "plate_number_snapshot=NULL, plate_number_normalized_snapshot=NULL, "
            "plate_country_code_snapshot=NULL, vehicle_type_snapshot=NULL, make_snapshot=NULL, "
            "model_snapshot=NULL, year_snapshot=NULL, color_snapshot=NULL"
        )
        # Neither a marker alone nor an unaudited clearing of a bound payload is authority.
        await forbidden(f"UPDATE {model.__tablename__} SET purged_at=now() WHERE id=:id")
        await forbidden(
            f"UPDATE {model.__tablename__} SET purged_at=now(), {clear_payload} WHERE id=:id"
        )

        class DurableBoundaryStorage(FakeStorageProvider):
            async def delete(self, object_key):
                async with factory() as proof:
                    retained = await proof.get(model, identity)
                    assert retained is not None
                    assert getattr(retained, "purged_at", None) is not None, (
                        "Provider delete preceded durable payload purge"
                    )
                    assert (
                        await proof.scalar(
                            select(func.count())
                            .select_from(documents)
                            .where(documents.submission_id == identity)
                        )
                        == 0
                    )
                    historical = await proof.get(decisions, decision_id)
                    assert {
                        column.name: getattr(historical, column.name)
                        for column in decisions.__table__.columns
                    } == original_decision
                    if kind == "driver":
                        assert retained.encrypted_nin is None
                        assert retained.nin_last_four is None
                    else:
                        assert retained.plate_number_snapshot is None
                        assert retained.snapshot_trusted is True
                await super().delete(object_key)

        storage = DurableBoundaryStorage()
        async with factory() as session:
            result = await purge_terminal_file_kyc(
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
            retained = await session.get(model, identity)
            assert (
                retained is not None
                and retained.version == version
                and retained.status == "rejected"
            )
            assert result.purged_submissions == 1
            expected_files = 2 if kind == "driver" else 3
            assert result.purged_files == expected_files
            assert len(storage.deleted) == expected_files
            assert await session.get(decisions, decision_id) is not None
            rendered = (
                _driver_response(DriverKycView(retained, {}))
                if kind == "driver"
                else _vehicle_response(VehicleEvidenceView(retained, {}))
            ).model_dump(mode="json")
            assert rendered["purged_at"] is not None
            assert rendered["document_file_ids"] == {}
            assert rendered["masked_nin" if kind == "driver" else "plate_number"] is None
            assert rendered["status"] == "rejected"

        for change in ("purged_at=NULL", "version=version+1", "status='approved'"):
            await forbidden(f"UPDATE {model.__tablename__} SET {change} WHERE id=:id")
        await forbidden(f"DELETE FROM {model.__tablename__} WHERE id=:id")
        if kind == "vehicle":
            await forbidden(f"UPDATE {model.__tablename__} SET snapshot_trusted=false WHERE id=:id")
        async with factory() as session:
            # A surviving peer isolates the retained-parent guard from the file foreign key.
            peer_file = files["registration" if kind == "driver" else "driver_photo"]
            session.add(
                documents(
                    submission_id=identity,
                    stored_file_id=peer_file,
                    document_type="driver_photo" if kind == "driver" else "vehicle_photo",
                )
            )
            with pytest.raises(
                (DBAPIError, ValueError), match="purged KYC submission cannot accept documents"
            ):
                await session.commit()

    asyncio.run(run())


def test_failed_retirement_commit_cannot_delete_and_legacy_intent_waits_for_authority(
    migrated_kyc_factory, settings, monkeypatch
):
    factory = migrated_kyc_factory
    admin, driver, _, bank_id, files = _seed_driver_authority(factory, suffix="purge-commit")
    storage = FakeStorageProvider()
    now = datetime.now(UTC)

    async def run():
        async with factory() as session:
            submission = await _create_terminal_submission(
                session,
                driver_id=driver.id,
                bank_id=bank_id,
                files=files,
                now=now,
                settings=settings,
            )
            identity = submission.id
            file = await session.get(StoredFile, files["driver_license"])
            legacy = await ensure_stored_object_deletion(
                session,
                storage_key=file.storage_key,
                object_checksum_sha256=file.checksum_sha256,
                reason="legacy_retention",
                owner_type="driver_kyc_submission",
                owner_id=identity,
                organization_id=None,
                subject_user_id=driver.id,
                stored_file_id=file.id,
                upload_intent_id=file.upload_intent_id,
            )
            legacy_id = legacy.id
            await session.commit()

        async with factory() as session:
            legacy = await session.get(StoredObjectDeletion, legacy_id)
            with pytest.raises(AppError) as denied:
                await delete_stored_object(session, intent=legacy, storage=storage)
            assert denied.value.code == "KYC_RETENTION_AUTHORITY_REQUIRED"
            await session.rollback()
        assert await process_stored_object_deletions(factory, storage=storage, limit=10) == 0
        assert storage.deleted == []

        async with factory() as session:

            async def fail_commit():
                raise RuntimeError("synthetic retirement commit failure")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="retirement commit failure"):
                await purge_terminal_file_kyc(
                    session,
                    storage=storage,
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="legacy_retention",
                    now=now,
                )
            await session.rollback()
        assert storage.deleted == []
        async with factory() as session:
            retained = await session.get(DriverKycSubmission, identity)
            assert retained.purged_at is None and retained.encrypted_nin is not None
            assert await session.scalar(select(func.count()).select_from(DriverKycDocument)) == 2
            assert await session.scalar(select(func.count()).select_from(StoredObjectDeletion)) == 1
            await purge_terminal_file_kyc(
                session,
                storage=storage,
                retention_days=30,
                limit=10,
                dry_run=False,
                actor_user_id=admin.id,
                reason="legacy_retention",
                now=now,
            )
            await session.commit()
        assert len(storage.deleted) == 2

        crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)
        for operation in (reveal_driver_nin, rewrap_driver_nin):
            async with factory() as session:
                with pytest.raises(AppError) as denied:
                    await operation(
                        session,
                        submission_id=identity,
                        actor_user_id=admin.id,
                        crypto=crypto,
                        **(
                            {"purpose": "synthetic_review"}
                            if operation is reveal_driver_nin
                            else {}
                        ),
                    )
                assert denied.value.code == "KYC_PAYLOAD_PURGED"
                assert denied.value.status_code == 410

    asyncio.run(run())


def test_document_binding_waits_on_parent_before_file_and_rejects_retired_payload(
    migrated_kyc_factory, settings
):
    factory = migrated_kyc_factory
    admin, driver, _, bank_id, files = _seed_driver_authority(factory, suffix="purge-binding")
    now = datetime.now(UTC)

    async def run():
        async with factory() as session:
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

        async with factory() as retirement:
            await retirement.scalar(
                select(DriverKycSubmission)
                .where(DriverKycSubmission.id == identity)
                .with_for_update()
            )

            async def bind():
                async with factory() as writer:
                    writer.add(
                        DriverKycDocument(
                            submission_id=identity,
                            stored_file_id=files["driver_license"],
                            document_type="driver_license",
                        )
                    )
                    with pytest.raises(
                        (ValueError, DBAPIError),
                        match="purged KYC submission cannot accept documents",
                    ):
                        await writer.commit()

            task = asyncio.create_task(bind())
            try:
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.25)
                # A writer waiting for the parent must not already own the file row.
                await retirement.scalar(
                    select(StoredFile.id)
                    .where(StoredFile.id == files["driver_license"])
                    .with_for_update(nowait=True)
                )
                await purge_terminal_file_kyc(
                    retirement,
                    storage=FakeStorageProvider(),
                    retention_days=30,
                    limit=10,
                    dry_run=False,
                    actor_user_id=admin.id,
                    reason="synthetic_binding_race",
                    now=now,
                )
                await retirement.commit()
                await asyncio.wait_for(task, timeout=5)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("migrated_kyc_factory", ["0087_kyc_payload_retention"], indirect=True)
def test_kyc_retention_migration_preserves_live_payload_and_serializes_downgrade(
    migrated_kyc_factory, settings, monkeypatch
):
    factory = migrated_kyc_factory
    url = factory.kw["bind"].url.render_as_string(hide_password=False)
    # Empty guarded downgrade and re-upgrade remain available.
    downgrade_to(url, "0086_audit_subjects", monkeypatch)
    upgrade_to(url, "0087_kyc_payload_retention", monkeypatch)
    admin, driver, profile, bank_id, files = _seed_driver_authority(
        factory, suffix="purge-migration"
    )
    identity = uuid4()
    nin_identity = uuid4()
    envelope = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1).encrypt(
        NIN.encode("ascii"),
        AssociatedData(tenant_id=driver.id, record_id=nin_identity, field_name="driver_kyc.nin"),
    )

    async def seed_and_race():
        async with factory() as session:
            # This frozen revision predates 0102; current capture/ORM fields cannot
            # be used to manufacture its historical payload.
            await session.execute(
                text("""
                    INSERT INTO driver_kyc_submissions
                    (id, driver_profile_id, nin_record_id, version, client_request_id,
                     status, encrypted_nin, encryption_algorithm, encryption_key_version,
                     nin_last_four, bank_account_version_id, created_by_user_id, created_at)
                    VALUES (:id, :profile, :nin_id, 1, :request, 'rejected',
                     CAST(:payload AS json), 'AES-256-GCM', 1,
                     '8901', :bank, :driver, now() - interval '31 days')
                """),
                {
                    "id": identity,
                    "profile": profile.id,
                    "nin_id": nin_identity,
                    "payload": json.dumps(envelope.to_mapping()),
                    "request": uuid4(),
                    "bank": bank_id,
                    "driver": driver.id,
                },
            )
            for document_type in ("driver_license", "driver_photo"):
                session.add(
                    DriverKycDocument(
                        submission_id=identity,
                        stored_file_id=files[document_type],
                        document_type=document_type,
                    )
                )
            await session.commit()
            await session.execute(
                text("SELECT id FROM driver_kyc_submissions WHERE id=:id FOR UPDATE"),
                {"id": identity},
            )
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await asyncio.to_thread(downgrade_to, url, "0086_audit_subjects", monkeypatch)

    async def snapshot_and_schema():
        async with factory() as session:
            before = (
                await session.execute(
                    text("SELECT to_jsonb(s)-'purged_at' FROM driver_kyc_submissions s")
                )
            ).all()
            bindings = (
                await session.execute(
                    text(
                        "SELECT document_type, stored_file_id FROM driver_kyc_documents "
                        "WHERE submission_id=:id ORDER BY document_type"
                    ),
                    {"id": identity},
                )
            ).all()
            assert bindings == [(name, files[name]) for name in ("driver_license", "driver_photo")]
            connection = await session.connection()
            changes = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )
            owned_changes = [
                change
                for change in changes
                if any(
                    name in repr(change)
                    for name in ("driver_kyc_submissions", "vehicle_evidence_submissions")
                )
            ]
            # The only intentional difference from today's model is 0102's
            # five additive capture fields. Every other owned drift still fails.
            assert len(owned_changes) == 5
            assert all(
                change[0] == "add_column" and change[2] == "driver_kyc_submissions"
                for change in owned_changes
            )
            assert {change[3].name for change in owned_changes} == {
                "agreement_version",
                "agreement_accepted_at",
                "agreement_acceptance_requested",
                "bank_check_receipt_sha256",
                "bank_name_confirmed",
            }
            return before, bindings

    asyncio.run(seed_and_race())
    before = asyncio.run(snapshot_and_schema())
    downgrade_to(url, "0086_audit_subjects", monkeypatch)
    upgrade_to(url, "0087_kyc_payload_retention", monkeypatch)
    assert asyncio.run(snapshot_and_schema()) == before

    async def retire_historical_payload():
        async with factory() as session:
            await session.execute(
                text("DELETE FROM driver_kyc_documents WHERE submission_id=:id"),
                {"id": identity},
            )
            await create_audit_event(
                session,
                actor_user_id=admin.id,
                action="driver_kyc_submission.payload_purge_authorized",
                entity_type="driver_kyc_submission",
                entity_id=str(identity),
                metadata={"reason": "synthetic_migration_guard"},
            )
            await session.execute(
                text("""
                    UPDATE driver_kyc_submissions SET purged_at=now(), encrypted_nin=NULL,
                    encryption_algorithm=NULL, encryption_key_version=NULL, nin_last_four=NULL
                    WHERE id=:id
                """),
                {"id": identity},
            )
            await session.commit()
            assert (
                await session.scalar(
                    text("SELECT purged_at IS NOT NULL FROM driver_kyc_submissions WHERE id=:id"),
                    {"id": identity},
                )
                is True
            )

    asyncio.run(retire_historical_payload())
    with pytest.raises(RuntimeError, match="0087 downgrade blocked"):
        downgrade_to(url, "0086_audit_subjects", monkeypatch)
