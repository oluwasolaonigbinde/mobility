import asyncio
import json
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import func, select
from test_stored_files import FakeStorageProvider

from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.storage import ObjectMetadata
from app.api.v1.dependencies import get_registration_rate_limiter, get_storage_provider
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import InMemoryRegistrationRateLimiter
from app.models.audit import AuditEvent
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication
from app.models.kyc import DriverKycReviewDecision, DriverKycSubmission
from app.models.payee import PayeeBankAccountVersion
from app.models.stored_file import FileScanStatus, FileUploadIntent, StoredFile
from app.models.user import UserRole
from app.schemas.driver_applications import DriverApplicationCreate
from app.schemas.driver_onboarding import (
    PersonPayeeReviewDecisionCreate,
    PersonPayeeSubmissionCreate,
)
from app.services.campaign_assignments import ensure_active_driver_profile
from app.services.driver_applications import submit_driver_application
from app.services.driver_onboarding import (
    review_application_person_payee,
    submit_application_person_payee,
)
from app.services.kyc import rewrap_driver_nin

PASSWORD = "long-secure-password"
NIN = "12345678901"


def _register(db_client, settings, *, suffix: str) -> tuple[str, DriverApplication]:
    enabled = settings.model_copy(update={"driver_registration_enabled": True})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: (
        InMemoryRegistrationRateLimiter()
    )
    response = db_client.post(
        "/api/v1/auth/register-driver",
        json={
            "email": f"person-payee-{suffix}@example.com",
            "full_name": "Person Payee Driver",
            "service_city": "Abuja",
            "country_code": "NG",
        },
    )
    assert response.status_code == 202
    return response.json()["application_reference"], response


def _application(db_sessionmaker, *, email: str) -> DriverApplication:
    async def fetch() -> DriverApplication:
        async with db_sessionmaker() as session:
            application = await session.scalar(
                select(DriverApplication).where(DriverApplication.email == email)
            )
            assert application is not None
            return application

    return asyncio.run(fetch())


def _seed_clean_kyc_files(db_sessionmaker, *, email: str) -> dict[str, UUID]:
    async def seed() -> dict[str, UUID]:
        async with db_sessionmaker() as session:
            application = await session.scalar(
                select(DriverApplication).where(DriverApplication.email == email)
            )
            assert application is not None
            result: dict[str, UUID] = {}
            for index, name in enumerate(
                ("driver_license", "driver_photo", "signed_agreement"), start=1
            ):
                intent = FileUploadIntent(
                    organization_id=None,
                    subject_user_id=application.user_id,
                    uploader_user_id=application.user_id,
                    client_request_id=uuid4(),
                    request_fingerprint=f"{index}" * 64,
                    purpose="driver_kyc",
                    original_filename=f"driver-kyc-{index}.png",
                    declared_content_type="image/png",
                    declared_size_bytes=68,
                    declared_sha256=f"{index}" * 64,
                    object_key=f"unconfirmed/subject/{application.user_id}/{uuid4()}",
                    expires_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    status="confirmed",
                )
                session.add(intent)
                await session.flush()
                stored = StoredFile(
                    upload_intent_id=intent.id,
                    organization_id=None,
                    subject_user_id=application.user_id,
                    uploader_user_id=application.user_id,
                    purpose="driver_kyc",
                    original_filename=f"driver-kyc-{index}.png",
                    storage_key=f"managed/subject/{application.user_id}/{intent.id}",
                    content_type="image/png",
                    size_bytes=68,
                    checksum_sha256=f"{index}" * 64,
                    scan_status=FileScanStatus.CLEAN,
                )
                session.add(stored)
                await session.flush()
                result[name] = stored.id
            await session.commit()
            return result

    return asyncio.run(seed())


def _person_payee_payload(reference: str, files: dict[str, UUID], *, request_id=None):
    return {
        "application_reference": reference,
        "client_request_id": str(request_id or uuid4()),
        "nin": NIN,
        "account_name": "Person Payee Driver",
        "account_number": "0123456789",
        "bank_code": "058",
        "verification_reference": "provider-neutral-synthetic-verification-000001",
        "driver_license_file_id": str(files["driver_license"]),
        "driver_photo_file_id": str(files["driver_photo"]),
        "signed_agreement_file_id": str(files["signed_agreement"]),
    }


