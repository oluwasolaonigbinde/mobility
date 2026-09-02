import asyncio
import json
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select

from app.adapters.crypto import EnvelopeCryptoProvider
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.kyc import DriverKycSubmission, VehicleEvidenceSubmission
from app.models.payee import PayeeBankAccountVersion
from app.models.stored_file import FileScanStatus, FileUploadIntent, StoredFile
from app.models.user import UserRole
from app.services.kyc import rewrap_driver_nin, submit_driver_kyc
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
)

PASSWORD = "long-secure-password"
NIN = "12345678901"


def _seed_driver_authority(db_sessionmaker, *, suffix: str):
    admin = create_test_user(
        db_sessionmaker,
        email=f"kyc-admin-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=f"kyc-driver-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)

    async def seed():
        async with db_sessionmaker() as session:
            payee, _ = await create_pilot_payee(
                session,
                driver_profile_id=profile.id,
                actor_user_id=admin.id,
            )
            bank = await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=VerifiedBankAccountDetails(
                    account_name="KYC Driver",
                    account_number="0123456789",
                    bank_code="058",
                ),
                verification_reference=f"provider-neutral-{suffix}-evidence-reference",
                actor_user_id=admin.id,
                crypto=EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1),
            )
            files: dict[str, UUID] = {}
            for index, name in enumerate(
                (
                    "driver_license",
                    "driver_photo",
                    "signed_agreement",
                    "registration",
                    "insurance",
                    "vehicle_photo",
                )
            ):
                purpose = "driver_kyc" if index < 3 else "vehicle_evidence"
                intent = FileUploadIntent(
                    organization_id=None,
                    subject_user_id=driver.id,
                    uploader_user_id=driver.id,
                    client_request_id=uuid4(),
                    request_fingerprint=(f"{index:x}" * 64)[:64],
                    purpose=purpose,
                    original_filename=f"{name}.png",
                    declared_content_type="image/png",
                    declared_size_bytes=68,
                    declared_sha256=(f"{index + 1:x}" * 64)[:64],
                    object_key=f"unconfirmed/subject/{driver.id}/{uuid4()}",
                    expires_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    status="confirmed",
                )
                session.add(intent)
                await session.flush()
                stored = StoredFile(
                    upload_intent_id=intent.id,
                    organization_id=None,
                    subject_user_id=driver.id,
                    uploader_user_id=driver.id,
                    purpose=purpose,
                    original_filename=f"{name}.png",
                    storage_key=f"managed/subject/{driver.id}/{intent.id}",
                    content_type="image/png",
                    size_bytes=68,
                    checksum_sha256=(f"{index + 1:x}" * 64)[:64],
                    scan_status=FileScanStatus.CLEAN,
                )
                session.add(stored)
                await session.flush()
                files[name] = stored.id
            await session.commit()
            return bank.id, files

    bank_id, files = asyncio.run(seed())
    return admin, driver, profile, bank_id, files


def _payload(bank_id: UUID, files: dict[str, UUID], **changes):
    payload = {
        "client_request_id": "32655c20-c095-40d8-a166-4d7a280fc747",
        "nin": NIN,
        "bank_account_version_id": str(bank_id),
        "driver_license_file_id": str(files["driver_license"]),
        "driver_photo_file_id": str(files["driver_photo"]),
        "signed_agreement_file_id": str(files["signed_agreement"]),
    }
    payload.update(changes)
    return payload


