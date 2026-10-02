import asyncio

import pytest
from conftest import (
    auth_headers,
    create_test_user,
    fetch_audit_events,
    fetch_user_by_email,
)
from starlette import status as http_status

from app.api.v1.dependencies import get_login_rate_limiter
from app.core.rate_limit import RateLimitDecision
from app.models.disbursement import CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID
from app.models.user import User, UserRole, UserStatus

PASSWORD = "long-secure-password"


@pytest.mark.parametrize("proof", [None, "wrong-password", PASSWORD])
@pytest.mark.parametrize("target_status", ["active", "invited"])
def test_admin_creation_uses_current_password_proof(
    db_client, db_sessionmaker, proof, target_status
):
    actor = create_test_user(db_sessionmaker, email="creator@example.com", password=PASSWORD)
    headers = auth_headers(db_client, actor.email, PASSWORD)
    limiter = ElevationProofLimiter()
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    payload = {
        "email": "new-admin@example.com",
        "password": PASSWORD,
        "full_name": "New admin",
        "role": "admin",
        "status": target_status,
    }
    if proof is not None:
        payload["current_password"] = proof
    response = db_client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert response.status_code == (201 if proof == PASSWORD else 401)
    assert len(limiter.reserve_calls) == 1
    target = fetch_user_by_email(db_sessionmaker, payload["email"])
    assert (target is not None) == (proof == PASSWORD)
    events = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.user.created"
    ]
    assert len(events) == (1 if proof == PASSWORD else 0)
    assert "current_password" not in response.text


def test_invited_admin_cannot_login_or_use_preexisting_token(db_client, db_sessionmaker, settings):
    from app.core.security import create_access_token

    invited = create_test_user(
        db_sessionmaker,
        email="invited-admin@example.com",
        password=PASSWORD,
        user_status=UserStatus.INVITED,
    )
    login = db_client.post(
        "/api/v1/auth/login", json={"email": invited.email, "password": PASSWORD}
    )
    assert login.status_code == 403
    token, _ = create_access_token(invited.id, settings, session_version=invited.session_version)
    headers = {"Authorization": f"Bearer {token}"}
    for method, path, body in [
        ("GET", "/api/v1/admin/users", None),
        ("PATCH", f"/api/v1/admin/users/{invited.id}", {"status": "active"}),
    ]:
        response = db_client.request(method, path, headers=headers, json=body)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "USER_NOT_ACTIVE"
    assert fetch_user_by_email(db_sessionmaker, invited.email).status == UserStatus.INVITED


@pytest.mark.parametrize("proof", [None, "wrong-password", PASSWORD])
def test_preassigned_admin_activation_reauthenticates_and_revokes_once(
    db_client,
    db_sessionmaker,
    settings,
    proof,
):
    from app.core.security import create_access_token

    actor = create_test_user(
        db_sessionmaker, email="activation-admin@example.com", password=PASSWORD
    )
    target = create_test_user(
        db_sessionmaker,
        email="activation-target@example.com",
        password=PASSWORD,
        user_status=UserStatus.INVITED,
    )
    old_token, _ = create_access_token(target.id, settings, session_version=target.session_version)
    headers = auth_headers(db_client, actor.email, PASSWORD)
    limiter = ElevationProofLimiter()
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    payload = {"status": "active"}
    if proof is not None:
        payload["current_password"] = proof
    response = db_client.patch(f"/api/v1/admin/users/{target.id}", headers=headers, json=payload)
    assert response.status_code == (200 if proof == PASSWORD else 401)
    assert len(limiter.reserve_calls) == 1
    refreshed = fetch_user_by_email(db_sessionmaker, target.email)
    assert refreshed.session_version == target.session_version + (proof == PASSWORD)
    if proof == PASSWORD:
        rejected = db_client.get("/api/v1/me", headers={"Authorization": f"Bearer {old_token}"})
        assert rejected.status_code == 401
        assert rejected.json()["error"]["code"] == "SESSION_REVOKED"
        retry = db_client.patch(
            f"/api/v1/admin/users/{target.id}", headers=headers, json={"status": "active"}
        )
        assert retry.status_code == 200
        assert (
            fetch_user_by_email(db_sessionmaker, target.email).session_version
            == refreshed.session_version
        )
        assert len(limiter.reserve_calls) == 1