def test_public_applicant_can_submit_person_payee_without_plaintext_projection(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, settings, suffix="submit")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-submit@example.com")

    response = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending_review"
    assert response.json()["masked_nin"] == "*******8901"
    assert NIN not in response.text
    assert "0123456789" not in response.text

    async def inspect() -> None:
        async with db_sessionmaker() as session:
            submission = await session.scalar(select(DriverKycSubmission))
            account = await session.scalar(select(PayeeBankAccountVersion))
            audits = list((await session.scalars(select(AuditEvent))).all())
            assert submission is not None and account is not None
            assert NIN not in json.dumps(submission.encrypted_nin)
            assert "0123456789" not in json.dumps(account.encrypted_details)
            assert NIN not in json.dumps([event.event_metadata for event in audits])
            assert "0123456789" not in json.dumps([event.event_metadata for event in audits])

    asyncio.run(inspect())


def test_public_application_reference_scopes_shared_private_upload_flow(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, settings, suffix="upload")
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    payload = {
        "application_reference": reference,
        "upload": {
            "client_request_id": str(uuid4()),
            "purpose": "driver_kyc",
            "filename": "12345678901-licence.png",
            "content_type": "image/png",
            "size_bytes": 68,
            "sha256": "a" * 64,
        },
    }
    created = db_client.post("/api/v1/auth/driver-onboarding/files/uploads", json=payload)
    assert created.status_code == 201
    key = created.json()["upload"]["fields"]["key"]
    application = _application(db_sessionmaker, email="person-payee-upload@example.com")
    assert key.startswith(f"unconfirmed/subject/{application.user_id}/")
    storage.objects[key] = ObjectMetadata(
        object_key=key,
        size_bytes=68,
        content_type="image/png",
        checksum_sha256="a" * 64,
    )
    confirmed = db_client.post(
        f"/api/v1/auth/driver-onboarding/files/uploads/{created.json()['upload_id']}/confirm",
        json={"application_reference": reference},
    )
    foreign = db_client.post(
        f"/api/v1/auth/driver-onboarding/files/uploads/{created.json()['upload_id']}/confirm",
        json={"application_reference": "x" * 48},
    )
    assert confirmed.status_code == 201
    assert set(confirmed.json()) == {"id", "scan_status"}
    assert confirmed.json()["scan_status"] == "pending"
    assert foreign.status_code == 404
    assert reference not in json.dumps(storage.presigned)


def test_exact_submission_retry_converges_and_changed_retry_fails(
    db_client, db_sessionmaker, settings, caplog
) -> None:
    reference, _ = _register(db_client, settings, suffix="retry")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-retry@example.com")
    request_id = uuid4()
    payload = _person_payee_payload(reference, files, request_id=request_id)
    first = db_client.post("/api/v1/auth/driver-onboarding/person-payee", json=payload)
    retry = db_client.post("/api/v1/auth/driver-onboarding/person-payee", json=payload)
    conflict = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json={**payload, "account_number": "9876543210"},
    )
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PERSON_PAYEE_RETRY_CONFLICT"
    assert NIN not in conflict.text + caplog.text
    assert "0123456789" not in conflict.text + caplog.text

    async def counts() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            submissions = int(await session.scalar(select(func.count(DriverKycSubmission.id))) or 0)
            accounts = int(
                await session.scalar(select(func.count(PayeeBankAccountVersion.id))) or 0
            )
            return submissions, accounts

    assert asyncio.run(counts()) == (1, 1)

    async def retry_read_audits() -> list[str]:
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(AuditEvent.action).where(
                            AuditEvent.action.in_(
                                (
                                    "driver_application.bank_account.retry_read",
                                    "driver.kyc.retry_read",
                                )
                            )
                        )
                    )
                ).all()
            )

    assert sorted(asyncio.run(retry_read_audits())) == [
        "driver.kyc.retry_read",
        "driver_application.bank_account.retry_read",
        "driver_application.bank_account.retry_read",
    ]