def test_collection_gate_denies_authenticated_kyc_before_encryption_or_writes(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    _, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="privacy-denial"
    )
    blocked = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_collection_live_authorized": False,
            "privacy_collection_synthetic_test_mode": False,
            "privacy_legal_approval_reference": "",
        }
    )
    db_client.app.dependency_overrides[get_settings] = lambda: blocked

    async def counts() -> tuple[int, int, int]:
        async with db_sessionmaker() as session:
            return (
                int(await session.scalar(select(func.count(DriverKycSubmission.id))) or 0),
                int(await session.scalar(select(func.count(StoredFile.id))) or 0),
                int(
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.action.like("driver.kyc.%")
                        )
                    )
                    or 0
                ),
            )

    before = asyncio.run(counts())
    response = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=_payload(bank_id, files),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PRIVACY_COLLECTION_BLOCKED"
    assert asyncio.run(counts()) == before

    live = blocked.model_copy(
        update={
            "privacy_collection_live_authorized": True,
            "privacy_legal_approval_reference": "approved-privacy-authority-v1",
        }
    )
    db_client.app.dependency_overrides[get_settings] = lambda: live
    allowed = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=_payload(bank_id, files),
    )
    assert allowed.status_code == 201
    assert allowed.json()["masked_nin"] == "*******8901"


def test_collection_gate_denies_direct_kyc_before_database_or_crypto_access(settings) -> None:
    class NoDatabaseSession:
        def __getattr__(self, name):
            raise AssertionError(f"database access attempted through {name}")

    class NoCrypto:
        def encrypt(self, *args, **kwargs):
            raise AssertionError("encryption attempted")

        def decrypt(self, *args, **kwargs):
            raise AssertionError("decryption attempted")

    blocked = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_collection_live_authorized": False,
            "privacy_collection_synthetic_test_mode": False,
            "privacy_legal_approval_reference": "",
        }
    )

    async def exercise() -> None:
        with pytest.raises(AppError) as denial:
            await submit_driver_kyc(
                NoDatabaseSession(),  # type: ignore[arg-type]
                actor_user_id=uuid4(),
                client_request_id=uuid4(),
                nin=NIN,
                bank_account_version_id=uuid4(),
                document_file_ids={
                    "driver_license": uuid4(),
                    "driver_photo": uuid4(),
                    "signed_agreement": uuid4(),
                },
                crypto=NoCrypto(),  # type: ignore[arg-type]
                settings=blocked,
            )
        assert denial.value.code == "PRIVACY_COLLECTION_BLOCKED"

    asyncio.run(exercise())


def test_kyc_submission_is_masked_idempotent_encrypted_and_reveal_is_audited(
    db_client, db_sessionmaker
) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(db_sessionmaker, suffix="happy")
    headers = auth_headers(db_client, driver.email, PASSWORD)

    first = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=headers, json=_payload(bank_id, files)
    )
    replay = db_client.post(
        "/api/v1/driver/kyc/submissions", headers=headers, json=_payload(bank_id, files)
    )
    changed = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=headers,
        json=_payload(bank_id, files, nin="10987654321"),
    )

    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["masked_nin"] == "*******8901"
    assert NIN not in json.dumps(first.json())
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "KYC_RETRY_CONFLICT"

    current = db_client.get("/api/v1/driver/kyc/current", headers=headers)
    reveal = db_client.post(
        f"/api/v1/admin/kyc/submissions/{first.json()['id']}/nin/reveal",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"purpose": "manual_kyc_review"},
    )
    assert current.status_code == 200 and current.json()["id"] == first.json()["id"]
    assert reveal.status_code == 200 and reveal.json() == {"nin": NIN}
    assert reveal.headers["cache-control"] == "no-store"

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            submissions = list((await session.scalars(select(DriverKycSubmission))).all())
            assert len(submissions) == 1
            serialized = json.dumps(submissions[0].encrypted_nin)
            assert NIN not in serialized
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "admin.kyc.nin_read")
            )
            assert audit is not None
            assert NIN not in json.dumps(audit.event_metadata)

    asyncio.run(inspect())


