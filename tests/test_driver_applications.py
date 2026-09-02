import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_user,
    fetch_auth_audit_events,
    fetch_user_by_email,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette import status as http_status

from app.api.v1.dependencies import get_registration_rate_limiter
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import InMemoryRegistrationRateLimiter, RateLimitDecision
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication, DriverApplicationAccessToken
from app.models.kyc import DriverKycSubmission
from app.models.payee import Payee
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle
from app.schemas.driver_applications import DriverApplicationCreate
from app.services import driver_applications as application_service
from app.services.driver_applications import (
    list_driver_applications,
    synthetic_driver_application_access_token,
)
from app.services.privacy_authority import require_collection_authority

PASSWORD = "long-secure-password"


def test_public_person_payee_collection_denies_before_application_or_payee_writes(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    blocked = settings.model_copy(
        update={
            "driver_registration_enabled": True,
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
                int(await session.scalar(select(func.count(Payee.id))) or 0),
                int(await session.scalar(select(func.count(DriverKycSubmission.id))) or 0),
                int(await session.scalar(select(func.count(AuditEvent.id))) or 0),
            )

    before = asyncio.run(counts())
    response = db_client.post(
        "/api/v1/auth/driver-onboarding/person-payee",
        json={
            "application_access_token": "synthetic-but-unauthorized-access-token",
            "client_request_id": str(uuid4()),
            "nin": "12345678901",
            "account_name": "Synthetic Applicant",
            "account_number": "0123456789",
            "bank_code": "058",
            "driver_license_file_id": str(uuid4()),
            "driver_photo_file_id": str(uuid4()),
            "signed_agreement_file_id": str(uuid4()),
        },
    )

    assert response.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"]["code"] == "PRIVACY_COLLECTION_BLOCKED"
    assert asyncio.run(counts()) == before


@pytest.mark.parametrize(
    "legal_reference",
    ["", "missing", "placeholder", "EXT-LEGAL-PRIVACY"],
)
def test_collection_authority_rejects_absent_or_placeholder_legal_references(
    settings, legal_reference
) -> None:
    blocked = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_collection_live_authorized": True,
            "privacy_collection_synthetic_test_mode": False,
            "privacy_legal_approval_reference": legal_reference,
        }
    )
    with pytest.raises(AppError) as denial:
        require_collection_authority(blocked)
    assert denial.value.code == "PRIVACY_COLLECTION_BLOCKED"

    approved = blocked.model_copy(
        update={"privacy_legal_approval_reference": "approved-privacy-authority-v1"}
    )
    require_collection_authority(approved)


def test_synthetic_privacy_authority_is_rejected_outside_test() -> None:
    with pytest.raises(
        ValueError,
        match="PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE requires environment=test",
    ):
        Settings(environment="local", privacy_collection_synthetic_test_mode=True)


def test_disclosure_synthetic_authority_does_not_default_collection_authority() -> None:
    disclosure_only = Settings(
        environment="test",
        privacy_disclosure_synthetic_test_mode=True,
    )
    assert disclosure_only.privacy_collection_synthetic_test_mode is False
    with pytest.raises(AppError) as denial:
        require_collection_authority(disclosure_only)
    assert denial.value.code == "PRIVACY_COLLECTION_BLOCKED"


def test_collection_authority_rechecks_synthetic_environment_at_runtime(settings) -> None:
    copied_without_validation = settings.model_copy(
        update={
            "environment": "production",
            "privacy_collection_synthetic_test_mode": True,
            "privacy_collection_live_authorized": False,
        }
    )
    with pytest.raises(AppError) as denial:
        require_collection_authority(copied_without_validation)
    assert denial.value.code == "PRIVACY_COLLECTION_BLOCKED"


def test_collection_and_disclosure_synthetic_authorities_can_be_controlled_separately(
    settings,
) -> None:
    collection_disabled = settings.model_copy(
        update={
            "privacy_collection_synthetic_test_mode": False,
            "privacy_collection_live_authorized": False,
        }
    )
    with pytest.raises(AppError) as denial:
        require_collection_authority(collection_disabled)
    assert denial.value.code == "PRIVACY_COLLECTION_BLOCKED"

    collection_enabled = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": False,
            "privacy_collection_synthetic_test_mode": True,
        }
    )
    require_collection_authority(collection_enabled)


