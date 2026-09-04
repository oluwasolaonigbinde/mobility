import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import (
    create_test_campaign_creative,
    create_test_campaign_zone,
    create_test_display_proof,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
    fetch_user_by_email,
)
from sqlalchemy import select
from test_campaign_assignments import create_postgres_offer
from test_payouts_v3 import create_revision_row
from test_trips import PASSWORD, create_trip_ready_graph

import app.services.campaign_assignments as assignments_service
import app.services.campaign_changes as changes_service
from app.core.errors import AppError
from app.models.campaign import Campaign, CreativeStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.payout import AssignmentRuleBinding, CampaignPayoutRuleRevision
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from app.schemas.campaign_changes import CampaignChangeCreate
from app.schemas.trips import TripStartRequest
from app.services.billing import reserve_assignment_liability
from app.services.payout_rule_serialization import database_clock
from app.services.trips import start_driver_trip


def test_campaign_extension_and_trip_start_serialize_on_frozen_assignment_window(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
) -> None:
    frozen_end = datetime.now(UTC) + timedelta(seconds=8)
    admin, campaign, old_driver, _, _, old_assignment = create_trip_ready_graph(
        postgis_db_sessionmaker,
        end_at=frozen_end,
        admin_email="r31-admin@example.com",
        advertiser_email="r31-advertiser@example.com",
        driver_email="r31-old-driver@example.com",
        plate_number="R31-OLD",
    )
    advertiser = fetch_user_by_email(
        postgis_db_sessionmaker,
        "r31-advertiser@example.com",
    )
    assert advertiser is not None

    creative = create_test_campaign_creative(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )
    create_test_campaign_zone(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )

    async def prepare_fresh_offer_authority() -> UUID:
        async with postgis_db_sessionmaker() as session:
            old_binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == old_assignment.id
                )
            )
            assert old_binding is not None
            old_revision = await session.get(
                CampaignPayoutRuleRevision,
                old_binding.revision_id,
            )
            assert old_revision is not None
            current_campaign = await session.get(Campaign, campaign.id)
            assert current_campaign is not None
            current_campaign.campaign_metadata = {
                **(current_campaign.campaign_metadata or {}),
                "_test_creative_id": str(creative.id),
            }
            await session.commit()
            return old_revision.payout_rule_id

    payout_rule_id = asyncio.run(prepare_fresh_offer_authority())
    campaign.campaign_metadata = {
        **(campaign.campaign_metadata or {}),
        "_test_creative_id": str(creative.id),
    }
    create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=payout_rule_id,
        created_by_user_id=admin.id,
        number=2,
        effective_from=datetime.now(UTC) - timedelta(seconds=1),
        base="1.00",
        premium="1.50",
        cap="1.00",
    )

    requested_end = frozen_end + timedelta(days=2)

    async def request_extension() -> UUID:
        async with postgis_db_sessionmaker() as session:
            request = await changes_service.request_campaign_change(
                session,
                actor_user_id=advertiser.id,
                campaign_id=campaign.id,
                payload=CampaignChangeCreate(
                    client_request_id=uuid4(),
                    end_at=requested_end,
                    reason="Extend funded campaign work by two days",
                ),
            )
            await session.commit()
            return request.id

    request_id = asyncio.run(request_extension())

    async def wait_for_frozen_end() -> None:
        while True:
            async with postgis_db_sessionmaker() as session:
                now = await database_clock(session)
            remaining = (frozen_end - now).total_seconds()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.1))

    asyncio.run(wait_for_frozen_end())

    extension_has_lock = asyncio.Event()
    release_extension = asyncio.Event()
    acquire_campaign_terms_lock = changes_service.acquire_campaign_terms_lock

    async def pause_extension_with_real_lock(session, campaign_id) -> None:
        await acquire_campaign_terms_lock(session, campaign_id)
        extension_has_lock.set()
        await release_extension.wait()

    monkeypatch.setattr(
        changes_service,
        "acquire_campaign_terms_lock",
        pause_extension_with_real_lock,
    )

    async def approve_extension() -> None:
        async with postgis_db_sessionmaker() as session:
            request = await changes_service.decide_campaign_change(
                session,
                actor_user_id=admin.id,
                request_id=request_id,
                approve=True,
                reason="Approve funded two-day campaign extension",
            )
            assert request.status == "applied"
            await session.commit()

    async def start_old_assignment() -> AppError:
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AppError) as caught:
                await start_driver_trip(
                    session,
                    user_id=old_driver.id,
                    payload=TripStartRequest(
                        assignment_id=old_assignment.id,
                        evidence_protocol_version=2,
                    ),
                    settings=settings,
                )
            await session.rollback()
            return caught.value

    async def force_overlap() -> tuple[AppError, bool]:
        extension_task = asyncio.create_task(approve_extension())
        await asyncio.wait_for(extension_has_lock.wait(), timeout=5)
        start_task = asyncio.create_task(start_old_assignment())
        await asyncio.sleep(0.1)
        serialized = not start_task.done()
        release_extension.set()
        error, _ = await asyncio.wait_for(
            asyncio.gather(start_task, extension_task),
            timeout=10,
        )
        return error, serialized

    error, serialized = asyncio.run(force_overlap())
    assert serialized is True
    assert (error.code, error.status_code) == (
        "ASSIGNMENT_PAYOUT_WINDOW_EXPIRED",
        409,
    )

    async def extension_state() -> tuple[datetime, datetime, int]:
        async with postgis_db_sessionmaker() as session:
            current_campaign = await session.get(Campaign, campaign.id)
            old_binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == old_assignment.id
                )
            )
            assert current_campaign is not None
            assert old_binding is not None
            binding_count = len(
                list(
                    await session.scalars(
                        select(AssignmentRuleBinding).where(
                            AssignmentRuleBinding.assignment_id == old_assignment.id
                        )
                    )
                )
            )
            return (
                current_campaign.end_at,
                old_binding.campaign_window_end_at,
                binding_count,
            )

    campaign_end, old_binding_end, old_binding_count = asyncio.run(extension_state())
    assert campaign_end == requested_end
    assert old_binding_end == frozen_end
    assert old_binding_count == 1

    fresh_driver = create_test_user(
        postgis_db_sessionmaker,
        email="r31-fresh-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    fresh_profile = create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=fresh_driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    fresh_vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=fresh_profile.id,
        plate_number="R31-NEW",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    fresh_assignment_id = create_postgres_offer(
        postgis_db_sessionmaker,
        settings,
        admin,
        campaign,
        fresh_profile,
        fresh_vehicle,
    )

    async def accept_and_activate_fresh_assignment() -> AssignmentRuleBinding:
        async with postgis_db_sessionmaker() as session:
            await assignments_service.accept_driver_assignment(
                session,
                user_id=fresh_driver.id,
                assignment_id=fresh_assignment_id,
                payload=CampaignAssignmentTransition(metadata={}),
                settings=settings,
            )
            assignment = await session.get(CampaignAssignment, fresh_assignment_id)
            assert assignment is not None
            assignment.status = CampaignAssignmentStatus.ACTIVE.value
            assignment.activated_at = await database_clock(session)
            await session.commit()
            binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == fresh_assignment_id
                )
            )
            assert binding is not None
            return binding

    fresh_binding = asyncio.run(accept_and_activate_fresh_assignment())
    create_test_display_proof(
        postgis_db_sessionmaker,
        assignment_id=fresh_assignment_id,
        reviewed_by_user_id=admin.id,
    )

    async def reserve_and_start_fresh_assignment():
        async with postgis_db_sessionmaker() as session:
            await reserve_assignment_liability(
                session,
                assignment_id=fresh_assignment_id,
                actor_user_id=admin.id,
            )
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            trip = await start_driver_trip(
                session,
                user_id=fresh_driver.id,
                payload=TripStartRequest(
                    assignment_id=fresh_assignment_id,
                    evidence_protocol_version=2,
                ),
                settings=settings,
            )
            await session.commit()
            return trip

    fresh_trip = asyncio.run(reserve_and_start_fresh_assignment())
    assert fresh_binding.campaign_window_frozen is True
    assert fresh_binding.campaign_window_end_at == requested_end
    assert fresh_binding.formula_version == "payout_v3"
    assert Decimal(fresh_binding.hourly_rate_naira) > 0
    assert Decimal(fresh_binding.daily_payable_hours_cap) > 0
    assert fresh_trip.started_at < requested_end
