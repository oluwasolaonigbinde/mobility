"""R36 / OFF-005: durable mixed-validity ping batch acknowledgement."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from starlette import status as http_status
from test_trips import (
    create_trip_ready_graph,
    driver_headers,
    ping_payload,
    start_trip,
)

from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.services.trip_evidence import (
    BATCH_RECEIPT_DOMAIN,
    batch_receipt_value,
    canonical_bytes,
    rejection_manifest_digest,
    signing_key,
    verify_batch_receipt,
    verify_signature,
)


def sample(sequence_number: int, **overrides) -> dict:
    recorded_at = datetime.now(UTC)
    recorded_at = recorded_at.replace(microsecond=recorded_at.microsecond // 1000 * 1000)
    base = {
        "recorded_at": recorded_at.isoformat(),
        "lat": 6.45,
        "lon": 3.39,
        "accuracy_m": 12.5,
        "speed_mps": 8.3,
        "heading_degrees": 180.0,
        "altitude_m": 42.0,
        "sequence_number": sequence_number,
        "metadata": {"source": "gps"},
    }
    base.update(overrides)
    return base


def far_future(sequence_number: int) -> dict:
    moment = datetime.now(UTC) + timedelta(seconds=901)
    moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
    return sample(sequence_number, recorded_at=moment.isoformat())


def demote_to_legacy_protocol(db_sessionmaker, trip_id) -> None:
    """New trips are v2-only; a v1 row only exists as retained history."""

    async def demote() -> None:
        async with db_sessionmaker() as session:
            trip = await session.get(TripSession, UUID(trip_id))
            trip.evidence_protocol_version = 1
            await session.commit()

    asyncio.run(demote())


def post_pings(db_client, trip_id, key, pings, *, batch_sequence=0):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=ping_payload(idempotency_key=key, batch_sequence=batch_sequence, pings=pings),
    )


def fetch_batches(db_sessionmaker) -> list[LocationPingBatch]:
    async def fetch():
        async with db_sessionmaker() as session:
            return list((await session.execute(select(LocationPingBatch))).scalars().all())

    return asyncio.run(fetch())


def fetch_pings(db_sessionmaker) -> list[LocationPing]:
    async def fetch():
        async with db_sessionmaker() as session:
            return list(
                (await session.execute(select(LocationPing).order_by(LocationPing.sequence_number)))
                .scalars()
                .all()
            )

    return asyncio.run(fetch())


def test_mixed_batch_keeps_valid_samples_and_reports_ordered_dispositions(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    response = post_pings(
        db_client,
        trip_id,
        "mixed-batch",
        [
            sample(0),
            far_future(1),
            sample(2, accuracy_m=100_000.0),
            sample(3),
            sample(4, speed_mps=100_000.0),
        ],
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["submitted_count"] == 5
    assert body["accepted_count"] == 2
    assert body["rejected_count"] == 3
    assert body["sample_results"] == [
        {"index": 0, "sequence_number": 0, "status": "accepted", "rejection_code": None},
        {
            "index": 1,
            "sequence_number": 1,
            "status": "rejected",
            "rejection_code": "INVALID_RECORDED_AT",
        },
        {
            "index": 2,
            "sequence_number": 2,
            "status": "rejected",
            "rejection_code": "INVALID_ACCURACY",
        },
        {"index": 3, "sequence_number": 3, "status": "accepted", "rejection_code": None},
        {
            "index": 4,
            "sequence_number": 4,
            "status": "rejected",
            "rejection_code": "INVALID_SPEED",
        },
    ]

    # Only the valid samples became durable evidence, and the batch row
    # conserves submitted = accepted + rejected.
    assert [ping.sequence_number for ping in fetch_pings(db_sessionmaker)] == [0, 3]
    batch = fetch_batches(db_sessionmaker)[0]
    assert (batch.pings_submitted, batch.pings_accepted, batch.pings_rejected) == (5, 2, 3)
    assert batch.rejection_digest == rejection_manifest_digest(batch.rejection_manifest)


def test_partial_disposition_is_bound_into_the_signed_receipt(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    post_pings(db_client, trip_id, "bound-batch", [sample(0), far_future(1)])
    batch = fetch_batches(db_sessionmaker)[0]

    assert verify_batch_receipt(batch, settings)
    value = batch_receipt_value(batch)
    assert value["rejection_digest"] == batch.rejection_digest

    # A receipt that only carried counts would still verify after the exact
    # disposition was swapped for a different one with the same totals.
    _, key = signing_key(settings, batch.receipt_key_version)
    tampered = dict(value)
    tampered["rejection_digest"] = "f" * 64
    assert not verify_signature(
        BATCH_RECEIPT_DOMAIN, tampered, key, batch.receipt_signature
    )


def test_replayed_mixed_batch_returns_identical_dispositions(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    pings = [sample(0), far_future(1), sample(2)]

    first = post_pings(db_client, trip_id, "replay-batch", pings)
    second = post_pings(db_client, trip_id, "replay-batch", pings)

    assert first.status_code == second.status_code == http_status.HTTP_200_OK
    assert second.json()["duplicate"] is True
    assert second.json()["sample_results"] == first.json()["sample_results"]
    assert second.json()["receipt_signature"] == first.json()["receipt_signature"]
    # Replay must not double-ingest the accepted samples.
    assert len(fetch_pings(db_sessionmaker)) == 2


def test_all_valid_batch_records_an_all_accepted_disposition(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    response = post_pings(db_client, trip_id, "all-valid", [sample(0), sample(1)])

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert (body["accepted_count"], body["rejected_count"]) == (2, 0)
    assert [entry["status"] for entry in body["sample_results"]] == ["accepted", "accepted"]
    batch = fetch_batches(db_sessionmaker)[0]
    assert batch.rejection_digest is not None
    assert verify_batch_receipt(batch, settings)


def test_all_invalid_batch_stays_a_deterministic_whole_batch_rejection(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    response = post_pings(db_client, trip_id, "all-invalid", [far_future(0), far_future(1)])

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "INVALID_RECORDED_AT"
    assert fetch_batches(db_sessionmaker) == []
    assert fetch_pings(db_sessionmaker) == []


def test_legacy_v1_batches_stay_all_or_nothing_without_a_disposition(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    demote_to_legacy_protocol(db_sessionmaker, trip_id)

    mixed = post_pings(db_client, trip_id, "legacy-mixed", [sample(0), far_future(1)])
    accepted = post_pings(db_client, trip_id, "legacy-valid", [sample(0)], batch_sequence=1)

    assert mixed.status_code == http_status.HTTP_400_BAD_REQUEST
    assert mixed.json()["error"]["code"] == "INVALID_RECORDED_AT"
    assert accepted.status_code == http_status.HTTP_200_OK
    assert accepted.json()["sample_results"] == []
    batch = fetch_batches(db_sessionmaker)[0]
    assert batch.rejection_manifest is None and batch.rejection_digest is None


def test_batches_signed_before_this_protocol_still_verify(db_sessionmaker, settings) -> None:
    # A row whose disposition columns are NULL must keep the exact receipt
    # value it was signed over, or migration 0080 would invalidate history.
    batch = LocationPingBatch(
        trip_session_id=UUID("75000000-0000-0000-0000-000000000001"),
        idempotency_key="pre-protocol",
        batch_sequence=0,
        payload_hash_version=2,
        payload_hash="a" * 64,
        pings_submitted=1,
        pings_accepted=1,
        pings_rejected=0,
        evidence_scope="manifest",
        received_at=datetime.now(UTC),
    )
    key_version, key = signing_key(settings)
    batch.receipt_format_version = 2
    batch.receipt_key_version = key_version
    batch.receipt_outcome = "accepted"

    legacy_value = {
        "format_version": 2,
        "trip_id": str(batch.trip_session_id),
        "batch_sequence": batch.batch_sequence,
        "idempotency_key": batch.idempotency_key,
        "payload_hash_version": batch.payload_hash_version,
        "payload_hash": batch.payload_hash,
        "submitted_count": 1,
        "accepted_count": 1,
        "rejected_count": 0,
        "outcome": "accepted",
        "evidence_scope": "manifest",
    }
    assert batch_receipt_value(batch) == legacy_value
    assert canonical_bytes(batch_receipt_value(batch)) == canonical_bytes(legacy_value)