class BlockingRegistrationLimiter:
    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        del ip, email
        return RateLimitDecision(allowed=False, bucket="email", retry_after_seconds=37)


def enable_registration(db_client, settings) -> None:
    enabled = settings.model_copy(update={"driver_registration_enabled": True})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: (
        InMemoryRegistrationRateLimiter()
    )


def test_public_registration_is_closed_by_default_and_does_not_write(db_client, db_sessionmaker):
    response = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": "new-driver@example.com", "full_name": "New Driver"},
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "APPLICATION_UNAVAILABLE"
    assert fetch_user_by_email(db_sessionmaker, "new-driver@example.com") is None


def test_public_registration_rate_limit_is_stable_and_does_not_write(
    db_client,
    db_sessionmaker,
    settings,
):
    enable_registration(db_client, settings)
    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: (
        BlockingRegistrationLimiter()
    )
    try:
        response = db_client.post(
            "/api/v1/auth/register-driver",
            json={"email": "limited-driver@example.com", "full_name": "Limited Driver"},
        )
    finally:
        db_client.app.dependency_overrides.pop(get_registration_rate_limiter, None)

    assert response.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers["Retry-After"] == "37"
    assert response.json()["error"]["details"]["retry_after_seconds"] == 37
    assert fetch_user_by_email(db_sessionmaker, "limited-driver@example.com") is None


def test_repeated_registration_blocks_emit_one_transition_audit(
    db_client,
    db_sessionmaker,
    settings,
):
    enabled = settings.model_copy(update={"driver_registration_enabled": True})
    limiter = InMemoryRegistrationRateLimiter(ip_limit=10, email_limit=1)
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: limiter

    payload = {"email": "audit-limited@example.com", "full_name": "Limited Driver"}
    assert db_client.post("/api/v1/auth/register-driver", json=payload).status_code == 202
    assert db_client.post("/api/v1/auth/register-driver", json=payload).status_code == 429
    assert db_client.post("/api/v1/auth/register-driver", json=payload).status_code == 429

    events = fetch_auth_audit_events(db_sessionmaker)
    actions = [event.action for event in events]
    assert actions.count("auth.driver_application.created") == 1
    assert actions.count("auth.driver_registration.rate_limited") == 1
    [rate_limit_event] = [
        event for event in events if event.action == "auth.driver_registration.rate_limited"
    ]
    assert rate_limit_event.event_metadata == {
        "bucket": "email",
        "retry_after_seconds": 60,
    }


def test_enabled_registration_fails_closed_without_rate_limit_storage(
    db_client,
    db_sessionmaker,
    settings,
):
    enabled = settings.model_copy(update={"driver_registration_enabled": True})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled

    response = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": "unavailable-driver@example.com", "full_name": "Unavailable Driver"},
    )

    assert response.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "60"
    assert fetch_user_by_email(db_sessionmaker, "unavailable-driver@example.com") is None


def test_public_registration_creates_pending_graph_and_returns_reference(
    db_client,
    db_sessionmaker,
    settings,
):
    enable_registration(db_client, settings)

    response = db_client.post(
        "/api/v1/auth/register-driver",
        json={
            "email": " New.Driver@Example.com ",
            "full_name": " New Driver ",
            "phone": "+234 800 000 0000",
            "service_city": " Lagos ",
            "country_code": "ng",
        },
    )

    assert response.status_code == http_status.HTTP_202_ACCEPTED
    data = response.json()
    assert data["status"] == "pending"
    assert data["message"] == "Application received for review."
    assert isinstance(data["application_reference"], str)
    assert "password_hash" not in response.text

    async def fetch_graph():
        async with db_sessionmaker() as session:
            user = await session.scalar(select(User).where(User.email == "new.driver@example.com"))
            profile = await session.scalar(
                select(DriverProfile).where(DriverProfile.user_id == user.id)
            )
            application = await session.scalar(
                select(DriverApplication).where(DriverApplication.user_id == user.id)
            )
            counts = []
            for model in (Vehicle, Payee, CampaignAssignment):
                counts.append(await session.scalar(select(func.count()).select_from(model)))
            return user, profile, application, counts

    user, profile, application, unrelated_counts = asyncio.run(fetch_graph())
    assert user is not None
    assert user.role == UserRole.DRIVER.value
    assert user.status == UserStatus.INVITED.value
    assert user.must_change_password is True
    assert user.password_hash != "new-driver-password"
    assert profile is not None
    assert profile.onboarding_status == "pending"
    assert profile.service_city == "Lagos"
    assert profile.country_code == "NG"
    assert application is not None
    assert application.status == "pending"
    assert application.status_reference_sha256 != data["application_reference"]
    assert unrelated_counts == [0, 0, 0]

    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": "new.driver@example.com", "password": "not-a-password"},
    )
    assert login.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert "access_token" not in login.text
    assert db_client.get("/api/v1/me").status_code == http_status.HTTP_401_UNAUTHORIZED

    known = db_client.get(f"/api/v1/auth/driver-application-status/{data['application_reference']}")
    unknown = db_client.get("/api/v1/auth/driver-application-status/not-a-real-reference")
    assert known.status_code == unknown.status_code == http_status.HTTP_200_OK
    assert known.json() == unknown.json()

    events = fetch_auth_audit_events(db_sessionmaker)
    assert [event.action for event in events].count("auth.driver_application.created") == 1
    assert [event.action for event in events].count("auth.login.failed") == 1


