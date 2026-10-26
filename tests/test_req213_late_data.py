"""REQ-213: late GPS never changes any calculated driver/campaign day."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_trip_session
from payout_fixtures import PASSWORD, build_v4_graph, drive
from sqlalchemy import func, select

from app.models.audit import AuditEvent
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import LocationPing, LocationPingBatch, TripSession, TripSessionStatus
from app.services.trip_evidence import verify_batch_receipt


@pytest.mark.parametrize("other_trip,cross_midnight", [(False, False), (True, False), (True, True)])
def test_any_calculated_day_drops_late_gps_with_stable_signed_receipt(
    db_client, db_sessionmaker, settings, other_trip, cross_midnight
):
    graph = build_v4_graph(
        db_sessionmaker,
        settings,
        "late-day-" + uuid4().hex[:8],
        daily_rate_naira="0.01",
        daily_target_miles="1000.000",
    )
    drive(db_sessionmaker, settings, graph.trip)
    target = graph.trip
    if other_trip:
        target = create_test_trip_session(
            db_sessionmaker,
            assignment_id=graph.assignment.id,
            campaign_id=graph.campaign.id,
            driver_profile_id=graph.profile.id,
            vehicle_id=graph.vehicle.id,
            started_by_user_id=graph.driver.id,
            trip_status=TripSessionStatus.SEALED,
            started_at=graph.trip.started_at - timedelta(hours=10)
            if cross_midnight
            else graph.trip.started_at,
            ended_at=graph.trip.ended_at,
        )
    headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    captured = graph.trip.started_at.replace(microsecond=0)
    payload = {
        "idempotency_key": "after-calculation",
        "batch_sequence": 99,
        "pings": [
            {
                "recorded_at": captured.isoformat(),
                "lat": 6.45,
                "lon": 3.40,
                "accuracy_m": 5.0,
                "sequence_number": 999,
            }
        ],
        "metadata": {"arbitrary_gps_must_not_be_stored": {"lat": 51.5, "lon": 0.1}},
    }

    async def facts():
        async with db_sessionmaker() as session:
            trip = await session.get(TripSession, target.id)
            calcs = list(await session.scalars(select(PayoutCalculation)))
            return (
                trip.updated_at,
                [(r.id, r.final_payout, r.inputs_fingerprint, r.amount_by_day) for r in calcs],
                await session.scalar(select(func.count(LocationPing.id))),
                await session.scalar(select(func.count(EarningsLedgerEntry.id))),
            )

    before = asyncio.run(facts())
    assert before[1][0][1] == Decimal("0.00")
    path = f"/api/v1/driver/trips/{target.id}/pings"
    response = db_client.post(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "dropped" and body["evidence_scope"] == "late_dropped"
    assert (body["accepted_count"], body["rejected_count"], body["submitted_count"]) == (0, 1, 1)
    assert body["sample_results"][0]["rejection_code"] == "PAY_ALREADY_CALCULATED"
    retry = db_client.post(path, headers=headers, json=payload)
    assert retry.json() == {**body, "duplicate": True}
    conflict = db_client.post(
        path, headers=headers, json={**payload, "metadata": {"changed": True}}
    )
    assert conflict.status_code == 409
    assert asyncio.run(facts()) == before

    async def verify():
        async with db_sessionmaker() as session:
            batch = await session.scalar(
                select(LocationPingBatch).where(
                    LocationPingBatch.idempotency_key == "after-calculation"
                )
            )
            assert batch.batch_metadata == {}
            assert verify_batch_receipt(batch, settings)
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "trip.late_data.dropped"
                    )
                )
                == 1
            )

    asyncio.run(verify())


@pytest.mark.parametrize("upload_first", [False, True])
def test_late_upload_and_initial_calculation_serialize_both_orders(
    postgis_db_sessionmaker, settings, monkeypatch, upload_first
):
    from datetime import UTC, date, datetime

    from payout_fixtures import moving_points
    from test_trip_processing import add_pings, run_pipeline

    from app.core.errors import AppError
    from app.schemas.trips import LocationPingBatchCreate
    from app.services import trip_processing
    from app.services.payouts import common, engine
    from app.services.trips import ingest_location_ping_batch

    db = postgis_db_sessionmaker
    # No eligible points on the second Nigeria day, but the full trip overlaps it.
    start = datetime(2026, 7, 20, 21, 50, tzinfo=UTC)
    graph = build_v4_graph(
        db,
        settings,
        "late-race-" + uuid4().hex[:8],
        started_at=start,
        ended_at=start + timedelta(hours=3),
    )
    add_pings(
        db,
        trip_id=graph.trip.id,
        points=moving_points(start, minutes=30),
        idempotency_key="before-calculation",
    )

    async def stop_before_money(*args, **kwargs):
        raise AppError(
            "PAYOUT_BINDING_NOT_FOUND", "Pause the synthetic pipeline before money", status_code=409
        )

    with monkeypatch.context() as prepare:
        prepare.setattr(trip_processing, "calculate_trip_payout", stop_before_money)
        assert run_pipeline(db, graph.trip.id, settings).overall == "partial"
    recorded = datetime(2026, 7, 20, 23, 10, tzinfo=UTC)
    target = create_test_trip_session(
        db,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=recorded,
        ended_at=recorded + timedelta(minutes=5),
    )
    payload = LocationPingBatchCreate.model_validate(
        {
            "idempotency_key": "racing-late",
            "batch_sequence": 0,
            "pings": [
                {
                    "recorded_at": recorded.isoformat(),
                    "lat": 6.45,
                    "lon": 3.4,
                    "accuracy_m": 5,
                    "sequence_number": 1,
                }
            ],
        }
    )

    async def race():
        acquired = asyncio.Event()
        release = asyncio.Event()
        leader = None
        actual = common.acquire_paycap_lock
        calculator_keys = []

        async def controlled(session, key):
            await actual(session, key)
            if asyncio.current_task().get_name() == "calculator":
                calculator_keys.append(key)
            if asyncio.current_task() is leader and not acquired.is_set():
                acquired.set()
                await release.wait()

        monkeypatch.setattr(common, "acquire_paycap_lock", controlled)
        monkeypatch.setattr(engine, "acquire_paycap_lock", controlled)

        async def upload():
            async with db() as session:
                outcome = await ingest_location_ping_batch(
                    session,
                    user_id=graph.driver.id,
                    trip_id=target.id,
                    payload=payload,
                    settings=settings,
                )
                scope = outcome.batch.evidence_scope
                await session.commit()
                return scope

        async def calculate():
            async with db() as session:
                outcome = await engine.calculate_trip_payout(
                    session,
                    trip_id=graph.trip.id,
                    payout_rule_id=None,
                    metadata={},
                    settings=settings,
                )
                await session.commit()
                return outcome[0].id

        first = asyncio.create_task(
            upload() if upload_first else calculate(),
            name="upload" if upload_first else "calculator",
        )
        leader = first
        await asyncio.wait_for(acquired.wait(), 10)
        second = asyncio.create_task(
            calculate() if upload_first else upload(),
            name="calculator" if upload_first else "upload",
        )
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(second), 0.1)
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 15)
        scope = results[0] if upload_first else results[1]
        assert scope == ("late" if upload_first else "late_dropped")
        assert (
            common.paycap_lock_key(graph.profile.id, graph.campaign.id, date(2026, 7, 21))
            in calculator_keys
        )
        async with db() as session:
            count = await session.scalar(
                select(func.count(LocationPing.id)).where(LocationPing.trip_session_id == target.id)
            )
            assert count == (1 if upload_first else 0)
            assert await session.scalar(select(func.count(PayoutCalculation.id))) == 1

    asyncio.run(race())
