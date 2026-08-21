import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverOnboardingStatus
from app.models.trip import LocationPing, LocationPingBatch, TripSessionStatus
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services.campaign_zones import geometry_expression
from app.services.trips import point_value

PASSWORD = "long-secure-password"
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def create_analytics_graph(
    db_sessionmaker,
    *,
    trip_status: TripSessionStatus = TripSessionStatus.ENDED,
    started_at: datetime = BASE_TIME,
    ended_at: datetime | None = BASE_TIME + timedelta(minutes=30),
    admin_email: str = "admin@example.com",
    advertiser_email: str = "advertiser@example.com",
    driver_email: str = "driver@example.com",
    plate_number: str = "ANA-123",
):
    admin = create_test_user(db_sessionmaker, email=admin_email, password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email=advertiser_email,
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=driver_email,
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=plate_number,
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=started_at,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=trip_status,
        started_at=started_at,
        ended_at=ended_at,
    )
    return admin, advertiser, driver, campaign, profile, vehicle, assignment, trip


def polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict:
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            ]
        ],
    }


def add_zone(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    campaign_id,
    created_by_user_id,
    zone_type: str,
    geometry: dict,
    name: str,
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign_id,
                created_by_user_id=created_by_user_id,
                name=name,
                zone_type=zone_type,
                geom=geometry_expression(json.dumps(geometry, separators=(",", ":"))),
                zone_metadata={},
            )
            session.add(zone)
            await session.commit()

    asyncio.run(create())


def add_pings(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip_id,
    points: list[tuple[datetime, float, float, float]],
    idempotency_key: str = "analytics-batch",
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            received_at = datetime.now(UTC)
            batch = LocationPingBatch(
                trip_session_id=trip_id,
                idempotency_key=idempotency_key,
                payload_hash=f"hash-{idempotency_key}",
                pings_accepted=len(points),
                received_at=received_at,
                batch_metadata={},
            )
            session.add(batch)
            await session.flush()
            for sequence_number, (recorded_at, lat, lon, accuracy_m) in enumerate(points):
                session.add(
                    LocationPing(
                        trip_session_id=trip_id,
                        batch_id=batch.id,
                        recorded_at=recorded_at,
                        received_at=received_at,
                        sequence_number=sequence_number,
                        latitude=lat,
                        longitude=lon,
                        accuracy_m=accuracy_m,
                        speed_mps=None,
                        heading_degrees=None,
                        altitude_m=None,
                        geom=point_value(session, lon=lon, lat=lat),
                        ping_metadata={},
                    )
                )
            await session.commit()

    asyncio.run(create())


def fetch_analytics_rows(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> list[TripAnalytics]:
    async def fetch() -> list[TripAnalytics]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(TripAnalytics))
            return list(result.scalars().all())

    return asyncio.run(fetch())


def fetch_flags(db_sessionmaker: async_sessionmaker[AsyncSession]) -> list[FraudFlag]:
    async def fetch() -> list[FraudFlag]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(FraudFlag).order_by(FraudFlag.flag_type))
            return list(result.scalars().all())

    return asyncio.run(fetch())


def expected_distance_m(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
) -> float:
    async def fetch() -> float:
        async with db_sessionmaker() as session:
            result = await session.scalar(
                text(
                    """
                    SELECT ST_Distance(
                        ST_SetSRID(ST_MakePoint(:start_lon, :start_lat), 4326)::geography,
                        ST_SetSRID(ST_MakePoint(:end_lon, :end_lat), 4326)::geography
                    )
                    """
                ),
                {
                    "start_lon": start_lon,
                    "start_lat": start_lat,
                    "end_lon": end_lon,
                    "end_lat": end_lat,
                },
            )
            return float(result)

    return asyncio.run(fetch())


def admin_headers(client):
    return auth_headers(client, "admin@example.com", PASSWORD)


def driver_headers(client, email: str = "driver@example.com"):
    return auth_headers(client, email, PASSWORD)


