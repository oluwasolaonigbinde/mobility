"""FND-07 (RM7): lost exclusivity races return stable 409 envelopes, not 500s.

The pre-checks in the assignment/trip services already return 409 for the
sequential case; these tests defeat or bypass the pre-checks so the four
partial unique indexes themselves fire, and assert the DB loser gets the same
stable code inside the standard error envelope. PostGIS tests race two real
transactions and skip without TEST_DATABASE_URL (CI runs them on Postgres).
"""

import asyncio
from datetime import UTC, datetime, timedelta

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
from sqlalchemy.exc import IntegrityError

import app.services.campaign_assignments as assignments_service
import app.services.trips as trips_service
from app.core.errors import AppError
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.trip import TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.trips import TripStartRequest

PASSWORD = "long-secure-password"
PAST = datetime.now(UTC) - timedelta(days=1)
FUTURE = datetime.now(UTC) + timedelta(days=30)


async def _noop_precheck(*args, **kwargs) -> None:
    return None


def build_graph(db_sessionmaker, suffix: str, campaign_count: int = 1):
    admin = create_test_user(
        db_sessionmaker, email=f"admin-{suffix}@example.com", password=PASSWORD
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=admin.id)
    campaigns = [
        create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Campaign {suffix}-{index}",
            campaign_status=CampaignStatus.ACTIVE,
            start_at=PAST,
            end_at=FUTURE,
        )
        for index in range(campaign_count)
    ]
    driver = create_test_user(
        db_sessionmaker,
        email=f"driver-{suffix}@example.com",
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
        plate_number=f"XCL-{suffix}"[:15],
        vehicle_status=VehicleStatus.ACTIVE,
    )
    return admin, campaigns, driver, profile, vehicle


def assert_conflict_envelope(response, code: str) -> None:
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["request_id"]


def test_lost_create_race_returns_duplicate_assignment_envelope(
    db_client, db_sessionmaker, monkeypatch
) -> None:
    admin, campaigns, _, profile, vehicle = build_graph(db_sessionmaker, "create")
    monkeypatch.setattr(
        assignments_service,
        "ensure_no_duplicate_non_terminal_assignment",
        _noop_precheck,
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    payload = {
        "campaign_id": str(campaigns[0].id),
        "driver_profile_id": str(profile.id),
        "vehicle_id": str(vehicle.id),
        "metadata": {},
    }

    first = db_client.post(
        "/api/v1/admin/campaign-assignments", headers=headers, json=payload
    )
    second = db_client.post(
        "/api/v1/admin/campaign-assignments", headers=headers, json=payload
    )

    assert first.status_code == 201
    assert_conflict_envelope(second, "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT")


def test_lost_activate_race_returns_active_vehicle_envelope(
    db_client, db_sessionmaker, monkeypatch
) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        db_sessionmaker, "activate", campaign_count=2
    )
    for campaign, already_active in ((campaigns[0], True), (campaigns[1], False)):
        create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
            assignment_status=(
                CampaignAssignmentStatus.ACTIVE
                if already_active
                else CampaignAssignmentStatus.ACCEPTED
            ),
            activated_at=datetime.now(UTC) if already_active else None,
            accepted_at=datetime.now(UTC),
        )
    monkeypatch.setattr(
        assignments_service,
        "ensure_no_other_active_assignment_for_vehicle",
        _noop_precheck,
    )
    headers = auth_headers(db_client, driver.email, PASSWORD)
    listed = db_client.get("/api/v1/driver/campaign-assignments", headers=headers).json()
    accepted_id = next(
        item["id"] for item in listed["items"] if item["status"] == "accepted"
    )

    response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{accepted_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )

    assert_conflict_envelope(response, "ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE")


