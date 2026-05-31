import pytest
from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
    fetch_user_by_email,
)
from starlette import status as http_status

from app.models.user import UserRole, UserStatus

PASSWORD = "long-secure-password"


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
