import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_impression_estimate,
    create_test_organization,
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_earnings_ledger_entries,
    fetch_impression_estimates,
    fetch_location_pings,
    fetch_payout_calculations,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.core.config import Settings
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.payout import PayoutCalculation
from app.models.trip import LocationPing, LocationPingBatch, TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus, VehicleType
from app.services.trips import point_value

PASSWORD = "long-secure-password"
BBOX = "3.30,6.40,3.55,6.60"
RECORDED_AT = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


def add_ping_batch(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip_id,
    points: list[tuple[datetime, float, float]],
    idempotency_key: str,
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
            for sequence_number, (recorded_at, lat, lon) in enumerate(points):
                session.add(
                    LocationPing(
                        trip_session_id=trip_id,
                        batch_id=batch.id,
                        recorded_at=recorded_at,
                        received_at=received_at,
                        sequence_number=sequence_number,
                        latitude=lat,
                        longitude=lon,
                        accuracy_m=10,
                        speed_mps=None,
                        heading_degrees=None,
                        altitude_m=None,
                        geom=point_value(session, lon=lon, lat=lat),
                        ping_metadata={},
                    )
                )
            await session.commit()

    asyncio.run(create())


def create_heatmap_graph(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    advertiser_email: str = "heatmap-advertiser@example.com",
    driver_email: str = "heatmap-driver@example.com",
    plate_number: str = "HMAP-1",
    vehicle_type: VehicleType = VehicleType.CAR,
    organization_name: str = "Heatmap Org",
):
    admin = create_test_user(db_sessionmaker, email=f"admin-{advertiser_email}", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email=advertiser_email,
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=organization_name,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    driver = create_test_user(
        db_sessionmaker,
        email=driver_email,
        password=PASSWORD,
        full_name="Private Heatmap Driver",
        phone="+234000000000",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        license_number="PRIVATE-LICENSE",
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=plate_number,
        vehicle_type=vehicle_type,
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=RECORDED_AT,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT + timedelta(hours=1),
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_at=RECORDED_AT,
        ended_at=RECORDED_AT + timedelta(hours=1),
        first_ping_at=RECORDED_AT,
        last_ping_at=RECORDED_AT + timedelta(minutes=10),
        distance_m=Decimal("1000.00"),
        quality_score=Decimal("0.8000"),
    )
    density_profile = create_test_traffic_density_profile(
        db_sessionmaker,
        name=f"Heatmap density {plate_number}",
    )
    estimate = create_test_impression_estimate(
        db_sessionmaker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=density_profile.id,
        estimated_impressions=Decimal("200.00"),
    )
    add_ping_batch(
        db_sessionmaker,
        trip_id=trip.id,
        idempotency_key=f"heatmap-{plate_number}",
        points=[
            (RECORDED_AT, 6.45, 3.39),
            (RECORDED_AT + timedelta(minutes=5), 6.45, 3.39),
        ],
    )
    return admin, advertiser, organization, campaign, driver, profile, vehicle, trip, estimate


def test_heatmap_settings_defaults_and_validation() -> None:
    settings = Settings()

    assert settings.heatmap_default_resolution_m == 500
    assert settings.heatmap_min_resolution_m == 50
    assert settings.heatmap_max_resolution_m == 5000
    assert settings.heatmap_max_bbox_area_sq_km == 2500
    assert settings.heatmap_max_date_range_days == 90
    assert settings.heatmap_max_cells == 5000
    assert settings.heatmap_min_trips_per_cell == 1

    with pytest.raises(ValueError):
        Settings(heatmap_min_resolution_m=1000, heatmap_default_resolution_m=500)
    with pytest.raises(ValueError):
        Settings(heatmap_min_trips_per_cell=0)


def test_heatmap_validation_rbac_cross_org_and_scope_guards(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="adv-validation@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    driver = create_test_user(
        db_sessionmaker,
        email="driver-validation@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    other_advertiser = create_test_user(
        db_sessionmaker,
        email="adv-other-validation@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other_org, _ = create_test_organization(
        db_sessionmaker,
        name="Other heatmap org",
        owner_user_id=other_advertiser.id,
    )
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=other_org.id,
        created_by_user_id=other_advertiser.id,
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)

    missing_bbox = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
    )
    malformed_bbox = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": "3.30,6.40,3.55"},
    )
    reversed_bbox = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": "3.55,6.40,3.30,6.60"},
    )
    too_large = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": "0,0,10,10"},
    )
    bad_resolution = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": BBOX, "resolution_m": 10},
    )
    too_many_cells = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": BBOX, "resolution_m": 50},
    )
    bad_metric = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": BBOX, "metric": "raw_gps"},
    )
    bad_date = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={
            "bbox": BBOX,
            "start_at": "2026-06-02T00:00:00Z",
            "end_at": "2026-06-01T00:00:00Z",
        },
    )
    long_date = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={
            "bbox": BBOX,
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-06-01T00:00:00Z",
        },
    )
    just_over_max_date = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={
            "bbox": BBOX,
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-04-01T00:00:01Z",
        },
    )
    naive_start_at = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=advertiser_headers,
        params={
            "bbox": BBOX,
            "start_at": "2026-06-01T00:00:00",
        },
    )
    cross_org = db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/heatmap",
        headers=advertiser_headers,
        params={"bbox": BBOX},
    )
    advertiser_as_admin = db_client.get(
        "/api/v1/admin/heatmap",
        headers=advertiser_headers,
        params={"bbox": BBOX},
    )
    driver_as_admin = db_client.get(
        "/api/v1/admin/heatmap",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        params={"bbox": BBOX},
    )
    admin_as_advertiser = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        params={"bbox": BBOX},
    )
    unauthenticated = db_client.get("/api/v1/admin/heatmap", params={"bbox": BBOX})
    mismatch = db_client.get(
        "/api/v1/admin/heatmap",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        params={
            "bbox": BBOX,
            "campaign_id": str(campaign.id),
            "organization_id": str(other_org.id),
        },
    )

    assert missing_bbox.status_code == http_status.HTTP_400_BAD_REQUEST
    assert missing_bbox.json()["error"]["code"] == "MISSING_BBOX"
    assert malformed_bbox.json()["error"]["code"] == "INVALID_BBOX"
    assert reversed_bbox.json()["error"]["code"] == "INVALID_BBOX"
    assert too_large.json()["error"]["code"] == "HEATMAP_BBOX_TOO_LARGE"
    assert bad_resolution.json()["error"]["code"] == "INVALID_HEATMAP_RESOLUTION"
    assert too_many_cells.json()["error"]["code"] == "HEATMAP_TOO_MANY_CELLS"
    assert bad_metric.json()["error"]["code"] == "INVALID_HEATMAP_METRIC"
    assert bad_date.json()["error"]["code"] == "INVALID_DATE_RANGE"
    assert long_date.json()["error"]["code"] == "HEATMAP_DATE_RANGE_TOO_LARGE"
    assert just_over_max_date.json()["error"]["code"] == "HEATMAP_DATE_RANGE_TOO_LARGE"
    assert naive_start_at.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert naive_start_at.json()["error"]["code"] == "VALIDATION_ERROR"
    assert cross_org.status_code == http_status.HTTP_404_NOT_FOUND
    assert advertiser_as_admin.status_code == http_status.HTTP_403_FORBIDDEN
    assert driver_as_admin.status_code == http_status.HTTP_403_FORBIDDEN
    assert admin_as_advertiser.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert mismatch.status_code == http_status.HTTP_400_BAD_REQUEST
    assert mismatch.json()["error"]["code"] == "INVALID_HEATMAP_FILTERS"

    versions = {path.name for path in Path("alembic/versions").glob("*.py")}
    assert "0010_payouts_and_earnings.py" in versions
    for migration in Path("alembic/versions").glob("*.py"):
        migration_text = migration.read_text()
        assert '"heatmaps"' not in migration_text
        assert '"heatmap_cache"' not in migration_text


