import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
    fetch_location_ping_batches,
    fetch_location_pings,
    fetch_trip_sessions,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status
from test_payouts_v2 import create_v2_rule
from test_payouts_v3 import create_revision_row

from app.models.billing import AcceptanceMethod, PaymentClass, QuoteRequestSource
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.payout import AssignmentRuleBinding
from app.models.trip import TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import Vehicle, VehicleStatus
from app.services.billing import (
    accept_quotation_revision,
    record_approved_credit_authorization,
    record_production_start,
    record_quotation_revision,
    request_custom_quote,
    reserve_assignment_liability,
)

PASSWORD = "long-secure-password"
PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


def create_trip_ready_graph(
    db_sessionmaker,
    *,
    campaign_status: CampaignStatus = CampaignStatus.ACTIVE,
    assignment_status: CampaignAssignmentStatus = CampaignAssignmentStatus.ACTIVE,
    driver_status: DriverOnboardingStatus = DriverOnboardingStatus.ACTIVE,
    vehicle_status: VehicleStatus = VehicleStatus.ACTIVE,
    start_at=PAST,
    end_at=FUTURE,
    admin_email: str = "admin@example.com",
    advertiser_email: str = "advertiser@example.com",
    driver_email: str = "driver@example.com",
    plate_number: str = "ABC-123",
    with_financial_authority: bool = True,
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
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=assignment_status,
        activated_at=datetime.now(UTC)
        if assignment_status == CampaignAssignmentStatus.ACTIVE
        else None,
    )

    async def add_financial_authority(payout_revision) -> None:
        async with db_sessionmaker() as session:
            empty_geometry_hash = hashlib.sha256(b"").hexdigest()
            session.add(
                AssignmentRuleBinding(
                    assignment_id=assignment.id,
                    revision_id=payout_revision.id,
                    hourly_rate_naira=Decimal("1.00"),
                    premium_hourly_rate_naira=None,
                    daily_payable_hours_cap=Decimal("1.00"),
                    eligibility_params={},
                    resolved_eligibility_params={},
                    formula_version="payout_v3",
                    premium_zone_ids=[],
                    premium_zone_geometry_hash=empty_geometry_hash,
                    premium_zone_geometry_wkts=[],
                    exclusion_zone_ids=[],
                    exclusion_zone_geometry_hash=empty_geometry_hash,
                    exclusion_zone_geometry_wkts=[],
                    stationary_policy_marker="stationary-rd-v1",
                    campaign_window_start_at=campaign.start_at or PAST,
                    campaign_window_end_at=campaign.end_at or FUTURE,
                    campaign_window_frozen=True,
                    bound_at=datetime.now(UTC),
                )
            )
            quote_request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=advertiser.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={"test_authority": True},
            )
            quote_revision = await record_quotation_revision(
                session,
                quote_request_id=quote_request.id,
                actor_user_id=admin.id,
                quote_reference=f"TRIP-{campaign.id}",
                currency="NGN",
                line_items=[
                    {
                        "code": "TEST",
                        "description": "Synthetic trip authority",
                        "kind": "media",
                        "amount": "1000000.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                payment_terms={"test_only": True},
                tax_rate="0",
            )
            await accept_quotation_revision(
                session,
                quotation_revision_id=quote_revision.id,
                actor_user_id=advertiser.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            await record_approved_credit_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                credit_limit="1000000.00",
                max_driver_liability="1000000.00",
                due_at=datetime(2100, 1, 1, tzinfo=UTC),
                approved_by_user_id=admin.id,
                credit_terms={"test_only": True},
                reason="synthetic trip test authority",
            )
            await record_production_start(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
            )
            await reserve_assignment_liability(
                session,
                assignment_id=assignment.id,
                actor_user_id=admin.id,
            )
            await session.commit()

    if with_financial_authority:
        # Trip tests exercise the trip protocol, not a funding bypass. Give
        # their graph genuine synthetic commercial authority and a reserve so
        # the production fail-closed gate is identical in tests and runtime.
        rule = create_v2_rule(
            db_sessionmaker,
            campaign_id=campaign.id,
            created_by_user_id=admin.id,
            hourly_rate="1.00",
            daily_cap_hours="1.00",
        )
        payout_revision = create_revision_row(
            db_sessionmaker,
            campaign_id=campaign.id,
            rule_id=rule.id,
            created_by_user_id=admin.id,
            base="1.00",
            premium=None,
            cap="1.00",
        )
        asyncio.run(add_financial_authority(payout_revision))
    return admin, campaign, driver, profile, vehicle, assignment


def driver_headers(db_client, email: str = "driver@example.com"):
    return auth_headers(db_client, email, PASSWORD)


def ping_payload(recorded_at: datetime | None = None, **overrides):
    payload = {
        "idempotency_key": "batch-1",
        "pings": [
            {
                "recorded_at": (recorded_at or datetime.now(UTC)).isoformat(),
                "lat": 6.45,
                "lon": 3.39,
                "accuracy_m": 12.5,
                "speed_mps": 8.3,
                "heading_degrees": 180.0,
                "altitude_m": 42.0,
                "sequence_number": 1,
                "metadata": {"source": "gps"},
            }
        ],
        "metadata": {"device": "phone"},
    }
    payload.update(overrides)
    return payload


def update_campaign_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    campaign_id,
    campaign_status: CampaignStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, campaign_id)
            campaign.status = campaign_status
            await session.commit()

    asyncio.run(update())


def update_assignment_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    assignment_id,
    assignment_status: CampaignAssignmentStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, assignment_id)
            assignment.status = assignment_status
            await session.commit()

    asyncio.run(update())