def test_kyc_rejects_cross_driver_bank_files_and_uncleared_evidence(
    db_client, db_sessionmaker
) -> None:
    _, first, _, first_bank, first_files = _seed_driver_authority(
        db_sessionmaker, suffix="isolation-a"
    )
    _, _, _, second_bank, second_files = _seed_driver_authority(
        db_sessionmaker, suffix="isolation-b"
    )
    headers = auth_headers(db_client, first.email, PASSWORD)

    foreign_bank = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=headers,
        json=_payload(second_bank, first_files),
    )
    foreign_file = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=headers,
        json=_payload(
            first_bank,
            first_files,
            client_request_id="1b089dcc-3917-4a54-9d08-926652a3241f",
            driver_photo_file_id=str(second_files["driver_photo"]),
        ),
    )

    async def mark_pending() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, first_files["driver_photo"])
            stored.scan_status = FileScanStatus.PENDING
            await session.commit()

    asyncio.run(mark_pending())
    pending = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=headers,
        json=_payload(
            first_bank,
            first_files,
            client_request_id="fb2c5c41-995e-4b12-a94d-178702b84f5f",
        ),
    )
    assert foreign_bank.status_code == 409
    assert foreign_bank.json()["error"]["code"] == "KYC_BANK_VERSION_INVALID"
    assert foreign_file.status_code == pending.status_code == 409
    assert foreign_file.json()["error"]["code"] == "KYC_DOCUMENT_NOT_CLEARED"


def test_tampered_nin_fails_closed_without_read_audit(db_client, db_sessionmaker) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(db_sessionmaker, suffix="tamper")
    submitted = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=_payload(bank_id, files),
    )
    submission_id = UUID(submitted.json()["id"])

    async def tamper() -> None:
        async with db_sessionmaker() as session:
            submission = await session.get(DriverKycSubmission, submission_id)
            envelope = dict(submission.encrypted_nin)
            envelope["ciphertext_b64"] = "AAAA"
            submission.encrypted_nin = envelope
            await session.commit()

    asyncio.run(tamper())
    response = db_client.post(
        f"/api/v1/admin/kyc/submissions/{submission_id}/nin/reveal",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"purpose": "manual_kyc_review"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "KYC_DECRYPTION_FAILED"

    async def count_reads() -> int:
        async with db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.kyc.nin_read"
                    )
                )
                or 0
            )

    assert asyncio.run(count_reads()) == 0


def test_vehicle_evidence_is_owned_versioned_and_idempotent(db_client, db_sessionmaker) -> None:
    _, driver, profile, _, files = _seed_driver_authority(db_sessionmaker, suffix="vehicle")
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    payload = {
        "client_request_id": "e824dfb1-f6b9-4cae-b515-ebcd70d0371c",
        "registration_file_id": str(files["registration"]),
        "insurance_file_id": str(files["insurance"]),
        "vehicle_photo_file_id": str(files["vehicle_photo"]),
    }
    headers = auth_headers(db_client, driver.email, PASSWORD)
    first = db_client.post(
        f"/api/v1/driver/vehicles/{vehicle.id}/evidence-submissions",
        headers=headers,
        json=payload,
    )
    replay = db_client.post(
        f"/api/v1/driver/vehicles/{vehicle.id}/evidence-submissions",
        headers=headers,
        json=payload,
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["status"] == "pending_review"

    async def count() -> int:
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count(VehicleEvidenceSubmission.id))) or 0)

    assert asyncio.run(count()) == 1


def test_nin_rewrap_appends_once_and_preserves_ciphertext(db_sessionmaker, settings) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(db_sessionmaker, suffix="rewrap")
    first_crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)
    rotating_crypto = EnvelopeCryptoProvider(
        keys={1: bytes(range(32)), 2: b"z" * 32}, active_key_version=2
    )

    async def exercise():
        async with db_sessionmaker() as session:
            original = await submit_driver_kyc(
                session,
                actor_user_id=driver.id,
                client_request_id=uuid4(),
                nin=NIN,
                bank_account_version_id=bank_id,
                document_file_ids={name: files[name] for name in (
                    "driver_license", "driver_photo", "signed_agreement"
                )},
                crypto=first_crypto,
                settings=settings,
            )
            await session.commit()
            original_mapping = dict(original.submission.encrypted_nin)
            rotated = await rewrap_driver_nin(
                session,
                submission_id=original.submission.id,
                actor_user_id=admin.id,
                crypto=rotating_crypto,
            )
            retried = await rewrap_driver_nin(
                session,
                submission_id=original.submission.id,
                actor_user_id=admin.id,
                crypto=rotating_crypto,
            )
            await session.commit()
            audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.kyc.nin_rewrapped"
                    )
                )
                or 0
            )
            versions = list(
                (await session.scalars(select(DriverKycSubmission).order_by(
                    DriverKycSubmission.version
                ))).all()
            )
            return original_mapping, rotated, retried, versions, audits

    original_mapping, rotated, retried, versions, audits = asyncio.run(exercise())
    assert [item.version for item in versions] == [1, 2]
    assert rotated.submission.id == retried.submission.id
    assert rotated.submission.encryption_key_version == 2
    assert original_mapping["nonce_b64"] == rotated.submission.encrypted_nin["nonce_b64"]
    assert original_mapping["ciphertext_b64"] == rotated.submission.encrypted_nin["ciphertext_b64"]
    assert (
        original_mapping["wrapped_key_b64"]
        != rotated.submission.encrypted_nin["wrapped_key_b64"]
    )
    assert audits == 1


