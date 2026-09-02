"""FND-07 (RM7): lost exclusivity races return stable 409 envelopes, not 500s.

The pre-checks in the assignment/trip services already return 409 for the
sequential case; these tests defeat or bypass the pre-checks so the four
partial unique indexes themselves fire, and assert the DB loser gets the same
stable code inside the standard error envelope. PostGIS tests race two real
transactions and skip without TEST_DATABASE_URL (CI runs them on Postgres).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_campaign_payout_revision,
    create_test_campaign_zone,
    create_test_display_proof,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
    fetch_activation_events,
)
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from test_trips import create_trip_ready_graph

import app.services.campaign_assignments as assignments_service
import app.services.trips as trips_service
from app.core.errors import AppError
from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.trip import TripSessionStatus
from app.models.trip_analytics import TripAnalytics
from app.models.user import UserRole
from app.models.vehicle import Vehicle, VehicleStatus
from app.schemas.campaign_assignments import (
    CampaignAssignmentCancel,
    CampaignAssignmentCreate,
    CampaignAssignmentTransition,
)
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
    for campaign in campaigns:
        creative = create_test_campaign_creative(
            db_sessionmaker,
            campaign_id=campaign.id,
            creative_status=CreativeStatus.APPROVED,
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


def create_offered_assignment(sessionmaker, settings, admin, campaign, profile, vehicle):
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


def accept_offered_assignment(sessionmaker, settings, driver_id, assignment_id):
    async def accept():
        async with sessionmaker() as session:
            assignment = await assignments_service.accept_driver_assignment(
                session,
                user_id=driver_id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            await session.commit()
            return assignment

    return asyncio.run(accept())


def test_cancel_and_admin_activation_serialize_postgres(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        postgis_db_sessionmaker, "cancel-activate"
    )
    activation_admin = create_test_user(
        postgis_db_sessionmaker,
        email="activation-admin-cancel-activate@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    assignment_id = create_offered_assignment(
        postgis_db_sessionmaker, settings, admin, campaigns[0], profile, vehicle
    )
    accepted = accept_offered_assignment(
        postgis_db_sessionmaker, settings, driver.id, assignment_id
    )
    assert accepted.status == CampaignAssignmentStatus.ACCEPTED.value

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

    async def cancel() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.cancel_admin_assignment(
                    session,
                    admin_user_id=admin.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentCancel(reason="reassigned"),
                )
                await session.commit()
                return "cancelled"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def activate() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.activate_admin_assignment(
                    session,
                    admin_user_id=activation_admin.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(),
                )
                await session.commit()
                return "activated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(cancel(), activate()), timeout=10)

    outcomes = asyncio.run(race())
    assert lock_call_count == 2
    assert "cancelled" in outcomes
    assert any(
        outcome in {"CAMPAIGN_REVIEW_APPROVAL_REQUIRED", "INVALID_ASSIGNMENT_TRANSITION"}
        for outcome in outcomes
    )
    events = fetch_activation_events(postgis_db_sessionmaker)
    assert [event.event_type for event in events] == ["assigned", "accepted", "cancelled"]
    assert events[-1].previous_status == CampaignAssignmentStatus.ACCEPTED.value


def test_cancel_and_driver_deactivation_serialize_postgres(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        postgis_db_sessionmaker, "cancel-deactivate"
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

    async def cancel() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.cancel_admin_assignment(
                    session,
                    admin_user_id=admin.id,
                    assignment_id=assignment.id,
                    payload=CampaignAssignmentCancel(reason="reassigned"),
                )
                await session.commit()
                return "cancelled"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def deactivate() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.deactivate_driver_assignment(
                    session,
                    user_id=driver.id,
                    assignment_id=assignment.id,
                    payload=CampaignAssignmentTransition(),
                )
                await session.commit()
                return "deactivated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(cancel(), deactivate()), timeout=10)

    outcomes = asyncio.run(race())
    assert lock_call_count == 2
    assert set(outcomes) in (
        {"cancelled", "INVALID_ASSIGNMENT_TRANSITION"},
        {"deactivated", "INVALID_ASSIGNMENT_TRANSITION"},
        {"cancelled", "deactivated"},
    )
    events = fetch_activation_events(postgis_db_sessionmaker)
    if set(outcomes) == {"cancelled", "deactivated"}:
        assert [event.event_type for event in events] == ["deactivated", "cancelled"]
        assert [event.previous_status for event in events] == [
            CampaignAssignmentStatus.ACTIVE.value,
            CampaignAssignmentStatus.DEACTIVATED.value,
        ]
    else:
        assert len(events) == 1
        assert events[0].event_type in {"cancelled", "deactivated"}
        assert events[0].previous_status == CampaignAssignmentStatus.ACTIVE.value


def test_cancel_and_trip_start_serialize_postgres(
    postgis_db_sessionmaker,
    monkeypatch,
    settings,
) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(postgis_db_sessionmaker, "cancel-trip")
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
    create_test_display_proof(
        postgis_db_sessionmaker,
        assignment_id=assignment.id,
        reviewed_by_user_id=admin.id,
    )
    monkeypatch.setattr(trips_service, "assert_new_work_authorized", _noop_precheck)
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
    monkeypatch.setattr(trips_service, "acquire_campaign_terms_lock", barrier_lock)

    async def cancel() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.cancel_admin_assignment(
                    session,
                    admin_user_id=admin.id,
                    assignment_id=assignment.id,
                    payload=CampaignAssignmentCancel(reason="reassigned"),
                )
                await session.commit()
                return "cancelled"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def start() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await trips_service.start_driver_trip(
                    session,
                    user_id=driver.id,
                    payload=TripStartRequest(
                        assignment_id=assignment.id,
                        evidence_protocol_version=2,
                        metadata={},
                    ),
                    settings=settings,
                )
                await session.commit()
                return "started"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(cancel(), start()), timeout=10)

    outcomes = asyncio.run(race())
    assert lock_call_count == 2
    assert "cancelled" in outcomes
    assert "started" in outcomes or "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE" in outcomes
    events = fetch_activation_events(postgis_db_sessionmaker)
    assert [event.event_type for event in events] == ["activated", "cancelled"]
    assert events[-1].previous_status == CampaignAssignmentStatus.ACTIVE.value


def test_deactivation_and_funded_trip_start_serialize_postgres(
    postgis_db_sessionmaker,
    monkeypatch,
    settings,
) -> None:
    admin, _campaign, driver, _profile, _vehicle, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker,
        admin_email="admin-deactivate-trip@example.com",
        advertiser_email="advertiser-deactivate-trip@example.com",
        driver_email="driver-deactivate-trip@example.com",
        plate_number="DCT-TRIP",
    )
    del admin
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
    monkeypatch.setattr(trips_service, "acquire_campaign_terms_lock", barrier_lock)

    async def deactivate() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.deactivate_driver_assignment(
                    session,
                    user_id=driver.id,
                    assignment_id=assignment.id,
                    payload=CampaignAssignmentTransition(),
                )
                await session.commit()
                return "deactivated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def start() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await trips_service.start_driver_trip(
                    session,
                    user_id=driver.id,
                    payload=TripStartRequest(
                        assignment_id=assignment.id,
                        evidence_protocol_version=2,
                        metadata={},
                    ),
                    settings=settings,
                )
                await session.commit()
                return "started"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(deactivate(), start()), timeout=10)

    outcomes = asyncio.run(race())
    assert lock_call_count == 2
    assert "deactivated" in outcomes
    assert "started" in outcomes or "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE" in outcomes
    events = fetch_activation_events(postgis_db_sessionmaker)
    assert [event.event_type for event in events] == ["activated", "deactivated"]
    assert events[-1].previous_status == CampaignAssignmentStatus.ACTIVE.value


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
        "creative_id": campaigns[0].campaign_metadata["_test_creative_id"],
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "metadata": {},
    }

    first = db_client.post("/api/v1/admin/campaign-assignments", headers=headers, json=payload)
    second = db_client.post("/api/v1/admin/campaign-assignments", headers=headers, json=payload)

    assert first.status_code == 201
    assert_conflict_envelope(second, "DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT")


def test_driver_activation_route_is_removed(db_client, db_sessionmaker, monkeypatch) -> None:
    del monkeypatch
    admin, campaigns, driver, profile, vehicle = build_graph(db_sessionmaker, "activate")
    headers = auth_headers(db_client, driver.email, PASSWORD)
    created = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={
            "campaign_id": str(campaigns[0].id),
            "driver_profile_id": str(profile.id),
            "vehicle_id": str(vehicle.id),
            "creative_id": campaigns[0].campaign_metadata["_test_creative_id"],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "metadata": {},
        },
    )
    assert created.status_code == 201
    accepted_id = created.json()["id"]
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{accepted_id}/accept",
        headers=headers,
        json={"metadata": {}},
    )
    assert accepted.status_code == 200

    response = db_client.post(
        f"/api/v1/driver/campaign-assignments/{accepted_id}/activate",
        headers=headers,
        json={"metadata": {}},
    )

    assert response.status_code == 404


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
    create_test_display_proof(
        db_sessionmaker,
        assignment_id=assignment.id,
        reviewed_by_user_id=admin.id,
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
    monkeypatch.setattr(trips_service, "assert_new_work_authorized", _noop_precheck)

    response = db_client.post(
        "/api/v1/driver/trips/start",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={
            "assignment_id": str(assignment.id),
            "evidence_protocol_version": 2,
            "metadata": {},
        },
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


def _start_trip_outcome(sessionmaker, *, user_id, assignment_id, settings):
    async def run_one() -> str:
        async with sessionmaker() as session:
            try:
                await trips_service.start_driver_trip(
                    session,
                    user_id=user_id,
                    payload=TripStartRequest(
                        assignment_id=assignment_id,
                        evidence_protocol_version=2,
                        metadata={},
                    ),
                    settings=settings,
                )
                await session.commit()
                return "started"
            except AppError as exc:
                assert exc.status_code == 409
                return exc.code

    return run_one


def test_concurrent_trip_starts_one_winner_postgis(
    postgis_db_sessionmaker, monkeypatch, settings
) -> None:
    monkeypatch.setattr(trips_service, "assert_new_work_authorized", _noop_precheck)
    admin, campaigns, driver, profile, vehicle = build_graph(postgis_db_sessionmaker, "pg-trip")
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
    create_test_display_proof(
        postgis_db_sessionmaker,
        assignment_id=assignment.id,
        reviewed_by_user_id=admin.id,
    )

    async def race() -> list[str]:
        one = _start_trip_outcome(
            postgis_db_sessionmaker,
            user_id=driver.id,
            assignment_id=assignment.id,
            settings=settings,
        )
        two = _start_trip_outcome(
            postgis_db_sessionmaker,
            user_id=driver.id,
            assignment_id=assignment.id,
            settings=settings,
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


def test_concurrent_admin_activations_fail_closed_postgis(postgis_db_sessionmaker) -> None:
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
                await assignments_service.activate_admin_assignment(
                    session,
                    admin_user_id=admin.id,
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
            await asyncio.gather(activate_one(assignment_ids[0]), activate_one(assignment_ids[1]))
        )

    outcomes = asyncio.run(race())

    assert outcomes == ["CAMPAIGN_REVIEW_APPROVAL_REQUIRED"] * 2


def test_recommendation_create_locks_selected_facts_postgis(
    postgis_db_sessionmaker, monkeypatch
) -> None:
    admin, campaigns, _, profile, vehicle = build_graph(postgis_db_sessionmaker, "pg-rec-lock")

    async def recommendation_payload() -> CampaignAssignmentCreate:
        async with postgis_db_sessionmaker() as session:
            candidates, _ = await assignments_service.list_assignment_recommendations(
                session,
                campaign_id=campaigns[0].id,
                service_city="Lagos",
                limit=1,
                offset=0,
            )
        candidate = candidates[0]
        return CampaignAssignmentCreate(
            campaign_id=campaigns[0].id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            creative_id=UUID(campaigns[0].campaign_metadata["_test_creative_id"]),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            recommendation_context={
                "service_city": candidate.service_city,
                "vehicle_type": candidate.vehicle_type,
                "matching_version": candidate.matching_version,
                "fingerprint": candidate.fingerprint,
            },
        )

    payload = asyncio.run(recommendation_payload())
    original_ensure = assignments_service.ensure_recommendation_context_current
    facts_locked = asyncio.Event()
    allow_create = asyncio.Event()

    async def pause_after_locked_recheck(*args, **kwargs) -> None:
        await original_ensure(*args, **kwargs)
        facts_locked.set()
        await allow_create.wait()

    monkeypatch.setattr(
        assignments_service,
        "ensure_recommendation_context_current",
        pause_after_locked_recheck,
    )

    async def create_assignment() -> None:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.create_campaign_assignment(
                session,
                admin_user_id=admin.id,
                payload=payload,
            )
            await session.commit()

    async def deactivate_vehicle() -> None:
        await facts_locked.wait()
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(Vehicle)
                .where(Vehicle.id == vehicle.id)
                .values(status=VehicleStatus.INACTIVE.value)
            )
            await session.commit()

    async def force_interleaving() -> None:
        create_task = asyncio.create_task(create_assignment())
        await facts_locked.wait()
        update_task = asyncio.create_task(deactivate_vehicle())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(update_task), timeout=0.2)
        allow_create.set()
        await create_task
        await update_task

    asyncio.run(force_interleaving())


@pytest.mark.parametrize("changed_aggregate", ["load", "activity"])
def test_recommendation_create_locks_aggregate_inputs_postgis(
    postgis_db_sessionmaker, monkeypatch, changed_aggregate
) -> None:
    admin, campaigns, driver, profile, vehicle = build_graph(
        postgis_db_sessionmaker, f"pg-rec-{changed_aggregate}", campaign_count=2
    )
    historical_assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaigns[1].id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    trip = create_test_trip_session(
        postgis_db_sessionmaker,
        assignment_id=historical_assignment.id,
        campaign_id=campaigns[1].id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
    )
    analytics = create_test_trip_analytics(
        postgis_db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=historical_assignment.id,
        campaign_id=campaigns[1].id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        active_tracking_seconds=120,
    )

    async def recommendation_payload() -> CampaignAssignmentCreate:
        async with postgis_db_sessionmaker() as session:
            candidates, _ = await assignments_service.list_assignment_recommendations(
                session,
                campaign_id=campaigns[0].id,
                service_city="Lagos",
                limit=1,
                offset=0,
            )
        candidate = candidates[0]
        return CampaignAssignmentCreate(
            campaign_id=campaigns[0].id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            creative_id=UUID(campaigns[0].campaign_metadata["_test_creative_id"]),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            recommendation_context={
                "service_city": candidate.service_city,
                "vehicle_type": candidate.vehicle_type,
                "matching_version": candidate.matching_version,
                "fingerprint": candidate.fingerprint,
            },
        )

    payload = asyncio.run(recommendation_payload())
    original_ensure = assignments_service.ensure_recommendation_context_current
    aggregates_locked = asyncio.Event()
    allow_create = asyncio.Event()

    async def pause_after_locked_recheck(*args, **kwargs) -> None:
        await original_ensure(*args, **kwargs)
        aggregates_locked.set()
        await allow_create.wait()

    monkeypatch.setattr(
        assignments_service,
        "ensure_recommendation_context_current",
        pause_after_locked_recheck,
    )

    async def create_assignment() -> None:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.create_campaign_assignment(
                session,
                admin_user_id=admin.id,
                payload=payload,
            )
            await session.commit()

    async def change_aggregate() -> None:
        await aggregates_locked.wait()
        async with postgis_db_sessionmaker() as session:
            if changed_aggregate == "load":
                statement = (
                    update(CampaignAssignment)
                    .where(CampaignAssignment.id == historical_assignment.id)
                    .values(
                        status=CampaignAssignmentStatus.CANCELLED.value,
                        cancelled_at=datetime.now(UTC),
                    )
                )
            else:
                statement = (
                    update(TripAnalytics)
                    .where(TripAnalytics.id == analytics.id)
                    .values(active_tracking_seconds=121)
                )
            await session.execute(statement)
            await session.commit()

    async def force_interleaving() -> None:
        create_task = asyncio.create_task(create_assignment())
        await aggregates_locked.wait()
        update_task = asyncio.create_task(change_aggregate())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(update_task), timeout=0.2)
        allow_create.set()
        await create_task
        await update_task

    asyncio.run(force_interleaving())