def test_duplicate_normalized_email_is_generic_and_does_not_mutate_existing_user(
    db_client,
    db_sessionmaker,
    settings,
):
    enable_registration(db_client, settings)
    existing = create_test_user(
        db_sessionmaker,
        email="existing@example.com",
        password=PASSWORD,
        full_name="Original Name",
        role=UserRole.ADVERTISER,
        user_status=UserStatus.ACTIVE,
    )

    first = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": "new@example.com", "full_name": "New Driver"},
    )
    duplicate = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": " EXISTING@Example.com ", "full_name": "Attacker Name"},
    )

    assert first.status_code == duplicate.status_code == http_status.HTTP_202_ACCEPTED
    assert duplicate.json()["status"] == first.json()["status"]
    assert duplicate.json()["message"] == first.json()["message"]
    assert isinstance(first.json()["application_reference"], str)
    assert isinstance(duplicate.json()["application_reference"], str)
    assert duplicate.json().keys() == first.json().keys()
    assert duplicate.json()["application_reference"] != first.json()["application_reference"]

    async def fetch_existing():
        async with db_sessionmaker() as session:
            return await session.get(type(existing), existing.id)

    unchanged = asyncio.run(fetch_existing())
    assert unchanged is not None
    assert unchanged.full_name == "Original Name"
    assert unchanged.role == UserRole.ADVERTISER.value
    assert len(fetch_auth_audit_events(db_sessionmaker)) == 1


def test_postgres_same_email_race_creates_one_pending_graph_and_generic_results(
    postgis_db_sessionmaker,
    monkeypatch,
):
    barrier = asyncio.Barrier(2)
    original_lookup = application_service.get_user_by_email

    async def synchronized_lookup(session, email):
        result = await original_lookup(session, email)
        if result is None:
            await barrier.wait()
        return result

    monkeypatch.setattr(application_service, "get_user_by_email", synchronized_lookup)
    payload = DriverApplicationCreate(
        email="race-driver@example.com",
        full_name="Race Driver",
        service_city="Lagos",
        country_code="NG",
    )

    async def submit_once():
        async with postgis_db_sessionmaker() as session:
            result = await application_service.submit_driver_application(session, payload)
            await session.commit()
            return result

    async def exercise():
        results = await asyncio.gather(submit_once(), submit_once())
        async with postgis_db_sessionmaker() as session:
            user_count = await session.scalar(
                select(func.count()).select_from(User).where(User.email == payload.email)
            )
            profile_count = await session.scalar(select(func.count()).select_from(DriverProfile))
            application_count = await session.scalar(
                select(func.count()).select_from(DriverApplication)
            )
        return results, user_count, profile_count, application_count

    results, user_count, profile_count, application_count = asyncio.run(exercise())
    assert sum(result.application is not None for result in results) == 1
    assert all(isinstance(result.reference, str) for result in results)
    assert user_count == profile_count == application_count == 1