def test_rewrap_cannot_resurrect_a_superseded_nin_chain(db_sessionmaker, settings) -> None:
    admin, driver, _, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="stale-rewrap"
    )
    first_crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)
    rotating_crypto = EnvelopeCryptoProvider(
        keys={1: bytes(range(32)), 2: b"z" * 32}, active_key_version=2
    )
    document_file_ids = {
        name: files[name]
        for name in ("driver_license", "driver_photo", "signed_agreement")
    }

    async def exercise() -> None:
        async with db_sessionmaker() as session:
            first = await submit_driver_kyc(
                session,
                actor_user_id=driver.id,
                client_request_id=uuid4(),
                nin=NIN,
                bank_account_version_id=bank_id,
                document_file_ids=document_file_ids,
                crypto=first_crypto,
                settings=settings,
            )
            await submit_driver_kyc(
                session,
                actor_user_id=driver.id,
                client_request_id=uuid4(),
                nin="10987654321",
                bank_account_version_id=bank_id,
                document_file_ids=document_file_ids,
                crypto=first_crypto,
                settings=settings,
            )
            await session.commit()
            with pytest.raises(AppError) as raised:
                await rewrap_driver_nin(
                    session,
                    submission_id=first.submission.id,
                    actor_user_id=admin.id,
                    crypto=rotating_crypto,
                )
            assert raised.value.code == "KYC_REWRAP_STALE"

    asyncio.run(exercise())


def test_postgres_concurrent_kyc_retry_and_versions_serialize(
    postgis_db_sessionmaker,
    settings,
) -> None:
    _, driver, _, bank_id, files = _seed_driver_authority(
        postgis_db_sessionmaker, suffix="concurrent"
    )
    crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)
    document_file_ids = {
        name: files[name]
        for name in ("driver_license", "driver_photo", "signed_agreement")
    }
    shared_request = uuid4()

    async def submit(request_id: UUID):
        async with postgis_db_sessionmaker() as session:
            view = await submit_driver_kyc(
                session,
                actor_user_id=driver.id,
                client_request_id=request_id,
                nin=NIN,
                bank_account_version_id=bank_id,
                document_file_ids=document_file_ids,
                crypto=crypto,
                settings=settings,
            )
            await session.commit()
            return view.submission.id, view.submission.version

    async def exercise():
        exact = await asyncio.gather(submit(shared_request), submit(shared_request))
        later = await asyncio.gather(submit(uuid4()), submit(uuid4()))
        async with postgis_db_sessionmaker() as session:
            count = int(
                await session.scalar(select(func.count(DriverKycSubmission.id))) or 0
            )
        return exact, later, count

    exact, later, count = asyncio.run(exercise())
    assert exact[0] == exact[1]
    assert sorted(version for _, version in later) == [2, 3]
    assert count == 3


def test_kyc_models_have_no_plaintext_nin_column() -> None:
    columns = set(DriverKycSubmission.__table__.columns.keys())
    assert "nin" not in columns
    assert {"encrypted_nin", "nin_last_four", "nin_record_id"} <= columns
    assert "encrypted_details" in PayeeBankAccountVersion.__table__.columns