class ElevationProofLimiter:
    def __init__(self, *, allowed_attempts: int = 1, storage_available: bool = True) -> None:
        self.allowed_attempts = allowed_attempts
        self.storage_available = storage_available
        self.reserve_calls: list[tuple[str, str]] = []
        self.reservations: list[tuple[str, str]] = []
        self.releases: list[tuple[str, str]] = []

    async def reserve(self, ip: str, email: str) -> RateLimitDecision:
        self.reserve_calls.append((ip, email))
        if not self.storage_available:
            return RateLimitDecision(
                allowed=False,
                bucket="storage",
                retry_after_seconds=60,
                storage_available=False,
            )
        if len(self.reservations) >= self.allowed_attempts:
            return RateLimitDecision(
                allowed=False,
                bucket="account",
                retry_after_seconds=60,
            )
        self.reservations.append((ip, email))
        return RateLimitDecision(allowed=True)

    async def release_success(self, ip: str, email: str) -> None:
        self.releases.append((ip, email))
        if self.reservations:
            self.reservations.pop()

    async def record_failure(self, ip: str, email: str) -> None:
        del ip, email


def test_admin_endpoint_rejects_unauthenticated_users(db_client) -> None:
    response = db_client.get("/api/v1/admin/users")

    assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_admin_endpoint_rejects_non_admin_users(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.get(
        "/api/v1/admin/users",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_admin_can_create_user_with_normalized_email_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    response = db_client.post(
        "/api/v1/admin/users",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "email": "Advertiser@Example.com",
            "password": PASSWORD,
            "full_name": "Advertiser User",
            "phone": None,
            "role": "advertiser",
            "status": "active",
        },
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == "advertiser@example.com"
    assert data["role"] == "advertiser"
    assert data["must_change_password"] is True
    assert "password_hash" not in response.text

    stored_user = fetch_user_by_email(db_sessionmaker, "advertiser@example.com")
    assert stored_user is not None
    assert stored_user.password_hash != PASSWORD

    login_response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "ADVERTISER@example.com", "password": PASSWORD},
    )
    assert login_response.status_code == http_status.HTTP_200_OK
    assert login_response.json()["user"]["must_change_password"] is True

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.user.created"]


def test_duplicate_normalized_email_is_rejected(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    first_response = db_client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "Advertiser@Example.com",
            "password": PASSWORD,
            "full_name": "Advertiser User",
            "phone": None,
            "role": "advertiser",
            "status": "active",
        },
    )
    second_response = db_client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "advertiser@example.com",
            "password": PASSWORD,
            "full_name": "Duplicate User",
            "phone": None,
            "role": "advertiser",
            "status": "active",
        },
    )

    assert first_response.status_code == http_status.HTTP_201_CREATED
    assert second_response.status_code == http_status.HTTP_409_CONFLICT
    assert second_response.json()["error"]["code"] == "DUPLICATE_EMAIL"