def test_incomplete_person_payee_cannot_be_approved(db_client, db_sessionmaker, settings) -> None:
    _, _ = _register(db_client, settings, suffix="incomplete")
    application = _application(db_sessionmaker, email="person-payee-incomplete@example.com")
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-incomplete-admin@example.com",
        password=PASSWORD,
    )

    response = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PERSON_PAYEE_INCOMPLETE"


def test_admin_approval_is_idempotent_audited_safe_and_non_work_eligible(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, settings, suffix="approval")
    application = _application(db_sessionmaker, email="person-payee-approval@example.com")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-approval@example.com")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )
    assert submitted.status_code == 201
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-approval-admin@example.com",
        password=PASSWORD,
    )
    decision_id = uuid4()
    decision = {
        "client_request_id": str(decision_id),
        "decision": "approved",
        "reason_code": "complete_current_evidence",
        "identity_match_confirmed": True,
        "bank_account_match_confirmed": True,
        "documents_readable_confirmed": True,
    }
    path = f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision"
    first = db_client.post(
        path, headers=auth_headers(db_client, admin.email, PASSWORD), json=decision
    )
    retry = db_client.post(
        path, headers=auth_headers(db_client, admin.email, PASSWORD), json=decision
    )
    conflict = db_client.post(
        path,
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            **decision,
            "decision": "rejected",
            "reason_code": "identity_mismatch",
        },
    )

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert first.json()["status"] == "approved"
    assert NIN not in first.text and "0123456789" not in first.text
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PERSON_PAYEE_DECISION_RETRY_CONFLICT"

    status_response = db_client.get(f"/api/v1/auth/driver-application-status/{reference}")
    queue = db_client.get(
        "/api/v1/admin/driver-applications",
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert status_response.json()["person_payee"]["status"] == "approved"
    assert queue.json()["items"][0]["person_payee"]["status"] == "approved"
    assert NIN not in status_response.text + queue.text
    assert "0123456789" not in status_response.text + queue.text

    async def inspect() -> tuple[DriverProfile, int, list[str]]:
        async with db_sessionmaker() as session:
            profile = await session.get(DriverProfile, application.driver_profile_id)
            assert profile is not None
            decisions = int(
                await session.scalar(select(func.count(DriverKycReviewDecision.id))) or 0
            )
            actions = list(
                (
                    await session.scalars(
                        select(AuditEvent.action).where(
                            AuditEvent.action.in_(
                                (
                                    "admin.kyc.nin_read",
                                    "admin.bank_account.read",
                                    "admin.driver_person_payee.approved",
                                )
                            )
                        )
                    )
                ).all()
            )
            return profile, decisions, actions

    profile, decision_count, actions = asyncio.run(inspect())
    assert profile.onboarding_status == "pending"
    assert decision_count == 1
    assert sorted(actions) == [
        "admin.bank_account.read",
        "admin.driver_person_payee.approved",
        "admin.kyc.nin_read",
    ]
    for boundary in ("assignment_accept", "trip_start"):
        with pytest.raises(AppError) as exc_info:
            ensure_active_driver_profile(profile)
        assert exc_info.value.code == "DRIVER_PROFILE_NOT_ACTIVE", boundary

    async def rotate_approved_identity() -> tuple[str, int, int]:
        async with db_sessionmaker() as session:
            view = await rewrap_driver_nin(
                session,
                submission_id=UUID(first.json()["submission_id"]),
                actor_user_id=admin.id,
                crypto=EnvelopeCryptoProvider(
                    keys={1: bytes(range(32)), 2: b"z" * 32}, active_key_version=2
                ),
            )
            await session.commit()
            decisions = int(
                await session.scalar(select(func.count(DriverKycReviewDecision.id))) or 0
            )
            return view.submission.status, view.submission.version, decisions

    assert asyncio.run(rotate_approved_identity()) == ("pending_review", 2, 1)


def test_approval_fails_closed_for_unsafe_evidence_and_unavailable_key(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, settings, suffix="fail-closed")
    application = _application(db_sessionmaker, email="person-payee-fail-closed@example.com")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-fail-closed@example.com")
    submitted = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )
    assert submitted.status_code == 201
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-fail-closed-admin@example.com",
        password=PASSWORD,
    )
    decision_payload = {
        "client_request_id": str(uuid4()),
        "decision": "approved",
        "reason_code": "complete_current_evidence",
        "identity_match_confirmed": True,
        "bank_account_match_confirmed": True,
        "documents_readable_confirmed": True,
    }

    async def make_unsafe() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, files["driver_photo"])
            assert stored is not None
            stored.scan_status = FileScanStatus.INFECTED
            await session.commit()

    asyncio.run(make_unsafe())
    unsafe = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=decision_payload,
    )
    assert unsafe.status_code == 409
    assert unsafe.json()["error"]["code"] == "KYC_DOCUMENT_NOT_CLEARED"

    async def restore_and_try_missing_key() -> AppError:
        async with db_sessionmaker() as session:
            stored = await session.get(StoredFile, files["driver_photo"])
            assert stored is not None
            stored.scan_status = FileScanStatus.CLEAN
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await review_application_person_payee(
                    session,
                    application_id=application.id,
                    actor_user_id=admin.id,
                    payload=PersonPayeeReviewDecisionCreate.model_validate(
                        {**decision_payload, "client_request_id": str(uuid4())}
                    ),
                    crypto=EnvelopeCryptoProvider(keys={2: b"z" * 32}, active_key_version=2),
                )
            await session.rollback()
            return exc_info.value

    key_error = asyncio.run(restore_and_try_missing_key())
    assert key_error.code == "KYC_DECRYPTION_FAILED"

    async def unchanged() -> tuple[str, int, int]:
        async with db_sessionmaker() as session:
            submission = await session.get(
                DriverKycSubmission, UUID(submitted.json()["submission_id"])
            )
            assert submission is not None
            decisions = int(
                await session.scalar(select(func.count(DriverKycReviewDecision.id))) or 0
            )
            sensitive_reads = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action.in_(("admin.kyc.nin_read", "admin.bank_account.read"))
                    )
                )
                or 0
            )
            return submission.status, decisions, sensitive_reads

    assert asyncio.run(unchanged()) == ("pending_review", 0, 0)


