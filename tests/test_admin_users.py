from conftest import (
    auth_headers,
    create_test_user,
    fetch_audit_events,
    fetch_user_by_email,
)
from starlette import status as http_status

from app.models.user import UserRole

PASSWORD = "long-secure-password"


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
