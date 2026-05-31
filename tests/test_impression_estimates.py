import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_impression_estimates,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus

PASSWORD = "long-secure-password"
BASE_TIME = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def admin_headers(client):
    return auth_headers(client, "admin@example.com", PASSWORD)


def create_estimation_graph(
    db_sessionmaker,
    *,
    trip_status: TripSessionStatus = TripSessionStatus.ENDED,
    analytics_status: str = "computed",
    started_at: datetime = BASE_TIME,
    ended_at: datetime | None = BASE_TIME + timedelta(minutes=30),
    quality_score=Decimal("0.5"),
    admin_email: str = "admin@example.com",
    advertiser_email: str = "advertiser@example.com",
    driver_email: str = "driver@example.com",
    plate_number: str = "IMP-123",
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
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        status=analytics_status,
        started_at=started_at,
        ended_at=ended_at,
        first_ping_at=started_at,
        last_ping_at=ended_at,
        distance_m=Decimal("10000"),
        stationary_seconds=600,
        target_zone_distance_m=Decimal("1000"),
        bonus_zone_distance_m=Decimal("2000"),
        exclusion_zone_distance_m=Decimal("1000"),
        quality_score=quality_score,
    )
    return admin, advertiser, driver, campaign, profile, vehicle, assignment, trip, analytics


def create_formula_profile(db_sessionmaker, **overrides):
    values = {
        "traffic_density_per_km": Decimal("100"),
        "dwell_impressions_per_minute": Decimal("4"),
        "road_category_weight": Decimal("1"),
        "morning_weight": Decimal("1"),
        "midday_weight": Decimal("2"),
        "evening_weight": Decimal("3"),
        "night_weight": Decimal("0.5"),
        "target_zone_weight": Decimal("1"),
        "bonus_zone_weight": Decimal("2"),
        "exclusion_zone_weight": Decimal("1"),
        "is_default": True,
    }
    values.update(overrides)
    return create_test_traffic_density_profile(db_sessionmaker, **values)


def add_fraud_flag(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip,
    analytics,
    severity: str,
    flag_type: str,
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            session.add(
                FraudFlag(
                    trip_session_id=trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=trip.assignment_id,
                    campaign_id=trip.campaign_id,
                    driver_profile_id=trip.driver_profile_id,
                    vehicle_id=trip.vehicle_id,
                    flag_type=flag_type,
                    severity=severity,
                    status=FraudFlagStatus.OPEN.value,
                    description=f"{severity} test flag",
                    evidence={},
                    detected_at=datetime.now(UTC),
                )
            )
            await session.commit()

    asyncio.run(create())


def test_admin_estimate_uses_formula_components_and_is_idempotent(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, campaign, profile, vehicle, assignment, trip, analytics = create_estimation_graph(
        db_sessionmaker
    )
    density_profile = create_formula_profile(db_sessionmaker)

    first = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id), "metadata": {"run": 1}},
    )
    second = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id), "metadata": {"run": 2}},
    )

    assert first.status_code == http_status.HTTP_200_OK
    data = first.json()
    assert data["status"] == "estimated"
    assert data["formula_version"] == "impressions_v1"
    assert data["base_distance_impressions"] == "1000.00"
    assert data["target_zone_impressions"] == "50.00"
    assert data["bonus_zone_impressions"] == "200.00"
    assert data["dwell_impressions"] == "40.00"
    assert data["exclusion_zone_adjustment"] == "100.00"
    assert data["estimated_impressions"] == "1190.00"
    assert data["quality_multiplier"] == "0.5000"
    assert data["fraud_adjustment_multiplier"] == "1.0000"
    assert data["confidence_score"] == "0.5000"
    assert data["metadata"]["time_bucket"] == "midday"
    assert data["metadata"]["request_metadata"] == {"run": 1}
    assert data["trip_analytics_id"] == str(analytics.id)
    assert data["assignment_id"] == str(assignment.id)
    assert data["campaign_id"] == str(campaign.id)
    assert data["driver_profile_id"] == str(profile.id)
    assert data["vehicle_id"] == str(vehicle.id)
    assert second.status_code == http_status.HTTP_200_OK
    assert second.json()["id"] == data["id"]
    assert second.json()["metadata"]["request_metadata"] == {"run": 2}
    assert len(fetch_impression_estimates(db_sessionmaker)) == 1


def test_estimate_creates_settings_backed_default_profile_when_omitted(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, _, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        advertiser_email="adv-default@example.com",
        driver_email="driver-default@example.com",
        plate_number="DEF-123",
    )

    response = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={},
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["traffic_density_profile_id"] is not None
    assert response.json()["metadata"]["traffic_density_profile"]["traffic_density_per_km"] in {
        "120",
        "120.0000",
    }


