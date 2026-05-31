from conftest import auth_headers, create_test_user
from starlette import status as http_status

from app.models.user import UserRole

PASSWORD = "long-secure-password"


def profile_payload(**overrides):
    payload = {
        "name": " Default Urban Profile ",
        "description": " Default v1 profile ",
        "profile_type": "default",
        "traffic_density_per_km": "120",
        "dwell_impressions_per_minute": "3",
        "road_category_weight": "1.0",
        "morning_weight": "1.1",
        "midday_weight": "1.0",
        "evening_weight": "1.2",
        "night_weight": "0.7",
        "target_zone_weight": "1.0",
        "bonus_zone_weight": "1.25",
        "exclusion_zone_weight": "1.0",
        "is_default": True,
        "status": "active",
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def admin_headers(client):
    return auth_headers(client, "admin@example.com", PASSWORD)


def test_admin_can_create_list_read_and_update_profiles(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)

    create_response = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=admin_headers(db_client),
        json=profile_payload(),
    )
    assert create_response.status_code == http_status.HTTP_200_OK
    created = create_response.json()
    assert created["name"] == "Default Urban Profile"
    assert created["description"] == "Default v1 profile"
    assert created["traffic_density_per_km"] == "120.0000"
    assert created["bonus_zone_weight"] == "1.2500"
    assert created["metadata"] == {"source": "test"}

    list_response = db_client.get(
        "/api/v1/admin/traffic-density-profiles?limit=10&offset=0&status=active",
        headers=admin_headers(db_client),
    )
    read_response = db_client.get(
        f"/api/v1/admin/traffic-density-profiles/{created['id']}",
        headers=admin_headers(db_client),
    )
    update_response = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{created['id']}",
        headers=admin_headers(db_client),
        json={
            "name": "Updated Profile",
            "profile_type": "urban",
            "traffic_density_per_km": "140",
            "metadata": {"updated": True},
        },
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["limit"] == 10
    assert read_response.status_code == http_status.HTTP_200_OK
    assert read_response.json()["id"] == created["id"]
    assert update_response.status_code == http_status.HTTP_200_OK
    assert update_response.json()["name"] == "Updated Profile"
    assert update_response.json()["profile_type"] == "urban"
    assert update_response.json()["traffic_density_per_km"] == "140.0000"
    assert update_response.json()["metadata"] == {"updated": True}


def test_setting_active_default_clears_prior_default(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    first = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=admin_headers(db_client),
        json=profile_payload(name="First", is_default=True),
    ).json()
    second = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=admin_headers(db_client),
        json=profile_payload(name="Second", profile_type="urban", is_default=True),
    ).json()

    first_read = db_client.get(
        f"/api/v1/admin/traffic-density-profiles/{first['id']}",
        headers=admin_headers(db_client),
    )
    second_read = db_client.get(
        f"/api/v1/admin/traffic-density-profiles/{second['id']}",
        headers=admin_headers(db_client),
    )

    assert first_read.json()["is_default"] is False
    assert second_read.json()["is_default"] is True


def test_profile_validation_rejects_invalid_values(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = admin_headers(db_client)

    invalid_cases = [
        profile_payload(name=" "),
        profile_payload(profile_type="airport"),
        profile_payload(status="archived"),
        profile_payload(traffic_density_per_km="-1"),
        profile_payload(dwell_impressions_per_minute="-1"),
        profile_payload(morning_weight="-0.1"),
        profile_payload(metadata=[]),
    ]

    for payload in invalid_cases:
        response = db_client.post(
            "/api/v1/admin/traffic-density-profiles",
            headers=headers,
            json=payload,
        )
        assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_update_rejects_non_object_metadata(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = admin_headers(db_client)
    profile = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=headers,
        json=profile_payload(),
    ).json()

    for metadata in [None, []]:
        response = db_client.patch(
            f"/api/v1/admin/traffic-density-profiles/{profile['id']}",
            headers=headers,
            json={"metadata": metadata},
        )
        assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_profile_endpoints_enforce_admin_role(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    profile = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=admin_headers(db_client),
        json=profile_payload(),
    ).json()
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)

    for headers in [advertiser_headers, driver_headers]:
        assert (
            db_client.post(
                "/api/v1/admin/traffic-density-profiles",
                headers=headers,
                json=profile_payload(name="Denied"),
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
        assert (
            db_client.get("/api/v1/admin/traffic-density-profiles", headers=headers).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
        assert (
            db_client.get(
                f"/api/v1/admin/traffic-density-profiles/{profile['id']}",
                headers=headers,
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )
        assert (
            db_client.patch(
                f"/api/v1/admin/traffic-density-profiles/{profile['id']}",
                headers=headers,
                json={"name": "Denied"},
            ).status_code
            == http_status.HTTP_403_FORBIDDEN
        )

    for response in [
        db_client.get("/api/v1/admin/traffic-density-profiles"),
        db_client.get(f"/api/v1/admin/traffic-density-profiles/{profile['id']}"),
        db_client.patch(
            f"/api/v1/admin/traffic-density-profiles/{profile['id']}",
            json={"name": "Denied"},
        ),
    ]:
        assert response.status_code == http_status.HTTP_401_UNAUTHORIZED
