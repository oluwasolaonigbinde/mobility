import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_driver_profile,
    create_test_impression_estimate,
    create_test_organization,
    create_test_payout_rule,
    create_test_traffic_density_profile,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_impression_estimates,
    fetch_payout_calculations,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryStatus, PayoutCalculation
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus, VehicleType

PASSWORD = "long-secure-password"
DAY_1 = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
DAY_2 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)


def create_report_graph(
    db_sessionmaker,
    *,
    admin,
    advertiser,
    campaign,
    driver_email: str,
    plate_number: str,
    started_at: datetime,
    service_city: str = "Lagos",
    driver_phone: str | None = "+234555000",
    trip_status: TripSessionStatus = TripSessionStatus.ENDED,
    analytics_status: str = "computed",
    estimate_status: str = "estimated",
    payout_status: str = "calculated",
    distance_m=Decimal("10000.00"),
    estimated_impressions=Decimal("500.00"),
    final_payout=Decimal("1200.00"),
    gross_payout=Decimal("1400.00"),
    quality_score=Decimal("0.9000"),
    confidence_score=Decimal("0.8500"),
):
    driver = create_test_user(
        db_sessionmaker,
        email=driver_email,
        password=PASSWORD,
        full_name="Sensitive Driver",
        phone=driver_phone,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        license_number="SECRET-LICENSE",
        service_city=service_city,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=plate_number,
        vehicle_type=VehicleType.CAR,
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
    ended_at = started_at + timedelta(hours=1) if trip_status == TripSessionStatus.ENDED else None
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
        distance_m=distance_m,
        active_tracking_seconds=3000,
        stationary_seconds=600,
        target_zone_distance_m=Decimal("4000.00"),
        bonus_zone_distance_m=Decimal("2000.00"),
        exclusion_zone_distance_m=Decimal("100.00"),
        quality_score=quality_score,
    )
    density_profile = create_test_traffic_density_profile(
        db_sessionmaker,
        name=f"Traffic {plate_number}",
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
        status=estimate_status,
        estimated_impressions=estimated_impressions,
    )
    rule = create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        currency=campaign.currency,
        status="inactive",
    )
    add_payout_calculation(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        estimate=estimate,
        payout_rule_id=rule.id,
        driver_user_id=driver.id,
        status=payout_status,
        final_payout=final_payout,
        gross_payout=gross_payout,
        calculated_at=started_at + timedelta(hours=2),
    )
    set_estimate_confidence(db_sessionmaker, estimate.id, confidence_score)
    return driver, profile, vehicle, assignment, trip, analytics, estimate


def add_campaign_zone(db_sessionmaker, *, campaign_id, created_by_user_id, zone_type: str) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            session.add(
                CampaignZone(
                    campaign_id=campaign_id,
                    created_by_user_id=created_by_user_id,
                    name=f"{zone_type} zone",
                    description=None,
                    zone_type=zone_type,
                    geom="MULTIPOLYGON EMPTY",
                    zone_metadata={},
                )
            )
            await session.commit()

    asyncio.run(create())


def add_fraud_flag(
    db_sessionmaker,
    *,
    trip,
    analytics,
    severity: str,
    flag_type: str,
    flag_status: str = FraudFlagStatus.OPEN.value,
    detected_at: datetime = DAY_1,
    reviewed_by_user_id=None,
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
                    status=flag_status,
                    description="reporting test flag",
                    evidence={},
                    detected_at=detected_at,
                    reviewed_by_user_id=reviewed_by_user_id,
                    reviewed_at=(detected_at if reviewed_by_user_id is not None else None),
                    resolution_note=(
                        "Dismissed for reporting fixture."
                        if flag_status == FraudFlagStatus.DISMISSED.value
                        else None
                    ),
                )
            )
            await session.commit()

    asyncio.run(create())


def set_estimate_confidence(db_sessionmaker, estimate_id, confidence_score) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            estimate = await session.get(ImpressionEstimate, estimate_id)
            estimate.confidence_score = confidence_score
            await session.commit()

    asyncio.run(update())


def set_estimate_fraud_counts(db_sessionmaker, estimate_id, counts: dict[str, int]) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            estimate = await session.get(ImpressionEstimate, estimate_id)
            metadata = dict(estimate.estimate_metadata or {})
            metadata["fraud_flag_counts"] = counts
            estimate.estimate_metadata = metadata
            await session.commit()

    asyncio.run(update())