def update_driver_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    profile_id,
    driver_status: DriverOnboardingStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            profile = await session.get(DriverProfile, profile_id)
            profile.onboarding_status = driver_status
            await session.commit()

    asyncio.run(update())


def update_vehicle_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    vehicle_id,
    vehicle_status: VehicleStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            vehicle = await session.get(Vehicle, vehicle_id)
            vehicle.status = vehicle_status
            await session.commit()

    asyncio.run(update())


def start_trip(db_client, assignment_id, email: str = "driver@example.com"):
    return db_client.post(
        "/api/v1/driver/trips/start",
        headers=driver_headers(db_client, email),
        json={"assignment_id": str(assignment_id), "metadata": {"shift": "morning"}},
    )


def test_driver_can_start_get_current_read_and_end_trip(db_client, db_sessionmaker) -> None:
    _, campaign, driver, profile, vehicle, assignment = create_trip_ready_graph(db_sessionmaker)
    headers = driver_headers(db_client)

    no_current = db_client.get("/api/v1/driver/trips/current", headers=headers)
    create_response = start_trip(db_client, assignment.id)
    trip_id = create_response.json()["id"]
    current = db_client.get("/api/v1/driver/trips/current", headers=headers)
    read_response = db_client.get(f"/api/v1/driver/trips/{trip_id}", headers=headers)
    end_response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=headers,
        json={"end_reason": " driver_ended ", "metadata": {"ignored": True}},
    )
    end_again = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=headers,
        json={"metadata": {}},
    )

    assert no_current.status_code == http_status.HTTP_200_OK
    assert no_current.json() == {"trip": None}
    assert create_response.status_code == http_status.HTTP_201_CREATED
    created = create_response.json()
    assert created["assignment_id"] == str(assignment.id)
    assert created["campaign_id"] == str(campaign.id)
    assert created["driver_profile_id"] == str(profile.id)
    assert created["vehicle_id"] == str(vehicle.id)
    assert created["status"] == "active"
    assert created["ping_count"] == 0
    assert created["metadata"] == {"shift": "morning"}
    assert "password_hash" not in create_response.text
    assert current.status_code == http_status.HTTP_200_OK
    assert current.json()["trip"]["id"] == trip_id
    assert read_response.status_code == http_status.HTTP_200_OK
    assert read_response.json()["id"] == trip_id
    assert end_response.status_code == http_status.HTTP_200_OK
    assert end_response.json()["status"] == "ended"
    assert end_response.json()["ended_at"] is not None
    assert end_response.json()["end_reason"] == "driver_ended"
    assert end_again.status_code == http_status.HTTP_400_BAD_REQUEST
    assert end_again.json()["error"]["code"] == "TRIP_ALREADY_ENDED"

    trips = fetch_trip_sessions(db_sessionmaker)
    assert trips[0].started_by_user_id == driver.id
    assert trips[0].status == TripSessionStatus.ENDED.value