def test_non_email_integrity_error_is_not_hidden_as_duplicate(db_sessionmaker):
    payload = DriverApplicationCreate(
        email="integrity-driver@example.com",
        full_name="Integrity Driver",
    )

    async def exercise():
        async with db_sessionmaker() as session:
            real_flush = session.flush
            calls = 0

            async def fail_profile_flush(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise IntegrityError(
                        "INSERT driver_profiles",
                        {},
                        RuntimeError("unexpected driver profile constraint"),
                    )
                return await real_flush(*args, **kwargs)

            session.flush = AsyncMock(side_effect=fail_profile_flush)
            with pytest.raises(IntegrityError, match="unexpected driver profile constraint"):
                await application_service.submit_driver_application(session, payload)

    asyncio.run(exercise())


def test_postgres_http_same_email_race_has_generic_responses_and_one_graph(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
):
    enable_registration(postgis_db_client, settings)
    barrier = asyncio.Barrier(2)
    original_lookup = application_service.get_user_by_email

    async def synchronized_lookup(session, email):
        result = await original_lookup(session, email)
        if result is None:
            await barrier.wait()
        return result

    monkeypatch.setattr(application_service, "get_user_by_email", synchronized_lookup)
    payload = {"email": "http-race@example.com", "full_name": "HTTP Race"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: postgis_db_client.post(
                    "/api/v1/auth/register-driver",
                    json=payload,
                ),
                range(2),
            )
        )

    assert [response.status_code for response in responses] == [202, 202]
    bodies = [response.json() for response in responses]
    assert bodies[0].keys() == bodies[1].keys()
    assert bodies[0]["status"] == bodies[1]["status"] == "pending"
    assert bodies[0]["message"] == bodies[1]["message"]
    assert all(isinstance(body["application_reference"], str) for body in bodies)

    async def counts():
        async with postgis_db_sessionmaker() as session:
            values = []
            for model in (User, DriverProfile, DriverApplication):
                values.append(await session.scalar(select(func.count()).select_from(model)))
            return tuple(values)

    assert asyncio.run(counts()) == (1, 1, 1)


@pytest.mark.parametrize(
    ("role", "user_status", "expected_code"),
    [
        (UserRole.DRIVER, UserStatus.ACTIVE, "FORBIDDEN_ROLE"),
        (UserRole.ADVERTISER, UserStatus.ACTIVE, "FORBIDDEN_ROLE"),
        (UserRole.ADMIN, UserStatus.DISABLED, "FORBIDDEN_ROLE"),
    ],
)
def test_direct_admin_queue_service_rejects_non_active_admin_without_mutation(
    db_sessionmaker,
    role,
    user_status,
    expected_code,
):
    actor = create_test_user(
        db_sessionmaker,
        email=f"queue-service-{role.value}-{user_status.value}@example.com",
        password=PASSWORD,
        role=role,
        user_status=user_status,
    )

    async def exercise():
        async with db_sessionmaker() as session:
            before = {
                model: await session.scalar(select(func.count()).select_from(model))
                for model in (DriverApplication, AuditEvent)
            }
            with pytest.raises(AppError) as exc_info:
                await list_driver_applications(
                    session,
                    admin_user_id=actor.id,
                    limit=25,
                    offset=0,
                )
            after = {
                model: await session.scalar(select(func.count()).select_from(model))
                for model in (DriverApplication, AuditEvent)
            }
            return exc_info.value, before, after

    error, before, after = asyncio.run(exercise())
    assert error.code == expected_code
    assert after == before


def test_direct_admin_queue_service_rejects_unknown_user_without_mutation(db_sessionmaker):
    async def exercise():
        async with db_sessionmaker() as session:
            before = {
                model: await session.scalar(select(func.count()).select_from(model))
                for model in (DriverApplication, AuditEvent)
            }
            with pytest.raises(AppError) as exc_info:
                await list_driver_applications(
                    session,
                    admin_user_id=uuid4(),
                    limit=25,
                    offset=0,
                )
            after = {
                model: await session.scalar(select(func.count()).select_from(model))
                for model in (DriverApplication, AuditEvent)
            }
            return exc_info.value, before, after

    error, before, after = asyncio.run(exercise())
    assert error.code == "FORBIDDEN_ROLE"
    assert after == before


