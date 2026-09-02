import asyncio
from datetime import UTC, datetime

from conftest import auth_headers, create_test_user
from sqlalchemy import func, select
from starlette import status as http_status

from app.core.errors import AppError
from app.models.impression import TrafficDensityProfile
from app.models.user import UserRole
from app.schemas.impressions import TrafficDensityProfileCreate, TrafficDensityProfileUpdate
from app.services.impressions import (
    create_traffic_density_profile,
    update_traffic_density_profile,
)

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


def test_profile_update_creates_an_immutable_effective_revision(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = admin_headers(db_client)
    original = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=headers,
        json=profile_payload(),
    ).json()

    replacement = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{original['id']}",
        headers=headers,
        json={
            "traffic_density_per_km": "240",
            "expected_revision": original["revision"],
            "expected_value_fingerprint": original["value_fingerprint"],
        },
    )

    assert replacement.status_code == http_status.HTTP_200_OK
    revised = replacement.json()
    assert revised["id"] != original["id"]
    assert revised["lineage_id"] == original["lineage_id"]
    assert revised["revision"] == 2
    assert revised["supersedes_id"] == original["id"]
    assert revised["effective_from"] > original["effective_from"]
    assert revised["value_fingerprint"] != original["value_fingerprint"]

    frozen = db_client.get(
        f"/api/v1/admin/traffic-density-profiles/{original['id']}", headers=headers
    ).json()
    assert frozen["traffic_density_per_km"] == "120.0000"
    assert frozen["value_fingerprint"] == original["value_fingerprint"]

    stale_retry = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{original['id']}",
        headers=headers,
        json={
            "traffic_density_per_km": "360",
            "expected_revision": original["revision"],
            "expected_value_fingerprint": original["value_fingerprint"],
        },
    )
    assert stale_retry.status_code == http_status.HTTP_409_CONFLICT
    assert stale_retry.json()["error"]["code"] == "TRAFFIC_DENSITY_PROFILE_STALE"


def test_profile_fingerprint_matches_database_numeric_scale(db_client, db_sessionmaker) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = admin_headers(db_client)
    original = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=headers,
        json=profile_payload(night_weight="0.70001"),
    ).json()

    assert original["night_weight"] == "0.7000"
    replacement = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{original['id']}",
        headers=headers,
        json={
            "description": "Revision after database numeric normalization",
            "expected_revision": original["revision"],
            "expected_value_fingerprint": original["value_fingerprint"],
        },
    )

    assert replacement.status_code == http_status.HTTP_200_OK, replacement.text
    assert replacement.json()["revision"] == 2


def test_profile_revision_rejects_non_monotonic_or_future_effective_time(
    db_client, db_sessionmaker
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    headers = admin_headers(db_client)
    original = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=headers,
        json=profile_payload(effective_from="2026-01-01T00:00:00Z"),
    ).json()

    for effective_from in (
        "2026-01-01T00:00:00Z",
        "2026-06-01T00:00:00Z",
        datetime(2099, 1, 1, tzinfo=UTC).isoformat(),
    ):
        response = db_client.patch(
            f"/api/v1/admin/traffic-density-profiles/{original['id']}",
            headers=headers,
            json={
                "traffic_density_per_km": "240",
                "effective_from": effective_from,
                "expected_revision": original["revision"],
                "expected_value_fingerprint": original["value_fingerprint"],
            },
        )
        assert response.status_code == http_status.HTTP_409_CONFLICT, response.text
        assert response.json()["error"]["code"] == (
            "TRAFFIC_DENSITY_PROFILE_EFFECTIVE_TIME_INVALID"
        )


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


def test_postgres_concurrent_profile_revision_cannot_branch(
    postgis_db_sessionmaker,
) -> None:
    async def exercise() -> None:
        async with postgis_db_sessionmaker() as session:
            profile = await create_traffic_density_profile(
                session,
                TrafficDensityProfileCreate.model_validate(profile_payload(is_default=False)),
            )
            profile_id = profile.id
            revision = profile.revision
            fingerprint = profile.value_fingerprint
            lineage_id = profile.lineage_id
            await session.commit()

        async def revise(density: str):
            async with postgis_db_sessionmaker() as session:
                try:
                    replacement = await update_traffic_density_profile(
                        session,
                        profile_id=profile_id,
                        payload=TrafficDensityProfileUpdate(
                            traffic_density_per_km=density,
                            expected_revision=revision,
                            expected_value_fingerprint=fingerprint,
                        ),
                    )
                    await session.commit()
                    return replacement.id
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        outcomes = await asyncio.gather(revise("200"), revise("300"))
        assert len([item for item in outcomes if item == "TRAFFIC_DENSITY_PROFILE_STALE"]) == 1

        async with postgis_db_sessionmaker() as session:
            successor_count = await session.scalar(
                select(func.count()).where(
                    TrafficDensityProfile.lineage_id == lineage_id,
                    TrafficDensityProfile.revision == 2,
                )
            )
            assert successor_count == 1

    asyncio.run(exercise())