def test_trip_start_validates_assignment_campaign_driver_vehicle_and_uniqueness(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, profile, vehicle, assignment = create_trip_ready_graph(db_sessionmaker)
    duplicate = start_trip(db_client, assignment.id)
    duplicate_again = start_trip(db_client, assignment.id)

    assert duplicate.status_code == http_status.HTTP_201_CREATED
    assert duplicate_again.status_code == http_status.HTTP_409_CONFLICT
    assert duplicate_again.json()["error"]["code"] == "ACTIVE_TRIP_EXISTS_FOR_DRIVER"

    other_driver = create_test_user(
        db_sessionmaker,
        email="other-start@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(
        db_sessionmaker,
        user_id=other_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    other_assignment = start_trip(
        db_client,
        assignment.id,
        email="other-start@example.com",
    )
    assert other_assignment.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_assignment.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_FOUND"
    assert str(assignment.id) not in other_assignment.text

    cases = [
        (
            {"assignment_status": CampaignAssignmentStatus.ACCEPTED},
            "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE",
        ),
        ({"campaign_status": CampaignStatus.PAUSED}, "CAMPAIGN_NOT_ACTIVE"),
        ({"start_at": FUTURE, "end_at": None}, "CAMPAIGN_NOT_STARTED"),
        ({"start_at": None, "end_at": PAST}, "CAMPAIGN_EXPIRED"),
        ({"driver_status": DriverOnboardingStatus.SUSPENDED}, "DRIVER_PROFILE_NOT_ACTIVE"),
        ({"vehicle_status": VehicleStatus.SUSPENDED}, "VEHICLE_NOT_ACTIVE"),
    ]
    for index, (overrides, expected_code) in enumerate(cases):
        _, _, _, _, _, rejected_assignment = create_trip_ready_graph(
            db_sessionmaker,
            admin_email=f"admin-{index}@example.com",
            advertiser_email=f"advertiser-{index}@example.com",
            driver_email=f"driver-{index}@example.com",
            plate_number=f"TRP-{index}",
            **overrides,
        )
        response = start_trip(
            db_client,
            rejected_assignment.id,
            email=f"driver-{index}@example.com",
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == expected_code

    create_test_user(
        db_sessionmaker,
        email="no-profile@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    no_profile = start_trip(db_client, assignment.id, email="no-profile@example.com")
    assert no_profile.status_code == http_status.HTTP_404_NOT_FOUND
    assert no_profile.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"

    update_driver_status(db_sessionmaker, profile.id, DriverOnboardingStatus.ACTIVE)
    update_vehicle_status(db_sessionmaker, vehicle.id, VehicleStatus.ACTIVE)


def test_trip_endpoints_enforce_driver_rbac_and_non_leaking_ownership(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
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
    create_test_user(db_sessionmaker, email="admin2@example.com", password=PASSWORD)
    create_test_user(
        db_sessionmaker,
        email="advertiser2@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    role_headers = [
        auth_headers(db_client, "admin2@example.com", PASSWORD),
        auth_headers(db_client, "advertiser2@example.com", PASSWORD),
        None,
    ]
    driver_endpoint_requests = [
        (
            "POST",
            "/api/v1/driver/trips/start",
            {"json": {"assignment_id": str(assignment.id), "metadata": {}}},
        ),
        ("GET", "/api/v1/driver/trips/current", {}),
        ("GET", f"/api/v1/driver/trips/{trip_id}", {}),
        (
            "POST",
            f"/api/v1/driver/trips/{trip_id}/end",
            {"json": {"metadata": {}}},
        ),
        (
            "POST",
            f"/api/v1/driver/trips/{trip_id}/pings",
            {"json": ping_payload()},
        ),
    ]

    other_read = db_client.get(
        f"/api/v1/driver/trips/{trip_id}",
        headers=driver_headers(db_client, "other@example.com"),
    )
    other_end = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client, "other@example.com"),
        json={"metadata": {}},
    )
    rbac_responses = [
        db_client.request(method, path, headers=headers, **kwargs)
        for method, path, kwargs in driver_endpoint_requests
        for headers in role_headers
    ]

    assert other_read.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_end.status_code == http_status.HTTP_404_NOT_FOUND
    assert {other_read.json()["error"]["code"], other_end.json()["error"]["code"]} == {
        "TRIP_NOT_FOUND"
    }
    assert [response.status_code for response in rbac_responses] == [
        expected
        for _ in driver_endpoint_requests
        for expected in (
            http_status.HTTP_403_FORBIDDEN,
            http_status.HTTP_403_FORBIDDEN,
            http_status.HTTP_401_UNAUTHORIZED,
        )
    ]


def test_driver_can_ingest_idempotent_location_ping_batches(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    headers = driver_headers(db_client)
    payload = ping_payload()

    create_response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=headers,
        json=payload,
    )
    duplicate = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=headers,
        json=payload,
    )
    conflict_payload = ping_payload(pings=[ping_payload()["pings"][0] | {"lat": 6.5}])
    conflict = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=headers,
        json=conflict_payload,
    )
    read_response = db_client.get(f"/api/v1/driver/trips/{trip_id}", headers=headers)

    assert create_response.status_code == http_status.HTTP_200_OK
    assert create_response.json()["accepted_count"] == 1
    assert create_response.json()["duplicate"] is False
    assert duplicate.status_code == http_status.HTTP_200_OK
    assert duplicate.json()["batch_id"] == create_response.json()["batch_id"]
    assert duplicate.json()["duplicate"] is True
    assert conflict.status_code == http_status.HTTP_409_CONFLICT
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert read_response.json()["ping_count"] == 1
    assert read_response.json()["first_ping_at"] is not None
    assert len(fetch_location_ping_batches(db_sessionmaker)) == 1
    assert len(fetch_location_pings(db_sessionmaker)) == 1


@pytest.mark.parametrize(
    ("payload_overrides", "expected_status"),
    [
        ({"pings": []}, http_status.HTTP_422_UNPROCESSABLE_CONTENT),
        ({"metadata": ["bad"]}, http_status.HTTP_422_UNPROCESSABLE_CONTENT),
        (
            {"pings": [ping_payload()["pings"][0] | {"lat": 91}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"lon": 181}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"accuracy_m": -1}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"speed_mps": -1}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"heading_degrees": 360}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"altitude_m": 10001}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
        (
            {"pings": [ping_payload()["pings"][0] | {"sequence_number": -1}]},
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ],
)
def test_ping_schema_validation_rejects_invalid_batches(
    db_client,
    db_sessionmaker,
    payload_overrides,
    expected_status,
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = ping_payload(**payload_overrides)

    response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )

    assert response.status_code == expected_status
    assert len(fetch_location_pings(db_sessionmaker)) == 0


