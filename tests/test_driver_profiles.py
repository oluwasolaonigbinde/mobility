from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    fetch_audit_events,
)
from starlette import status as http_status

from app.models.driver import DriverOnboardingStatus
from app.models.user import UserRole

PASSWORD = "long-secure-password"


def test_admin_can_create_driver_profile_with_normalization_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        full_name="Driver User",
        phone="+2348000000000",
        role=UserRole.DRIVER,
    )

    response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/profile",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "onboarding_status": "pending",
            "license_number": " DRV-123 ",
            "service_city": " Lagos ",
            "country_code": "ng",
            "metadata": {"source": "manual"},
        },
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["user_id"] == str(driver.id)
    assert data["email"] == "driver@example.com"
    assert data["full_name"] == "Driver User"
    assert data["phone"] == "+2348000000000"
    assert data["license_number"] == "DRV-123"
    assert data["service_city"] == "Lagos"
    assert data["country_code"] == "NG"
    assert data["metadata"] == {"source": "manual"}
    assert "password_hash" not in response.text

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.driver_profile.created"]


def test_admin_create_driver_profile_rejects_non_driver_users(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.post(
        f"/api/v1/admin/drivers/{advertiser.id}/profile",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={"onboarding_status": "pending", "metadata": {}},
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "USER_IS_NOT_DRIVER"


def test_admin_create_driver_profile_rejects_admin_users(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)

    response = db_client.post(
        f"/api/v1/admin/drivers/{admin.id}/profile",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={"onboarding_status": "pending", "metadata": {}},
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "USER_IS_NOT_DRIVER"


def test_duplicate_driver_profile_is_rejected(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)

    response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/profile",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={"onboarding_status": "pending", "metadata": {}},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "DUPLICATE_DRIVER_PROFILE"


def test_admin_driver_profile_rejects_invalid_onboarding_status(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    create_response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/profile",
        headers=headers,
        json={"onboarding_status": "paused", "metadata": {}},
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    update_response = db_client.patch(
        f"/api/v1/admin/drivers/{profile.id}",
        headers=headers,
        json={"onboarding_status": "paused"},
    )

    assert create_response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert update_response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert create_response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert update_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_driver_can_retrieve_and_update_own_profile(db_client, db_sessionmaker) -> None:
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        full_name="Driver User",
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        metadata={"internal": "admin-only"},
    )
    headers = auth_headers(db_client, "driver@example.com", PASSWORD)

    get_response = db_client.get("/api/v1/driver/profile", headers=headers)
    patch_response = db_client.patch(
        "/api/v1/driver/profile",
        headers=headers,
        json={
            "license_number": " NEW-456 ",
            "service_city": " Abuja ",
            "country_code": "ng",
        },
    )

    assert get_response.status_code == http_status.HTTP_200_OK
    assert "metadata" not in get_response.json()
    assert get_response.json()["onboarding_status"] == "active"
    assert patch_response.status_code == http_status.HTTP_200_OK
    data = patch_response.json()
    assert data["license_number"] == "NEW-456"
    assert data["service_city"] == "Abuja"
    assert data["country_code"] == "NG"
    assert data["onboarding_status"] == "active"
    assert "password_hash" not in patch_response.text


def test_driver_profile_missing_returns_standard_error(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.get(
        "/api/v1/driver/profile",
        headers={
            **auth_headers(db_client, "driver@example.com", PASSWORD),
            "X-Request-ID": "req-driver-profile",
        },
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"] == {
        "code": "DRIVER_PROFILE_NOT_FOUND",
        "message": "Driver profile was not found for the current user",
        "details": {},
        "request_id": "req-driver-profile",
    }


def test_driver_cannot_update_onboarding_status(db_client, db_sessionmaker) -> None:
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)

    response = db_client.patch(
        "/api/v1/driver/profile",
        headers=auth_headers(db_client, "driver@example.com", PASSWORD),
        json={"onboarding_status": "active"},
    )

    assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_advertiser_is_rejected_from_driver_profile_endpoints(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.get(
        "/api/v1/driver/profile",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_supply_endpoints_reject_unauthenticated_users(db_client) -> None:
    driver_response = db_client.get("/api/v1/driver/profile")
    admin_response = db_client.get("/api/v1/admin/drivers")

    assert driver_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert admin_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert driver_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert admin_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_admin_can_list_and_update_driver_profiles(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    list_response = db_client.get("/api/v1/admin/drivers?limit=1&offset=0", headers=headers)
    get_response = db_client.get(f"/api/v1/admin/drivers/{profile.id}", headers=headers)
    update_response = db_client.patch(
        f"/api/v1/admin/drivers/{profile.id}",
        headers=headers,
        json={"onboarding_status": "active", "metadata": {"reviewed": True}},
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    data = list_response.json()
    assert set(data) == {"items", "total", "limit", "offset"}
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert "password_hash" not in list_response.text

    assert get_response.status_code == http_status.HTTP_200_OK
    assert get_response.json()["id"] == str(profile.id)
    assert "password_hash" not in get_response.text

    assert update_response.status_code == http_status.HTTP_200_OK
    assert update_response.json()["onboarding_status"] == "active"
    assert update_response.json()["metadata"] == {"reviewed": True}

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.driver_profile.updated"]