def add_payout_calculation(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    trip,
    analytics,
    estimate,
    payout_rule_id,
    driver_user_id,
    status: str,
    final_payout,
    gross_payout,
    calculated_at: datetime,
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            calculation = PayoutCalculation(
                trip_session_id=trip.id,
                trip_analytics_id=analytics.id,
                impression_estimate_id=estimate.id,
                payout_rule_id=payout_rule_id,
                assignment_id=trip.assignment_id,
                campaign_id=trip.campaign_id,
                driver_profile_id=trip.driver_profile_id,
                vehicle_id=trip.vehicle_id,
                formula_version="payout_v1",
                status=status,
                currency="NGN",
                distance_component=Decimal("0.00"),
                active_time_component=Decimal("0.00"),
                target_zone_bonus_component=Decimal("0.00"),
                bonus_zone_bonus_component=Decimal("0.00"),
                impression_component=Decimal("0.00"),
                gross_payout=gross_payout,
                quality_multiplier=Decimal("1.0000"),
                fraud_multiplier=Decimal("1.0000"),
                cap_adjustment=Decimal("0.00"),
                final_payout=final_payout,
                calculated_at=calculated_at,
                payout_metadata={},
            )
            session.add(calculation)
            await session.flush()
            if status == "calculated" and Decimal(str(final_payout)) > 0:
                session.add(
                    EarningsLedgerEntry(
                        payout_calculation_id=calculation.id,
                        driver_profile_id=trip.driver_profile_id,
                        driver_user_id=driver_user_id,
                        campaign_id=trip.campaign_id,
                        trip_session_id=trip.id,
                        vehicle_id=trip.vehicle_id,
                        entry_type="trip_payout",
                        status=EarningsLedgerEntryStatus.PENDING.value,
                        amount=final_payout,
                        currency="NGN",
                        description="Trip payout",
                        occurred_at=calculated_at,
                        ledger_metadata={},
                    )
                )
            await session.commit()

    asyncio.run(create())


def test_advertiser_dashboard_campaign_summary_daily_metrics_and_report(db_client, db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="adv-report@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="Lagos Launch Campaign",
        campaign_status=CampaignStatus.ACTIVE,
        start_at=DAY_1,
        end_at=DAY_2 + timedelta(days=30),
        budget_amount=Decimal("500000.00"),
        daily_budget_amount=Decimal("25000.00"),
    )
    create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="Draft campaign",
        campaign_status=CampaignStatus.DRAFT,
    )
    create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )
    create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        name="Draft creative",
        creative_status=CreativeStatus.DRAFT,
    )
    for zone_type in ["target", "bonus", "exclusion"]:
        add_campaign_zone(
            db_sessionmaker,
            campaign_id=campaign.id,
            created_by_user_id=advertiser.id,
            zone_type=zone_type,
        )
    _, _, _, _, trip, analytics, estimate = create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="driver-report@example.com",
        plate_number="RPT-1",
        started_at=DAY_1,
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        severity="high",
        flag_type="impossible_speed",
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        severity="low",
        flag_type="poor_accuracy",
        flag_status=FraudFlagStatus.DISMISSED.value,
        reviewed_by_user_id=admin.id,
    )
    set_estimate_fraud_counts(
        db_sessionmaker,
        estimate.id,
        {"low": 0, "medium": 0, "high": 1},
    )
    create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="driver-report-2@example.com",
        plate_number="RPT-2",
        started_at=DAY_2,
        trip_status=TripSessionStatus.ACTIVE,
        analytics_status="insufficient_data",
        estimate_status="insufficient_data",
        payout_status="insufficient_data",
        distance_m=Decimal("5000.00"),
        estimated_impressions=Decimal("0.00"),
        final_payout=Decimal("0.00"),
        gross_payout=Decimal("0.00"),
        quality_score=Decimal("0.5000"),
        confidence_score=Decimal("0.1000"),
    )
    other_advertiser = create_test_user(
        db_sessionmaker,
        email="other-adv-report@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other_org, _ = create_test_organization(
        db_sessionmaker,
        name="Other Org",
        owner_user_id=other_advertiser.id,
    )
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=other_org.id,
        created_by_user_id=other_advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=other_advertiser,
        campaign=other_campaign,
        driver_email="other-driver-report@example.com",
        plate_number="OTH-1",
        started_at=DAY_1,
        estimated_impressions=Decimal("9999.00"),
        final_payout=Decimal("9999.00"),
        gross_payout=Decimal("9999.00"),
    )

    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    dashboard = db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers)
    campaign_summary = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/summary",
        headers=headers,
    )
    daily = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics?limit=1",
        headers=headers,
    )
    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        headers=headers,
    )

    assert dashboard.status_code == http_status.HTTP_200_OK
    dashboard_data = dashboard.json()
    assert dashboard_data["campaigns"]["total"] == 2
    assert dashboard_data["campaigns"]["active"] == 1
    assert dashboard_data["campaigns"]["draft"] == 1
    assert dashboard_data["trips"] == {"total": 2, "ended": 1, "active": 1}
    assert dashboard_data["impressions"]["estimated_impressions"] == "500.00"
    assert dashboard_data["impressions"]["estimated_trip_count"] == 1
    assert dashboard_data["impressions"]["insufficient_data_trip_count"] == 1
    assert dashboard_data["costs"]["totals_by_currency"][0]["final_payout_total"] == "1200.00"
    assert dashboard_data["costs"]["totals_by_currency"][0]["ledger_entry_count"] == 1
    assert dashboard_data["quality"]["fraud_flags"]["open"] == 1
    assert dashboard_data["quality"]["fraud_flags"]["dismissed"] == 1
    assert dashboard_data["quality"]["fraud_flags"]["high"] == 1

    assert campaign_summary.status_code == http_status.HTTP_200_OK
    summary_data = campaign_summary.json()
    assert summary_data["campaign"]["name"] == "Lagos Launch Campaign"
    assert summary_data["campaign"]["budget_amount"] == "500000.00"
    assert summary_data["creatives"] == {"total": 2, "ready": 0, "draft": 1, "archived": 0}
    assert summary_data["zones"] == {"total": 3, "target": 1, "bonus": 1, "exclusion": 1}
    assert summary_data["route_analytics"]["analyzed_trip_count"] == 2
    assert summary_data["route_analytics"]["total_distance_m"] == "15000.00"
    assert summary_data["costs"]["totals_by_currency"][0]["calculated_trip_count"] == 1
    assert summary_data["costs"]["totals_by_currency"][0]["insufficient_data_trip_count"] == 1
    assert summary_data["fraud_flags"]["open"] == 1

    assert daily.status_code == http_status.HTTP_200_OK
    daily_data = daily.json()
    assert daily_data["total"] == 2
    assert daily_data["limit"] == 1
    assert daily_data["items"][0]["date"] == "2026-06-02"
    assert daily_data["items"][0]["trip_count"] == 1
    assert daily_data["items"][0]["average_confidence_score"] == "0.1000"

    assert report.status_code == http_status.HTTP_200_OK
    report_data = report.json()
    assert "items" not in report_data
    assert "driver" not in str(report_data).lower()
    assert report_data["summary"]["id"] == str(campaign.id)
    assert len(report_data["daily_metrics"]) == 2
    assert report_data["creative_summary"]["total"] == 2


