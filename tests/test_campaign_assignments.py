import asyncio
from datetime import UTC, datetime

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
    fetch_activation_events,
    fetch_audit_events,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.user import UserRole
from app.models.vehicle import Vehicle, VehicleStatus

PASSWORD = "long-secure-password"
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def create_assignment_ready_graph(
    db_sessionmaker,
    *,
    campaign_status: CampaignStatus = CampaignStatus.SCHEDULED,
    driver_status: DriverOnboardingStatus = DriverOnboardingStatus.ACTIVE,
    vehicle_status: VehicleStatus = VehicleStatus.ACTIVE,
    start_at=None,
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


def fetch_assignments(db_sessionmaker) -> list[CampaignAssignment]:
    async def fetch() -> list[CampaignAssignment]:
        async with db_sessionmaker() as session:
            result = await session.execute(select(CampaignAssignment))
            return list(result.scalars().all())

    return asyncio.run(fetch())


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
    assert created["campaign"]["id"] == str(campaign.id)
    assert created["driver_profile"]["id"] == str(profile.id)
    assert created["vehicle"]["id"] == str(vehicle.id)
    assert "password_hash" not in create_response.text
    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == assignment_id
    assert read_response.status_code == http_status.HTTP_200_OK
    assert [event["event_type"] for event in read_response.json()["events"]] == ["assigned"]
    assert cancel_response.status_code == http_status.HTTP_200_OK
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["cancelled_at"] is not None
    assert [event["event_type"] for event in cancel_response.json()["events"]] == [
        "assigned",
        "cancelled",
    ]
    assert cancel_again.status_code == http_status.HTTP_400_BAD_REQUEST
    assert cancel_again.json()["error"]["code"] == "INVALID_ASSIGNMENT_TRANSITION"

    activation_events = fetch_activation_events(db_sessionmaker)
    assert [event.event_type for event in activation_events] == ["assigned", "cancelled"]
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

    duplicate = post_assignment(db_client, campaign, profile, vehicle)
    invalid_metadata = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(campaign, profile, vehicle, metadata=["bad"]),
    )
    db_client.post(
        f"/api/v1/admin/campaign-assignments/{fetch_assignments(db_sessionmaker)[0].id}/cancel",
        headers=admin_headers(db_client),
        json={"metadata": {}},
    )
    allowed_after_cancel = post_assignment(db_client, campaign, profile, vehicle)

    assert duplicate.status_code == http_status.HTTP_409_CONFLICT
    assert duplicate.json()["error"]["code"] == "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT"
    assert invalid_metadata.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
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


def test_driver_can_accept_activate_deactivate_and_read_current_active(
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
    headers = driver_headers(db_client)

    no_active = db_client.get("/api/v1/driver/campaign-assignments/active", headers=headers)
    accept = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=headers,
        json={"metadata": {"accepted": True}},
    )
    accept_again = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=headers,
        json={"metadata": {}},
    )
    activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/activate",
        headers=headers,
        json={"metadata": {"odometer": "100"}},
    )
    active = db_client.get("/api/v1/driver/campaign-assignments/active", headers=headers)
    deactivate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/deactivate",
        headers=headers,
        json={"metadata": {"break": "fuel"}},
    )
    reactivate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )

    assert no_active.status_code == http_status.HTTP_200_OK
    assert no_active.json() == {"assignment": None}
    assert accept.status_code == http_status.HTTP_200_OK
    assert accept.json()["status"] == "accepted"
    assert accept.json()["accepted_at"] is not None
    assert accept_again.status_code == http_status.HTTP_400_BAD_REQUEST
    assert activate.status_code == http_status.HTTP_200_OK
    assert activate.json()["status"] == "active"
    assert activate.json()["activated_at"] is not None
    assert active.status_code == http_status.HTTP_200_OK
    assert active.json()["assignment"]["id"] == assignment_id
    assert deactivate.status_code == http_status.HTTP_200_OK
    assert deactivate.json()["status"] == "deactivated"
    assert deactivate.json()["deactivated_at"] is not None
    assert reactivate.status_code == http_status.HTTP_200_OK
    assert reactivate.json()["status"] == "active"

    activation_events = fetch_activation_events(db_sessionmaker)
    assert [event.event_type for event in activation_events] == [
        "assigned",
        "accepted",
        "activated",
        "deactivated",
        "activated",
    ]
    assert [event.action for event in fetch_audit_events(db_sessionmaker)] == [
        "admin.campaign_assignment.created"
    ]


def test_driver_lifecycle_rejects_invalid_states_and_campaign_windows(
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
        f"/api/v1/driver/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )
    db_client.post(
        f"/api/v1/driver/campaign-assignments/{scheduled_assignment_id}/accept",
        headers=headers,
        json={"metadata": {}},
    )
    scheduled_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )
    update_campaign_status(db_sessionmaker, scheduled_campaign.id, CampaignStatus.PAUSED)
    paused_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{scheduled_assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )

    _, future_campaign, _, future_profile, future_vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=FUTURE,
        end_at=None,
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
        f"/api/v1/driver/campaign-assignments/{future_assignment_id}/activate",
        headers=future_headers,
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
        f"/api/v1/driver/campaign-assignments/{active_assignment_id}/activate",
        headers=eligibility_headers,
        json={"metadata": {}},
    )
    update_driver_status(db_sessionmaker, active_profile.id, DriverOnboardingStatus.ACTIVE)
    update_vehicle_status(db_sessionmaker, active_vehicle.id, VehicleStatus.SUSPENDED)
    inactive_vehicle_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{active_assignment_id}/activate",
        headers=eligibility_headers,
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


def test_one_active_assignment_per_vehicle_is_enforced(
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
    first_assignment_id = post_assignment(db_client, first_campaign, profile, vehicle).json()["id"]
    second_assignment_id = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=admin_headers(db_client),
        json=assignment_payload(second_campaign, profile, vehicle),
    ).json()["id"]
    headers = driver_headers(db_client)

    for assignment_id in [first_assignment_id, second_assignment_id]:
        db_client.post(
            f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
            headers=headers,
            json={"metadata": {}},
        )
    first_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{first_assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )
    second_activate = db_client.post(
        f"/api/v1/driver/campaign-assignments/{second_assignment_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )

    assert first_activate.status_code == http_status.HTTP_200_OK
    assert second_activate.status_code == http_status.HTTP_409_CONFLICT
    assert second_activate.json()["error"]["code"] == "ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE"


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
    assert {response.json()["error"]["code"] for response in [accept, activate, deactivate]} == {
        "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
    }
