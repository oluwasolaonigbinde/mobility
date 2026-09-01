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
from fastapi.routing import APIRoute
from starlette import status as http_status

from app.api.v1.dependencies import get_current_user, oauth2_scheme
from app.models.user import UserRole, UserStatus
from app.services.users import get_user_by_email

PASSWORD = "long-secure-password"
NEW_PASSWORD = "different-secure-password"
REQUIRED_ACCESS_TOKEN_CLAIMS = ("sub", "exp", "iat", "auth_time", "sv")


def access_token_claims(user, *, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(UTC)
    issued_at = int(now.timestamp()) - 1
    return {
        "sub": str(user.id),
        "exp": issued_at + 1800,
        "iat": issued_at,
        "auth_time": issued_at,
        "sv": user.session_version,
    }


def signed_access_token(settings, claims: dict[str, object]) -> str:
    return jwt.encode(
        claims,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def assert_invalid_token(response, *, request_id: str) -> None:
    assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == {
        "code": "INVALID_TOKEN",
        "message": "Invalid authentication token",
        "details": {},
        "request_id": request_id,
    }


def dependency_calls(dependant) -> set[object]:
    calls = {dependant.call}
    for dependency in dependant.dependencies:
        calls.update(dependency_calls(dependency))
    return calls


def included_api_routes(routes, prefix: str = ""):
    for route in routes:
        if isinstance(route, APIRoute):
            yield f"{prefix}{route.path}", route
            continue
        original_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        if original_router is not None and include_context is not None:
            yield from included_api_routes(
                original_router.routes,
                f"{prefix}{include_context.prefix}",
            )


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


@pytest.mark.parametrize("claim", REQUIRED_ACCESS_TOKEN_CLAIMS)
@pytest.mark.parametrize("case", ["missing", "null"])
def test_protected_route_rejects_missing_or_null_required_claim(
    db_client,
    db_sessionmaker,
    settings,
    claim: str,
    case: str,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email=f"{case}-{claim.replace('_', '-')}@example.com",
        password=PASSWORD,
    )
    claims = access_token_claims(user)
    if case == "missing":
        claims.pop(claim)
    else:
        claims[claim] = None
    request_id = f"invalid-{case}-{claim}"

    response = db_client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {signed_access_token(settings, claims)}",
            "X-Request-ID": request_id,
        },
    )

    assert_invalid_token(response, request_id=request_id)


@pytest.mark.parametrize("claim", ["exp", "iat", "auth_time", "sv"])
@pytest.mark.parametrize(
    ("case", "invalid_value"),
    [("boolean", True), ("stringified-number", "1"), ("float", 1.0)],
)
def test_protected_route_rejects_coercible_numeric_claims(
    db_client,
    db_sessionmaker,
    settings,
    claim: str,
    case: str,
    invalid_value: object,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email=f"{case}-{claim.replace('_', '-')}@example.com",
        password=PASSWORD,
    )
    claims = access_token_claims(user)
    claims[claim] = invalid_value
    request_id = f"invalid-{case}-{claim}"

    response = db_client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {signed_access_token(settings, claims)}",
            "X-Request-ID": request_id,
        },
    )

    assert_invalid_token(response, request_id=request_id)


@pytest.mark.parametrize(
    ("case", "invalid_subject"),
    [
        ("boolean", True),
        ("integer", 1),
        ("float", 1.0),
        ("stringified-number", "1"),
        ("malformed", "not-a-uuid"),
    ],
)
def test_protected_route_rejects_malformed_subject(
    db_client,
    db_sessionmaker,
    settings,
    case: str,
    invalid_subject: object,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email=f"subject-{case}@example.com",
        password=PASSWORD,
    )
    claims = access_token_claims(user)
    claims["sub"] = invalid_subject
    request_id = f"invalid-subject-{case}"

    response = db_client.get(
        "/api/v1/me",
        headers={
            "Authorization": f"Bearer {signed_access_token(settings, claims)}",
            "X-Request-ID": request_id,
        },
    )

    assert_invalid_token(response, request_id=request_id)


def test_protected_route_rejects_noncanonical_uuid_subject(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email="noncanonical-subject@example.com",
        password=PASSWORD,
    )
    base_claims = access_token_claims(user)

    for case, subject in {
        "hex": user.id.hex,
        "braced": f"{{{user.id}}}",
    }.items():
        claims = {**base_claims, "sub": subject}
        request_id = f"invalid-subject-{case}"
        response = db_client.get(
            "/api/v1/me",
            headers={
                "Authorization": f"Bearer {signed_access_token(settings, claims)}",
                "X-Request-ID": request_id,
            },
        )
        assert_invalid_token(response, request_id=request_id)


def test_protected_route_rejects_invalid_claim_boundaries_and_order(
    db_client,
    db_sessionmaker,
    settings,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email="claim-boundaries@example.com",
        password=PASSWORD,
    )
    now = datetime.now(UTC)
    now_epoch = int(now.timestamp())
    base_claims = access_token_claims(user, now=now)
    invalid_claims = {
        "expired": {**base_claims, "exp": now_epoch - 1},
        "expiry-boundary": {**base_claims, "exp": now_epoch},
        "future-issued": {**base_claims, "iat": now_epoch + 300},
        "auth-after-issue": {**base_claims, "auth_time": base_claims["iat"] + 1},
        "expiry-at-issue": {**base_claims, "exp": base_claims["iat"]},
        "out-of-range-auth-time": {**base_claims, "auth_time": -(10**100)},
        "out-of-range-expiry": {**base_claims, "exp": 10**100},
        "zero-session-version": {**base_claims, "sv": 0},
        "negative-session-version": {**base_claims, "sv": -1},
    }

    for case, claims in invalid_claims.items():
        request_id = f"invalid-{case}"
        response = db_client.get(
            "/api/v1/me",
            headers={
                "Authorization": f"Bearer {signed_access_token(settings, claims)}",
                "X-Request-ID": request_id,
            },
        )
        assert_invalid_token(response, request_id=request_id)


def test_every_bearer_route_uses_the_central_current_user_dependency(client) -> None:
    bearer_routes: list[str] = []

    for path, route in included_api_routes(client.app.routes):
        calls = dependency_calls(route.dependant)
        if oauth2_scheme not in calls:
            continue
        bearer_routes.append(f"{','.join(sorted(route.methods))} {path}")
        assert get_current_user in calls

    assert bearer_routes


def test_refresh_second_decode_expiry_returns_invalid_token_envelope(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    user = create_test_user(
        db_sessionmaker,
        email="refresh-expiry-boundary@example.com",
        password=PASSWORD,
    )
    login = db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    from app.api.v1 import auth as auth_api

    def expire_on_second_decode(*_args, **_kwargs):
        raise ValueError("Invalid token")

    monkeypatch.setattr(auth_api, "decode_token_claims", expire_on_second_decode)
    request_id = "refresh-second-decode-expired"

    response = db_client.post(
        "/api/v1/auth/refresh",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Request-ID": request_id,
        },
    )

    assert_invalid_token(response, request_id=request_id)


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
