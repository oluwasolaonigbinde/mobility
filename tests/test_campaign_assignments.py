import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_campaign_payout_revision,
    create_test_campaign_zone,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_activation_events,
    fetch_audit_events,
    fetch_user_by_email,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

import app.services.campaign_assignments as assignments_service
from app.api.v1 import campaign_assignments as assignments_api
from app.core.errors import AppError
from app.models.billing import CampaignLiabilityReservation
from app.models.campaign import Campaign, CampaignCreative, CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import AssignmentRuleBinding
from app.models.trip import TripSessionStatus
from app.models.user import UserRole, UserStatus
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.campaign_assignments import (
    CampaignAssignmentCancel,
    CampaignAssignmentCreate,
    CampaignAssignmentTransition,
)

PASSWORD = "long-secure-password"
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def create_assignment_ready_graph(
    db_sessionmaker,
    *,
    campaign_status: CampaignStatus = CampaignStatus.SCHEDULED,
    driver_status: DriverOnboardingStatus = DriverOnboardingStatus.ACTIVE,
    vehicle_status: VehicleStatus = VehicleStatus.ACTIVE,
    start_at=PAST,
    end_at=FUTURE,
    admin_email: str = "admin@example.com",
    advertiser_email: str = "advertiser@example.com",
    driver_email: str = "driver@example.com",
    plate_number: str = "ABC-123",
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
        campaign_status=campaign_status,
        start_at=start_at,
        end_at=end_at,
    )
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.READY,
    )
    create_test_campaign_payout_revision(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        effective_from=PAST,
    )
    create_test_campaign_zone(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    campaign.campaign_metadata["_test_creative_id"] = str(creative.id)
    driver = create_test_user(
        db_sessionmaker,
        email=driver_email,
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=driver.id,
        onboarding_status=driver_status,
    )
    vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number=plate_number,
        vehicle_status=vehicle_status,
    )
    return admin, campaign, driver, profile, vehicle


def assignment_payload(campaign: Campaign, profile: DriverProfile, vehicle: Vehicle, **overrides):
    payload = {
        "campaign_id": str(campaign.id),
        "driver_profile_id": str(profile.id),
        "vehicle_id": str(vehicle.id),
        "creative_id": campaign.campaign_metadata["_test_creative_id"],
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "notes": " Driver accepted wrap kit ",
        "metadata": {"source": "ops"},
    }
    payload.update(overrides)
    return payload


def admin_headers(db_client):
    return auth_headers(db_client, "admin@example.com", PASSWORD)


def driver_headers(db_client, email: str = "driver@example.com"):
    return auth_headers(db_client, email, PASSWORD)


def post_assignment(db_client, campaign, profile, vehicle):
    return db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle),
    )


def create_postgres_offer(sessionmaker, settings, admin, campaign, profile, vehicle):
    async def create():
        async with sessionmaker() as session:
            assignment = await assignments_service.create_campaign_assignment(
                session,
                admin_user_id=admin.id,
                payload=CampaignAssignmentCreate(
                    campaign_id=campaign.id,
                    driver_profile_id=profile.id,
                    vehicle_id=vehicle.id,
                    creative_id=UUID(campaign.campaign_metadata["_test_creative_id"]),
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                ),
                settings=settings,
            )
            await session.commit()
            return assignment.id

    return asyncio.run(create())


def set_offer_due(sessionmaker, assignment_id) -> None:
    async def update_expiry() -> None:
        async with sessionmaker() as session:
            await session.execute(
                update(CampaignAssignment)
                .where(CampaignAssignment.id == assignment_id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()

    asyncio.run(update_expiry())


def update_campaign_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    campaign_id,
    status: CampaignStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, campaign_id)
            campaign.status = status
            await session.commit()

    asyncio.run(update())


def update_driver_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    profile_id,
    status: DriverOnboardingStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            profile = await session.get(DriverProfile, profile_id)
            profile.onboarding_status = status
            await session.commit()

    asyncio.run(update())


def update_vehicle_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    vehicle_id,
    status: VehicleStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            vehicle = await session.get(Vehicle, vehicle_id)
            vehicle.status = status
            await session.commit()

    asyncio.run(update())


def update_creative_status(db_sessionmaker, creative_id, creative_status: CreativeStatus) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            creative = await session.get(CampaignCreative, creative_id)
            creative.status = creative_status
            await session.commit()

    asyncio.run(update())


def delete_assignment_binding(db_sessionmaker, assignment_id) -> None:
    async def delete_binding() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                delete(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == assignment_id
                )
            )
            await session.commit()

    asyncio.run(delete_binding())


def update_driver_city(db_sessionmaker, profile_id, service_city: str) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            profile = await session.get(DriverProfile, profile_id)
            profile.service_city = service_city
            await session.commit()

    asyncio.run(update())


def update_vehicle_type(db_sessionmaker, vehicle_id, vehicle_type: VehicleType) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            vehicle = await session.get(Vehicle, vehicle_id)
            vehicle.vehicle_type = vehicle_type
            await session.commit()

    asyncio.run(update())


def fetch_assignments(db_sessionmaker) -> list[CampaignAssignment]:
    async def fetch() -> list[CampaignAssignment]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(CampaignAssignment))
            return list(result.scalars().all())

    return asyncio.run(fetch())


@pytest.mark.parametrize("actor_kind", ["driver", "advertiser", "disabled_admin", "unknown"])
def test_direct_assignment_services_require_active_admin_before_mutation(
    db_sessionmaker,
    settings,
    actor_kind,
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        admin_email=f"authority-admin-{actor_kind}@example.com",
        advertiser_email=f"authority-advertiser-{actor_kind}@example.com",
        driver_email=f"authority-driver-{actor_kind}@example.com",
        plate_number=f"AUTH-{actor_kind[:3].upper()}-1",
    )
    disabled_admin = create_test_user(
        db_sessionmaker,
        email=f"authority-disabled-{actor_kind}@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
        user_status=UserStatus.DISABLED,
    )
    actor_id = {
        "driver": driver.id,
        "advertiser": fetch_user_by_email(
            db_sessionmaker, f"authority-advertiser-{actor_kind}@example.com"
        ).id,
        "disabled_admin": disabled_admin.id,
        "unknown": UUID(int=0),
    }[actor_kind]

    before = (
        len(fetch_assignments(db_sessionmaker)),
        len(fetch_activation_events(db_sessionmaker)),
        len(fetch_audit_events(db_sessionmaker)),
    )

    async def attempt_create() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await assignments_service.create_campaign_assignment(
                    session,
                    admin_user_id=actor_id,
                    payload=CampaignAssignmentCreate(
                        campaign_id=campaign.id,
                        driver_profile_id=profile.id,
                        vehicle_id=vehicle.id,
                        creative_id=UUID(campaign.campaign_metadata["_test_creative_id"]),
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                    ),
                    settings=settings,
                )
            assert exc_info.value.code == "ADMIN_REQUIRED"
            await session.rollback()

    asyncio.run(attempt_create())
    assert (
        len(fetch_assignments(db_sessionmaker)),
        len(fetch_activation_events(db_sessionmaker)),
        len(fetch_audit_events(db_sessionmaker)),
    ) == before

    async def create_valid() -> UUID:
        async with db_sessionmaker() as session:
            assignment = await assignments_service.create_campaign_assignment(
                session,
                admin_user_id=admin.id,
                payload=CampaignAssignmentCreate(
                    campaign_id=campaign.id,
                    driver_profile_id=profile.id,
                    vehicle_id=vehicle.id,
                    creative_id=UUID(campaign.campaign_metadata["_test_creative_id"]),
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                ),
                settings=settings,
            )
            await session.commit()
            return assignment.id

    assignment_id = asyncio.run(create_valid())
    baseline = (
        len(fetch_assignments(db_sessionmaker)),
        len(fetch_activation_events(db_sessionmaker)),
        len(fetch_audit_events(db_sessionmaker)),
    )

    async def attempt_cancel() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as exc_info:
                await assignments_service.cancel_admin_assignment(
                    session,
                    admin_user_id=actor_id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentCancel(reason="unauthorized"),
                )
            assert exc_info.value.code == "ADMIN_REQUIRED"
            await session.rollback()

    asyncio.run(attempt_cancel())
    assert (
        len(fetch_assignments(db_sessionmaker)),
        len(fetch_activation_events(db_sessionmaker)),
        len(fetch_audit_events(db_sessionmaker)),
    ) == baseline
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.OFFERED.value