def test_ping_service_validation_and_all_or_nothing_behavior(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    headers = driver_headers(db_client)
    too_future = datetime.now(UTC) + timedelta(seconds=301)
    too_old = PAST - timedelta(seconds=901)
    cases = [
        (ping_payload(too_future), "INVALID_RECORDED_AT"),
        (ping_payload(too_old), "INVALID_RECORDED_AT"),
        (
            ping_payload(pings=[ping_payload()["pings"][0] | {"accuracy_m": 10001}]),
            "INVALID_ACCURACY",
        ),
        (
            ping_payload(pings=[ping_payload()["pings"][0] | {"speed_mps": 121}]),
            "INVALID_SPEED",
        ),
    ]

    for index, (payload, expected_code) in enumerate(cases):
        payload["idempotency_key"] = f"invalid-{index}"
        response = db_client.post(
            f"/api/v1/driver/trips/{trip_id}/pings",
            headers=headers,
            json=payload,
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == expected_code
        assert len(fetch_location_pings(db_sessionmaker)) == 0

    many_pings = [ping_payload()["pings"][0] | {"sequence_number": number} for number in range(501)]
    too_large = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=headers,
        json=ping_payload(idempotency_key="too-large", pings=many_pings),
    )
    assert too_large.status_code == http_status.HTTP_400_BAD_REQUEST
    assert too_large.json()["error"]["code"] == "LOCATION_PING_BATCH_TOO_LARGE"
    assert len(fetch_location_pings(db_sessionmaker)) == 0


def test_pings_require_active_owned_trip_and_active_assignment(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
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
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = ping_payload()

    other = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client, "other@example.com"),
        json=payload,
    )
    db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )
    ended = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=ping_payload(idempotency_key="ended"),
    )

    _, _, _, _, _, second_assignment = create_trip_ready_graph(
        db_sessionmaker,
        admin_email="admin2@example.com",
        advertiser_email="advertiser2@example.com",
        driver_email="driver2@example.com",
        plate_number="XYZ-123",
    )
    second_trip_id = start_trip(
        db_client,
        second_assignment.id,
        email="driver2@example.com",
    ).json()["id"]
    update_assignment_status(
        db_sessionmaker,
        second_assignment.id,
        CampaignAssignmentStatus.DEACTIVATED,
    )
    inactive_assignment = db_client.post(
        f"/api/v1/driver/trips/{second_trip_id}/pings",
        headers=driver_headers(db_client, "driver2@example.com"),
        json=ping_payload(idempotency_key="inactive-assignment"),
    )

    assert other.status_code == http_status.HTTP_404_NOT_FOUND
    assert other.json()["error"]["code"] == "TRIP_NOT_FOUND"
    # RM3: an ended (not yet sealed) trip is inside its recovery window —
    # late batches are accepted as live evidence, no longer rejected 400.
    assert ended.status_code == http_status.HTTP_200_OK
    assert ended.json()["accepted_count"] == 1
    assert ended.json()["quarantined"] is False
    assert inactive_assignment.status_code == http_status.HTTP_400_BAD_REQUEST
    assert inactive_assignment.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE"