def test_advertiser_heatmap_aggregates_metrics_and_preserves_privacy(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, driver, profile, vehicle, _, _ = create_heatmap_graph(
        postgis_db_sessionmaker
    )
    headers = auth_headers(postgis_db_client, advertiser.email, PASSWORD)
    before_estimates = len(fetch_impression_estimates(postgis_db_sessionmaker))
    before_payouts = len(fetch_payout_calculations(postgis_db_sessionmaker))
    before_ledger = len(fetch_earnings_ledger_entries(postgis_db_sessionmaker))

    response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={"bbox": BBOX, "resolution_m": 500, "metric": "estimated_impressions"},
    )
    date_filtered = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={
            "bbox": BBOX,
            "resolution_m": 500,
            "metric": "ping_count",
            "start_at": (RECORDED_AT + timedelta(minutes=1)).isoformat(),
        },
    )
    trip_metric = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={"bbox": BBOX, "resolution_m": 500, "metric": "trip_count"},
    )
    distance_metric = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={"bbox": BBOX, "resolution_m": 500, "metric": "distance_m"},
    )

    data = response.json()
    serialized = str(data)
    assert response.status_code == http_status.HTTP_200_OK
    assert data["type"] == "FeatureCollection"
    assert data["metadata"]["campaign_id"] == str(campaign.id)
    assert data["metadata"]["metric"] == "estimated_impressions"
    assert data["metadata"]["aggregation_version"] == "heatmap_v1"
    assert len(data["features"]) == 1
    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"]["metric"] == "estimated_impressions"
    assert feature["properties"]["weight"] == "200.00"
    assert feature["properties"]["ping_count"] == 2
    assert feature["properties"]["trip_count"] == 1
    assert feature["properties"]["distance_m"] == "1000.00"
    assert feature["properties"]["estimated_impressions"] == "200.00"
    assert feature["properties"]["average_quality_score"] == "0.8000"
    assert date_filtered.json()["features"][0]["properties"]["ping_count"] == 1
    assert trip_metric.json()["features"][0]["properties"]["weight"] == "1"
    assert distance_metric.json()["features"][0]["properties"]["weight"] == "1000.00"
    for forbidden in [
        str(driver.id),
        str(profile.id),
        vehicle.plate_number,
        "Private Heatmap Driver",
        "+234000000000",
        "PRIVATE-LICENSE",
        "driver_profile_id",
        "plate_number",
        "idempotency_key",
        "ledger",
        "password_hash",
    ]:
        assert forbidden not in serialized
    assert len(fetch_impression_estimates(postgis_db_sessionmaker)) == before_estimates
    assert len(fetch_payout_calculations(postgis_db_sessionmaker)) == before_payouts
    assert len(fetch_earnings_ledger_entries(postgis_db_sessionmaker)) == before_ledger