@pytest.mark.parametrize("producer_kind", ["campaign_window", "zone"])
def test_offer_creation_observes_campaign_or_zone_edit_after_pg_lock(
    postgis_db_sessionmaker,
    settings,
    producer_kind,
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email=f"offer-producer-{producer_kind}@example.com",
        advertiser_email=f"offer-producer-advertiser-{producer_kind}@example.com",
        driver_email=f"offer-producer-driver-{producer_kind}@example.com",
        plate_number=f"OP-{producer_kind[:8].upper()}"[:15],
    )
    producer_ready = asyncio.Event()

    async def producer() -> None:
        async with postgis_db_sessionmaker() as session:
            locked_campaign = await session.scalar(
                select(Campaign).where(Campaign.id == campaign.id).with_for_update()
            )
            assert locked_campaign is not None
            if producer_kind == "campaign_window":
                locked_campaign.end_at = FUTURE + timedelta(days=1)
            else:
                zone = await session.scalar(
                    select(CampaignZone)
                    .where(
                        CampaignZone.campaign_id == campaign.id,
                        CampaignZone.zone_type == CampaignZoneType.TARGET.value,
                    )
                    .order_by(CampaignZone.id)
                    .limit(1)
                    .with_for_update()
                )
                assert zone is not None
                zone.name = "Producer-updated target"
            producer_ready.set()
            await asyncio.sleep(0.2)
            await session.commit()

    async def offer():
        await producer_ready.wait()
        async with postgis_db_sessionmaker() as session:
            assignment = await assignments_service.create_campaign_assignment(
                session,
                admin_user_id=admin.id,
                payload=CampaignAssignmentCreate(
                    campaign_id=campaign.id,
                    driver_profile_id=profile.id,
                    vehicle_id=vehicle.id,
                    creative_id=UUID(campaign.campaign_metadata["_test_creative_id"]),
                    expires_at=FUTURE - timedelta(days=1),
                ),
                settings=settings,
            )
            await session.commit()
            return assignment

    async def race():
        return await asyncio.wait_for(asyncio.gather(producer(), offer()), timeout=10)

    _, assignment = asyncio.run(race())
    assert assignment.offer_terms is not None
    if producer_kind == "campaign_window":
        assert assignment.offer_terms["campaign_window_end_at"] == (
            FUTURE + timedelta(days=1)
        ).isoformat()
    else:
        assert assignment.offer_terms["zones"]["target"][0]["name"] == "Producer-updated target"


def test_offer_creation_fails_closed_after_creative_archive_pg_lock(
    postgis_db_sessionmaker,
    settings,
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="offer-creative-admin@example.com",
        advertiser_email="offer-creative-advertiser@example.com",
        driver_email="offer-creative-driver@example.com",
        plate_number="OFC-001",
    )
    creative_id = UUID(campaign.campaign_metadata["_test_creative_id"])
    producer_ready = asyncio.Event()

    async def producer() -> None:
        async with postgis_db_sessionmaker() as session:
            creative = await session.scalar(
                select(CampaignCreative)
                .where(CampaignCreative.id == creative_id)
                .with_for_update()
            )
            assert creative is not None
            creative.status = CreativeStatus.ARCHIVED.value
            producer_ready.set()
            await asyncio.sleep(0.2)
            await session.commit()

    async def offer() -> str:
        await producer_ready.wait()
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.create_campaign_assignment(
                    session,
                    admin_user_id=admin.id,
                    payload=CampaignAssignmentCreate(
                        campaign_id=campaign.id,
                        driver_profile_id=profile.id,
                        vehicle_id=vehicle.id,
                        creative_id=creative_id,
                        expires_at=FUTURE - timedelta(days=1),
                    ),
                    settings=settings,
                )
                await session.commit()
            except AppError as exc:
                await session.rollback()
                return exc.code
        return "offered"

    async def race():
        return await asyncio.wait_for(asyncio.gather(producer(), offer()), timeout=10)

    _, outcome = asyncio.run(race())
    assert outcome == "READY_CAMPAIGN_CREATIVE_REQUIRED"
    assert fetch_assignments(postgis_db_sessionmaker) == []


def fetch_bindings_for_assignment(db_sessionmaker, assignment_id):
    async def fetch():
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(AssignmentRuleBinding).where(
                            AssignmentRuleBinding.assignment_id == assignment_id
                        )
                    )
                ).all()
            )

    return asyncio.run(fetch())


def fetch_reservations_for_assignment(db_sessionmaker, assignment_id):
    async def fetch():
        async with db_sessionmaker() as session:
            return list(
                (
                    await session.scalars(
                        select(CampaignLiabilityReservation).where(
                            CampaignLiabilityReservation.assignment_id == assignment_id
                        )
                    )
                ).all()
            )

    return asyncio.run(fetch())


def test_admin_can_list_ranked_car_recommendations(db_client, db_sessionmaker) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    response = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": " Lagos "},
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    candidate = body["items"][0]
    assert candidate["rank"] == 1
    assert candidate["driver_profile_id"] == str(profile.id)
    assert candidate["driver_name"]
    assert candidate["vehicle_id"] == str(vehicle.id)
    assert candidate["vehicle_plate_number"] == vehicle.plate_number
    assert candidate["service_city"] == "Lagos"
    assert candidate["vehicle_type"] == "car"
    assert candidate["matching_version"] == "matching_v1"
    assert candidate["fingerprint"]
    assert candidate["components"] == {
        "vehicle_load": 0,
        "driver_load": 0,
        "active_tracking_seconds": 0,
        "latest_computed_at": None,
    }


