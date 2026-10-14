import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import (
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import text
from test_trips import create_trip_ready_graph, ping_payload

from app.core.errors import AppError
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.schemas.trips import LocationPingBatchCreate
from app.services import campaign_cancellations, trips
from app.services.payout_rule_serialization import acquire_campaign_terms_lock


async def wait_blocked(db, pid):
    async def observe():
        while True:
            async with db() as session:
                if await session.scalar(
                    text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid}
                ):
                    return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(observe(), 10)


def setup_trip(db):
    _, campaign, driver, profile, vehicle, assignment = create_trip_ready_graph(
        db, with_financial_authority=False
    )
    now = datetime.now(UTC).replace(microsecond=0)
    trip = create_test_trip_session(
        db,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        started_at=now - timedelta(minutes=1),
    )
    return campaign, driver, trip, now


@pytest.mark.parametrize("same_trip", [False, True])
def test_ingestion_readers_share_campaign_but_serialize_one_trip(
    db_sessionmaker, settings, monkeypatch, same_trip
):
    campaign, driver, first, now = setup_trip(db_sessionmaker)
    second = first
    if not same_trip:
        other_driver = create_test_user(
            db_sessionmaker, email="second-reader@example.com", role="driver"
        )
        profile = create_test_driver_profile(
            db_sessionmaker, user_id=other_driver.id, onboarding_status="active"
        )
        vehicle = create_test_vehicle(
            db_sessionmaker,
            driver_profile_id=profile.id,
            plate_number="SECOND-READER",
            vehicle_status="active",
        )
        assignment = create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=campaign.created_by_user_id,
            assignment_status=CampaignAssignmentStatus.ACTIVE,
            accepted_at=now - timedelta(minutes=6),
            activated_at=now - timedelta(minutes=5),
        )
        second = create_test_trip_session(
            db_sessionmaker,
            assignment_id=assignment.id,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            started_by_user_id=other_driver.id,
            started_at=now - timedelta(minutes=3),
        )
    original = trips.campaign_financial_cutoff

    async def exercise():
        first_locked, second_locked, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}

        async def cutoff(session, campaign_id):
            if asyncio.current_task().get_name() == "first-reader":
                first_locked.set()
                await release.wait()
            else:
                second_locked.set()
            return await original(session, campaign_id)

        monkeypatch.setattr(trips, "campaign_financial_cutoff", cutoff)

        async def ingest(trip):
            async with db_sessionmaker() as session:
                pids[asyncio.current_task().get_name()] = await session.scalar(
                    text("SELECT pg_backend_pid()")
                )
                moment = now if trip is first else trip.started_at + timedelta(seconds=1)
                result = await trips.ingest_location_ping_batch(
                    session,
                    user_id=trip.started_by_user_id,
                    trip_id=trip.id,
                    payload=LocationPingBatchCreate.model_validate(ping_payload(moment)),
                    settings=settings,
                )
                await session.commit()
                return result

        first_task = asyncio.create_task(ingest(first), name="first-reader")
        second_task = None
        try:
            await asyncio.wait_for(first_locked.wait(), 10)
            second_task = asyncio.create_task(ingest(second), name="second-reader")
            while "second-reader" not in pids:
                await asyncio.sleep(0)
            if same_trip:
                await wait_blocked(db_sessionmaker, pids["second-reader"])
                assert not second_locked.is_set()
            else:
                await asyncio.wait_for(second_locked.wait(), 10)
                await asyncio.wait_for(asyncio.shield(second_task), 10)
            # A terms writer must wait for the first reader in both cases.
            async with db_sessionmaker() as writer:
                pid = await writer.scalar(text("SELECT pg_backend_pid()"))
                writer_task = asyncio.create_task(acquire_campaign_terms_lock(writer, campaign.id))
                await wait_blocked(db_sessionmaker, pid)
                assert not writer_task.done()
                release.set()
                await asyncio.wait_for(asyncio.gather(first_task, second_task, writer_task), 10)
                await writer.rollback()
            assert second_locked.is_set()
        finally:
            release.set()
            pending = [
                task for task in (first_task, second_task) if task is not None and not task.done()
            ]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("writer_first", [False, True])
def test_cancellation_and_ingestion_observe_lock_order(
    db_sessionmaker, settings, monkeypatch, writer_first
):
    campaign, driver, trip, now = setup_trip(db_sessionmaker)
    cutoff = now + timedelta(milliseconds=-1 if writer_first else 1)
    original_read = trips.acquire_campaign_terms_shared_lock
    original_write = campaign_cancellations.acquire_campaign_terms_lock

    async def exercise():
        held, release = asyncio.Event(), asyncio.Event()
        pids = {}

        async def read_lock(session, campaign_id):
            await original_read(session, campaign_id)
            if not writer_first:
                held.set()
                await release.wait()

        async def write_lock(session, campaign_id):
            await original_write(session, campaign_id)
            if writer_first:
                held.set()
                await release.wait()

        async def clock(session):
            return cutoff

        monkeypatch.setattr(trips, "acquire_campaign_terms_shared_lock", read_lock)
        monkeypatch.setattr(campaign_cancellations, "acquire_campaign_terms_lock", write_lock)
        monkeypatch.setattr(campaign_cancellations, "database_clock", clock)

        async def cancel():
            async with db_sessionmaker() as session:
                pids["cancel"] = await session.scalar(text("SELECT pg_backend_pid()"))
                await campaign_cancellations.request_campaign_cancellation(
                    session,
                    actor_user_id=campaign.created_by_user_id,
                    campaign_id=campaign.id,
                    payload=CampaignCancellationCreate(
                        client_request_id=uuid4(), reason="Lock ordering"
                    ),
                )
                await session.commit()

        async def ingest():
            async with db_sessionmaker() as session:
                pids["ingest"] = await session.scalar(text("SELECT pg_backend_pid()"))
                try:
                    result = await trips.ingest_location_ping_batch(
                        session,
                        user_id=driver.id,
                        trip_id=trip.id,
                        payload=LocationPingBatchCreate.model_validate(ping_payload(now)),
                        settings=settings,
                    )
                    await session.commit()
                    return result.batch.pings_accepted
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        first = asyncio.create_task(cancel() if writer_first else ingest())
        second = None
        try:
            await asyncio.wait_for(held.wait(), 10)
            second = asyncio.create_task(ingest() if writer_first else cancel())
            key = "ingest" if writer_first else "cancel"
            while key not in pids:
                await asyncio.sleep(0)
            await wait_blocked(db_sessionmaker, pids[key])
            release.set()
            results = await asyncio.wait_for(asyncio.gather(first, second), 10)
            assert results[1 if writer_first else 0] == (
                "INVALID_ASSIGNMENT_AUTHORITY" if writer_first else 1
            )
        finally:
            release.set()
            pending = [task for task in (first, second) if task is not None and not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    asyncio.run(exercise())