def test_admin_recompute_calculates_postgis_distance_zone_overlap_and_is_idempotent(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin, _, _, campaign, profile, vehicle, assignment, trip = create_analytics_graph(
        postgis_db_sessionmaker
    )
    add_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        zone_type="target",
        geometry=polygon(3.38, 6.44, 3.43, 6.46),
        name="Target A",
    )
    add_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        zone_type="target",
        geometry=polygon(3.38, 6.44, 3.43, 6.46),
        name="Target B",
    )
    add_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        zone_type="bonus",
        geometry=polygon(3.41, 6.44, 3.45, 6.46),
        name="Bonus",
    )
    points = [
        (BASE_TIME, 6.45, 3.39, 10),
        (BASE_TIME + timedelta(minutes=5), 6.45, 3.40, 12),
        (BASE_TIME + timedelta(minutes=10), 6.45, 3.42, 14),
    ]
    add_pings(postgis_db_sessionmaker, trip_id=trip.id, points=points)

    response = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={"metadata": {"source": "test"}},
    )
    second = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    expected = expected_distance_m(
        postgis_db_sessionmaker,
        start_lon=3.39,
        start_lat=6.45,
        end_lon=3.40,
        end_lat=6.45,
    ) + expected_distance_m(
        postgis_db_sessionmaker,
        start_lon=3.40,
        start_lat=6.45,
        end_lon=3.42,
        end_lat=6.45,
    )
    assert float(data["distance_m"]) == pytest.approx(expected, abs=1.0)
    assert data["duration_seconds"] == 1800
    assert data["active_tracking_seconds"] == 600
    assert data["moving_seconds"] == 600
    assert data["stationary_seconds"] == 0
    assert data["ping_count"] == 3
    assert data["valid_ping_count"] == 3
    assert data["invalid_ping_count"] == 0
    assert data["avg_speed_mps"] is not None
    assert data["max_observed_speed_mps"] is not None
    assert data["avg_accuracy_m"] == "12.00"
    assert data["poor_accuracy_ping_count"] == 0
    assert data["metadata"]["formula_version"] == "route_analytics_v1"
    assert data["metadata"]["zone_approximation_method"] == (
        "whole_segment_attribution_on_postgis_intersection"
    )
    assert data["metadata"]["request_metadata"] == {"source": "test"}
    assert data["assignment_id"] == str(assignment.id)
    assert data["campaign_id"] == str(campaign.id)
    assert data["driver_profile_id"] == str(profile.id)
    assert data["vehicle_id"] == str(vehicle.id)
    assert float(data["target_zone_distance_m"]) == pytest.approx(float(data["distance_m"]), abs=1)
    assert float(data["target_zone_distance_m"]) < float(data["distance_m"]) * 1.1
    assert float(data["bonus_zone_distance_m"]) > 0
    assert Decimal(data["quality_score"]) >= Decimal("0")
    assert Decimal(data["quality_score"]) <= Decimal("1")
    assert second.status_code == http_status.HTTP_200_OK
    assert second.json()["id"] == data["id"]
    assert len(fetch_analytics_rows(postgis_db_sessionmaker)) == 1


def test_insufficient_data_creates_deterministic_low_metrics_and_flag(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, _, _, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        admin_email="admin@example.com",
        advertiser_email="adv-insufficient@example.com",
        driver_email="driver-insufficient@example.com",
        plate_number="INS-123",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[(BASE_TIME, 6.45, 3.39, 10)],
        idempotency_key="insufficient",
    )

    response = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "insufficient_data"
    assert data["distance_m"] == "0.00"
    assert data["moving_seconds"] == 0
    assert data["stationary_seconds"] == 0
    assert data["quality_score"] == "0.0000"
    assert [flag["flag_type"] for flag in data["fraud_flags"]] == ["insufficient_pings"]
    assert data["fraud_flags"][0]["severity"] == "medium"