def test_campaign_trip_reports_are_private_filterable_and_rbac_protected(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="adv-trips@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    driver, _, vehicle, _, trip, analytics, estimate = create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email="driver-private@example.com",
        plate_number="SECRET-PLATE",
        started_at=DAY_1,
    )
    add_fraud_flag(
        db_sessionmaker,
        trip=trip,
        analytics=analytics,
        severity="medium",
        flag_type="poor_accuracy",
    )
    set_estimate_fraud_counts(
        db_sessionmaker,
        estimate.id,
        {"low": 0, "medium": 1, "high": 0},
    )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/trips"
        "?status=ended&has_fraud_flags=true&analytics_status=computed"
        "&impression_status=estimated&payout_status=calculated",
        headers=headers,
    )
    invalid_filter = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/trips?status=done",
        headers=headers,
    )

    data = response.json()
    serialized = str(data)
    assert response.status_code == http_status.HTTP_200_OK
    assert data["total"] == 1
    item = data["items"][0]
    assert item["trip_id"] == str(trip.id)
    assert item["assignment_id"] == str(trip.assignment_id)
    assert item["vehicle_type"] == vehicle.vehicle_type
    assert item["analytics"]["distance_m"] == "10000.00"
    assert item["impressions"]["estimated_impressions"] == "500.00"
    assert item["cost"]["final_payout"] == "1200.00"
    assert item["fraud_flags"] == {
        "open_count": 1,
        "high_count": 0,
        "medium_count": 1,
        "low_count": 0,
    }
    for forbidden in [
        str(driver.id),
        "Sensitive Driver",
        "+234555000",
        "SECRET-LICENSE",
        "SECRET-PLATE",
        "driver_profile_id",
        "plate_number",
        "latitude",
        "longitude",
        "idempotency_key",
        "ledger",
    ]:
        assert forbidden not in serialized
    assert invalid_filter.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_filter.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/trips",
            headers=auth_headers(db_client, driver.email, PASSWORD),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/trips",
            headers=auth_headers(db_client, admin.email, PASSWORD),
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        db_client.get(f"/api/v1/advertiser/campaigns/{campaign.id}/trips").status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )


def test_reporting_zero_state_cross_org_date_validation_and_no_auto_calculation(
    db_client,
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker,
        email="adv-zero@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    empty_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    for campaign_status in [
        CampaignStatus.PENDING_REVIEW,
        CampaignStatus.APPROVED,
        CampaignStatus.REJECTED,
    ]:
        create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=advertiser.id,
            campaign_status=campaign_status,
        )
    other_advertiser = create_test_user(
        db_sessionmaker,
        email="adv-zero-other@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other_org, _ = create_test_organization(
        db_sessionmaker,
        name="Other zero org",
        owner_user_id=other_advertiser.id,
    )
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=other_org.id,
        created_by_user_id=other_advertiser.id,
    )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    before_estimates = len(fetch_impression_estimates(db_sessionmaker))
    before_payouts = len(fetch_payout_calculations(db_sessionmaker))

    summary = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/summary",
        headers=headers,
    )
    dashboard = db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers)
    daily = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/daily-metrics",
        headers=headers,
    )
    trips = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/trips",
        headers=headers,
    )
    cross_org = db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/summary",
        headers=headers,
    )
    invalid_range = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/summary"
        "?start_at=2026-06-02T00:00:00Z&end_at=2026-06-01T00:00:00Z",
        headers=headers,
    )
    naive_date = db_client.get(
        f"/api/v1/advertiser/campaigns/{empty_campaign.id}/summary?start_at=2026-06-01T00:00:00",
        headers=headers,
    )

    assert summary.status_code == http_status.HTTP_200_OK
    assert dashboard.status_code == http_status.HTTP_200_OK
    assert dashboard.json()["campaigns"] == {
        "total": 4,
        "draft": 0,
        "pending_review": 1,
        "approved": 1,
        "rejected": 1,
        "scheduled": 0,
        "active": 1,
        "paused": 0,
        "completed": 0,
        "cancelled": 0,
    }
    data = summary.json()
    assert data["trips"] == {"total": 0, "ended": 0, "active": 0}
    assert data["impressions"]["estimated_impressions"] == "0.00"
    assert data["costs"]["totals_by_currency"][0]["final_payout_total"] == "0.00"
    assert data["fraud_flags"] == {
        "open": 0,
        "acknowledged": 0,
        "confirmed": 0,
        "dismissed": 0,
        "low": 0,
        "medium": 0,
        "high": 0,
    }
    assert daily.json()["items"] == []
    assert trips.json()["items"] == []
    assert cross_org.status_code == http_status.HTTP_404_NOT_FOUND
    assert invalid_range.status_code == http_status.HTTP_400_BAD_REQUEST
    assert invalid_range.json()["error"]["code"] == "INVALID_DATE_RANGE"
    assert naive_date.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert naive_date.json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(fetch_impression_estimates(db_sessionmaker)) == before_estimates
    assert len(fetch_payout_calculations(db_sessionmaker)) == before_payouts
    assert admin.role == UserRole.ADMIN


def test_slice10_adds_no_migration_or_reporting_tables() -> None:
    from pathlib import Path

    versions = {path.name for path in Path("alembic/versions").glob("*.py")}
    assert "0010_payouts_and_earnings.py" in versions
    text = Path("alembic/versions/0010_payouts_and_earnings.py").read_text()
    for forbidden_table in [
        "campaign_daily_metrics",
        "advertiser_reports",
        "heatmaps",
        "heatmap_cache",
        "billing",
        "invoices",
        "settlements",
        "withdrawals",
        "payments",
    ]:
        assert f'"{forbidden_table}"' not in text
