"""PostgreSQL barriers for receipt reversal versus campaign authority consumers."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from conftest import create_test_display_proof
from sqlalchemy import select
from test_campaign_assignments import create_assignment_ready_graph, create_postgres_offer
from test_financial_authority import _fixture, _funded_terms
from test_payouts_v2 import create_v2_rule
from test_payouts_v3 import create_revision_row, insert_binding
from test_trips import create_trip_ready_graph

from app.core.errors import AppError
from app.models.billing import PaymentReceipt, ReceiptLifecycleEvent, ReceiptLifecycleStatus
from app.models.campaign import CampaignReviewEvent, CampaignStatus
from app.models.campaign_assignment import CampaignActivationEvent
from app.models.payout import CampaignPayoutRuleRevision
from app.models.trip import TripSession
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from app.schemas.trips import TripStartRequest
from app.services.billing import (
    assert_new_work_authorized,
    record_expedited_production_waiver,
    record_production_start,
    reserve_assignment_liability,
    reverse_payment_receipt,
)
from app.services.campaign_assignments import (
    accept_driver_assignment,
    activate_admin_assignment,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock
from app.services.trips import start_driver_trip


async def _blocked_reversal(
    sessionmaker, *, receipt_id, admin_id, receipt_locked: asyncio.Event
):
    async with sessionmaker() as session:
        await session.scalar(
            select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
        )
        receipt_locked.set()
        await reverse_payment_receipt(
            session,
            receipt_id=receipt_id,
            actor_user_id=admin_id,
            reason="forced serialization",
        )
        await session.commit()


async def _reversal_time(sessionmaker, receipt_id):
    async with sessionmaker() as session:
        return await session.scalar(
            select(ReceiptLifecycleEvent.occurred_at).where(
                ReceiptLifecycleEvent.receipt_id == receipt_id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
            )
        )


def test_production_start_commits_before_waiting_reversal_cutoff(
    postgis_db_sessionmaker,
) -> None:
    admin, owner, organization, campaign = _fixture(
        postgis_db_sessionmaker, "production-reversal-race"
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="PRODUCTION-REVERSAL-RACE",
            )
            waiver = await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version="race-v1",
                accepted_wording="I request expedited production.",
            )
            await session.commit()
            return allocation.receipt_id, waiver.id

    receipt_id, waiver_id = asyncio.run(setup())

    async def race():
        async with postgis_db_sessionmaker() as start_session:
            await acquire_campaign_terms_lock(start_session, campaign.id)
            receipt_locked = asyncio.Event()
            reversal = asyncio.create_task(
                _blocked_reversal(
                    postgis_db_sessionmaker,
                    receipt_id=receipt_id,
                    admin_id=admin.id,
                    receipt_locked=receipt_locked,
                )
            )
            await receipt_locked.wait()
            production = await record_production_start(
                start_session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver_id,
            )
            await start_session.commit()
            await reversal
            return production.started_at

    started_at = asyncio.run(race())
    reversed_at = asyncio.run(_reversal_time(postgis_db_sessionmaker, receipt_id))
    assert reversed_at is not None and started_at <= reversed_at


def test_campaign_activation_commits_before_waiting_reversal_cutoff(
    postgis_db_sessionmaker,
    settings,
) -> None:
    now = datetime.now(UTC)
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        postgis_db_sessionmaker,
        campaign_status=CampaignStatus.ACTIVE,
        admin_email="activation-reversal-admin@example.com",
        advertiser_email="activation-reversal-owner@example.com",
        driver_email="activation-reversal-driver@example.com",
        plate_number="ACT-REV-1",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(days=2),
    )

    async def current_rule_id():
        async with postgis_db_sessionmaker() as session:
            return await session.scalar(
                select(CampaignPayoutRuleRevision.payout_rule_id)
                .where(CampaignPayoutRuleRevision.campaign_id == campaign.id)
                .order_by(CampaignPayoutRuleRevision.revision_number.desc())
                .limit(1)
            )

    rule_id = asyncio.run(current_rule_id())
    assert rule_id is not None
    create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=rule_id,
        created_by_user_id=admin.id,
        number=2,
        effective_from=now - timedelta(minutes=30),
        base="1.00",
        premium="1.00",
        cap="1.00",
    )
    assignment_id = create_postgres_offer(
        postgis_db_sessionmaker, settings, admin, campaign, profile, vehicle
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            from app.models.organization import AdvertiserOrganization
            from app.models.user import User

            owner = await session.get(User, campaign.created_by_user_id)
            organization = await session.get(AdvertiserOrganization, campaign.organization_id)
            assert owner is not None and organization is not None
            await accept_driver_assignment(
                session,
                user_id=driver.id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            reviewed_snapshot = {"campaign_id": str(campaign.id), "synthetic_test": True}
            submission = CampaignReviewEvent(
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                prior_status=CampaignStatus.DRAFT.value,
                new_status=CampaignStatus.PENDING_REVIEW.value,
                reviewed_snapshot=reviewed_snapshot,
                reviewed_snapshot_sha256="a" * 64,
            )
            session.add(submission)
            await session.flush()
            session.add(
                CampaignReviewEvent(
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    prior_status=CampaignStatus.PENDING_REVIEW.value,
                    new_status=CampaignStatus.APPROVED.value,
                    submission_event_id=submission.id,
                )
            )
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="ACTIVATION-REVERSAL-RACE",
            )
            waiver = await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version="race-v1",
                accepted_wording="I request expedited production.",
            )
            await record_production_start(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver.id,
            )
            await reserve_assignment_liability(
                session,
                assignment_id=assignment_id,
                actor_user_id=admin.id,
            )
            await session.commit()
            return allocation.receipt_id

    receipt_id = asyncio.run(setup())
    create_test_display_proof(
        postgis_db_sessionmaker,
        assignment_id=assignment_id,
        reviewed_by_user_id=admin.id,
    )

    async def race():
        async with postgis_db_sessionmaker() as activation_session:
            await acquire_campaign_terms_lock(activation_session, campaign.id)
            receipt_locked = asyncio.Event()
            reversal = asyncio.create_task(
                _blocked_reversal(
                    postgis_db_sessionmaker,
                    receipt_id=receipt_id,
                    admin_id=admin.id,
                    receipt_locked=receipt_locked,
                )
            )
            await receipt_locked.wait()
            activated = await activate_admin_assignment(
                activation_session,
                admin_user_id=admin.id,
                assignment_id=assignment_id,
                payload=CampaignAssignmentTransition(),
                settings=settings,
            )
            await activation_session.commit()
            await reversal
            return activated.id

    activated_id = asyncio.run(race())
    reversed_at = asyncio.run(_reversal_time(postgis_db_sessionmaker, receipt_id))

    async def activation_time_and_current_authority():
        async with postgis_db_sessionmaker() as session:
            activated_at = await session.scalar(
                select(CampaignActivationEvent.occurred_at).where(
                    CampaignActivationEvent.assignment_id == activated_id,
                    CampaignActivationEvent.event_type == "activated",
                )
            )
            with pytest.raises(AppError) as invalidated:
                await assert_new_work_authorized(
                    session,
                    campaign_id=campaign.id,
                    assignment_id=assignment_id,
                )
            return activated_at, invalidated.value.code

    activated_at, invalidated_code = asyncio.run(activation_time_and_current_authority())
    assert activated_at is not None and reversed_at is not None and activated_at <= reversed_at
    assert invalidated_code == "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED"


def test_trip_start_commits_before_waiting_reversal_cutoff(
    postgis_db_sessionmaker, settings
) -> None:
    admin, campaign, driver, _, _, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker,
        admin_email="trip-reversal-admin@example.com",
        advertiser_email="trip-reversal-owner@example.com",
        driver_email="trip-reversal-driver@example.com",
        plate_number="TR-REV-1",
        start_at=datetime.now(UTC) - timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=1),
        with_financial_authority=False,
    )
    owner_id = campaign.created_by_user_id
    organization_id = campaign.organization_id
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        hourly_rate="1.00",
        daily_cap_hours="1.00",
        rule_status="inactive",
    )
    revision = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=rule.id,
        created_by_user_id=admin.id,
        base="1.00",
        premium=None,
        cap="1.00",
    )
    insert_binding(
        postgis_db_sessionmaker,
        settings,
        assignment_id=assignment.id,
        revision=revision,
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            from app.models.organization import AdvertiserOrganization
            from app.models.user import User

            owner = await session.get(User, owner_id)
            organization = await session.get(AdvertiserOrganization, organization_id)
            assert owner is not None and organization is not None
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="TRIP-REVERSAL-RACE",
            )
            waiver = await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version="race-v1",
                accepted_wording="I request expedited production.",
            )
            await record_production_start(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver.id,
            )
            await reserve_assignment_liability(
                session, assignment_id=assignment.id, actor_user_id=admin.id
            )
            await session.commit()
            return allocation.receipt_id

    receipt_id = asyncio.run(setup())

    async def race():
        async with postgis_db_sessionmaker() as trip_session:
            await acquire_campaign_terms_lock(trip_session, campaign.id)
            receipt_locked = asyncio.Event()
            reversal = asyncio.create_task(
                _blocked_reversal(
                    postgis_db_sessionmaker,
                    receipt_id=receipt_id,
                    admin_id=admin.id,
                    receipt_locked=receipt_locked,
                )
            )
            await receipt_locked.wait()
            trip = await start_driver_trip(
                trip_session,
                user_id=driver.id,
                payload=TripStartRequest(assignment_id=assignment.id, metadata={}),
                settings=settings,
            )
            await trip_session.commit()
            await reversal
            return trip.id

    trip_id = asyncio.run(race())

    async def times():
        async with postgis_db_sessionmaker() as session:
            trip = await session.get(TripSession, trip_id)
            return trip.started_at if trip else None

    started_at = asyncio.run(times())
    reversed_at = asyncio.run(_reversal_time(postgis_db_sessionmaker, receipt_id))
    assert started_at is not None and reversed_at is not None and started_at <= reversed_at