def test_recommendations_rank_current_car_candidates_and_enforce_rbac(
    db_client, db_sessionmaker
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    activity_driver = create_test_user(
        db_sessionmaker,
        email="activity-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    activity_profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=activity_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
        service_city="lagos",
    )
    activity_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=activity_profile.id,
        plate_number="ACT-123",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    inactive_analytics_driver = create_test_user(
        db_sessionmaker,
        email="inactive-analytics-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    inactive_analytics_profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=inactive_analytics_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    inactive_analytics_vehicle = create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=inactive_analytics_profile.id,
        plate_number="INA-123",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    create_test_vehicle(
        db_sessionmaker,
        driver_profile_id=activity_profile.id,
        plate_number="VAN-123",
        vehicle_status=VehicleStatus.ACTIVE,
        vehicle_type=VehicleType.VAN,
    )
    historical_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.SCHEDULED,
        end_at=FUTURE,
    )
    historical_assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=historical_campaign.id,
        driver_profile_id=activity_profile.id,
        vehicle_id=activity_vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.CANCELLED,
        cancelled_at=datetime.now(UTC),
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=historical_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=activity_profile.id,
        vehicle_id=activity_vehicle.id,
        started_by_user_id=activity_driver.id,
    )
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=historical_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=activity_profile.id,
        vehicle_id=activity_vehicle.id,
        active_tracking_seconds=120,
    )
    insufficient_assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=historical_campaign.id,
        driver_profile_id=inactive_analytics_profile.id,
        vehicle_id=inactive_analytics_vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.CANCELLED,
        cancelled_at=datetime.now(UTC),
    )
    insufficient_trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=insufficient_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=inactive_analytics_profile.id,
        vehicle_id=inactive_analytics_vehicle.id,
        started_by_user_id=inactive_analytics_driver.id,
    )
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=insufficient_trip.id,
        assignment_id=insufficient_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=inactive_analytics_profile.id,
        vehicle_id=inactive_analytics_vehicle.id,
        status="insufficient_data",
        active_tracking_seconds=999,
    )
    blocked_trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=insufficient_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=inactive_analytics_profile.id,
        vehicle_id=inactive_analytics_vehicle.id,
        started_by_user_id=inactive_analytics_driver.id,
        trip_status=TripSessionStatus.SEALED,
    )
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=blocked_trip.id,
        assignment_id=insufficient_assignment.id,
        campaign_id=historical_campaign.id,
        driver_profile_id=inactive_analytics_profile.id,
        vehicle_id=inactive_analytics_vehicle.id,
        status="blocked",
        active_tracking_seconds=999,
    )

    response = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos", "limit": 3},
    )
    forbidden = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=driver_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos"},
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["total"] == 3
    assert response.json()["items"][0]["driver_profile_id"] == str(activity_profile.id)
    assert {item["driver_profile_id"] for item in response.json()["items"][1:]} == {
        str(profile.id),
        str(inactive_analytics_profile.id),
    }
    assert response.json()["items"][0]["components"]["active_tracking_seconds"] == 120
    assert response.json()["items"][0]["components"]["latest_computed_at"] is not None
    paginated = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos", "limit": 1, "offset": 2},
    )
    assert paginated.status_code == http_status.HTTP_200_OK
    assert paginated.json()["items"][0]["rank"] == 3
    assert paginated.json()["items"][0]["components"] == {
        "vehicle_load": 0,
        "driver_load": 0,
        "active_tracking_seconds": 0,
        "latest_computed_at": None,
    }
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN


def test_recommendations_exclude_ineligible_and_already_assigned_candidates(
    db_client, db_sessionmaker
) -> None:
    admin, campaign, _, eligible_profile, eligible_vehicle = create_assignment_ready_graph(
        db_sessionmaker
    )

    def add_candidate(
        suffix: str,
        *,
        plate_number: str,
        driver_status: DriverOnboardingStatus = DriverOnboardingStatus.ACTIVE,
        service_city: str = "Lagos",
        vehicle_status: VehicleStatus = VehicleStatus.ACTIVE,
        vehicle_type: VehicleType = VehicleType.CAR,
    ):
        user = create_test_user(
            db_sessionmaker,
            email=f"{suffix}@example.com",
            password=PASSWORD,
            role=UserRole.DRIVER,
        )
        profile = create_test_driver_profile(
            db_sessionmaker,
            user_id=user.id,
            onboarding_status=driver_status,
            service_city=service_city,
        )
        vehicle = create_test_vehicle(
            db_sessionmaker,
            driver_profile_id=profile.id,
            plate_number=plate_number,
            vehicle_status=vehicle_status,
            vehicle_type=vehicle_type,
        )
        return profile, vehicle

    add_candidate(
        "inactive-driver",
        plate_number="IDR-123",
        driver_status=DriverOnboardingStatus.SUSPENDED,
    )
    add_candidate(
        "inactive-vehicle", plate_number="IVE-123", vehicle_status=VehicleStatus.INACTIVE
    )
    add_candidate("wrong-city", plate_number="WCT-123", service_city="Abuja")
    add_candidate("non-car", plate_number="NCR-123", vehicle_type=VehicleType.VAN)
    assigned_profile, assigned_vehicle = add_candidate(
        "already-assigned", plate_number="AAS-123"
    )
    create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=assigned_profile.id,
        vehicle_id=assigned_vehicle.id,
        assigned_by_user_id=admin.id,
    )

    response = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos"},
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["driver_profile_id"] == str(eligible_profile.id)
    assert response.json()["items"][0]["vehicle_id"] == str(eligible_vehicle.id)


@pytest.mark.parametrize(
    "changed_fact",
    ["driver_status", "service_city", "vehicle_status", "vehicle_type", "activity"],
)
def test_assignment_rejects_each_stale_recommendation_fact(
    db_client, db_sessionmaker, changed_fact
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    listed = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos"},
    )
    context = {
        key: listed.json()["items"][0][key]
        for key in ("service_city", "vehicle_type", "matching_version", "fingerprint")
    }

    if changed_fact == "driver_status":
        update_driver_status(db_sessionmaker, profile.id, DriverOnboardingStatus.SUSPENDED)
    elif changed_fact == "service_city":
        update_driver_city(db_sessionmaker, profile.id, "Abuja")
    elif changed_fact == "vehicle_status":
        update_vehicle_status(db_sessionmaker, vehicle.id, VehicleStatus.INACTIVE)
    elif changed_fact == "vehicle_type":
        update_vehicle_type(db_sessionmaker, vehicle.id, VehicleType.VAN)
    else:
        history = create_test_campaign(
            db_sessionmaker,
            organization_id=campaign.organization_id,
            created_by_user_id=admin.id,
            campaign_status=CampaignStatus.SCHEDULED,
            end_at=FUTURE,
        )
        assignment = create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=history.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
            assignment_status=CampaignAssignmentStatus.CANCELLED,
            cancelled_at=datetime.now(UTC),
        )
        trip = create_test_trip_session(
            db_sessionmaker,
            assignment_id=assignment.id,
            campaign_id=history.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            started_by_user_id=driver.id,
        )
        create_test_trip_analytics(
            db_sessionmaker,
            trip_session_id=trip.id,
            assignment_id=assignment.id,
            campaign_id=history.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            active_tracking_seconds=1,
        )

    response = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle, recommendation_context=context),
    )

    assert listed.status_code == http_status.HTTP_200_OK
    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "STALE_RECOMMENDATION"


def test_assignment_rejects_stale_recommendation_but_manual_payload_stays_compatible(
    db_client, db_sessionmaker
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    listed = db_client.get(
        "/api/v1/admin/campaign-assignments/recommendations",
        headers=admin_headers(db_client),
        params={"campaign_id": str(campaign.id), "service_city": "Lagos"},
    )
    context = {
        key: listed.json()["items"][0][key]
        for key in ("service_city", "vehicle_type", "matching_version", "fingerprint")
    }
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.SCHEDULED,
        end_at=FUTURE,
    )
    create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=other_campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )

    stale = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle, recommendation_context=context),
    )
    manual = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle),
    )

    assert listed.status_code == http_status.HTTP_200_OK
    assert stale.status_code == http_status.HTTP_409_CONFLICT
    assert stale.json()["error"]["code"] == "STALE_RECOMMENDATION"
    assert manual.status_code == http_status.HTTP_201_CREATED


