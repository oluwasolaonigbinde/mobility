import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_creative,
    create_test_campaign_payout_revision,
    create_test_campaign_zone,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.services.campaign_assignments as assignments_service
from app.core.errors import AppError
from app.models.campaign import CampaignStatus, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from tests.test_campaign_assignments import (
    FUTURE,
    PAST,
    create_assignment_ready_graph,
    create_postgres_offer,
)


class _NamedConstraintError(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__(f'constraint "{constraint_name}"')
        self.constraint_name = constraint_name


class _FailingFlushSession:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name
        self.rolled_back = False

    async def flush(self) -> None:
        raise IntegrityError(
            "UPDATE campaign_assignments",
            {},
            _NamedConstraintError(self.constraint_name),
        )

    async def rollback(self) -> None:
        self.rolled_back = True


def test_named_driver_conflict_translates_to_stable_409() -> None:
    session = _FailingFlushSession("uq_campaign_assignments_driver_active")

    with pytest.raises(AppError) as caught:
        asyncio.run(assignments_service.flush_translating_exclusivity_conflict(session))

    assert (caught.value.code, caught.value.status_code) == (
        "ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER",
        409,
    )
    assert session.rolled_back is True


def test_unknown_assignment_constraint_is_re_raised() -> None:
    session = _FailingFlushSession("uq_unrelated")

    with pytest.raises(IntegrityError):
        asyncio.run(assignments_service.flush_translating_exclusivity_conflict(session))

    assert session.rolled_back is False


def test_database_rejects_two_active_assignments_for_one_driver(
    postgis_db_sessionmaker,
) -> None:
    admin, campaign, _, profile, first_vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        admin_email="r29-direct-admin@example.com",
        advertiser_email="r29-direct-advertiser@example.com",
        driver_email="r29-direct-driver@example.com",
        plate_number="R29-001",
    )
    second_vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="R29-002",
        vehicle_status=VehicleStatus.ACTIVE,
    )

    async def insert_duplicates() -> None:
        now = datetime.now(UTC)
        async with postgis_db_sessionmaker() as session:
            session.add_all(
                [
                    CampaignAssignment(
                        campaign_id=campaign.id,
                        driver_profile_id=profile.id,
                        vehicle_id=vehicle_id,
                        assigned_by_user_id=admin.id,
                        status=CampaignAssignmentStatus.ACTIVE.value,
                        offered_at=now,
                    )
                    for vehicle_id in (first_vehicle.id, second_vehicle.id)
                ]
            )
            with pytest.raises(
                IntegrityError,
                match="uq_campaign_assignments_driver_active",
            ):
                await session.commit()

    asyncio.run(insert_duplicates())


def test_concurrent_activation_and_deactivate_reactivate_are_driver_exclusive(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    admin, first_campaign, driver, profile, first_vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        admin_email="r29-race-admin@example.com",
        advertiser_email="r29-race-first-advertiser@example.com",
        driver_email="r29-race-driver@example.com",
        plate_number="R29-R01",
    )
    advertiser = create_test_user(
        postgis_db_sessionmaker,
        email="r29-race-second-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        postgis_db_sessionmaker,
        name="R29 second advertiser",
        owner_user_id=advertiser.id,
    )
    second_campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="R29 second campaign",
        campaign_status=CampaignStatus.ACTIVE,
        start_at=PAST,
        end_at=FUTURE,
    )
    second_creative = create_test_campaign_creative(
        postgis_db_sessionmaker,
        campaign_id=second_campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )
    create_test_campaign_payout_revision(
        postgis_db_sessionmaker,
        campaign_id=second_campaign.id,
        created_by_user_id=admin.id,
        effective_from=PAST,
    )
    create_test_campaign_zone(
        postgis_db_sessionmaker,
        campaign_id=second_campaign.id,
        created_by_user_id=admin.id,
    )
    second_campaign.campaign_metadata["_test_creative_id"] = str(second_creative.id)
    second_vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="R29-R02",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment_ids = [
        create_postgres_offer(
            postgis_db_sessionmaker,
            settings,
            admin,
            campaign,
            profile,
            vehicle,
        )
        for campaign, vehicle in (
            (first_campaign, first_vehicle),
            (second_campaign, second_vehicle),
        )
    ]

    async def accept(assignment_id: UUID) -> None:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.accept_driver_assignment(
                session,
                user_id=driver.id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(metadata={}),
                settings=settings,
            )
            await session.commit()

    for assignment_id in assignment_ids:
        asyncio.run(accept(assignment_id))

    async def review_passes(*_args, **_kwargs):
        return SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000011"))

    async def reserve_success(*_args, **_kwargs):
        return SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000012"),
            status="reserved",
        )

    async def authority_passes(*_args, **_kwargs):
        return SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000013"))

    async def evidence_passes(*_args, **_kwargs):
        return SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000014"),
            revision=1,
        )

    async def production_start_passes(*_args, **_kwargs):
        return SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000015"),
            authority_basis="approved_credit",
            waiver_id=None,
        )

    monkeypatch.setattr(assignments_service, "ensure_campaign_review_approved", review_passes)
    monkeypatch.setattr(assignments_service, "reserve_assignment_liability", reserve_success)
    monkeypatch.setattr(
        assignments_service,
        "assert_campaign_production_authorized",
        authority_passes,
    )
    monkeypatch.setattr(assignments_service, "assert_new_work_authorized", authority_passes)
    monkeypatch.setattr(
        assignments_service,
        "ensure_current_approved_installation_evidence",
        evidence_passes,
    )
    monkeypatch.setattr(
        assignments_service,
        "activation_production_start",
        production_start_passes,
    )

    async def activate(assignment_id: UUID) -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await assignments_service.activate_admin_assignment(
                    session,
                    admin_user_id=admin.id,
                    assignment_id=assignment_id,
                    payload=CampaignAssignmentTransition(metadata={}),
                    settings=settings,
                )
                await session.commit()
                return "active"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def activate_concurrently() -> list[str]:
        return list(
            await asyncio.wait_for(
                asyncio.gather(*(activate(assignment_id) for assignment_id in assignment_ids)),
                timeout=10,
            )
        )

    outcomes = asyncio.run(activate_concurrently())
    assert sorted(outcomes) == ["ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER", "active"]

    async def active_assignment_id() -> UUID:
        async with postgis_db_sessionmaker() as session:
            result = await session.scalar(
                select(CampaignAssignment.id).where(
                    CampaignAssignment.status == CampaignAssignmentStatus.ACTIVE.value
                )
            )
            assert result is not None
            return result

    first_active_id = asyncio.run(active_assignment_id())
    next_id = next(item for item in assignment_ids if item != first_active_id)

    async def deactivate(assignment_id: UUID) -> None:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.deactivate_driver_assignment(
                session,
                user_id=driver.id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(metadata={}),
            )
            await session.commit()

    asyncio.run(deactivate(first_active_id))
    assert asyncio.run(activate(next_id)) == "active"
    assert asyncio.run(activate(first_active_id)) == "ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER"