def test_admin_heatmap_filters_global_campaign_org_and_vehicle_type(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin, advertiser, organization, campaign, *_ = create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="heatmap-filter-advertiser@example.com",
        driver_email="heatmap-filter-driver@example.com",
        plate_number="HMAP-2",
        vehicle_type=VehicleType.CAR,
        organization_name="Heatmap Filter Org",
    )
    create_heatmap_graph(
        postgis_db_sessionmaker,
        advertiser_email="heatmap-filter-other@example.com",
        driver_email="heatmap-filter-other-driver@example.com",
        plate_number="HMAP-3",
        vehicle_type=VehicleType.BUS,
        organization_name="Heatmap Other Org",
    )
    headers = auth_headers(postgis_db_client, admin.email, PASSWORD)

    global_response = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={"bbox": BBOX, "resolution_m": 500, "metric": "ping_count"},
    )
    campaign_response = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={
            "bbox": BBOX,
            "resolution_m": 500,
            "metric": "ping_count",
            "campaign_id": str(campaign.id),
        },
    )
    organization_response = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={
            "bbox": BBOX,
            "resolution_m": 500,
            "metric": "ping_count",
            "organization_id": str(organization.id),
        },
    )
    vehicle_type_response = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={"bbox": BBOX, "resolution_m": 500, "vehicle_type": "car"},
    )
    empty_vehicle_type = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={
            "bbox": BBOX,
            "resolution_m": 500,
            "campaign_id": str(campaign.id),
            "vehicle_type": "bus",
        },
    )
    invalid_vehicle_type = postgis_db_client.get(
        "/api/v1/admin/heatmap",
        headers=headers,
        params={"bbox": BBOX, "vehicle_type": "spaceship"},
    )

    assert global_response.status_code == http_status.HTTP_200_OK
    assert global_response.json()["features"][0]["properties"]["ping_count"] == 4
    assert campaign_response.json()["metadata"]["campaign_id"] == str(campaign.id)
    assert campaign_response.json()["features"][0]["properties"]["ping_count"] == 2
    assert organization_response.json()["metadata"]["organization_id"] == str(organization.id)
    assert organization_response.json()["features"][0]["properties"]["ping_count"] == 2
    assert vehicle_type_response.json()["metadata"]["vehicle_type"] == "car"
    assert vehicle_type_response.json()["features"][0]["properties"]["ping_count"] == 2
    assert empty_vehicle_type.json()["features"] == []
    assert invalid_vehicle_type.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_vehicle_type.json()["error"]["code"] == "VALIDATION_ERROR"
    assert advertiser.role == UserRole.ADVERTISER


def test_heatmap_empty_feature_collection(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, *_ = create_heatmap_graph(postgis_db_sessionmaker)
    headers = auth_headers(postgis_db_client, advertiser.email, PASSWORD)

    response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={
            "bbox": BBOX,
            "start_at": "2026-06-10T00:00:00Z",
            "end_at": "2026-06-11T00:00:00Z",
        },
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["type"] == "FeatureCollection"
    assert response.json()["features"] == []
    assert len(fetch_location_pings(postgis_db_sessionmaker)) == 2


def test_heatmap_postgis_sql_uses_bbox_filter_and_meter_grid() -> None:
    service_text = Path("app/services/heatmaps.py").read_text()

    assert "lp.geom && bbox.geom" in service_text
    assert "ST_Intersects(lp.geom, bbox.geom)" in service_text
    assert "ST_Transform(lp.geom, 3857)" in service_text
    assert "floor(ST_X" in service_text
    assert "ST_MakeEnvelope" in service_text
    assert "ST_AsGeoJSON" in service_text


def test_heatmap_endpoint_does_not_create_rows_on_sqlite(
    db_client,
    db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, *_ = create_heatmap_graph(db_sessionmaker)
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    before = asyncio.run(count_rows(db_sessionmaker))
    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/heatmap",
        headers=headers,
        params={"bbox": BBOX},
    )
    after = asyncio.run(count_rows(db_sessionmaker))

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "POSTGIS_REQUIRED"
    assert after == before


async def count_rows(db_sessionmaker: async_sessionmaker[AsyncSession]) -> tuple[int, int, int]:
    async with db_sessionmaker() as session:
        estimates = await session.scalar(select(func.count()).select_from(ImpressionEstimate))
        payouts = await session.scalar(select(func.count()).select_from(PayoutCalculation))
        pings = await session.scalar(select(func.count()).select_from(LocationPing))
        return int(estimates or 0), int(payouts or 0), int(pings or 0)