def test_insufficient_data_produces_low_confidence_zero_estimate(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, _, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        analytics_status="insufficient_data",
        quality_score=Decimal("0"),
        advertiser_email="adv-insufficient@example.com",
        driver_email="driver-insufficient@example.com",
        plate_number="INS-123",
    )
    density_profile = create_formula_profile(db_sessionmaker)

    response = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id)},
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["status"] == "insufficient_data"
    assert response.json()["estimated_impressions"] == "0.00"
    assert response.json()["confidence_score"] == "0.1000"


def test_blocked_analytics_produces_excluded_zero_estimate(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, _, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        analytics_status="blocked",
        quality_score=Decimal("0.75"),
        advertiser_email="adv-blocked@example.com",
        driver_email="driver-blocked@example.com",
        plate_number="BLK-123",
    )
    density_profile = create_formula_profile(db_sessionmaker)

    response = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id), "metadata": {"run": 1}},
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "excluded"
    assert data["estimated_impressions"] == "0.00"
    assert data["base_distance_impressions"] == "0.00"
    assert data["dwell_impressions"] == "0.00"
    assert data["target_zone_impressions"] == "0.00"
    assert data["bonus_zone_impressions"] == "0.00"
    assert data["exclusion_zone_adjustment"] == "0.00"
    assert data["quality_multiplier"] == "0.7500"
    assert data["fraud_adjustment_multiplier"] == "1.0000"
    assert data["confidence_score"] == "0.0000"
    assert data["metadata"]["components"]["reason"] == "blocked_analytics"
    assert data["metadata"]["request_metadata"] == {"run": 1}


def test_open_fraud_flags_apply_deterministic_severity_multipliers(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    cases = [
        ("high", "impossible_speed", "0.2500", "297.50"),
        ("medium", "poor_accuracy", "0.7000", "833.00"),
        ("low", "route_looping", "0.9000", "1071.00"),
    ]
    for index, (severity, flag_type, multiplier, expected) in enumerate(cases):
        _, _, _, _, _, _, _, trip, analytics = create_estimation_graph(
            db_sessionmaker,
            admin_email=f"admin-fraud-{index}@example.com",
            advertiser_email=f"adv-fraud-{index}@example.com",
            driver_email=f"driver-fraud-{index}@example.com",
            plate_number=f"FRD-{index}",
        )
        density_profile = create_formula_profile(
            db_sessionmaker,
            name=f"Fraud Profile {index}",
            is_default=False,
        )
        add_fraud_flag(
            db_sessionmaker,
            trip=trip,
            analytics=analytics,
            severity=severity,
            flag_type=flag_type,
        )

        response = db_client.post(
            f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
            headers=admin_headers(db_client),
            json={"traffic_density_profile_id": str(density_profile.id)},
        )

        assert response.status_code == http_status.HTTP_200_OK
        assert response.json()["fraud_adjustment_multiplier"] == multiplier
        assert response.json()["estimated_impressions"] == expected


def test_estimate_rejects_missing_analytics_active_trip_and_inactive_profile(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, campaign, profile, vehicle, assignment, active_trip, _ = create_estimation_graph(
        db_sessionmaker,
        admin_email="admin@example.com",
        trip_status=TripSessionStatus.ACTIVE,
        ended_at=None,
        advertiser_email="adv-active@example.com",
        driver_email="driver-active@example.com",
        plate_number="ACT-123",
    )
    ended_trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=active_trip.started_by_user_id,
        trip_status=TripSessionStatus.ENDED,
        started_at=BASE_TIME,
        ended_at=BASE_TIME + timedelta(minutes=1),
    )
    inactive_profile = create_formula_profile(
        db_sessionmaker,
        name="Inactive",
        is_default=False,
        status="inactive",
    )
    _, _, _, _, _, _, _, inactive_trip, _ = create_estimation_graph(
        db_sessionmaker,
        admin_email="admin-inactive-profile@example.com",
        advertiser_email="adv-inactive-profile@example.com",
        driver_email="driver-inactive-profile@example.com",
        plate_number="IAC-123",
    )

    active_response = db_client.post(
        f"/api/v1/admin/trips/{active_trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={},
    )
    missing_analytics = db_client.post(
        f"/api/v1/admin/trips/{ended_trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={},
    )
    inactive_response = db_client.post(
        f"/api/v1/admin/trips/{inactive_trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(inactive_profile.id)},
    )

    assert active_response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert active_response.json()["error"]["code"] == "TRIP_NOT_ENDED"
    assert missing_analytics.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_analytics.json()["error"]["code"] == "ANALYTICS_NOT_FOUND"
    assert inactive_response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_response.json()["error"]["code"] == "TRAFFIC_DENSITY_PROFILE_INACTIVE"


def test_admin_can_list_and_filter_impression_estimates(db_client, db_sessionmaker) -> None:
    _, _, _, campaign, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        advertiser_email="adv-list@example.com",
        driver_email="driver-list@example.com",
        plate_number="LST-123",
    )
    density_profile = create_formula_profile(db_sessionmaker)
    estimate = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id)},
    )
    assert estimate.status_code == http_status.HTTP_200_OK

    response = db_client.get(
        f"/api/v1/admin/impression-estimates?campaign_id={campaign.id}&status=estimated",
        headers=admin_headers(db_client),
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["campaign_id"] == str(campaign.id)


def test_advertiser_summary_is_scoped_and_aggregates_stored_estimates(
    db_client,
    db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        advertiser_email="adv-summary@example.com",
        driver_email="driver-summary@example.com",
        plate_number="SUM-123",
    )
    density_profile = create_formula_profile(db_sessionmaker)
    estimate = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id)},
    )
    assert estimate.status_code == http_status.HTTP_200_OK

    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    own = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
        headers=advertiser_headers,
    )

    other_advertiser = create_test_user(
        db_sessionmaker,
        email="other-adv@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, name="Other Org", owner_user_id=other_advertiser.id)
    other = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
        headers=auth_headers(db_client, other_advertiser.email, PASSWORD),
    )
    empty_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=advertiser.id,
        name="Empty",
        campaign_status=CampaignStatus.ACTIVE,
    )
    empty = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/impressions/summary",
        headers=advertiser_headers,
    )

    assert own.status_code == http_status.HTTP_200_OK
    assert own.json()["estimated_impressions"] == "1190.00"
    assert own.json()["trip_count"] == 1
    assert own.json()["estimated_trip_count"] == 1
    assert own.json()["average_confidence_score"] == "0.5000"
    assert other.status_code == http_status.HTTP_404_NOT_FOUND
    assert empty.status_code == http_status.HTTP_200_OK
    assert empty.json()["estimated_impressions"] == "0.00"
    assert empty.json()["trip_count"] == 0