@pytest.mark.parametrize(
    ("same_driver", "expected_code"),
    [
        (True, "ACTIVE_TRIP_EXISTS_FOR_DRIVER"),
        (False, "ACTIVE_TRIP_EXISTS_FOR_VEHICLE"),
    ],
)
def test_lost_trip_start_race_returns_active_trip_envelope(
    db_client, db_sessionmaker, monkeypatch, same_driver, expected_code
) -> None:
    suffix = "trip-d" if same_driver else "trip-v"
    admin, campaigns, driver, profile, vehicle = build_graph(
        db_sessionmaker, suffix, campaign_count=2
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaigns[0].id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        accepted_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
    )
    if same_driver:
        # Same driver already tracking on a second vehicle: only the driver
        # exclusivity index can fire.
        other_vehicle = create_test_vehicle(
            db_sessionmaker,
            driver_profile_id=profile.id,
            plate_number=f"OTH-{suffix}"[:15],
            vehicle_status=VehicleStatus.ACTIVE,
        )
        blocking_profile, blocking_vehicle = profile, other_vehicle
    else:
        # A different driver already tracking on the same vehicle: only the
        # vehicle exclusivity index can fire.
        other_user = create_test_user(
            db_sessionmaker,
            email=f"other-{suffix}@example.com",
            password=PASSWORD,
            role=UserRole.DRIVER,
        )
        other_profile = create_test_driver_profile(
            db_sessionmaker,
            user_id=other_user.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE,
        )
        blocking_profile, blocking_vehicle = other_profile, vehicle
    blocking_assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaigns[1].id,
        driver_profile_id=blocking_profile.id,
        vehicle_id=blocking_vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.DEACTIVATED,
    )
    create_test_trip_session(
        db_sessionmaker,
        assignment_id=blocking_assignment.id,
        campaign_id=campaigns[1].id,
        driver_profile_id=blocking_profile.id,
        vehicle_id=blocking_vehicle.id,
        started_by_user_id=admin.id,
        trip_status=TripSessionStatus.ACTIVE,
    )
    monkeypatch.setattr(
        trips_service, "ensure_no_active_trip_for_driver_or_vehicle", _noop_precheck
    )

    response = db_client.post(
        "/api/v1/driver/trips/start",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"assignment_id": str(assignment.id), "metadata": {}},
    )

    assert_conflict_envelope(response, expected_code)


def test_unrelated_integrity_failure_still_raises(db_sessionmaker) -> None:
    """The translator maps only the four exclusivity names (FND-07 acceptance)."""

    async def violate_check_constraint() -> None:
        async with db_sessionmaker() as session:
            session.add(
                CampaignAssignment(
                    campaign_id=None,
                    driver_profile_id=None,
                    vehicle_id=None,
                    assigned_by_user_id=None,
                    status="bogus-status",
                    offered_at=datetime.now(UTC),
                )
            )
            await assignments_service.flush_translating_exclusivity_conflict(session)

    with pytest.raises(IntegrityError):
        asyncio.run(violate_check_constraint())


def _start_trip_outcome(sessionmaker, *, user_id, assignment_id):
    async def run_one() -> str:
        async with sessionmaker() as session:
            try:
                await trips_service.start_driver_trip(
                    session,
                    user_id=user_id,
                    payload=TripStartRequest(assignment_id=assignment_id, metadata={}),
                )
                await session.commit()
                return "started"
            except AppError as exc:
                assert exc.status_code == 409
                return exc.code

    return run_one


def test_concurrent_trip_starts_one_winner_postgis(postgis_db_sessionmaker) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        postgis_db_sessionmaker, "pg-trip"
    )
    assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaigns[0].id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        accepted_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
    )

    async def race() -> list[str]:
        one = _start_trip_outcome(
            postgis_db_sessionmaker, user_id=driver.id, assignment_id=assignment.id
        )
        two = _start_trip_outcome(
            postgis_db_sessionmaker, user_id=driver.id, assignment_id=assignment.id
        )
        return list(await asyncio.gather(one(), two()))

    outcomes = asyncio.run(race())

    assert sorted(outcomes)[-1] == "started"
    losers = [outcome for outcome in outcomes if outcome != "started"]
    assert len(losers) == 1
    assert losers[0] in {
        "ACTIVE_TRIP_EXISTS_FOR_DRIVER",
        "ACTIVE_TRIP_EXISTS_FOR_VEHICLE",
    }


def test_concurrent_activations_one_winner_postgis(postgis_db_sessionmaker) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        postgis_db_sessionmaker, "pg-act", campaign_count=2
    )
    assignment_ids = [
        create_test_campaign_assignment(
            postgis_db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
            assignment_status=CampaignAssignmentStatus.ACCEPTED,
            accepted_at=datetime.now(UTC),
        ).id
        for campaign in campaigns
    ]

    async def activate_one(assignment_id) -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.activate_driver_assignment(
                    session,
                    user_id=driver.id,
                    assignment_id=assignment_id,
                    payload=assignments_service.CampaignAssignmentTransition(metadata={}),
                )
                await session.commit()
                return "activated"
            except AppError as exc:
                assert exc.status_code == 409
                return exc.code

    async def race() -> list[str]:
        return list(
            await asyncio.gather(
                activate_one(assignment_ids[0]), activate_one(assignment_ids[1])
            )
        )

    outcomes = asyncio.run(race())

    assert outcomes.count("activated") == 1
    losers = [outcome for outcome in outcomes if outcome != "activated"]
    assert losers == ["ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE"]
