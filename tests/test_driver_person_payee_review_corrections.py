import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import select
from test_driver_person_payee_onboarding import (
    PASSWORD,
    _application,
    _complete_admin_review,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)
from test_email_delivery import RecordingEmailAdapter
from test_stored_files import FakeStorageProvider

from app.adapters.crypto import EnvelopeCryptoProvider
from app.api.v1.dependencies import get_storage_provider
from app.core.errors import AppError
from app.jobs.email_delivery import process_email_notification
from app.models.driver_application import DriverApplicationAccessToken
from app.models.notification import Notification, NotificationType
from app.models.payee import Payee
from app.models.user import UserRole
from app.services.disbursements import _frozen_payee_authority
from app.services.driver_applications import (
    application_from_access_token,
    synthetic_driver_application_access_token,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_applicant_bank_account_version,
    verify_bank_account_version_for_payout,
)


def _approval_payload(request_id=None) -> dict[str, object]:
    return {
        "client_request_id": str(request_id or uuid4()),
        "decision": "approved",
        "reason_code": "complete_current_evidence",
        "identity_match_confirmed": True,
        "bank_account_match_confirmed": True,
        "documents_readable_confirmed": True,
    }


def test_approval_requires_actual_exact_current_review_reads(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, db_sessionmaker, settings, suffix="review-evidence-red")
    application = _application(
        db_sessionmaker, email="person-payee-review-evidence-red@example.com"
    )
    files = _seed_clean_kyc_files(
        db_sessionmaker, email="person-payee-review-evidence-red@example.com"
    )
    assert (
        db_client.post(
            "/api/v1/auth/driver-onboarding/person-payee",
            json=_person_payee_payload(reference, files),
        ).status_code
        == 201
    )
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-review-evidence-red-admin@example.com",
        password=PASSWORD,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="person-payee-capture-authority-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    async def current_version_id():
        from app.models.payee import PayeeBankAccountVersion

        async with db_sessionmaker() as session:
            version = await session.scalar(select(PayeeBankAccountVersion))
            assert version is not None
            return version.id

    denied = db_client.post(
        f"/api/v1/admin/payees/bank-account-versions/"
        f"{asyncio.run(current_version_id())}/payout-verification",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={"verification_reference": f"unauthorized-{uuid4().hex}"},
    )
    assert denied.status_code == 403
    approval = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=_approval_payload(),
    )
    assert approval.status_code == 409
    assert approval.json()["error"]["code"] == "PERSON_PAYEE_BANK_ACCOUNT_UNVERIFIED"
    async def current_submission():
        from app.models.kyc import DriverKycSubmission

        async with db_sessionmaker() as session:
            submission = await session.scalar(select(DriverKycSubmission))
            assert submission is not None
            return submission

    headers = auth_headers(db_client, admin.email, PASSWORD)
    submission = asyncio.run(current_submission())
    verified = db_client.post(
        f"/api/v1/admin/payees/bank-account-versions/"
        f"{submission.bank_account_version_id}/payout-verification",
        headers=headers,
        json={"verification_reference": f"admin-provider-review-{submission.id.hex}"},
    )
    assert verified.status_code == 200

    response = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=headers,
        json=_approval_payload(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PERSON_PAYEE_REVIEW_EVIDENCE_INCOMPLETE"
    _complete_admin_review(
        db_client,
        db_sessionmaker,
        admin=admin,
        application=application,
        files=files,
    )
    approved = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=headers,
        json=_approval_payload(),
    )
    assert approved.status_code == 200, approved.json()