def test_advertiser_summary_excludes_non_current_formula_estimates(
    db_client,
    db_sessionmaker,
) -> None:
    _, advertiser, _, campaign, profile, vehicle, assignment, trip, analytics = (
        create_estimation_graph(
            db_sessionmaker,
            advertiser_email="adv-summary-formula@example.com",
            driver_email="driver-summary-formula@example.com",
            plate_number="SMF-123",
        )
    )
    density_profile = create_formula_profile(db_sessionmaker)
    estimate = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
        headers=admin_headers(db_client),
        json={"traffic_density_profile_id": str(density_profile.id)},
    )
    assert estimate.status_code == http_status.HTTP_200_OK

    async def add_old_formula_estimate() -> None:
        async with db_sessionmaker() as session:
            session.add(
                ImpressionEstimate(
                    trip_session_id=trip.id,
                    trip_analytics_id=analytics.id,
                    assignment_id=assignment.id,
                    campaign_id=campaign.id,
                    driver_profile_id=profile.id,
                    vehicle_id=vehicle.id,
                    traffic_density_profile_id=density_profile.id,
                    formula_version="impressions_v0",
                    status="estimated",
                    estimated_impressions=Decimal("999.00"),
                    base_distance_impressions=Decimal("999.00"),
                    dwell_impressions=Decimal("0.00"),
                    target_zone_impressions=Decimal("0.00"),
                    bonus_zone_impressions=Decimal("0.00"),
                    exclusion_zone_adjustment=Decimal("0.00"),
                    quality_multiplier=Decimal("1.0000"),
                    fraud_adjustment_multiplier=Decimal("1.0000"),
                    confidence_score=Decimal("1.0000"),
                    started_at=analytics.started_at,
                    ended_at=analytics.ended_at,
                    estimated_at=BASE_TIME,
                    estimate_metadata={"formula_version": "impressions_v0"},
                )
            )
            await session.commit()

    asyncio.run(add_old_formula_estimate())

    summary = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
    )

    assert summary.status_code == http_status.HTTP_200_OK
    assert summary.json()["formula_version"] == "impressions_v1"
    assert summary.json()["estimated_impressions"] == "1190.00"
    assert summary.json()["trip_count"] == 1


def test_impression_endpoints_enforce_roles(db_client, db_sessionmaker) -> None:
    _, advertiser, driver, campaign, _, _, _, trip, _ = create_estimation_graph(
        db_sessionmaker,
        advertiser_email="adv-rbac@example.com",
        driver_email="driver-rbac@example.com",
        plate_number="RBC-123",
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    driver_headers = auth_headers(db_client, driver.email, PASSWORD)

    for headers in [advertiser_headers, driver_headers]:
        response = db_client.post(
            f"/api/v1/admin/trips/{trip.id}/estimate-impressions",
            headers=headers,
            json={},
        )
        assert response.status_code == http_status.HTTP_403_FORBIDDEN
    assert (
        db_client.post(f"/api/v1/admin/trips/{trip.id}/estimate-impressions").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
            headers=driver_headers,
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary",
            headers=admin_headers(db_client),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(f"/api/v1/advertiser/campaigns/{campaign.id}/impressions/summary").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