def test_admin_can_list_users_with_pagination_shape(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.get(
        "/api/v1/admin/users?limit=1&offset=0",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert set(data) == {"items", "total", "limit", "offset"}
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert "password_hash" not in response.text


def test_list_users_excludes_automatic_actor_before_search_count_and_paging(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(
        db_sessionmaker,
        email="human-admin@example.com",
        password=PASSWORD,
        full_name="Terrax admin",
    )
    other = create_test_user(
        db_sessionmaker,
        email="human-staff@example.com",
        password=PASSWORD,
        full_name="Terrax staff",
    )

    async def add_actor() -> None:
        async with db_sessionmaker() as session:
            session.add(
                User(
                    id=CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID,
                    email="automatic-payouts@cardvert.invalid",
                    full_name="Terrax automatic payouts",
                    password_hash="disabled-system-account",
                    role=UserRole.ADMIN,
                    status=UserStatus.DISABLED,
                )
            )
            await session.commit()

    asyncio.run(add_actor())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    pages = [
        db_client.get(
            f"/api/v1/admin/users?role=admin&q=Terrax&limit=1&offset={offset}", headers=headers
        )
        for offset in (0, 1)
    ]
    assert all(page.status_code == 200 for page in pages)
    assert all(page.json()["total"] == 2 for page in pages)
    assert {page.json()["items"][0]["id"] for page in pages} == {str(admin.id), str(other.id)}
    actor_search = db_client.get("/api/v1/admin/users?q=automatic-payouts", headers=headers)
    assert actor_search.status_code == 200
    assert actor_search.json()["items"] == []
    assert actor_search.json()["total"] == 0
    unfiltered = db_client.get("/api/v1/admin/users", headers=headers)
    assert unfiltered.json()["total"] == 2
    assert str(CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID) not in unfiltered.text


def test_admin_can_update_allowed_user_fields(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        full_name="Driver User",
        role=UserRole.DRIVER,
    )

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={"full_name": "Updated Driver", "phone": "+2348000000000", "status": "suspended"},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["full_name"] == "Updated Driver"
    assert data["phone"] == "+2348000000000"
    assert data["status"] == "suspended"
    assert "password_hash" not in response.text

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.user.updated"]


def test_admin_update_rejects_password_hash_field(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(db_sessionmaker, email="driver@example.com", password=PASSWORD)

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={"password_hash": "plaintext"},
    )

    assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "elevation_payload",
    [
        pytest.param({"role": "admin"}, id="missing-password"),
        pytest.param(
            {"role": "admin", "current_password": "wrong-password"},
            id="wrong-password",
        ),
    ],
)
def test_admin_elevation_requires_current_password_before_mutating_target(
    db_client, db_sessionmaker, elevation_payload
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json=elevation_payload,
    )

    assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    stored_user = fetch_user_by_email(db_sessionmaker, "driver@example.com")
    assert stored_user is not None
    assert stored_user.role == UserRole.DRIVER
    assert fetch_audit_events(db_sessionmaker) == []


def test_admin_elevation_fails_closed_when_authentication_limiter_is_unavailable(
    db_client, db_sessionmaker
) -> None:
    limiter = ElevationProofLimiter(storage_available=False)
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=headers,
        json={"role": "admin", "current_password": PASSWORD},
    )

    assert response.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"]["code"] == "RATE_LIMIT_UNAVAILABLE"
    stored_user = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert stored_user is not None
    assert stored_user.role == UserRole.DRIVER
    assert [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.user.updated"
    ] == []


def test_successful_elevation_refunds_its_reservation_and_non_elevation_skips_it(
    db_client, db_sessionmaker
) -> None:
    limiter = ElevationProofLimiter()
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    elevation_target = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    ordinary_target = create_test_user(
        db_sessionmaker,
        email="other-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    elevated = db_client.patch(
        f"/api/v1/admin/users/{elevation_target.id}",
        headers=headers,
        json={"role": "admin", "current_password": PASSWORD},
    )
    replay = db_client.patch(
        f"/api/v1/admin/users/{elevation_target.id}",
        headers=headers,
        json={"role": "admin"},
    )
    ordinary = db_client.patch(
        f"/api/v1/admin/users/{ordinary_target.id}",
        headers=headers,
        json={"role": "advertiser"},
    )

    assert elevated.status_code == http_status.HTTP_200_OK
    assert replay.status_code == http_status.HTTP_200_OK
    assert ordinary.status_code == http_status.HTTP_200_OK
    assert len(limiter.reserve_calls) == 1
    assert len(limiter.releases) == 1
    assert limiter.reservations == []


def test_admin_elevation_password_guesses_share_authentication_rate_limits(
    db_client, db_sessionmaker
) -> None:
    limiter = ElevationProofLimiter()
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)
    db_client.app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    wrong = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=headers,
        json={"role": "admin", "current_password": "wrong-password"},
    )
    blocked = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=headers,
        json={"role": "admin", "current_password": "another-wrong-password"},
    )

    assert wrong.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert blocked.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert limiter.releases == []
    stored_user = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert stored_user is not None
    assert stored_user.role == UserRole.DRIVER