def test_person_payee_decision_requires_an_active_admin(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, settings, suffix="authorization")
    application = _application(db_sessionmaker, email="person-payee-authorization@example.com")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-authorization@example.com")
    assert (
        db_client.post(
            "/api/v1/auth/driver-onboarding/person-payee",
            json=_person_payee_payload(reference, files),
        ).status_code
        == 201
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="person-payee-authorization-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    response = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert response.status_code == 403
    assert NIN not in response.text and "0123456789" not in response.text


@pytest.mark.parametrize(
    ("decision", "reason"),
    (("rejected", "unreadable_evidence"), ("expired", "expired_evidence")),
)
def test_rejected_or_expired_submission_resubmits_as_new_truthful_version(
    db_client, db_sessionmaker, settings, decision: str, reason: str
) -> None:
    suffix = f"resubmit-{decision}"
    reference, _ = _register(db_client, settings, suffix=suffix)
    application = _application(db_sessionmaker, email=f"person-payee-{suffix}@example.com")
    files = _seed_clean_kyc_files(db_sessionmaker, email=f"person-payee-{suffix}@example.com")
    first_request = uuid4()
    first = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files, request_id=first_request),
    )
    admin = create_test_user(
        db_sessionmaker,
        email=f"person-payee-{suffix}-admin@example.com",
        password=PASSWORD,
    )
    decided = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "decision": decision,
            "reason_code": reason,
        },
    )
    second = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )

    assert first.status_code == second.status_code == 201
    assert decided.status_code == 200
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert first.json()["submission_id"] != second.json()["submission_id"]
    assert second.json()["status"] == "pending_review"

    async def history() -> tuple[list[str], int]:
        async with db_sessionmaker() as session:
            statuses = list(
                (
                    await session.scalars(
                        select(DriverKycSubmission.status).order_by(DriverKycSubmission.version)
                    )
                ).all()
            )
            decisions = int(
                await session.scalar(select(func.count(DriverKycReviewDecision.id))) or 0
            )
            return statuses, decisions

    assert asyncio.run(history()) == ([decision, "pending_review"], 1)


