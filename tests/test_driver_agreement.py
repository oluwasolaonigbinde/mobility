import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_driver_person_payee_onboarding import (
    _application,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)

from app.adapters.crypto import EnvelopeCryptoProvider
from app.api.v1.dependencies import get_registration_rate_limiter
from app.core.rate_limit import RateLimitDecision
from app.models.driver_application import DriverApplication
from app.models.kyc import DriverKycSubmission
from app.schemas.driver_onboarding import PersonPayeeSubmissionCreate
from app.services.driver_onboarding import submit_application_person_payee


@pytest.mark.parametrize("fresh", [True, False])
def test_renewal_exact_retry_preserves_fresh_or_reused_consent_provenance(fresh):
    from types import SimpleNamespace

    from app.core.errors import AppError
    from app.services.driver_agreement import require_agreement_retry

    recorded = SimpleNamespace(agreement_version="1", agreement_acceptance_requested=fresh)
    version = "1" if fresh else None
    require_agreement_retry(recorded, version=version, accepted=fresh)
    with pytest.raises(AppError):
        require_agreement_retry(recorded, version=version, accepted=not fresh)
    with pytest.raises(AppError):
        require_agreement_retry(recorded, version="changed", accepted=fresh)


@pytest.mark.parametrize("changes", [{"agreement_accepted": False}, {"agreement_version": "old"}])
def test_public_capture_rejects_missing_or_stale_consent_atomically(
    db_client, db_sessionmaker, settings, changes
):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix="consent-denied")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-consent-denied@example.com")
    data = _person_payee_payload(token, files, db_client)
    response = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee", json={**data, **changes}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DRIVER_AGREEMENT_REQUIRED"
    application = _application(db_sessionmaker, email="person-payee-consent-denied@example.com")
    assert application.agreement_version is None and application.agreement_accepted_at is None


def test_acceptance_is_server_dated_mirrored_and_exact_retry_survives_version_change(
    db_client, db_sessionmaker, settings, monkeypatch
):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix="consent-retry")
    files = _seed_clean_kyc_files(db_sessionmaker, email="person-payee-consent-retry@example.com")
    data = _person_payee_payload(token, files, db_client)
    data["account_name"] = "  Person Payee Driver  "
    first = db_client.post("/api/v1/auth/driver-onboarding/person-payee", json=data)
    assert first.status_code == 201, first.text
    application = _application(db_sessionmaker, email="person-payee-consent-retry@example.com")
    assert application.agreement_version == "1" and application.agreement_accepted_at is not None
    monkeypatch.setattr("app.services.driver_agreement.DRIVER_AGREEMENT_VERSION", "2")
    from datetime import UTC, datetime, timedelta

    import jwt

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(minutes=30)

    monkeypatch.setattr("jwt.api_jwt.datetime", Later)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(data["bank_check_receipt"], settings.jwt_secret_key, algorithms=["HS256"])

    async def unavailable_catalog(_):
        raise AssertionError("An exact committed retry must not consult the changed provider")

    monkeypatch.setattr("app.adapters.banks.BankAdapter.banks", unavailable_catalog)
    retry = db_client.post("/api/v1/auth/driver-onboarding/person-payee", json=data)
    assert retry.status_code == 201 and retry.json() == first.json()
    after = _application(db_sessionmaker, email=application.email)
    assert after.agreement_accepted_at == application.agreement_accepted_at
    changed = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee", json={**data, "agreement_accepted": False}
    )
    assert changed.status_code == 409


def test_concurrent_exact_capture_records_one_acceptance(
    postgis_db_client, postgis_db_sessionmaker, settings
):
    token, _ = _register(
        postgis_db_client, postgis_db_sessionmaker, settings, suffix="consent-concurrent"
    )
    files = _seed_clean_kyc_files(
        postgis_db_sessionmaker, email="person-payee-consent-concurrent@example.com"
    )
    data = PersonPayeeSubmissionCreate.model_validate(
        _person_payee_payload(token, files, postgis_db_client)
    )

    async def capture():
        async with postgis_db_sessionmaker() as session:
            result = await submit_application_person_payee(
                session,
                payload=data,
                crypto=EnvelopeCryptoProvider(keys={1: bytes(range(32))}, active_key_version=1),
                settings=settings,
            )
            await session.commit()
            return result.submission.id, result.submission.agreement_accepted_at

    async def inspect():
        first, second = await asyncio.gather(capture(), capture())
        assert first == second
        async with postgis_db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverKycSubmission.id))) == 1
            application = await session.scalar(select(DriverApplication))
            assert (
                application.agreement_version == "1"
                and application.agreement_accepted_at == first[1]
            )

    asyncio.run(inspect())