def test_anomaly_flags_zone_exclusion_and_recompute_open_flag_idempotency(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin, _, _, campaign, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        advertiser_email="adv-flags@example.com",
        driver_email="driver-flags@example.com",
        plate_number="FLG-123",
    )
    add_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        zone_type="exclusion",
        geometry=polygon(3.0, 5.9, 4.1, 6.1),
        name="Exclusion",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.0, 3.0, 200),
            (BASE_TIME + timedelta(seconds=1000), 6.0, 3.0, 200),
            (BASE_TIME + timedelta(seconds=1010), 6.0, 4.0, 200),
            (BASE_TIME + timedelta(seconds=1020), 6.0, 3.0, 200),
        ],
        idempotency_key="flags",
    )

    first = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )
    second = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )

    assert first.status_code == http_status.HTTP_200_OK
    flag_types = {flag["flag_type"] for flag in first.json()["fraud_flags"]}
    assert {
        "impossible_speed",
        "poor_accuracy",
        "stationary_trip",
        "excessive_ping_gap",
        "route_looping",
        "exclusion_zone_presence",
    }.issubset(flag_types)
    impossible = next(
        flag for flag in first.json()["fraud_flags"] if flag["flag_type"] == "impossible_speed"
    )
    assert impossible["severity"] == "high"
    assert impossible["evidence"]["offending_segment_count"] >= 1
    assert second.status_code == http_status.HTTP_200_OK
    assert len(second.json()["fraud_flags"]) == len(first.json()["fraud_flags"])
    stored_flags = fetch_flags(postgis_db_sessionmaker)
    assert len(stored_flags) == len(first.json()["fraud_flags"])
    assert len({(flag.trip_session_id, flag.flag_type) for flag in stored_flags}) == len(
        stored_flags
    )


@pytest.mark.parametrize("review_status", ["acknowledged", "confirmed", "dismissed"])
def test_recompute_preserves_reviewed_flags_and_redetects_only_after_dismissal(
    postgis_db_client,
    postgis_db_sessionmaker,
    review_status: str,
) -> None:
    _, _, _, _, _, _, _, trip = create_analytics_graph(postgis_db_sessionmaker)
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.0, 3.0, 10),
            (BASE_TIME + timedelta(seconds=10), 6.0, 4.0, 10),
        ],
        idempotency_key=f"review-{review_status}",
    )
    first = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )
    assert first.status_code == http_status.HTTP_200_OK
    original = next(
        item for item in first.json()["fraud_flags"] if item["flag_type"] == "impossible_speed"
    )

    acknowledged = postgis_db_client.post(
        f"/api/v1/admin/fraud-flags/{original['id']}/review/acknowledge",
        headers=admin_headers(postgis_db_client),
    )
    assert acknowledged.status_code == http_status.HTTP_200_OK
    if review_status != "acknowledged":
        resolved = postgis_db_client.post(
            f"/api/v1/admin/fraud-flags/{original['id']}/review/resolve",
            headers=admin_headers(postgis_db_client),
            json={"outcome": review_status, "note": f"Review outcome: {review_status}."},
        )
        assert resolved.status_code == http_status.HTTP_200_OK

    second = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )
    assert second.status_code == http_status.HTTP_200_OK

    stored = [
        flag
        for flag in fetch_flags(postgis_db_sessionmaker)
        if flag.flag_type == "impossible_speed"
    ]
    if review_status == "dismissed":
        assert len(stored) == 2
        assert {flag.status for flag in stored} == {"dismissed", "open"}
        assert [
            item
            for item in second.json()["fraud_flags"]
            if item["flag_type"] == "impossible_speed"
        ][0]["status"] == "open"
    else:
        assert len(stored) == 1
        assert str(stored[0].id) == original["id"]
        assert stored[0].status == review_status