def test_applicant_capture_is_not_payout_authority(db_client, db_sessionmaker, settings) -> None:
    reference, _ = _register(db_client, db_sessionmaker, settings, suffix="capture-authority-red")
    application = _application(
        db_sessionmaker, email="person-payee-capture-authority-red@example.com"
    )
    files = _seed_clean_kyc_files(
        db_sessionmaker, email="person-payee-capture-authority-red@example.com"
    )
    assert (
        db_client.post(
            "/api/v1/auth/driver-onboarding/person-payee",
            json=_person_payee_payload(reference, files),
        ).status_code
        == 201
    )

    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-capture-authority-red-admin@example.com",
        password=PASSWORD,
    )

    async def exercise() -> tuple[str, bool, str]:
        async with db_sessionmaker() as session:
            payee = await session.scalar(
                select(Payee).where(Payee.subject_id == application.driver_profile_id)
            )
            assert payee is not None
            with pytest.raises(AppError) as exc_info:
                await _frozen_payee_authority(session, None, payee)  # type: ignore[arg-type]
            from app.models.payee import PayeeBankAccountVersion

            first_version = await session.scalar(select(PayeeBankAccountVersion))
            assert first_version is not None
            verification_reference = f"authorized-provider-{uuid4().hex}"
            _, first_verification = await verify_bank_account_version_for_payout(
                session,
                bank_account_version_id=first_version.id,
                verification_reference=verification_reference,
                actor_user_id=admin.id,
            )
            _, exact_retry = await verify_bank_account_version_for_payout(
                session,
                bank_account_version_id=first_version.id,
                verification_reference=verification_reference,
                actor_user_id=admin.id,
            )
            assert exact_retry.id == first_verification.id
            with pytest.raises(AppError) as verification_conflict:
                await verify_bank_account_version_for_payout(
                    session,
                    bank_account_version_id=first_version.id,
                    verification_reference=f"conflicting-provider-{uuid4().hex}",
                    actor_user_id=admin.id,
                )
            assert (
                verification_conflict.value.code
                == "BANK_ACCOUNT_PAYOUT_VERIFICATION_CONFLICT"
            )
            _, permitted = await _frozen_payee_authority(
                session, None, payee  # type: ignore[arg-type]
            )
            second_version = await add_applicant_bank_account_version(
                session,
                payee_id=payee.id,
                details=VerifiedBankAccountDetails(
                    account_name="Person Payee Driver",
                    account_number="9876543210",
                    bank_code="058",
                ),
                verification_reference=f"applicant-capture-{uuid4().hex}",
                actor_user_id=application.user_id,
                crypto=EnvelopeCryptoProvider(
                    keys={1: bytes(range(32))}, active_key_version=1
                ),
            )
            with pytest.raises(AppError) as stale:
                await _frozen_payee_authority(session, None, payee)  # type: ignore[arg-type]
            assert second_version.id != first_version.id
            return exc_info.value.code, permitted.id == first_version.id, stale.value.code

    assert asyncio.run(exercise()) == (
        "PAYOUT_BANK_ACCOUNT_UNVERIFIED",
        True,
        "PAYOUT_BANK_ACCOUNT_UNVERIFIED",
    )


def test_historical_decision_retry_resolves_original_submission(
    db_client, db_sessionmaker, settings
) -> None:
    reference, _ = _register(db_client, db_sessionmaker, settings, suffix="historical-retry-red")
    application = _application(
        db_sessionmaker, email="person-payee-historical-retry-red@example.com"
    )
    files = _seed_clean_kyc_files(
        db_sessionmaker, email="person-payee-historical-retry-red@example.com"
    )
    first = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-historical-retry-red-admin@example.com",
        password=PASSWORD,
    )
    request_id = uuid4()
    decision = {
        "client_request_id": str(request_id),
        "decision": "rejected",
        "reason_code": "unreadable_evidence",
    }
    path = f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision"
    rejected = db_client.post(
        path,
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=decision,
    )
    second = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(reference, files),
    )
    replay = db_client.post(
        path,
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=decision,
    )

    assert first.status_code == second.status_code == 201
    assert rejected.status_code == replay.status_code == 200
    assert replay.json()["submission_id"] == first.json()["submission_id"]
    assert replay.json()["version"] == 1