@pytest.mark.parametrize("storage,allowed,status", [(False, False, 503), (True, False, 429)])
def test_capability_and_local_rate_failures_never_unlock_manual_fallback(
    db_client, db_sessionmaker, settings, storage, allowed, status
):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix="name-limited")

    class Limiter:
        async def reserve(self, ip, email):
            return RateLimitDecision(
                allowed=allowed, storage_available=storage, retry_after_seconds=60
            )

    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: Limiter()
    for capability, expected in ((token, status), (str(uuid4()), 404)):
        response = db_client.post(
            "/api/v1/auth/driver-onboarding/account-name",
            json={
                "application_access_token": capability,
                "bank_code": "058",
                "account_number": "0123456789",
            },
        )
        assert response.status_code == expected
        assert "bank_check_receipt" not in response.text


def test_staff_created_driver_without_consent_cannot_be_approved_and_can_accept_in_renewal(
    db_client, db_sessionmaker
):
    from types import SimpleNamespace

    from conftest import auth_headers
    from test_driver_person_payee_onboarding import _complete_admin_review
    from test_kyc import PASSWORD, _payload, _seed_driver_authority

    admin, driver, profile, bank_id, files = _seed_driver_authority(
        db_sessionmaker, suffix="missing-consent"
    )
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    initial = db_client.post(
        "/api/v1/driver/kyc/submissions",
        headers=driver_headers,
        json=_payload(bank_id, files),
    )
    assert initial.status_code == 201

    async def remove_legacy_consent():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(DriverApplication.id))) == 0
            current = await session.scalar(select(DriverKycSubmission))
            current.agreement_version = None
            current.agreement_accepted_at = None
            current.agreement_acceptance_requested = None
            await session.commit()
            return str(current.id)

    original_id = asyncio.run(remove_legacy_consent())
    decision_path = f"/api/v1/admin/drivers/{profile.id}/documents/person-payee-decision"
    denied = db_client.post(
        decision_path,
        headers=admin_headers,
        json={
            "submission_id": original_id,
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "DRIVER_AGREEMENT_REQUIRED"

    async def legacy_approved_state():
        async with db_sessionmaker() as session:
            current = await session.scalar(select(DriverKycSubmission))
            current.status = "approved"
            await session.commit()

    asyncio.run(legacy_approved_state())
    renewal_path = "/api/v1/driver/documents/person-payee"
    payload = {"expected_submission_id": original_id, "client_request_id": str(uuid4())}
    missing = db_client.post(renewal_path, headers=driver_headers, json=payload)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "DRIVER_AGREEMENT_REQUIRED"
    payload.update(agreement_version="1", agreement_accepted=True)
    accepted = db_client.post(renewal_path, headers=driver_headers, json=payload)
    retry = db_client.post(renewal_path, headers=driver_headers, json=payload)
    assert accepted.status_code == retry.status_code == 201, accepted.text
    assert accepted.json() == retry.json()
    status = db_client.get("/api/v1/driver/documents", headers=driver_headers).json()
    assert status["person_payee"]["agreement_version"] == "1"
    assert (
        status["person_payee"]["agreement_accepted_at"] == accepted.json()["agreement_accepted_at"]
    )

    async def persisted_acceptance():
        async with db_sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(DriverKycSubmission).order_by(DriverKycSubmission.version)
                )
            )
            assert len(rows) == 2
            assert rows[0].agreement_accepted_at is None
            assert rows[1].agreement_accepted_at is not None
            assert rows[1].agreement_acceptance_requested is True
            assert rows[1].bank_account_version_id == rows[0].bank_account_version_id

    asyncio.run(persisted_acceptance())
    changed = db_client.post(
        renewal_path, headers=driver_headers, json={**payload, "agreement_accepted": False}
    )
    assert changed.status_code == 409
    _complete_admin_review(
        db_client,
        db_sessionmaker,
        admin=admin,
        application=SimpleNamespace(driver_profile_id=profile.id),
        files={kind: files[kind] for kind in ("driver_license", "driver_photo")},
        verification_reference="provider-neutral-missing-consent-evidence-reference",
    )
    approved = db_client.post(
        decision_path,
        headers=admin_headers,
        json={
            "submission_id": accepted.json()["submission_id"],
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "identity_match_confirmed": True,
            "bank_account_match_confirmed": True,
            "documents_readable_confirmed": True,
        },
    )
    assert approved.status_code == 200, approved.text


def test_submitted_version_does_not_substitute_for_affirmative_consent():
    from app.core.errors import AppError
    from app.services.driver_agreement import submission_agreement

    with pytest.raises(AppError) as caught:
        asyncio.run(
            submission_agreement(None, current=None, version="1", accepted=False, renewal=True)
        )
    assert caught.value.code == "DRIVER_AGREEMENT_REQUIRED"