def test_future_timestamp_flag_uses_direct_corrupt_ping_insertion(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    future_ping_at = datetime.now(UTC) + timedelta(seconds=500)
    _, _, _, _, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        started_at=datetime.now(UTC),
        ended_at=future_ping_at + timedelta(minutes=1),
        advertiser_email="adv-future@example.com",
        driver_email="driver-future@example.com",
        plate_number="FUT-123",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (future_ping_at, 6.45, 3.39, 10),
            (future_ping_at + timedelta(seconds=10), 6.45, 3.3901, 10),
        ],
        idempotency_key="future",
    )

    response = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_200_OK
    flag_types = {flag["flag_type"] for flag in response.json()["fraud_flags"]}
    assert "future_timestamp" in flag_types


def test_admin_and_driver_analytics_endpoints_enforce_rbac_and_ownership(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker
    )
    advertiser_headers = auth_headers(postgis_db_client, advertiser.email, PASSWORD)
    other_driver = create_test_user(
        postgis_db_sessionmaker,
        email="other-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.45, 3.39, 10),
            (BASE_TIME + timedelta(minutes=5), 6.45, 3.40, 10),
        ],
    )
    missing = postgis_db_client.get(
        f"/api/v1/admin/trips/{trip.id}/analytics",
        headers=admin_headers(postgis_db_client),
    )
    recompute = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )
    read = postgis_db_client.get(
        f"/api/v1/admin/trips/{trip.id}/analytics",
        headers=admin_headers(postgis_db_client),
    )
    list_all = postgis_db_client.get(
        "/api/v1/admin/fraud-flags?limit=10&offset=0",
        headers=admin_headers(postgis_db_client),
    )
    list_by_campaign = postgis_db_client.get(
        f"/api/v1/admin/fraud-flags?campaign_id={campaign.id}",
        headers=admin_headers(postgis_db_client),
    )
    own_summary = postgis_db_client.get(
        f"/api/v1/driver/trips/{trip.id}/analytics-summary",
        headers=driver_headers(postgis_db_client),
    )
    other_summary = postgis_db_client.get(
        f"/api/v1/driver/trips/{trip.id}/analytics-summary",
        headers=driver_headers(postgis_db_client, "other-driver@example.com"),
    )
    admin_summary = postgis_db_client.get(
        f"/api/v1/driver/trips/{trip.id}/analytics-summary",
        headers=admin_headers(postgis_db_client),
    )
    advertiser_read = postgis_db_client.get(
        f"/api/v1/admin/trips/{trip.id}/analytics",
        headers=advertiser_headers,
    )
    advertiser_recompute = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=advertiser_headers,
        json={},
    )
    advertiser_list_flags = postgis_db_client.get(
        "/api/v1/admin/fraud-flags",
        headers=advertiser_headers,
    )
    advertiser_summary = postgis_db_client.get(
        f"/api/v1/driver/trips/{trip.id}/analytics-summary",
        headers=advertiser_headers,
    )
    unauthenticated_recompute = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        json={},
    )
    unauthenticated_read = postgis_db_client.get(f"/api/v1/admin/trips/{trip.id}/analytics")
    unauthenticated_list_flags = postgis_db_client.get("/api/v1/admin/fraud-flags")
    unauthenticated_summary = postgis_db_client.get(
        f"/api/v1/driver/trips/{trip.id}/analytics-summary"
    )

    assert missing.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing.json()["error"]["code"] == "ANALYTICS_NOT_FOUND"
    assert recompute.status_code == http_status.HTTP_200_OK
    assert read.status_code == http_status.HTTP_200_OK
    assert "password_hash" not in read.text
    assert list_all.status_code == http_status.HTTP_200_OK
    assert list_all.json()["limit"] == 10
    assert list_by_campaign.status_code == http_status.HTTP_200_OK
    assert own_summary.status_code == http_status.HTTP_200_OK
    assert own_summary.json()["trip_id"] == str(trip.id)
    assert own_summary.json()["flag_counts"] == {"low": 0, "medium": 0, "high": 0}
    assert other_summary.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_summary.json()["error"]["code"] == "TRIP_NOT_FOUND"
    assert admin_summary.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_read.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_recompute.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_list_flags.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_summary.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated_recompute.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert unauthenticated_read.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert unauthenticated_list_flags.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert unauthenticated_summary.status_code == http_status.HTTP_401_UNAUTHORIZED