def test_admin_can_create_list_read_and_cancel_assignment_with_events_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)

    create_response = post_assignment(db_client, campaign, profile, vehicle)
    assignment_id = create_response.json()["id"]
    list_response = db_client.get(
        "/api/v1/admin/campaign-assignments?status=offered&limit=1&offset=0",
        headers=admin_headers(db_client),
    )
    read_response = db_client.get(
        f"/api/v1/admin/campaign-assignments/{assignment_id}",
        headers=admin_headers(db_client),
    )
    accept_response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver_headers(db_client),
        json={"metadata": {"accepted": True}},
    )
    cancel_response = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
        headers=admin_headers(db_client),
        json={"reason": " reassigned ", "metadata": {"ticket": "OPS-7"}},
    )
    cancel_again = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    assert create_response.status_code == http_status.HTTP_201_CREATED
    created = create_response.json()
    assert created["status"] == "offered"
    assert created["notes"] == "Driver accepted wrap kit"
    assert created["metadata"] == {"source": "ops"}
    assert created["expires_at"] is not None
    assert len(created["offer_terms_sha256"]) == 64
    assert created["offer_terms"]["offer_terms_version"] == "campaign-assignment-offer-v1"
    assert created["offer_terms"]["payout"]["formula_version"] == "payout_v3"
    assert created["offer_terms"]["zones"]["target"]
    assert created["offer_terms"]["zones"]["premium"]
    assert created["offer_terms"]["creative"]["id"] == campaign.campaign_metadata[
        "_test_creative_id"
    ]
    assert created["campaign"]["id"] == str(campaign.id)
    assert created["driver_profile"]["id"] == str(profile.id)
    assert created["vehicle"]["id"] == str(vehicle.id)
    assert "password_hash" not in create_response.text
    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == assignment_id
    assert read_response.status_code == http_status.HTTP_200_OK
    assert [event["event_type"] for event in read_response.json()["events"]] == ["assigned"]
    assert accept_response.status_code == http_status.HTTP_200_OK
    assert accept_response.json()["status"] == "accepted"
    assert cancel_response.status_code == http_status.HTTP_200_OK
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["cancelled_at"] is not None
    assert [event["event_type"] for event in cancel_response.json()["events"]] == [
        "assigned",
        "accepted",
        "cancelled",
    ]
    assert cancel_again.status_code == http_status.HTTP_400_BAD_REQUEST
    assert cancel_again.json()["error"]["code"] == "INVALID_ASSIGNMENT_TRANSITION"

    activation_events = fetch_activation_events(db_sessionmaker)
    assert [event.event_type for event in activation_events] == [
        "assigned",
        "accepted",
        "cancelled",
    ]
    assert activation_events[-1].event_metadata == {"ticket": "OPS-7", "reason": "reassigned"}
    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == [
        "admin.campaign_assignment.created",
        "admin.campaign_assignment.cancelled",
    ]


def test_admin_assignment_creation_validates_eligibility_and_duplicates(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    post_assignment(db_client, campaign, profile, vehicle)

    missing_offer_inputs = assignment_payload(campaign, profile, vehicle)
    del missing_offer_inputs["creative_id"]
    del missing_offer_inputs["expires_at"]
    missing_offer_response = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=missing_offer_inputs,
    )

    duplicate = post_assignment(db_client, campaign, profile, vehicle)
    invalid_metadata = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle, metadata=["bad"]),
    )
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{fetch_assignments(db_sessionmaker)[0].id}/accept",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )
    db_client.post(
        f"/api/v1/admin/campaign-assignments/{fetch_assignments(db_sessionmaker)[0].id}/cancel",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    allowed_after_cancel = post_assignment(db_client, campaign, profile, vehicle)

    assert duplicate.status_code == http_status.HTTP_409_CONFLICT
    assert duplicate.json()["error"]["code"] == "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT"
    assert missing_offer_response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_metadata.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert accepted.status_code == http_status.HTTP_200_OK
    assert allowed_after_cancel.status_code == http_status.HTTP_201_CREATED

    for rejected_status in [
        CampaignStatus.DRAFT,
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
    ]:
        _, rejected_campaign, _, rejected_profile, rejected_vehicle = create_assignment_ready_graph(
            db_sessionmaker,
            campaign_status=rejected_status,
            admin_email=f"admin-{rejected_status}@example.com",
            advertiser_email=f"advertiser-{rejected_status}@example.com",
            driver_email=f"{rejected_status}@example.com",
            plate_number=f"{rejected_status}-123",
        )
        response = db_client.post(
            "/api/v1/admin/campaign-assignments",
            headers=admin_headers(db_client),
            json=assignment_payload(rejected_campaign, rejected_profile, rejected_vehicle),
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "CAMPAIGN_NOT_ASSIGNABLE"

    _, expired_campaign, _, expired_profile, expired_vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        start_at=PAST - timedelta(days=1),
        end_at=PAST,
        admin_email="admin-expired@example.com",
        advertiser_email="advertiser-expired@example.com",
        driver_email="expired-driver@example.com",
        plate_number="EXP-123",
    )
    expired = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(expired_campaign, expired_profile, expired_vehicle),
    )
    inactive_driver_graph = create_assignment_ready_graph(
        db_sessionmaker,
        driver_status=DriverOnboardingStatus.PENDING,
        admin_email="admin-pending-driver@example.com",
        advertiser_email="advertiser-pending-driver@example.com",
        driver_email="pending-driver@example.com",
        plate_number="PND-123",
    )
    inactive_driver = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(
            inactive_driver_graph[1],
            inactive_driver_graph[3],
            inactive_driver_graph[4],
        ),
    )
    inactive_vehicle_graph = create_assignment_ready_graph(
        db_sessionmaker,
        vehicle_status=VehicleStatus.PENDING,
        admin_email="admin-pending-vehicle@example.com",
        advertiser_email="advertiser-pending-vehicle@example.com",
        driver_email="pending-vehicle-driver@example.com",
        plate_number="VEH-123",
    )
    inactive_vehicle = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(
            inactive_vehicle_graph[1],
            inactive_vehicle_graph[3],
            inactive_vehicle_graph[4],
        ),
    )
    other_driver = create_test_user(
        db_sessionmaker,
        email="other-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    other_profile = create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    mismatch = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, other_profile, vehicle),
    )

    assert expired.status_code == http_status.HTTP_400_BAD_REQUEST
    assert expired.json()["error"]["code"] == "CAMPAIGN_EXPIRED"
    assert inactive_driver.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_driver.json()["error"]["code"] == "DRIVER_PROFILE_NOT_ACTIVE"
    assert inactive_vehicle.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_vehicle.json()["error"]["code"] == "VEHICLE_NOT_ACTIVE"
    assert mismatch.status_code == http_status.HTTP_400_BAD_REQUEST
    assert mismatch.json()["error"]["code"] == "VEHICLE_DRIVER_PROFILE_MISMATCH"