def test_public_applicant_cannot_be_manually_activated_before_vehicle_approval(
    db_client, db_sessionmaker, settings
) -> None:
    _, _ = _register(db_client, settings, suffix="eligibility")
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-eligibility-admin@example.com",
        password=PASSWORD,
    )

    async def profile_id() -> UUID:
        async with db_sessionmaker() as session:
            application = await session.scalar(
                select(DriverApplication).where(
                    DriverApplication.email == "person-payee-eligibility@example.com"
                )
            )
            assert application is not None
            return application.driver_profile_id

    response = db_client.patch(
        f"/api/v1/admin/drivers/{asyncio.run(profile_id())}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"onboarding_status": "active"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DRIVER_WORK_ELIGIBILITY_INCOMPLETE"


def test_postgres_concurrent_conflicting_decisions_serialize_once(
    postgis_db_sessionmaker,
) -> None:
    async def seed_application() -> tuple[str, DriverApplication]:
        async with postgis_db_sessionmaker() as session:
            result = await submit_driver_application(
                session,
                DriverApplicationCreate(
                    email="person-payee-concurrent@example.com",
                    full_name="Concurrent Driver",
                    service_city="Abuja",
                    country_code="NG",
                ),
            )
            assert result.application is not None and result.reference is not None
            await session.commit()
            return result.reference, result.application

    reference, application = asyncio.run(seed_application())
    files = _seed_clean_kyc_files(
        postgis_db_sessionmaker, email="person-payee-concurrent@example.com"
    )
    crypto = EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1)

    async def submit_stage() -> None:
        async with postgis_db_sessionmaker() as session:
            await submit_application_person_payee(
                session,
                payload=PersonPayeeSubmissionCreate.model_validate(
                    _person_payee_payload(reference, files)
                ),
                crypto=crypto,
            )
            await session.commit()

    asyncio.run(submit_stage())
    first_admin = create_test_user(
        postgis_db_sessionmaker,
        email="person-payee-concurrent-admin-a@example.com",
        password=PASSWORD,
    )
    second_admin = create_test_user(
        postgis_db_sessionmaker,
        email="person-payee-concurrent-admin-b@example.com",
        password=PASSWORD,
    )
    barrier = asyncio.Barrier(2)

    async def decide(actor_id: UUID, decision: str, reason: str) -> str:
        async with postgis_db_sessionmaker() as session:
            await barrier.wait()
            try:
                view = await review_application_person_payee(
                    session,
                    application_id=application.id,
                    actor_user_id=actor_id,
                    payload=PersonPayeeReviewDecisionCreate(
                        client_request_id=uuid4(),
                        decision=decision,
                        reason_code=reason,
                        identity_match_confirmed=decision == "approved",
                        bank_account_match_confirmed=decision == "approved",
                        documents_readable_confirmed=decision == "approved",
                    ),
                    crypto=crypto,
                )
                await session.commit()
                assert view.submission is not None
                return view.submission.status
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def exercise() -> tuple[list[str], str, int]:
        results = await asyncio.gather(
            decide(first_admin.id, "approved", "complete_current_evidence"),
            decide(second_admin.id, "rejected", "identity_mismatch"),
        )
        async with postgis_db_sessionmaker() as session:
            submission = await session.scalar(select(DriverKycSubmission))
            assert submission is not None
            count = int(await session.scalar(select(func.count(DriverKycReviewDecision.id))) or 0)
            return sorted(results), submission.status, count

    results, terminal_status, decision_count = asyncio.run(exercise())
    assert results == sorted([terminal_status, "PERSON_PAYEE_ALREADY_DECIDED"])
    assert terminal_status in {"approved", "rejected"}
    assert decision_count == 1