def test_recompute_rejects_active_trip(postgis_db_client, postgis_db_sessionmaker) -> None:
    _, _, _, _, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        trip_status=TripSessionStatus.ACTIVE,
        ended_at=None,
        advertiser_email="adv-active@example.com",
        driver_email="driver-active@example.com",
        plate_number="ACT-123",
    )

    response = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "TRIP_NOT_ENDED"


def test_fraud_flag_filters_by_status_severity_and_type(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, _, _, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        advertiser_email="adv-filter@example.com",
        driver_email="driver-filter@example.com",
        plate_number="FIL-123",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.45, 3.39, 200),
            (BASE_TIME + timedelta(seconds=10), 6.45, 4.39, 200),
        ],
        idempotency_key="filter",
    )
    recompute = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )
    assert recompute.status_code == http_status.HTTP_200_OK

    status_response = postgis_db_client.get(
        "/api/v1/admin/fraud-flags?status=open",
        headers=admin_headers(postgis_db_client),
    )
    severity_response = postgis_db_client.get(
        "/api/v1/admin/fraud-flags?severity=high",
        headers=admin_headers(postgis_db_client),
    )
    type_response = postgis_db_client.get(
        "/api/v1/admin/fraud-flags?flag_type=impossible_speed",
        headers=admin_headers(postgis_db_client),
    )

    assert status_response.status_code == http_status.HTTP_200_OK
    assert status_response.json()["total"] >= 1
    assert severity_response.status_code == http_status.HTTP_200_OK
    assert {item["severity"] for item in severity_response.json()["items"]} == {"high"}
    assert type_response.status_code == http_status.HTTP_200_OK
    assert {item["flag_type"] for item in type_response.json()["items"]} == {"impossible_speed"}


def test_trip_outside_campaign_zones_has_zero_zone_metrics(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin, _, _, campaign, _, _, _, trip = create_analytics_graph(
        postgis_db_sessionmaker,
        advertiser_email="adv-outside@example.com",
        driver_email="driver-outside@example.com",
        plate_number="OUT-123",
    )
    add_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        zone_type="target",
        geometry=polygon(10, 10, 11, 11),
        name="Far Away",
    )
    add_pings(
        postgis_db_sessionmaker,
        trip_id=trip.id,
        points=[
            (BASE_TIME, 6.45, 3.39, 10),
            (BASE_TIME + timedelta(minutes=5), 6.45, 3.40, 10),
        ],
        idempotency_key="outside",
    )

    response = postgis_db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics",
        headers=admin_headers(postgis_db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["target_zone_distance_m"] == "0.00"
    assert data["bonus_zone_distance_m"] == "0.00"
    assert data["exclusion_zone_distance_m"] == "0.00"
    assert data["target_zone_seconds"] == 0
    assert data["bonus_zone_seconds"] == 0
    assert data["exclusion_zone_seconds"] == 0


def test_unique_nonterminal_flag_index_is_present_in_postgres(
    postgis_db_sessionmaker,
) -> None:
    async def fetch_index_count() -> int:
        async with postgis_db_sessionmaker() as session:
            return int(
                await session.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_indexes
                        WHERE schemaname = current_schema()
                          AND indexname = 'uq_fraud_flags_trip_nonterminal_flag_type'
                          AND indexdef ILIKE :predicate
                        """
                    ),
                    {"predicate": "%WHERE%open%acknowledged%confirmed%"},
                )
                or 0
            )

    assert asyncio.run(fetch_index_count()) == 1