def test_admin_elevation_rotates_target_authority_once_and_audits_actor_and_target(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    target_login = db_client.post(
        "/api/v1/auth/login",
        json={"email": target_user.email, "password": PASSWORD},
    )
    assert target_login.status_code == http_status.HTTP_200_OK
    target_token = target_login.json()["access_token"]
    starting_version = target_user.session_version

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"role": "admin", "current_password": PASSWORD},
    )

    assert response.status_code == http_status.HTTP_200_OK
    stored_user = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert stored_user is not None
    assert stored_user.role == UserRole.ADMIN
    assert stored_user.session_version == starting_version + 1

    old_headers = {"Authorization": f"Bearer {target_token}"}
    revoked = db_client.get("/api/v1/me", headers=old_headers)
    assert revoked.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert revoked.json()["error"]["code"] == "SESSION_REVOKED"
    refresh = db_client.post("/api/v1/auth/refresh", headers=old_headers)
    assert refresh.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert refresh.json()["error"]["code"] == "SESSION_REVOKED"

    audit_events = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.user.updated"
    ]
    assert len(audit_events) == 1
    updated = audit_events[0]
    assert updated.action == "admin.user.updated"
    assert updated.actor_user_id == admin.id
    assert updated.entity_id == str(target_user.id)
    assert updated.event_metadata == {
        "changed_fields": ["role"],
        "sessions_revoked": True,
    }

    replay = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"role": "admin"},
    )
    assert replay.status_code == http_status.HTTP_200_OK
    replayed_user = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert replayed_user is not None
    assert replayed_user.session_version == starting_version + 1
    elevation_audits = [
        event
        for event in fetch_audit_events(db_sessionmaker)
        if event.action == "admin.user.updated"
        and event.event_metadata.get("sessions_revoked") is True
    ]
    assert len(elevation_audits) == 1