def test_trip_end_does_not_deactivate_assignment(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={"metadata": {}},
    )

    assert response.status_code == http_status.HTTP_200_OK
    async def fetch_status() -> str:
        async with db_sessionmaker() as session:
            refreshed = await session.get(CampaignAssignment, assignment.id)
            return refreshed.status

    assert asyncio.run(fetch_status()) == CampaignAssignmentStatus.ACTIVE.value


def test_location_pings_are_stored_as_postgis_points(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(postgis_db_sessionmaker)
    trip_id = start_trip(postgis_db_client, assignment.id).json()["id"]
    response = postgis_db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(postgis_db_client),
        json=ping_payload(),
    )

    async def fetch_point() -> tuple[int, float, float]:
        async with postgis_db_sessionmaker() as session:
            result = await session.execute(
                text(
                    "SELECT ST_SRID(geom), ST_X(geom), ST_Y(geom) "
                    "FROM location_pings LIMIT 1"
                )
            )
            row = result.one()
            return int(row[0]), float(row[1]), float(row[2])

    srid, x_lon, y_lat = asyncio.run(fetch_point())
    assert response.status_code == http_status.HTTP_200_OK
    assert srid == 4326
    assert x_lon == pytest.approx(3.39)
    assert y_lat == pytest.approx(6.45)
