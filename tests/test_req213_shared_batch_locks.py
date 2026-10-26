"""REQ-213: multi-driver corrections lock every batch before any driver row."""

import asyncio
from datetime import UTC, datetime, timedelta
from math import sin
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import create_test_campaign_assignment
from payout_fixtures import (
    build_v4_graph,
    create_signed_v2_test_trip_session,
    drive,
    insert_v4_binding,
)
from sqlalchemy import select, text
from test_payout_corrections import RELEASE_AT, create_order
from test_r21_final_authorization_postgresql import _prepare_cross_trip_batch

from app.adapters.disbursement import FakeDisbursementAdapter
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.disbursement import PayoutBatchLine
from app.models.payout import EarningsLedgerEntry
from app.models.trip_analytics import TripAnalytics
from app.services import disbursements, payout_balances, payout_corrections
from app.services.disbursements import poll_payout_line, process_payout_submission_intent


def test_multi_driver_correction_waits_for_shared_batch_before_any_driver_lock(
    postgis_db_sessionmaker, settings, monkeypatch
):
    db = postgis_db_sessionmaker
    graphs = [build_v4_graph(db, settings, uuid4().hex[:8] + "-shared-lock") for _ in range(2)]
    low, high = sorted(graphs, key=lambda g: str(g.profile.id))
    drive(db, settings, low.trip)

    def other_campaign_trip(campaign_graph, driver_graph):
        start = campaign_graph.trip.started_at
        assignment = create_test_campaign_assignment(
            db,
            campaign_id=campaign_graph.campaign.id,
            driver_profile_id=driver_graph.profile.id,
            vehicle_id=driver_graph.vehicle.id,
            assigned_by_user_id=campaign_graph.admin.id,
            assignment_status=CampaignAssignmentStatus.CANCELLED,
            cancelled_at=campaign_graph.trip.ended_at + timedelta(minutes=5),
            accepted_at=start - timedelta(days=1),
            activated_at=start - timedelta(hours=1),
        )
        insert_v4_binding(
            db,
            settings,
            assignment_id=assignment.id,
            revision=campaign_graph.revision,
            zone_ids=[campaign_graph.zone.id],
        )
        trip = create_signed_v2_test_trip_session(
            db,
            settings,
            assignment_id=assignment.id,
            campaign_id=campaign_graph.campaign.id,
            driver_profile_id=driver_graph.profile.id,
            vehicle_id=driver_graph.vehicle.id,
            started_by_user_id=driver_graph.driver.id,
            started_at=start,
            ended_at=campaign_graph.trip.ended_at,
        )
        from payout_fixtures import moving_points
        from test_trip_processing import add_pings, run_pipeline

        points = []
        for index, (moment, _lat, _lon, accuracy) in enumerate(moving_points(start)):
            if campaign_graph is low:
                lat, lon = 6.45 + 0.005 * sin(index / 6), 3.39 + index * 0.00081
            else:
                lat, lon = 6.47 + index * 0.00065, 3.43 + 0.004 * sin(index / 3)
            points.append((moment, lat, lon, accuracy))
        add_pings(
            db, trip_id=trip.id, points=points, idempotency_key="distinct-route-" + trip.id.hex
        )
        assert run_pipeline(db, trip.id, settings).overall == "completed"

        async def analytics():
            async with db() as session:
                return await session.scalar(
                    select(TripAnalytics).where(TripAnalytics.trip_session_id == trip.id)
                )

        return SimpleNamespace(
            campaign=campaign_graph.campaign,
            admin=campaign_graph.admin,
            driver=driver_graph.driver,
            profile=driver_graph.profile,
            vehicle=driver_graph.vehicle,
            assignment=assignment,
            trip=trip,
            analytics=asyncio.run(analytics()),
        )

    high_in_x = other_campaign_trip(low, high)
    low_in_y = other_campaign_trip(high, low)
    fake = FakeDisbursementAdapter()

    async def prepare():
        batch_id, intents = await _prepare_cross_trip_batch(db, [low_in_y, high_in_x], fake)
        for intent_id in intents:
            assert (
                await process_payout_submission_intent(db, intent_id=intent_id, adapter=fake)
                == "resolved"
            )
        async with db() as session:
            line = await session.scalar(
                select(PayoutBatchLine).where(
                    PayoutBatchLine.batch_id == batch_id,
                    PayoutBatchLine.ledger_entry_id.in_(
                        select(EarningsLedgerEntry.id).where(
                            EarningsLedgerEntry.trip_session_id == low_in_y.trip.id
                        )
                    ),
                )
            )
            return line.id, line.provider_transfer_reference

    line_id, reference = asyncio.run(prepare())
    order = create_order(db, settings, low)

    async def race():
        batch_held = asyncio.Event()
        release = asyncio.Event()
        correction_driver = asyncio.Event()
        correction_before_chain = asyncio.Event()
        allow_correction_chain = asyncio.Event()
        reconcile_task = None
        correction_task = None
        real = payout_balances.lock_driver_money_scope
        real_chains = disbursements.lock_payout_chains
        pids = {}

        async def recon_scope(session, **kwargs):
            if asyncio.current_task() is reconcile_task:
                pids["reconcile"] = await session.scalar(text("SELECT pg_backend_pid()"))
                batch_held.set()
                await release.wait()
            return await real(session, **kwargs)

        async def correction_scope(session, **kwargs):
            if asyncio.current_task() is correction_task:
                correction_driver.set()
            return await real(session, **kwargs)

        async def correction_chains(session, **kwargs):
            if asyncio.current_task() is correction_task:
                correction_before_chain.set()
                await allow_correction_chain.wait()
            return await real_chains(session, **kwargs)

        monkeypatch.setattr(disbursements, "lock_driver_money_scope", recon_scope)
        monkeypatch.setattr(payout_balances, "lock_driver_money_scope", correction_scope)
        monkeypatch.setattr(disbursements, "lock_payout_chains", correction_chains)

        async def reconcile():
            fake.set_poll_result(
                provider_transfer_reference=reference,
                provider_event_id="shared-lock-success",
                outcome="succeeded",
                occurred_at=datetime.now(UTC),
            )
            async with db() as session:
                await poll_payout_line(
                    session,
                    line_id=line_id,
                    actor_user_id=high.admin.id,
                    reason="Verify shared-batch payment",
                    adapter=fake,
                )
                await session.commit()

        async def correct():
            async with db() as session:
                pids["correction"] = await session.scalar(text("SELECT pg_backend_pid()"))
                _, changed = await payout_corrections.approve_correction_order(
                    session,
                    order_id=order.id,
                    actor_user_id=low.admin.id,
                    reason="Apply verified campaign-day correction",
                    release_at=RELEASE_AT,
                    request_metadata={},
                    settings=settings,
                )
                await session.commit()
                return changed

        reconcile_task = asyncio.create_task(reconcile())
        await asyncio.wait_for(batch_held.wait(), 10)
        correction_task = asyncio.create_task(correct())
        try:
            await asyncio.wait_for(correction_before_chain.wait(), 10)
            assert not correction_driver.is_set()
            assert not correction_task.done()
            async with db() as observer:
                blocked = text("SELECT :leader = ANY(pg_blocking_pids(:follower))")
                owners = {"leader": pids["reconcile"], "follower": pids["correction"]}
                # An unfinished correction can still be before the database
                # lock. Reproduce that window instead of assuming100ms suffices.
                assert await observer.scalar(blocked, owners) is False
                allow_correction_chain.set()

                async def wait_for_batch_blocker():
                    while True:
                        assert not correction_driver.is_set()
                        if correction_task.done():
                            await correction_task  # surface any real domain/database error
                            pytest.fail("Correction finished before waiting for the held batch")
                        if await observer.scalar(blocked, owners):
                            assert not correction_driver.is_set()
                            return

                await asyncio.wait_for(wait_for_batch_blocker(), 10)
        finally:
            allow_correction_chain.set()
            release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(reconcile_task, correction_task), 15)
        assert outcomes[1] is True and correction_driver.is_set()

    asyncio.run(race())
