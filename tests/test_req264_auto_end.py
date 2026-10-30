"""REQ-264: an active trip with no location for 2 hours ends by itself."""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from starlette import status as http_status
from test_req259_fresh_device_trip import post_batch
from test_trip_seal import driver_headers, make_batch_payload
from test_trips import create_trip_ready_graph, start_trip

import app.jobs.trip_processing as jobs
from app.models.audit import AuditEvent
from app.models.trip import (
    LocationPingBatch,
    TripEvidenceManifestEntry,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.services.trip_evidence import verify_manifest_receipt
from app.services.trips import (
    TRIP_AUTO_END_NO_LOCATION_SECONDS,
    auto_end_inactive_trip,
    find_trips_to_auto_end,
    utc_now,
)

PAST_THRESHOLD = timedelta(seconds=TRIP_AUTO_END_NO_LOCATION_SECONDS + 1)


class RecordingEnqueuer:
    def __init__(self) -> None:
        self.trip_ids: list[UUID] = []

    async def enqueue_trip_processing(self, trip_id: UUID) -> None:
        self.trip_ids.append(trip_id)


def run_sweep(db_sessionmaker, settings, monkeypatch, *, later: timedelta = PAST_THRESHOLD):
    enqueuer = RecordingEnqueuer()
    monkeypatch.setattr(jobs, "build_trip_enqueuer", lambda _settings: enqueuer)
    future = utc_now() + later
    monkeypatch.setattr(jobs, "utc_now", lambda: future)
    result = asyncio.run(
        jobs.seal_ended_trips_job({"settings": settings, "sessionmaker": db_sessionmaker})
    )
    return result, enqueuer


def load(db_sessionmaker, trip_id: str):
    async def fetch():
        async with db_sessionmaker() as session:
            trip = await session.get(TripSession, UUID(trip_id))
            entries = list(
                await session.scalars(
                    select(TripEvidenceManifestEntry)
                    .where(TripEvidenceManifestEntry.trip_session_id == UUID(trip_id))
                    .order_by(TripEvidenceManifestEntry.batch_sequence)
                )
            )
            batches = list(
                await session.scalars(
                    select(LocationPingBatch)
                    .where(LocationPingBatch.trip_session_id == UUID(trip_id))
                    .order_by(LocationPingBatch.batch_sequence)
                )
            )
            audits = list(
                await session.scalars(
                    select(AuditEvent.action).where(AuditEvent.entity_id == trip_id)
                )
            )
            return trip, entries, batches, audits

    return asyncio.run(fetch())


def test_trip_with_no_location_for_two_hours_is_sealed_on_held_batches(
    db_client, db_sessionmaker, settings, monkeypatch, caplog
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    # A lost phone leaves a sequence gap: 0 and 2 arrive, 1 never does.
    for key, sequence in (("old-0", 0), ("old-2", 2)):
        payload = make_batch_payload(key, batch_sequence=sequence)
        assert post_batch(db_client, trip_id, payload).status_code == http_status.HTTP_200_OK

    with caplog.at_level(logging.INFO, logger="app.jobs.trip_processing"):
        result, enqueuer = run_sweep(db_sessionmaker, settings, monkeypatch)

    assert result["sealed"] == 1 and result["enqueued"] == 1
    assert "sealed=1 enqueued=1" in caplog.text
    assert enqueuer.trip_ids == [UUID(trip_id)]
    trip, entries, batches, audits = load(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert trip.seal_reason == TripSealReason.AUTO_ENDED.value
    assert trip.end_reason == "auto_ended_no_location"
    assert trip.ended_at == max(batch.received_at for batch in batches)
    assert verify_manifest_receipt(trip, settings)
    assert [(e.batch_sequence, e.idempotency_key, e.payload_hash) for e in entries] == [
        (b.batch_sequence, b.idempotency_key, b.payload_hash) for b in batches
    ]
    assert trip.evidence_manifest_ping_count == 2
    assert "trip.auto_ended" in audits and "trip.sealed" in audits

    # Nothing left to do on the next sweep.
    again, _ = run_sweep(db_sessionmaker, settings, monkeypatch)
    assert again["sealed"] == 0 and again["enqueued"] == 0


def test_trip_with_no_batches_seals_an_empty_manifest(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    result, _ = run_sweep(db_sessionmaker, settings, monkeypatch)

    assert result["sealed"] == 1
    trip, entries, _, _ = load(db_sessionmaker, trip_id)
    assert trip.seal_reason == TripSealReason.AUTO_ENDED.value
    assert trip.ended_at == trip.started_at
    assert entries == [] and trip.evidence_manifest_ping_count == 0
    assert verify_manifest_receipt(trip, settings)


def test_trip_with_recent_location_is_left_running(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    assert post_batch(db_client, trip_id, make_batch_payload("b-1")).status_code == 200

    result, enqueuer = run_sweep(
        db_sessionmaker, settings, monkeypatch, later=timedelta(seconds=7000)
    )

    assert result["sealed"] == 0 and enqueuer.trip_ids == []
    trip, entries, _, _ = load(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.ACTIVE.value and entries == []


def test_recheck_under_lock_skips_a_trip_that_just_received_location(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    assert post_batch(db_client, trip_id, make_batch_payload("b-1")).status_code == 200
    now = utc_now() + PAST_THRESHOLD

    async def scenario() -> tuple[list[UUID], bool]:
        async with db_sessionmaker() as session:
            candidates = await find_trips_to_auto_end(session, now=now, limit=10)
        # A batch lands between the unlocked scan and the locked re-check.
        async with db_sessionmaker() as session:
            await session.execute(
                update(LocationPingBatch)
                .where(LocationPingBatch.trip_session_id == UUID(trip_id))
                .values(received_at=now)
            )
            await session.commit()
        async with db_sessionmaker() as session:
            sealed = await auto_end_inactive_trip(
                session, trip_id=UUID(trip_id), settings=settings, now=now
            )
            await session.commit()
        return candidates, sealed

    candidates, sealed = asyncio.run(scenario())

    assert UUID(trip_id) in candidates
    assert sealed is False
    trip, _, _, _ = load(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.ACTIVE.value


def test_phone_still_recording_after_auto_end_is_told_the_trip_ended(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    held = make_batch_payload("b-1", batch_sequence=0)
    assert post_batch(db_client, trip_id, held).status_code == 200
    run_sweep(db_sessionmaker, settings, monkeypatch)
    attempts = []

    async def capture(_settings, attempt) -> None:
        attempts.append(attempt.rejected)

    monkeypatch.setattr("app.api.v1.trips.record_gps_attempt", capture)

    late = post_batch(db_client, trip_id, make_batch_payload("b-2", batch_sequence=1))
    retry = post_batch(db_client, trip_id, held)
    ended = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end", headers=driver_headers(db_client), json={}
    )

    assert late.status_code == http_status.HTTP_409_CONFLICT
    assert late.json()["error"]["code"] == "TRIP_ALREADY_ENDED"
    assert attempts == [False, False]
    # A lost-reply retry of a held batch still gets its original receipt.
    assert retry.status_code == http_status.HTTP_200_OK and retry.json()["duplicate"] is True
    assert ended.status_code == http_status.HTTP_400_BAD_REQUEST
    assert ended.json()["error"]["code"] == "TRIP_ALREADY_ENDED"
    _, _, batches, _ = load(db_sessionmaker, trip_id)
    assert [batch.idempotency_key for batch in batches] == ["b-1"]
    # The driver is free to start the next trip.
    restarted = start_trip(db_client, assignment.id)
    assert restarted.json()["status"] == TripSessionStatus.ACTIVE.value