def test_admin_queue_is_sanitized_and_requires_admin(db_client, db_sessionmaker, settings):
    enable_registration(db_client, settings)
    response = db_client.post(
        "/api/v1/auth/register-driver",
        json={
            "email": "queue-driver@example.com",
            "full_name": "Queue Driver",
            "phone": "+2348000000000",
            "service_city": "Abuja",
            "country_code": "NG",
        },
    )
    assert response.status_code == http_status.HTTP_202_ACCEPTED

    admin = create_test_user(db_sessionmaker, email="queue-admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="queue-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    admin_response = db_client.get(
        "/api/v1/admin/driver-applications?limit=1&offset=0",
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    advertiser_response = db_client.get(
        "/api/v1/admin/driver-applications",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    assert admin_response.status_code == http_status.HTTP_200_OK
    data = admin_response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["email"] == "queue-driver@example.com"
    assert item["status"] == "pending"
    assert "status_reference_sha256" not in admin_response.text
    assert "password_hash" not in admin_response.text
    assert "ratelimit" not in admin_response.text
    assert advertiser_response.status_code == http_status.HTTP_403_FORBIDDEN


def test_explicit_public_applicant_rejection_is_terminal_and_revokes_access(
    db_client, db_sessionmaker, settings
) -> None:
    enable_registration(db_client, settings)
    registration = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": "rejected-applicant@example.com", "full_name": "Rejected Applicant"},
    )
    assert registration.status_code == http_status.HTTP_202_ACCEPTED
    admin = create_test_user(
        db_sessionmaker,
        email="rejected-applicant-admin@example.com",
        password=PASSWORD,
    )

    async def application_authority() -> tuple[DriverApplication, str, int]:
        async with db_sessionmaker() as session:
            application = await session.scalar(
                select(DriverApplication).where(
                    DriverApplication.email == "rejected-applicant@example.com"
                )
            )
            assert application is not None
            access = await session.scalar(
                select(DriverApplicationAccessToken).where(
                    DriverApplicationAccessToken.application_id == application.id
                )
            )
            assert access is not None
            token = synthetic_driver_application_access_token(
                access,
                settings,
                synthetic_test_authority=True,
            )
            count = int(
                await session.scalar(
                    select(func.count(DriverApplicationAccessToken.id)).where(
                        DriverApplicationAccessToken.application_id == application.id
                    )
                )
                or 0
            )
            return application, token, count

    application, token, access_count = asyncio.run(application_authority())
    rejected = db_client.patch(
        f"/api/v1/admin/drivers/{application.driver_profile_id}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"onboarding_status": "rejected"},
    )
    assert rejected.status_code == http_status.HTTP_200_OK

    duplicate = db_client.post(
        "/api/v1/auth/register-driver",
        json={"email": application.email, "full_name": "Generic Duplicate"},
    )
    invalid_mutation = db_client.post(
        f"/api/v1/auth/driver-onboarding/files/{uuid4()}/status",
        json={"application_access_token": token},
    )
    queue = db_client.get(
        "/api/v1/admin/driver-applications",
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    terminal_public_status = db_client.get(
        f"/api/v1/auth/driver-application-status/{registration.json()['application_reference']}"
    )
    unknown_public_status = db_client.get(
        "/api/v1/auth/driver-application-status/not-a-real-reference"
    )

    async def terminal_evidence() -> tuple[str, int, int]:
        async with db_sessionmaker() as session:
            refreshed = await session.get(DriverApplication, application.id)
            assert refreshed is not None
            accesses = int(
                await session.scalar(
                    select(func.count(DriverApplicationAccessToken.id)).where(
                        DriverApplicationAccessToken.application_id == application.id
                    )
                )
                or 0
            )
            audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.driver_application.rejected",
                        AuditEvent.entity_id == str(application.id),
                    )
                )
                or 0
            )
            return refreshed.status, accesses, audits

    application_status, final_access_count, terminal_audits = asyncio.run(terminal_evidence())
    assert application_status == "rejected"
    assert duplicate.status_code == http_status.HTTP_202_ACCEPTED
    assert duplicate.json().keys() == registration.json().keys()
    assert final_access_count == access_count
    assert invalid_mutation.status_code == http_status.HTTP_404_NOT_FOUND
    assert invalid_mutation.json()["error"]["code"] == "ONBOARDING_ACCESS_INVALID"
    assert queue.json()["total"] == 0
    assert terminal_public_status.status_code == unknown_public_status.status_code == 200
    assert terminal_public_status.json() == unknown_public_status.json()
    assert terminal_public_status.json()["status"] == "pending"
    assert terminal_audits == 1
