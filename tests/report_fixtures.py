import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_driver_profile,
    create_test_estimate_source,
    create_test_impression_estimate,
    create_test_installation_evidence,
    create_test_organization,
    create_test_payout_rule,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.campaign import CampaignStatus, CreativeStatus, CreativeType
from app.models.campaign_assignment import CampaignActivationEvent, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverOnboardingStatus
from app.models.impression import ImpressionEstimate
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryStatus, PayoutCalculation
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus, VehicleType
from app.services.campaign_assignments import activation_snapshot_digest
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


def create_report_fixture(
    db_sessionmaker,
    *,
    identity_tag: str = "measurement",
    identity_domain: str = "example.com",
    organization_name: str = "Acme Ads",
    billing_email: str = "billing@acme.test",
    campaign_name: str = "Launch Campaign",
    service_city: str = "Lagos",
    advertiser_first: bool = False,
):
    actors = {}
    actor_roles = (
        (UserRole.ADVERTISER, UserRole.ADMIN)
        if advertiser_first
        else (UserRole.ADMIN, UserRole.ADVERTISER)
    )
    for role in actor_roles:
        actors[role] = create_test_user(
            db_sessionmaker,
            email=f"{identity_tag}-{role.value}@{identity_domain}",
            password=PASSWORD,
            role=role,
        )
    admin = actors[UserRole.ADMIN]
    advertiser = actors[UserRole.ADVERTISER]
    organization, _ = create_test_organization(
        db_sessionmaker,
        name=organization_name,
        billing_email=billing_email,
        owner_user_id=advertiser.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=DAY_1 - timedelta(days=1),
        end_at=DAY_1 + timedelta(days=10),
        name=campaign_name,
    )
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
        creative_type=CreativeType.PDF,
        mime_type="application/pdf",
    )
    *_, assignment, _trip, _analytics, _estimate = create_report_graph(
        db_sessionmaker,
        admin=admin,
        advertiser=advertiser,
        campaign=campaign,
        driver_email=f"{identity_tag}-driver@{identity_domain}",
        plate_number="MEASURE-1",
        started_at=DAY_1,
        service_city=service_city,
        driver_phone=None if identity_domain.endswith(".invalid") else "+234555000",
    )
    proof = create_test_installation_evidence(
        db_sessionmaker,
        assignment_id=assignment.id,
        reviewed_by_user_id=admin.id,
    )

    async def bind_proof() -> None:
        async with db_sessionmaker() as session:
            event = await session.scalar(
                select(CampaignActivationEvent).where(
                    CampaignActivationEvent.assignment_id == assignment.id
                )
            )
            assert event is not None
            evidence = await session.get(InstallationEvidenceSubmission, proof.id)
            assert evidence is not None
            evidence.reviewed_at = event.occurred_at - timedelta(minutes=1)
            evidence.approved_until = event.occurred_at + timedelta(days=1)
            snapshot = dict(event.event_metadata["activation_snapshot"])
            snapshot["creative_id"] = str(creative.id)
            snapshot["installation_evidence_submission_id"] = str(proof.id)
            snapshot["installation_evidence_revision"] = evidence.revision
            event.event_metadata = {
                **event.event_metadata,
                "activation_snapshot": snapshot,
                "activation_snapshot_sha256": activation_snapshot_digest(snapshot),
            }
            await session.commit()

    asyncio.run(bind_proof())
    return admin, advertiser, campaign