def test_assignment_endpoints_enforce_rbac_and_driver_ownership(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    other_driver = create_test_user(
        db_sessionmaker,
        email="other@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    create_test_user(
        db_sessionmaker,
        email="no-profile@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_user(
        db_sessionmaker,
        email="plain-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]

    own_list = db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=driver_headers(db_client),
    )
    own_read = db_client.get(
        f"/api/v1/driver/campaign-assignments/{assignment_id}",
        headers=driver_headers(db_client),
    )
    other_read = db_client.get(
        f"/api/v1/driver/campaign-assignments/{assignment_id}",
        headers=driver_headers(db_client, "other@example.com"),
    )
    no_profile = db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=driver_headers(db_client, "no-profile@example.com"),
    )
    advertiser_driver_endpoint = db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=auth_headers(db_client, "plain-advertiser@example.com", PASSWORD),
    )
    admin_driver_endpoint = db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=admin_headers(db_client),
    )
    driver_admin_endpoint = db_client.get(
        "/api/v1/admin/campaign-assignments",
        headers=driver_headers(db_client),
    )
    advertiser_admin_endpoint = db_client.get(
        "/api/v1/admin/campaign-assignments",
        headers=auth_headers(db_client, "plain-advertiser@example.com", PASSWORD),
    )
    unauthenticated_admin = db_client.get("/api/v1/admin/campaign-assignments")
    unauthenticated_driver = db_client.get("/api/v1/driver/campaign-assignments")

    assert own_list.status_code == http_status.HTTP_200_OK
    assert own_list.json()["total"] == 1
    assert own_read.status_code == http_status.HTTP_200_OK
    assert other_read.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_read.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
    assert no_profile.status_code == http_status.HTTP_404_NOT_FOUND
    assert no_profile.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"
    assert advertiser_driver_endpoint.status_code == http_status.HTTP_403_FORBIDDEN
    assert admin_driver_endpoint.status_code == http_status.HTTP_403_FORBIDDEN
    assert driver_admin_endpoint.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_admin_endpoint.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated_admin.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert unauthenticated_driver.status_code == http_status.HTTP_401_UNAUTHORIZED


def test_driver_decides_offer_and_admin_activation_is_fail_closed(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    driver = driver_headers(db_client)

    accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver,
        json={"metadata": {"accepted": True}},
    )
    accept_again = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver,
        json={"metadata": {}},
    )
    stale_driver_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/activate",
        headers=driver,
        json={"metadata": {}},
    )
    admin_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    assert accept.status_code == http_status.HTTP_200_OK
    assert accept.json()["status"] == "accepted"
    assert accept_again.status_code == http_status.HTTP_200_OK
    assert accept_again.json()["status"] == "accepted"
    assert stale_driver_activate.status_code == http_status.HTTP_404_NOT_FOUND
    assert admin_activate.status_code == http_status.HTTP_409_CONFLICT
    assert admin_activate.json()["error"]["code"] == "CAMPAIGN_REVIEW_APPROVAL_REQUIRED"
    assert [event.event_type for event in fetch_activation_events(db_sessionmaker)] == [
        "assigned",
        "accepted",
    ]


def test_driver_decline_is_idempotent_and_opposite_accept_conflicts(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    headers = driver_headers(db_client)

    decline = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/decline",
        headers=headers,
        json={"metadata": {"reason": "not available"}},
    )
    decline_again = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/decline",
        headers=headers,
        json={"metadata": {}},
    )
    accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=headers,
        json={"metadata": {}},
    )

    assert decline.status_code == http_status.HTTP_200_OK
    assert decline.json()["status"] == "declined"
    assert decline.json()["declined_at"] is not None
    assert decline_again.status_code == http_status.HTTP_200_OK
    assert accept.status_code == http_status.HTTP_409_CONFLICT
    assert accept.json()["error"]["code"] == "ASSIGNMENT_DECISION_CONFLICT"
    events = fetch_activation_events(db_sessionmaker)
    assert [event.event_type for event in events] == ["assigned", "declined"]


