from conftest import (
    auth_headers,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
    fetch_audit_events,
)
from starlette import status as http_status

from app.models.user import UserRole
from app.models.vehicle import VehicleStatus

PASSWORD = "long-secure-password"


def create_driver_with_profile(db_sessionmaker, email: str):
    driver = create_test_user(
        db_sessionmaker,
        email=email,
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    return driver, profile


def test_admin_can_create_vehicle_with_normalized_plate_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver, profile = create_driver_with_profile(db_sessionmaker, "driver@example.com")

    response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "plate_number": " abc-123 ",
            "plate_country_code": "ng",
            "vehicle_type": "car",
            "make": " Toyota ",
            "model": " Corolla ",
            "year": 2018,
            "color": " White ",
            "status": "pending",
            "metadata": {"inspection": "pending"},
        },
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["driver_profile_id"] == str(profile.id)
    assert data["plate_number"] == "abc-123"
    assert data["plate_number_normalized"] == "ABC123"
    assert data["plate_country_code"] == "NG"
    assert data["make"] == "Toyota"
    assert data["model"] == "Corolla"
    assert data["color"] == "White"
    assert data["metadata"] == {"inspection": "pending"}
    assert data["driver_profile"]["email"] == "driver@example.com"
    assert "password_hash" not in response.text

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.vehicle.created"]


def test_admin_create_vehicle_rejects_non_driver_user(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.post(
        f"/api/v1/admin/drivers/{advertiser.id}/vehicles",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "plate_number": "ABC-123",
            "plate_country_code": "NG",
            "vehicle_type": "car",
            "status": "pending",
            "metadata": {},
        },
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "USER_IS_NOT_DRIVER"


def test_admin_create_vehicle_rejects_driver_without_profile(
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

    response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "plate_number": "ABC-123",
            "plate_country_code": "NG",
            "vehicle_type": "car",
            "status": "pending",
            "metadata": {},
        },
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"


def test_duplicate_normalized_plate_same_country_is_rejected_but_other_country_allowed(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver, profile = create_driver_with_profile(db_sessionmaker, "driver@example.com")
    create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="ABC-123",
        plate_country_code="NG",
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    duplicate_response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=headers,
        json={
            "plate_number": "ABC 123",
            "plate_country_code": "NG",
            "vehicle_type": "car",
            "status": "pending",
            "metadata": {},
        },
    )
    other_country_response = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=headers,
        json={
            "plate_number": "ABC 123",
            "plate_country_code": "GH",
            "vehicle_type": "car",
            "status": "pending",
            "metadata": {},
        },
    )

    assert duplicate_response.status_code == http_status.HTTP_409_CONFLICT
    assert duplicate_response.json()["error"]["code"] == "DUPLICATE_VEHICLE_PLATE"
    assert other_country_response.status_code == http_status.HTTP_201_CREATED


def test_vehicle_create_validation_rejects_invalid_type_status_and_year(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver, _ = create_driver_with_profile(db_sessionmaker, "driver@example.com")
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)
    base_payload = {
        "plate_number": "ABC-123",
        "plate_country_code": "NG",
        "vehicle_type": "car",
        "status": "pending",
        "metadata": {},
    }

    invalid_type = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=headers,
        json={**base_payload, "vehicle_type": "truck"},
    )
    invalid_status = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=headers,
        json={**base_payload, "status": "retired"},
    )
    invalid_year = db_client.post(
        f"/api/v1/admin/drivers/{driver.id}/vehicles",
        headers=headers,
        json={**base_payload, "year": 1979},
    )

    assert invalid_type.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_status.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_year.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_type.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_status.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_year.json()["error"]["code"] == "VALIDATION_ERROR"


def test_driver_can_list_and_retrieve_only_own_vehicles(db_client, db_sessionmaker) -> None:
    driver, profile = create_driver_with_profile(db_sessionmaker, "driver@example.com")
    other_driver, other_profile = create_driver_with_profile(db_sessionmaker, "other@example.com")
    own_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="OWN-123",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    other_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=other_profile.id,
        plate_number="OTH-123",
    )
    del driver, other_driver
    headers = auth_headers(db_client, "driver@example.com", PASSWORD)

    list_response = db_client.get("/api/v1/driver/vehicles", headers=headers)
    own_response = db_client.get(f"/api/v1/driver/vehicles/{own_vehicle.id}", headers=headers)
    other_response = db_client.get(f"/api/v1/driver/vehicles/{other_vehicle.id}", headers=headers)

    assert list_response.status_code == http_status.HTTP_200_OK
    data = list_response.json()
    assert set(data) == {"items", "total", "limit", "offset"}
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(own_vehicle.id)
    assert own_response.status_code == http_status.HTTP_200_OK
    assert own_response.json()["id"] == str(own_vehicle.id)
    assert other_response.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"


def test_driver_vehicle_list_requires_existing_profile(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.get(
        "/api/v1/driver/vehicles",
        headers=auth_headers(db_client, "driver@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"


def test_admin_can_list_get_and_update_vehicles(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, profile = create_driver_with_profile(db_sessionmaker, "driver@example.com")
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="ABC-123",
        vehicle_status=VehicleStatus.PENDING,
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    list_response = db_client.get("/api/v1/admin/vehicles?limit=1&offset=0", headers=headers)
    get_response = db_client.get(f"/api/v1/admin/vehicles/{vehicle.id}", headers=headers)
    update_response = db_client.patch(
        f"/api/v1/admin/vehicles/{vehicle.id}",
        headers=headers,
        json={
            "plate_number": " new 456 ",
            "plate_country_code": "ng",
            "vehicle_type": "van",
            "make": "Honda",
            "model": "Odyssey",
            "year": 2020,
            "color": "Blue",
            "status": "active",
            "metadata": {"inspection": "passed"},
        },
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    data = list_response.json()
    assert set(data) == {"items", "total", "limit", "offset"}
    assert data["total"] == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert "password_hash" not in list_response.text

    assert get_response.status_code == http_status.HTTP_200_OK
    assert get_response.json()["id"] == str(vehicle.id)
    assert "password_hash" not in get_response.text

    assert update_response.status_code == http_status.HTTP_200_OK
    updated = update_response.json()
    assert updated["plate_number"] == "new 456"
    assert updated["plate_number_normalized"] == "NEW456"
    assert updated["plate_country_code"] == "NG"
    assert updated["vehicle_type"] == "van"
    assert updated["status"] == "active"
    assert updated["metadata"] == {"inspection": "passed"}

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["admin.vehicle.updated"]


def test_vehicle_update_recomputes_plate_and_rejects_duplicates(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    _, profile = create_driver_with_profile(db_sessionmaker, "driver@example.com")
    first_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="ABC-123",
    )
    second_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="XYZ-789",
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    response = db_client.patch(
        f"/api/v1/admin/vehicles/{second_vehicle.id}",
        headers=headers,
        json={"plate_number": "ABC 123", "plate_country_code": "NG"},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "DUPLICATE_VEHICLE_PLATE"
    assert first_vehicle.id != second_vehicle.id


def test_advertiser_and_unauthenticated_users_are_rejected_from_vehicle_endpoints(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    advertiser_response = db_client.get(
        "/api/v1/driver/vehicles",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )
    unauthenticated_response = db_client.get("/api/v1/admin/vehicles")

    assert advertiser_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert unauthenticated_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert unauthenticated_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
