import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
    fetch_auth_audit_events,
    fetch_user_by_email,
)
from starlette import status as http_status

from app.models.user import UserRole, UserStatus
from app.services.users import get_user_by_email

PASSWORD = "long-secure-password"
NEW_PASSWORD = "different-secure-password"


def set_must_change_password(db_sessionmaker, email: str) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            user = await get_user_by_email(session, email)
            assert user is not None
            user.must_change_password = True
            await session.commit()

    asyncio.run(update())


def test_login_succeeds_with_correct_credentials(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="Admin@Example.com",
        password=PASSWORD,
        full_name="Admin User",
        role=UserRole.ADMIN,
    )

    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.com", "password": PASSWORD},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    assert data["user"] == {
        "id": data["user"]["id"],
        "email": "admin@example.com",
        "full_name": "Admin User",
        "role": "admin",
        "status": "active",
        "must_change_password": False,
    }
    assert "password_hash" not in response.text


def test_login_fails_with_bad_password(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)

    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )

    assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_and_wrong_password_paths_both_verify_argon2(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    create_test_user(db_sessionmaker, email="known@example.com", password=PASSWORD)
    from app.services import auth as auth_service

    calls: list[str] = []
    original = auth_service.verify_password

    def recording_verify(password: str, password_hash: str) -> bool:
        calls.append(password)
        return original(password, password_hash)

    monkeypatch.setattr(auth_service, "verify_password", recording_verify)
    missing = db_client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong"},
    )
    wrong = db_client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "wrong"},
    )
    assert missing.status_code == wrong.status_code == 401
    assert calls == ["wrong", "wrong"]


@pytest.mark.parametrize(
    "user_status",
    [UserStatus.DISABLED, UserStatus.SUSPENDED],
)
def test_login_fails_for_disabled_or_suspended_user(
    db_client,
    db_sessionmaker,
    user_status: UserStatus,
) -> None:
    create_test_user(
        db_sessionmaker,
        email=f"{user_status}@example.com",
        password=PASSWORD,
        user_status=user_status,
    )

    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": f"{user_status}@example.com", "password": PASSWORD},
    )

    assert response.status_code == http_status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "USER_NOT_ACTIVE"


def test_password_hash_is_not_plaintext(db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)

    stored_user = fetch_user_by_email(db_sessionmaker, "admin@example.com")

    assert stored_user is not None
    assert stored_user.password_hash != PASSWORD
    assert stored_user.password_hash.startswith("$argon2")


def test_me_requires_authentication(db_client) -> None:
    response = db_client.get("/api/v1/me", headers={"X-Request-ID": "req-auth"})

    assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "Authentication credentials were not provided",
        "details": {},
        "request_id": "req-auth",
    }


def test_forced_password_change_revokes_old_session_and_returns_working_token(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="forced@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    set_must_change_password(db_sessionmaker, "forced@example.com")

    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": "forced@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    old_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    blocked = db_client.get("/api/v1/admin/users", headers=old_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert db_client.get("/api/v1/me", headers=old_headers).status_code == 200

    changed = db_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=old_headers,
    )
    assert changed.status_code == 200
    assert changed.json()["user"]["must_change_password"] is False
    new_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert db_client.get("/api/v1/me", headers=new_headers).status_code == 200
    revoked = db_client.get("/api/v1/me", headers=old_headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "SESSION_REVOKED"

    relogin = db_client.post(
        "/api/v1/auth/login",
        json={"email": "forced@example.com", "password": NEW_PASSWORD},
    )
    assert relogin.status_code == 200


def test_change_password_rejects_wrong_current_short_and_reused_password(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="password@example.com", password=PASSWORD)
    headers = auth_headers(db_client, "password@example.com", PASSWORD)

    wrong = db_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "CURRENT_PASSWORD_INCORRECT"

    failed_changes = [
        event
        for event in fetch_auth_audit_events(db_sessionmaker)
        if event.action == "auth.password.change_failed"
    ]
    assert len(failed_changes) == 1
    assert failed_changes[0].event_metadata["reason"] == "current_password_incorrect"

    short = db_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=headers,
    )
    assert short.status_code == 400
    assert short.json()["error"]["code"] == "PASSWORD_TOO_SHORT"

    reused = db_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers=headers,
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "PASSWORD_REUSE"


def test_refresh_preserves_authentication_and_returns_a_new_token(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="refresh@example.com", password=PASSWORD)
    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    refreshed = db_client.post("/api/v1/auth/refresh", headers=headers)

    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    refreshed_headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    assert db_client.get("/api/v1/me", headers=refreshed_headers).status_code == 200
    assert [event.action for event in fetch_auth_audit_events(db_sessionmaker)].count(
        "auth.session.refreshed"
    ) == 1


def test_claimless_legacy_token_authenticates_but_cannot_refresh(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    user = create_test_user(db_sessionmaker, email="legacy-token@example.com", password=PASSWORD)
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(minutes=30)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert db_client.get("/api/v1/me", headers=headers).status_code == 200
    refresh = db_client.post("/api/v1/auth/refresh", headers=headers)
    assert refresh.status_code == 401
    assert refresh.json()["error"]["code"] == "REFRESH_NOT_ALLOWED"


def test_absolute_session_cap_is_enforced_and_refresh_expiry_is_clamped(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    user = create_test_user(db_sessionmaker, email="cap@example.com", password=PASSWORD)
    now = datetime.now(UTC)
    expired_auth_time = now - timedelta(minutes=settings.session_absolute_lifetime_minutes + 1)
    expired_token = jwt.encode(
        {
            "sub": str(user.id),
            "sv": user.session_version,
            "auth_time": int(expired_auth_time.timestamp()),
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired = db_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "SESSION_EXPIRED"

    near_cap_auth_time = now - timedelta(minutes=settings.session_absolute_lifetime_minutes - 1)
    near_cap_token = jwt.encode(
        {
            "sub": str(user.id),
            "sv": user.session_version,
            "auth_time": int(near_cap_auth_time.timestamp()),
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    refreshed = db_client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {near_cap_token}"},
    )
    assert refreshed.status_code == 200
    claims = jwt.decode(
        refreshed.json()["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert claims["exp"] <= int(
        (
            near_cap_auth_time + timedelta(minutes=settings.session_absolute_lifetime_minutes)
        ).timestamp()
    )


def test_me_returns_user_and_advertiser_organization_context(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        full_name="Advertiser User",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name="Acme Ads",
        owner_user_id=advertiser.id,
    )

    response = db_client.get(
        "/api/v1/me",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["user"]["email"] == "advertiser@example.com"
    assert data["user"]["role"] == "advertiser"
    assert data["user"]["status"] == "active"
    assert data["advertiser_organization"] == {
        "id": str(organization.id),
        "name": "Acme Ads",
        "currency": "NGN",
        "membership_role": "owner",
        "membership_status": "active",
    }
    assert "password_hash" not in response.text