def test_offer_expiry_materializes_before_post_expiry_decision(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]

    async def expire() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, UUID(assignment_id))
            assignment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    expired_read = db_client.get(
        f"/api/v1/driver/campaign-assignments/{assignment_id}",
        headers=driver_headers(db_client),
    )
    accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )

    assert expired_read.status_code == http_status.HTTP_200_OK
    assert expired_read.json()["status"] == "expired"
    assert expired_read.json()["expired_at"] is not None
    assert [event["event_type"] for event in expired_read.json()["events"]] == [
        "assigned",
        "expired",
    ]
    assert accept.status_code == http_status.HTTP_409_CONFLICT
    assert accept.json()["error"]["code"] == "ASSIGNMENT_DECISION_CONFLICT"
    assert len(fetch_activation_events(db_sessionmaker)) == 2


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_driver_decision_clock_crossing_commits_new_expiry_before_conflict(
    db_client,
    db_sessionmaker,
    monkeypatch,
    action,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    set_offer_due(db_sessionmaker, UUID(assignment_id))

    async def preflight_before_boundary(_session, _assignment_id):
        return False

    monkeypatch.setattr(assignments_api, "expire_assignment_offer", preflight_before_boundary)
    response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/{action}",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "OFFER_EXPIRED"
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.EXPIRED.value
    assert [event.event_type for event in fetch_activation_events(db_sessionmaker)] == [
        "assigned",
        "expired",
    ]


def test_due_offer_expiry_precedes_campaign_expiry_validation(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    set_offer_due(db_sessionmaker, UUID(assignment_id))

    async def cross_campaign_and_offer_boundaries() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(Campaign, campaign.id)
            stored.end_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    async def preflight_before_boundary(_session, _assignment_id):
        return False

    asyncio.run(cross_campaign_and_offer_boundaries())
    monkeypatch.setattr(assignments_api, "expire_assignment_offer", preflight_before_boundary)
    response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "OFFER_EXPIRED"
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.EXPIRED.value


def test_admin_cancel_due_offer_commits_expiry_before_conflict(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    set_offer_due(db_sessionmaker, UUID(assignment_id))

    response = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
        headers=admin_headers(db_client),
        json={"reason": "operator correction"},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "OFFER_EXPIRED"
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.EXPIRED.value
    assert [event.event_type for event in fetch_activation_events(db_sessionmaker)] == [
        "assigned",
        "expired",
    ]


def test_direct_cancel_service_materializes_expiry_for_targeted_transaction_commit(
    db_client,
    db_sessionmaker,
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = UUID(post_assignment(db_client, campaign, profile, vehicle).json()["id"])
    set_offer_due(db_sessionmaker, assignment_id)

    async def cancel() -> str:
        async with db_sessionmaker() as session:
            try:
                await assignments_service.cancel_admin_assignment(
                    session,
                    admin_user_id=admin.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentCancel(reason="operator correction"),
                )
            except assignments_service.OfferExpiredError as exc:
                await session.commit()
                return exc.code
        raise AssertionError("due cancel must return an expiry conflict")

    assert asyncio.run(cancel()) == "OFFER_EXPIRED"
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.EXPIRED.value
    assert [event.event_type for event in fetch_activation_events(db_sessionmaker)] == [
        "assigned",
        "expired",
    ]


def test_driver_list_has_one_route_sweep_and_never_exposes_unmaterialized_due_offer(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    set_offer_due(db_sessionmaker, UUID(assignment_id))
    route_sweeps = 0

    async def bounded_route_sweep(_session):
        nonlocal route_sweeps
        route_sweeps += 1
        # Models the requested row being beyond the global sweep's first page.
        return 100

    async def forbidden_service_sweep(*_args, **_kwargs):
        raise AssertionError("list service must remain a pure read")

    monkeypatch.setattr(assignments_api, "expire_due_assignment_offers", bounded_route_sweep)
    monkeypatch.setattr(
        assignments_service,
        "expire_due_assignment_offers",
        forbidden_service_sweep,
    )
    response = db_client.get(
        "/api/v1/driver/campaign-assignments?status=offered",
        headers=driver_headers(db_client),
    )

    assert response.status_code == http_status.HTTP_200_OK
    assert route_sweeps == 1
    assert assignment_id not in {item["id"] for item in response.json()["items"]}


def test_driver_list_service_is_a_pure_db_time_read(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    _, campaign, driver, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = UUID(post_assignment(db_client, campaign, profile, vehicle).json()["id"])
    set_offer_due(db_sessionmaker, assignment_id)

    async def forbidden_sweep(*_args, **_kwargs):
        raise AssertionError("pure list service cannot materialize expiry")

    monkeypatch.setattr(assignments_service, "expire_due_assignment_offers", forbidden_sweep)

    async def read_ids():
        async with db_sessionmaker() as session:
            assignments, total = await assignments_service.list_driver_assignments(
                session,
                user_id=driver.id,
                limit=50,
                offset=0,
                assignment_status=CampaignAssignmentStatus.OFFERED.value,
            )
            return [assignment.id for assignment in assignments], total

    assignment_ids, total = asyncio.run(read_ids())
    assert assignment_id not in assignment_ids
    assert total == 0
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.OFFERED.value


def test_generic_post_mutation_conflict_is_not_committed(
    db_client,
    db_sessionmaker,
    monkeypatch,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]

    async def synthetic_conflict(session, **_kwargs):
        assignment = await session.get(CampaignAssignment, UUID(assignment_id))
        assignment.notes = "must roll back"
        await session.flush()
        raise AppError(
            "SYNTHETIC_CONFLICT",
            "This conflict must not commit pending work",
            status_code=http_status.HTTP_409_CONFLICT,
        )

    monkeypatch.setattr(assignments_api, "accept_driver_assignment", synthetic_conflict)
    response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "SYNTHETIC_CONFLICT"
    assert fetch_assignments(db_sessionmaker)[0].notes == "Driver accepted wrap kit"


def test_admin_cannot_cancel_a_complete_offered_assignment(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]

    response = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
        headers=admin_headers(db_client),
        json={"reason": "operator correction"},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "OFFER_DECISION_REQUIRED"
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.OFFERED.value
    assert [event.event_type for event in fetch_activation_events(db_sessionmaker)] == [
        "assigned"
    ]


def test_concurrent_accept_decline_has_one_terminal_decision_postgres(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="race-admin@example.com",
        advertiser_email="race-advertiser@example.com",
        driver_email="race-driver@example.com",
        plate_number="RACE-001",
    )
    assignment_id = create_postgres_offer(
        postgis_db_sessionmaker,
        settings,
        admin,
        campaign,
        profile,
        vehicle,
    )
    original_lock = assignments_service.acquire_campaign_terms_lock
    both_at_lock = asyncio.Event()
    lock_call_count = 0

    async def barrier_lock(session, campaign_id):
        nonlocal lock_call_count
        lock_call_count += 1
        if lock_call_count == 2:
            both_at_lock.set()
        await both_at_lock.wait()
        await original_lock(session, campaign_id)

    monkeypatch.setattr(assignments_service, "acquire_campaign_terms_lock", barrier_lock)

    async def accept() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.accept_driver_assignment(
                    session,
                    user_id=driver.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(),
                    settings=settings,
                )
                await session.commit()
                return "accepted"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def decline() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.decline_driver_assignment(
                    session,
                    user_id=driver.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(),
                )
                await session.commit()
                return "declined"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(accept(), decline()), timeout=10)

    outcomes = asyncio.run(race())

    assert lock_call_count == 2
    assert sorted(outcomes) == ["ASSIGNMENT_DECISION_CONFLICT", "accepted"] or sorted(
        outcomes
    ) == ["ASSIGNMENT_DECISION_CONFLICT", "declined"]
    terminal_events = [
        event
        for event in fetch_activation_events(postgis_db_sessionmaker)
        if event.event_type in {"accepted", "declined", "expired"}
    ]
    assert len(terminal_events) == 1
    assert len(
        fetch_bindings_for_assignment(postgis_db_sessionmaker, assignment_id)
    ) <= 1
    assert len(fetch_reservations_for_assignment(postgis_db_sessionmaker, assignment_id)) <= 1


def test_duplicate_expiry_sweeps_have_one_terminal_event_postgres(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="sweep-admin@example.com",
        advertiser_email="sweep-advertiser@example.com",
        driver_email="sweep-driver@example.com",
        plate_number="SWEEP-001",
    )
    assignment_id = create_postgres_offer(
        postgis_db_sessionmaker,
        settings,
        admin,
        campaign,
        profile,
        vehicle,
    )
    set_offer_due(postgis_db_sessionmaker, assignment_id)
    original_lock = assignments_service.acquire_campaign_terms_lock
    both_at_lock = asyncio.Event()
    lock_call_count = 0

    async def barrier_lock(session, campaign_id):
        nonlocal lock_call_count
        lock_call_count += 1
        if lock_call_count == 2:
            both_at_lock.set()
        await both_at_lock.wait()
        await original_lock(session, campaign_id)

    monkeypatch.setattr(assignments_service, "acquire_campaign_terms_lock", barrier_lock)

    async def sweep() -> int:
        async with postgis_db_sessionmaker() as session:
            expired = await assignments_service.expire_due_assignment_offers(session)
            await session.commit()
            return expired

    async def race():
        return await asyncio.wait_for(asyncio.gather(sweep(), sweep()), timeout=10)

    outcomes = asyncio.run(race())

    assert lock_call_count == 2
    assert sorted(outcomes) == [0, 1]
    terminal_events = [
        event
        for event in fetch_activation_events(postgis_db_sessionmaker)
        if event.event_type in {"accepted", "declined", "expired"}
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0].event_type == "expired"
    assert len(fetch_bindings_for_assignment(postgis_db_sessionmaker, assignment_id)) == 0
    assert len(fetch_reservations_for_assignment(postgis_db_sessionmaker, assignment_id)) == 0


def test_postgres_due_accept_decline_cancel_and_sweep_converge_to_one_expiry(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="expiry-race-admin@example.com",
        advertiser_email="expiry-race-advertiser@example.com",
        driver_email="expiry-race-driver@example.com",
        plate_number="EXP-RACE-1",
    )
    assignment_id = create_postgres_offer(
        postgis_db_sessionmaker,
        settings,
        admin,
        campaign,
        profile,
        vehicle,
    )
    crossing_time = datetime.now(UTC) + timedelta(days=2)
    original_lock = assignments_service.acquire_campaign_terms_lock
    all_at_lock = asyncio.Event()
    lock_call_count = 0

    async def preflight_before_boundary(_session, _assignment_id):
        return False

    async def future_clock(_session):
        return crossing_time

    async def barrier_lock(session, campaign_id):
        nonlocal lock_call_count
        lock_call_count += 1
        if lock_call_count == 4:
            all_at_lock.set()
        await all_at_lock.wait()
        await original_lock(session, campaign_id)

    monkeypatch.setattr(assignments_api, "expire_assignment_offer", preflight_before_boundary)
    monkeypatch.setattr(assignments_service, "database_clock", future_clock)
    monkeypatch.setattr(assignments_service, "acquire_campaign_terms_lock", barrier_lock)

    async def accept() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_api.driver_accept_campaign_assignment(
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(),
                    current_user=driver,
                    session=session,
                    settings=settings,
                )
                return "accepted"
            except AppError as exc:
                return exc.code

    async def decline() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_api.driver_decline_campaign_assignment(
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(),
                    current_user=driver,
                    session=session,
                )
                return "declined"
            except AppError as exc:
                return exc.code

    async def cancel() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_api.admin_cancel_campaign_assignment(
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentCancel(reason="operator correction"),
                    current_user=admin,
                    session=session,
                )
                return "cancelled"
            except AppError as exc:
                return exc.code

    async def sweep() -> str:
        async with postgis_db_sessionmaker() as session:
            count = await assignments_service.expire_due_assignment_offers(session)
            await session.commit()
            return f"sweep:{count}"

    async def race():
        return await asyncio.wait_for(
            asyncio.gather(accept(), decline(), cancel(), sweep()),
            timeout=10,
        )

    outcomes = asyncio.run(race())

    assert lock_call_count == 4
    assert "OFFER_EXPIRED" in outcomes or "sweep:1" in outcomes
    terminal_events = [
        event
        for event in fetch_activation_events(postgis_db_sessionmaker)
        if event.event_type in {"accepted", "declined", "expired"}
    ]
    assert [event.event_type for event in terminal_events] == ["expired"]
    assert len(fetch_bindings_for_assignment(postgis_db_sessionmaker, assignment_id)) == 0
    assert len(fetch_reservations_for_assignment(postgis_db_sessionmaker, assignment_id)) == 0


def test_postgres_list_uses_wall_clock_after_transaction_start(
    postgis_db_sessionmaker,
    settings,
) -> None:
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="list-clock-admin@example.com",
        advertiser_email="list-clock-advertiser@example.com",
        driver_email="list-clock-driver@example.com",
        plate_number="LIST-CLOCK-1",
    )
    assignment_id = create_postgres_offer(
        postgis_db_sessionmaker,
        settings,
        admin,
        campaign,
        profile,
        vehicle,
    )

    async def cross_boundary() -> tuple[list[UUID], datetime, datetime]:
        async with postgis_db_sessionmaker() as setup_session:
            expires_at = await setup_session.scalar(
                select(func.clock_timestamp() + timedelta(seconds=1))
            )
            await setup_session.execute(
                update(CampaignAssignment)
                .where(CampaignAssignment.id == assignment_id)
                .values(expires_at=expires_at)
            )
            await setup_session.commit()

        async with postgis_db_sessionmaker() as session:
            transaction_started_at = await session.scalar(select(func.now()))
            assert transaction_started_at < expires_at
            await asyncio.sleep(1.1)
            assignments, _ = await assignments_service.list_driver_assignments(
                session,
                user_id=driver.id,
                limit=50,
                offset=0,
                assignment_status=CampaignAssignmentStatus.OFFERED.value,
            )
            statement_wall_clock = await assignments_service.database_clock(session)
            return [assignment.id for assignment in assignments], expires_at, statement_wall_clock

    assignment_ids, expires_at, statement_wall_clock = asyncio.run(cross_boundary())
    assert statement_wall_clock > expires_at
    assert assignment_id not in assignment_ids


def test_admin_activation_checks_campaign_and_driver_gates(
    db_client,
    db_sessionmaker,
) -> None:
    _, scheduled_campaign, _, scheduled_profile, scheduled_vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.SCHEDULED,
        start_at=PAST,
        end_at=FUTURE,
    )
    scheduled_assignment_id = post_assignment(
        db_client,
        scheduled_campaign,
        scheduled_profile,
        scheduled_vehicle,
    ).json()["id"]
    headers = driver_headers(db_client)

    offered_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    db_client.post(
        f"/api/v1/driver/campaign-assignments/{scheduled_assignment_id}/accept",
        headers=headers,
        json={"metadata": {}},
    )
    scheduled_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    update_campaign_status(db_sessionmaker, scheduled_campaign.id, CampaignStatus.PAUSED)
    paused_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    _, future_campaign, _, future_profile, future_vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=FUTURE,
        end_at=FUTURE + timedelta(days=1),
        admin_email="admin-future@example.com",
        advertiser_email="advertiser-future@example.com",
        driver_email="future-driver@example.com",
        plate_number="FUT-123",
    )
    future_assignment_id = post_assignment(
        db_client,
        future_campaign,
        future_profile,
        future_vehicle,
    ).json()["id"]
    future_headers = driver_headers(db_client, "future-driver@example.com")
    db_client.post(
        f"/api/v1/driver/campaign-assignments/{future_assignment_id}/accept",
        headers=future_headers,
        json={"metadata": {}},
    )
    future_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{future_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    _, active_campaign, _, active_profile, active_vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email="admin-eligibility@example.com",
        advertiser_email="advertiser-eligibility@example.com",
        driver_email="eligibility-driver@example.com",
        plate_number="ELG-123",
    )
    active_assignment_id = post_assignment(
        db_client,
        active_campaign,
        active_profile,
        active_vehicle,
    ).json()["id"]
    eligibility_headers = driver_headers(db_client, "eligibility-driver@example.com")
    db_client.post(
        f"/api/v1/driver/campaign-assignments/{active_assignment_id}/accept",
        headers=eligibility_headers,
        json={"metadata": {}},
    )
    update_driver_status(db_sessionmaker, active_profile.id, DriverOnboardingStatus.SUSPENDED)
    inactive_driver_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{active_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    update_driver_status(db_sessionmaker, active_profile.id, DriverOnboardingStatus.ACTIVE)
    update_vehicle_status(db_sessionmaker, active_vehicle.id, VehicleStatus.SUSPENDED)
    inactive_vehicle_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{active_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    assert offered_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert offered_activate.json()["error"]["code"] == "INVALID_ASSIGNMENT_TRANSITION"
    assert scheduled_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert scheduled_activate.json()["error"]["code"] == "CAMPAIGN_NOT_ACTIVE"
    assert paused_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert paused_activate.json()["error"]["code"] == "CAMPAIGN_NOT_ACTIVE"
    assert future_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert future_activate.json()["error"]["code"] == "CAMPAIGN_NOT_STARTED"
    assert inactive_driver_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_driver_activate.json()["error"]["code"] == "DRIVER_PROFILE_NOT_ACTIVE"
    assert inactive_vehicle_activate.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_vehicle_activate.json()["error"]["code"] == "VEHICLE_NOT_ACTIVE"


@pytest.mark.parametrize(
    ("gate", "expected_code"),
    [
        ("creative", "READY_CAMPAIGN_CREATIVE_REQUIRED"),
        ("binding", "FROZEN_PAYOUT_BINDING_REQUIRED"),
        ("funding", "ASSIGNMENT_FUNDING_REQUIRED"),
        ("production", "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED"),
        ("new_work", "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED"),
        ("unavailable", "ACTIVATION_APPROVAL_GATES_UNAVAILABLE"),
    ],
)
def test_admin_activation_rejects_each_built_and_unavailable_gate(
    db_client,
    db_sessionmaker,
    monkeypatch,
    gate,
    expected_code,
) -> None:
    suffix = gate.replace("_", "-")
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        admin_email=f"gate-admin-{suffix}@example.com",
        advertiser_email=f"gate-advertiser-{suffix}@example.com",
        driver_email=f"gate-driver-{suffix}@example.com",
        plate_number=f"GAT-{suffix[:11]}",
    )
    created = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=auth_headers(db_client, f"gate-admin-{suffix}@example.com", PASSWORD),
        json=assignment_payload(campaign, profile, vehicle),
    )
    assert created.status_code == http_status.HTTP_201_CREATED
    assignment_id = created.json()["id"]
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=driver_headers(db_client, f"gate-driver-{suffix}@example.com"),
        json={"metadata": {}},
    )
    assert accepted.status_code == http_status.HTTP_200_OK

    async def review_passes(*args, **kwargs) -> None:
        return None

    async def reserve_pending(*args, **kwargs):
        return SimpleNamespace(status="pending_funding")

    async def reserve_success(*args, **kwargs):
        return SimpleNamespace(status="reserved")

    async def production_fails(*args, **kwargs):
        raise AppError(
            "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED",
            "production gate test",
            status_code=http_status.HTTP_409_CONFLICT,
        )

    async def production_passes(*args, **kwargs):
        return None

    async def new_work_fails(*args, **kwargs):
        raise AppError(
            "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED",
            "new-work gate test",
            status_code=http_status.HTTP_409_CONFLICT,
        )

    monkeypatch.setattr(assignments_service, "ensure_campaign_review_approved", review_passes)
    if gate == "creative":
        update_creative_status(
            db_sessionmaker,
            UUID(campaign.campaign_metadata["_test_creative_id"]),
            CreativeStatus.ARCHIVED,
        )
    elif gate == "binding":
        delete_assignment_binding(db_sessionmaker, UUID(assignment_id))
    elif gate == "funding":
        monkeypatch.setattr(assignments_service, "reserve_assignment_liability", reserve_pending)
    else:
        monkeypatch.setattr(assignments_service, "reserve_assignment_liability", reserve_success)
        if gate == "production":
            monkeypatch.setattr(
                assignments_service,
                "assert_campaign_production_authorized",
                production_fails,
            )
        elif gate == "new_work":
            monkeypatch.setattr(
                assignments_service,
                "assert_campaign_production_authorized",
                production_passes,
            )
            monkeypatch.setattr(assignments_service, "assert_new_work_authorized", new_work_fails)
        else:
            monkeypatch.setattr(
                assignments_service,
                "assert_campaign_production_authorized",
                production_passes,
            )
            monkeypatch.setattr(
                assignments_service,
                "assert_new_work_authorized",
                production_passes,
            )

    response = db_client.post(
        f"/api/v1/admin/campaign-assignments/{assignment_id}/activate",
        headers=auth_headers(db_client, f"gate-admin-{suffix}@example.com", PASSWORD),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == expected_code
    assert fetch_assignments(db_sessionmaker)[0].status == CampaignAssignmentStatus.ACCEPTED.value


def test_accept_rejects_cancelled_completed_and_expired_campaigns(
    db_client,
    db_sessionmaker,
) -> None:
    for campaign_status, expected_code in [
        (CampaignStatus.CANCELLED, "CAMPAIGN_NOT_ACCEPTABLE"),
        (CampaignStatus.COMPLETED, "CAMPAIGN_NOT_ACCEPTABLE"),
    ]:
        admin, campaign, _, profile, vehicle = create_assignment_ready_graph(
            db_sessionmaker,
            campaign_status=CampaignStatus.ACTIVE,
            start_at=None,
            end_at=FUTURE,
            admin_email=f"admin-accept-{campaign_status}@example.com",
            advertiser_email=f"advertiser-accept-{campaign_status}@example.com",
            driver_email=f"accept-{campaign_status}@example.com",
            plate_number=f"ACC-{campaign_status}",
        )
        assignment = create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
        )
        update_campaign_status(db_sessionmaker, campaign.id, campaign_status)
        response = db_client.post(
            f"/api/v1/driver/campaign-assignments/{assignment.id}/accept",
            headers=driver_headers(db_client, f"accept-{campaign_status}@example.com"),
            json={"metadata": {}},
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == expected_code

    expired_admin, expired_campaign, _, expired_profile, expired_vehicle = (
        create_assignment_ready_graph(
            db_sessionmaker,
            campaign_status=CampaignStatus.ACTIVE,
            start_at=None,
            end_at=FUTURE,
            admin_email="admin-expired-accept@example.com",
            advertiser_email="advertiser-expired-accept@example.com",
            driver_email="expired-accept@example.com",
            plate_number="EAC-123",
        )
    )
    expired_assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=expired_campaign.id,
        driver_profile_id=expired_profile.id,
        vehicle_id=expired_vehicle.id,
        assigned_by_user_id=expired_admin.id,
    )

    async def expire_campaign() -> None:
        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, expired_campaign.id)
            campaign.end_at = PAST
            await session.commit()

    asyncio.run(expire_campaign())
    expired_accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{expired_assignment.id}/accept",
        headers=driver_headers(db_client, "expired-accept@example.com"),
        json={"metadata": {}},
    )
    assert expired_accept.status_code == http_status.HTTP_400_BAD_REQUEST
    assert expired_accept.json()["error"]["code"] == "CAMPAIGN_EXPIRED"


