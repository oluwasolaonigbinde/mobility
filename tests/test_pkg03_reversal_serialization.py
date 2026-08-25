"""PostgreSQL barriers for receipt reversal versus campaign authority consumers."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_financial_authority import _fixture, _funded_terms
from test_payouts_v2 import create_v2_rule
from test_payouts_v3 import create_revision_row, insert_binding
from test_trips import create_trip_ready_graph

from app.models.billing import PaymentReceipt, ReceiptLifecycleEvent, ReceiptLifecycleStatus
from app.models.campaign import CampaignStatus
from app.models.trip import TripSession
from app.schemas.trips import TripStartRequest
from app.services.billing import (
    record_expedited_production_waiver,
    record_production_start,
    reserve_assignment_liability,
    reverse_payment_receipt,
)
from app.services.campaigns import decide_campaign_review, submit_campaign_for_review
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
) -> None:
    admin, owner, organization, campaign = _fixture(
        postgis_db_sessionmaker, "activation-reversal-race"
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
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
            await session.commit()
            return allocation.receipt_id

    receipt_id = asyncio.run(setup())

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
            await submit_campaign_for_review(
                activation_session,
                user_id=owner.id,
                campaign_id=campaign.id,
            )
            activated = await decide_campaign_review(
                activation_session,
                admin_user_id=admin.id,
                campaign_id=campaign.id,
                target_status=CampaignStatus.APPROVED,
            )
            await activation_session.commit()
            await reversal
            return activated.updated_at

    activated_at = asyncio.run(race())
    reversed_at = asyncio.run(_reversal_time(postgis_db_sessionmaker, receipt_id))
    assert reversed_at is not None and activated_at <= reversed_at


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