def test_role_noop_and_non_admin_role_changes_do_not_require_password_or_rotate(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    another_admin = create_test_user(
        db_sessionmaker,
        email="other-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)

    noop = db_client.patch(
        f"/api/v1/admin/users/{another_admin.id}",
        headers=headers,
        json={"role": "admin"},
    )
    changed = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=headers,
        json={"role": "advertiser"},
    )

    assert noop.status_code == http_status.HTTP_200_OK
    assert changed.status_code == http_status.HTTP_200_OK
    stored_admin = fetch_user_by_email(db_sessionmaker, another_admin.email)
    stored_target = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert stored_admin is not None and stored_target is not None
    assert stored_admin.session_version == another_admin.session_version
    assert stored_target.role == UserRole.ADVERTISER
    assert stored_target.session_version == target_user.session_version


def test_combined_status_and_admin_elevation_rotates_only_once(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    target_user = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.patch(
        f"/api/v1/admin/users/{target_user.id}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "role": "admin",
            "status": "suspended",
            "current_password": PASSWORD,
        },
    )

    assert response.status_code == http_status.HTTP_200_OK
    stored_user = fetch_user_by_email(db_sessionmaker, target_user.email)
    assert stored_user is not None
    assert stored_user.role == UserRole.ADMIN
    assert stored_user.status == "suspended"
    assert stored_user.session_version == target_user.session_version + 1


def _public_applicant(db_client, db_sessionmaker, settings, email: str):
    from app.api.v1.dependencies import get_registration_rate_limiter
    from app.core.config import get_settings
    from app.core.rate_limit import InMemoryRegistrationRateLimiter

    enabled = settings.model_copy(update={"driver_registration_enabled": True})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    db_client.app.dependency_overrides[get_registration_rate_limiter] = lambda: (
        InMemoryRegistrationRateLimiter()
    )
    response = db_client.post(
        "/api/v1/auth/register-driver", json={"email": email, "full_name": "Public Applicant"}
    )
    assert response.status_code == http_status.HTTP_202_ACCEPTED
    applicant = fetch_user_by_email(db_sessionmaker, email)
    assert applicant is not None and applicant.status == UserStatus.INVITED
    return applicant


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param([{"status": "active"}], id="direct"),
        pytest.param([{"role": "advertiser"}, {"status": "active"}], id="role-flip"),
        pytest.param([{"status": "suspended"}, {"status": "active"}], id="suspend-first"),
        pytest.param([{"role": "advertiser", "status": "active"}], id="combined"),
    ],
)
def test_public_applicant_cannot_be_activated_outside_account_setup(
    db_client, db_sessionmaker, settings, steps
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    applicant = _public_applicant(db_client, db_sessionmaker, settings, "applicant@example.com")
    headers = auth_headers(db_client, admin.email, PASSWORD)

    responses = [
        db_client.patch(f"/api/v1/admin/users/{applicant.id}", headers=headers, json=step)
        for step in steps
    ]

    refused = responses[-1]
    assert refused.status_code == http_status.HTTP_409_CONFLICT
    assert refused.json()["error"]["code"] == "DRIVER_ACTIVATION_REQUIRES_SETUP"
    assert fetch_user_by_email(db_sessionmaker, applicant.email).status != UserStatus.ACTIVE


@pytest.mark.parametrize("role", ["advertiser", "admin"])
def test_public_applicant_role_cannot_change_before_setup(
    db_client, db_sessionmaker, settings, role
) -> None:
    # Another role would make the invited applicant eligible for password recovery.
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    applicant = _public_applicant(db_client, db_sessionmaker, settings, "flip@example.com")

    response = db_client.patch(
        f"/api/v1/admin/users/{applicant.id}",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"role": role, "current_password": PASSWORD},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    # Elevation to admin is already refused for any inactive user.
    expected = "USER_NOT_ACTIVE" if role == "admin" else "DRIVER_ACTIVATION_REQUIRES_SETUP"
    assert response.json()["error"]["code"] == expected
    stored = fetch_user_by_email(db_sessionmaker, applicant.email)
    assert stored.role == UserRole.DRIVER and stored.status == UserStatus.INVITED


def test_applicant_who_completed_setup_can_be_reactivated_after_suspension(
    db_client, db_sessionmaker, settings
) -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from sqlalchemy import select, update

    from app.models.driver_application import DriverAccountSetupToken, DriverApplication
    from app.models.user import User

    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    applicant = _public_applicant(db_client, db_sessionmaker, settings, "set-up@example.com")

    async def record_completed_setup() -> None:
        # Stands in for complete_driver_account_setup, which is covered by its own suite.
        now = datetime.now(UTC)
        async with db_sessionmaker() as session:
            application_id = await session.scalar(
                select(DriverApplication.id).where(DriverApplication.user_id == applicant.id)
            )
            session.add(
                DriverAccountSetupToken(
                    application_id=application_id,
                    user_id=applicant.id,
                    issued_by_user_id=admin.id,
                    client_request_id=uuid4(),
                    request_fingerprint="a" * 64,
                    token_sha256="b" * 64,
                    evidence_sha256="c" * 64,
                    session_version=1,
                    created_at=now - timedelta(minutes=5),
                    expires_at=now + timedelta(hours=1),
                    used_at=now,
                )
            )
            await session.execute(
                update(User).where(User.id == applicant.id).values(status=UserStatus.ACTIVE)
            )
            await session.commit()

    asyncio.run(record_completed_setup())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    for target in ("suspended", "active"):
        response = db_client.patch(
            f"/api/v1/admin/users/{applicant.id}", headers=headers, json={"status": target}
        )
        assert response.status_code == http_status.HTTP_200_OK
    assert fetch_user_by_email(db_sessionmaker, applicant.email).status == UserStatus.ACTIVE


def test_operator_created_driver_can_still_be_suspended_and_reactivated(
    db_client, db_sessionmaker
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker, email="driver@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)

    for target in ("suspended", "active"):
        response = db_client.patch(
            f"/api/v1/admin/users/{driver.id}", headers=headers, json={"status": target}
        )
        assert response.status_code == http_status.HTTP_200_OK
    assert fetch_user_by_email(db_sessionmaker, driver.email).status == UserStatus.ACTIVE