def test_admin_activation_owns_final_transition(
    db_client,
    db_sessionmaker,
) -> None:
    _, first_campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email="second-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    second_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
        name="Second Campaign",
    )
    second_creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=second_campaign.id,
        creative_status=CreativeStatus.READY,
    )
    create_test_campaign_payout_revision(
        db_sessionmaker,
        campaign_id=second_campaign.id,
        created_by_user_id=advertiser.id,
        effective_from=PAST,
    )
    create_test_campaign_zone(
        db_sessionmaker,
        campaign_id=second_campaign.id,
        created_by_user_id=advertiser.id,
    )
    second_campaign.campaign_metadata["_test_creative_id"] = str(second_creative.id)
    first_assignment_id = post_assignment(db_client, first_campaign, profile, vehicle).json()["id"]
    second_assignment_id = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(second_campaign, profile, vehicle),
    ).json()["id"]
    headers = driver_headers(db_client)
    for assignment_id in [first_assignment_id, second_assignment_id]:
        accepted = db_client.post(
            f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
            headers=headers,
            json={"metadata": {}},
        )
        assert accepted.status_code == http_status.HTTP_200_OK
    first_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{first_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    second_activate = db_client.post(
        f"/api/v1/admin/campaign-assignments/{second_assignment_id}/activate",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )

    assert first_activate.status_code == http_status.HTTP_409_CONFLICT
    assert second_activate.status_code == http_status.HTTP_409_CONFLICT
    assert first_activate.json()["error"]["code"] == "CAMPAIGN_REVIEW_APPROVAL_REQUIRED"
    assert second_activate.json()["error"]["code"] == "CAMPAIGN_REVIEW_APPROVAL_REQUIRED"


def test_driver_cannot_accept_activate_or_deactivate_another_drivers_assignment(
    db_client,
    db_sessionmaker,
) -> None:
    _, campaign, _, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    other_driver = create_test_user(
        db_sessionmaker,
        email="other-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    assignment_id = post_assignment(db_client, campaign, profile, vehicle).json()["id"]
    other_headers = driver_headers(db_client, "other-driver@example.com")

    accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=other_headers,
        json={"metadata": {}},
    )
    activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/activate",
        headers=other_headers,
        json={"metadata": {}},
    )
    deactivate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/deactivate",
        headers=other_headers,
        json={"metadata": {}},
    )

    assert accept.status_code == http_status.HTTP_404_NOT_FOUND
    assert activate.status_code == http_status.HTTP_404_NOT_FOUND
    assert deactivate.status_code == http_status.HTTP_404_NOT_FOUND
    assert accept.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
    assert deactivate.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
