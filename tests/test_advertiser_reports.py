import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from conftest import (
    auth_headers,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_estimate_source,
    create_test_impression_estimate,
    create_test_payout_rule,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryStatus, PayoutCalculation
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus, VehicleType
from app.services.impressions import profile_metadata

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
    density_profile = create_test_estimate_source(
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
        # Mirror what estimate_values() freezes in production so the frozen
        # density provenance under test is the real estimate-time snapshot.
        metadata={
            "fraud_flag_counts": {"low": 0, "medium": 0, "high": 0},
            "road_category_method": "profile_default_weight_no_road_classification_v1",
            "traffic_density_profile": profile_metadata(density_profile),
        },
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
                formula_version="payout_v4",
                eligible_seconds=0,
                excluded_seconds_by_reason={},
                inputs_fingerprint="synthetic-report-fixture",
                distance_m_by_day={},
                amount_by_day={},
                status=status,
                currency="NGN",
                gross_payout=gross_payout,
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


def test_current_advertiser_outputs(db_client, db_sessionmaker):
    from test_req217_reports import owner_graph

    owner, _, campaign = owner_graph(db_sessionmaker, "current-output")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    root = f"/api/v1/advertiser/campaigns/{campaign.id}"
    for suffix in ("report", "daily-metrics"):
        response = db_client.get(f"{root}/{suffix}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["campaign_id"] == str(campaign.id)
        assert db_client.get(f"{root}/{suffix}").status_code == 401
    assert (
        db_client.get(
            f"{root}/daily-metrics", headers=headers, params={"start_at": "2026-06-01T10:00:00Z"}
        ).status_code
        == 422
    )


def test_current_outputs_keep_company_isolation(db_client, db_sessionmaker):
    from test_req217_reports import owner_graph

    owner, _, campaign = owner_graph(db_sessionmaker, "company-one")
    other, _, _ = owner_graph(db_sessionmaker, "company-two")
    headers = auth_headers(db_client, other.email, PASSWORD)
    for suffix in ("report", "daily-metrics", "live-positions"):
        assert (
            db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/{suffix}", headers=headers
            ).status_code
            == 404
        )