def test_resubmission_invalidates_every_stale_exact_review_read(
    db_client, db_sessionmaker, settings
) -> None:
    access_token, _ = _register(
        db_client, db_sessionmaker, settings, suffix="stale-review"
    )
    application = _application(
        db_sessionmaker, email="person-payee-stale-review@example.com"
    )
    files = _seed_clean_kyc_files(
        db_sessionmaker, email="person-payee-stale-review@example.com"
    )
    first = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(access_token, files),
    )
    admin = create_test_user(
        db_sessionmaker,
        email="person-payee-stale-review-admin@example.com",
        password=PASSWORD,
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    _complete_admin_review(
        db_client,
        db_sessionmaker,
        admin=admin,
        application=application,
        files=files,
    )
    rejected = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "decision": "rejected",
            "reason_code": "identity_mismatch",
        },
    )
    second = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json=_person_payee_payload(access_token, files),
    )
    assert first.status_code == 201
    assert rejected.status_code == 200
    assert second.status_code == 201

    submission_id = second.json()["submission_id"]

    async def current_account_version_id():
        from app.models.kyc import DriverKycSubmission

        async with db_sessionmaker() as session:
            current = await session.get(DriverKycSubmission, UUID(submission_id))
            assert current is not None
            return current.bank_account_version_id

    account_version_id = asyncio.run(current_account_version_id())
    verified = db_client.post(
        f"/api/v1/admin/payees/bank-account-versions/{account_version_id}/payout-verification",
        headers=headers,
        json={"verification_reference": f"admin-provider-review-{submission_id}"},
    )
    assert verified.status_code == 200
    assert (
        db_client.post(
            f"/api/v1/admin/kyc/submissions/{submission_id}/nin/reveal",
            headers=headers,
            json={"purpose": "person_payee_approval"},
        ).status_code
        == 200
    )
    assert (
        db_client.post(
            f"/api/v1/admin/payees/bank-account-versions/{account_version_id}/reveal",
            headers=headers,
            json={"purpose": "person_payee_approval"},
        ).status_code
        == 200
    )
    path = f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision"
    stale_documents = db_client.post(
        path,
        headers=headers,
        json=_approval_payload(),
    )
    assert stale_documents.status_code == 409
    assert (
        stale_documents.json()["error"]["code"]
        == "PERSON_PAYEE_REVIEW_EVIDENCE_INCOMPLETE"
    )
    for file_id in files.values():
        assert (
            db_client.post(
                f"/api/v1/admin/files/{file_id}/download",
                headers=headers,
                json={
                    "purpose": "kyc_review",
                    "reason": f"person_payee_approval:{submission_id}",
                },
            ).status_code
            == 200
        )
    assert db_client.post(path, headers=headers, json=_approval_payload()).status_code == 200


def test_status_references_are_indistinguishable_across_every_mutation_probe(
    db_client, db_sessionmaker, settings
) -> None:
    _, response = _register(db_client, db_sessionmaker, settings, suffix="probe-red")
    real_reference = response.json()["application_reference"]
    duplicate = db_client.post(
        "/api/v1/auth/register-driver",
        json={
            "email": "person-payee-probe-red@example.com",
            "full_name": "Duplicate probe",
        },
    )
    assert duplicate.status_code == 202
    fake_reference = duplicate.json()["application_reference"]
    assert fake_reference != real_reference
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    upload_id = uuid4()
    file_id = uuid4()
    files = {
        "driver_license": uuid4(),
        "driver_photo": uuid4(),
        "signed_agreement": uuid4(),
    }

    probes = (
        (
            "/api/v1/auth/driver-onboarding/files/uploads",
            lambda reference: {
                    "application_access_token": reference,
                "upload": {
                    "client_request_id": str(uuid4()),
                    "purpose": "driver_kyc",
                    "filename": "probe.png",
                    "content_type": "image/png",
                    "size_bytes": 68,
                    "sha256": "a" * 64,
                },
            },
        ),
        (
            f"/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm",
            lambda reference: {"application_access_token": reference},
        ),
        (
            f"/api/v1/auth/driver-onboarding/files/{file_id}/status",
            lambda reference: {"application_access_token": reference},
        ),
        (
            "/api/v1/auth/driver-onboarding/person-payee",
            lambda reference: _person_payee_payload(reference, files),
        ),
    )
    for path, payload in probes:
        fresh = db_client.post(path, json=payload(real_reference))
        repeated = db_client.post(path, json=payload(fake_reference))
        fresh_error = fresh.json()["error"]
        repeated_error = repeated.json()["error"]
        for error in (fresh_error, repeated_error):
            error.pop("request_id", None)
        assert (fresh.status_code, fresh_error) == (repeated.status_code, repeated_error), path

    assert response.json().keys() == duplicate.json().keys()


def test_fresh_and_duplicate_driver_probes_deliver_separate_non_enumerating_authority(
    db_client, db_sessionmaker, settings, caplog
) -> None:
    fresh_token, fresh = _register(
        db_client, db_sessionmaker, settings, suffix="access-delivery"
    )

    async def existing_access_ids() -> set:
        async with db_sessionmaker() as session:
            return set((await session.scalars(select(DriverApplicationAccessToken.id))).all())

    prior_ids = asyncio.run(existing_access_ids())
    duplicate = db_client.post(
        "/api/v1/auth/register-driver",
        json={
            "email": "person-payee-access-delivery@example.com",
            "full_name": "Probe must remain generic",
        },
    )
    assert duplicate.status_code == fresh.status_code == 202
    assert duplicate.json().keys() == fresh.json().keys()
    assert "access" not in duplicate.text.lower()

    async def inspect_and_deliver() -> tuple[str, list[str], list[dict], str, str]:
        async with db_sessionmaker() as session:
            accesses = list((await session.scalars(select(DriverApplicationAccessToken))).all())
            new_access = next(access for access in accesses if access.id not in prior_ids)
            duplicate_token = synthetic_driver_application_access_token(
                new_access,
                settings,
                synthetic_test_authority=True,
            )
            notices = list(
                (
                    await session.scalars(
                        select(Notification).where(
                            Notification.type_key
                            == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value
                        )
                    )
                ).all()
            )
            notice = next(
                item
                for item in notices
                if item.payload["driver_application_access_id"] == str(new_access.id)
            )
            notice_id = notice.id
            mismatched_notice_id = next(item.id for item in notices if item.id != notice_id)
            payloads = [item.payload for item in notices]
            digests = [access.token_sha256 for access in accesses]
        adapter = RecordingEmailAdapter()
        result = await process_email_notification(
            {
                "sessionmaker": db_sessionmaker,
                "settings": settings,
                "email_adapter": adapter,
            },
            str(notice_id),
            now=datetime.now(UTC),
        )
        assert result == "sent"
        assert len(adapter.messages) == 1
        delivered_body = adapter.messages[0].text_body
        assert duplicate_token in delivered_body
        mismatched_adapter = RecordingEmailAdapter()
        mismatch_result = await process_email_notification(
            {
                "sessionmaker": db_sessionmaker,
                "settings": settings.model_copy(
                    update={"jwt_secret_key": "different-test-secret-key-at-least-32-bytes"}
                ),
                "email_adapter": mismatched_adapter,
            },
            str(mismatched_notice_id),
            now=datetime.now(UTC),
        )
        assert mismatch_result == "failed"
        assert mismatched_adapter.messages == []
        async with db_sessionmaker() as session:
            first_app = await application_from_access_token(
                session, token=fresh_token, settings=settings, lock=False
            )
            duplicate_app = await application_from_access_token(
                session, token=duplicate_token, settings=settings, lock=False
            )
            assert first_app.id == duplicate_app.id
            new_access = await session.scalar(
                select(DriverApplicationAccessToken).where(
                    DriverApplicationAccessToken.id.not_in(prior_ids)
                )
            )
            assert new_access is not None
            new_access.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            mismatched_notice = await session.get(Notification, mismatched_notice_id)
            assert mismatched_notice is not None
            mismatch_code = str(mismatched_notice.last_error_code)
        return duplicate_token, digests, payloads, delivered_body, mismatch_code

    duplicate_token, digests, payloads, delivered_body, mismatch_code = asyncio.run(
        inspect_and_deliver()
    )
    assert len(digests) == len(set(digests)) == 2
    assert len(payloads) == 2
    assert all(set(payload) == {"driver_application_access_id"} for payload in payloads)
    assert fresh_token not in str(payloads)
    assert duplicate_token not in str(payloads)
    assert "person-payee-access-delivery@example.com" not in delivered_body
    assert fresh_token not in caplog.text
    assert duplicate_token not in caplog.text
    assert mismatch_code == "driver_onboarding_access_evidence_mismatch"

    async def invalid_errors() -> tuple[tuple, tuple]:
        results = []
        async with db_sessionmaker() as session:
            for token in (duplicate_token, "not-a-valid-access-token"):
                with pytest.raises(AppError) as exc_info:
                    await application_from_access_token(
                        session, token=token, settings=settings, lock=False
                    )
                error = exc_info.value
                results.append((error.code, error.message, error.status_code))
        return results[0], results[1]

    expired, unknown = asyncio.run(invalid_errors())
    assert expired == unknown == (
        "ONBOARDING_ACCESS_INVALID",
        "Driver onboarding access is unavailable",
        404,
    )
