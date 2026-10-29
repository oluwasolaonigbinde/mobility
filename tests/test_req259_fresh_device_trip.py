"""REQ-259: a trip continued on a fresh device can learn the server's evidence and end."""

import asyncio
from uuid import UUID

from sqlalchemy import func, select
from starlette import status as http_status
from test_trip_seal import batch_descriptor, driver_headers, make_batch_payload
from test_trips import create_trip_ready_graph, start_trip

from app.models.trip import LocationPing, LocationPingBatch, TripSessionStatus
from app.schemas.trips import TripEvidenceManifestEntryCreate
from app.services.trip_evidence import manifest_root


def counts(db_sessionmaker, trip_id: str) -> tuple[int, int]:
    async def fetch() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            batches = await session.scalar(
                select(func.count(LocationPingBatch.id)).where(
                    LocationPingBatch.trip_session_id == UUID(trip_id)
                )
            )
            pings = await session.scalar(
                select(func.count(LocationPing.id)).where(
                    LocationPing.trip_session_id == UUID(trip_id)
                )
            )
            return int(batches or 0), int(pings or 0)

    return asyncio.run(fetch())


def post_batch(db_client, trip_id: str, payload: dict, email: str = "driver@example.com"):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client, email),
        json=payload,
    )


def test_new_key_at_a_held_sequence_is_a_typed_conflict_not_a_500(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    old = post_batch(db_client, trip_id, make_batch_payload("old-device-1", batch_sequence=0))
    assert old.status_code == http_status.HTTP_200_OK

    # A fresh browser restarts numbering at 0 with a new key.
    fresh = post_batch(db_client, trip_id, make_batch_payload("fresh-device-1", batch_sequence=0))

    assert fresh.status_code == http_status.HTTP_409_CONFLICT
    assert fresh.json()["error"]["code"] == "TRIP_EVIDENCE_BATCH_SEQUENCE_TAKEN"
    assert counts(db_sessionmaker, trip_id) == (1, 1)


def test_driver_reads_server_held_evidence_receipts_without_locations(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    sent = [
        post_batch(
            db_client, trip_id, make_batch_payload(f"old-{index}", batch_sequence=index)
        ).json()
        for index in (1, 0)
    ]

    response = db_client.get(
        f"/api/v1/driver/trips/{trip_id}/evidence",
        headers=driver_headers(db_client),
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["trip_id"] == trip_id
    assert body["status"] == TripSessionStatus.ACTIVE.value
    assert [batch["batch_sequence"] for batch in body["batches"]] == [0, 1]
    by_sequence = {item["batch_sequence"]: item for item in sent}
    for batch in body["batches"]:
        expected = by_sequence[batch["batch_sequence"]]
        for field in (
            "batch_id",
            "idempotency_key",
            "payload_hash",
            "submitted_count",
            "accepted_count",
            "receipt_signature",
            "receipt_key_version",
        ):
            if field == "idempotency_key":
                assert batch[field] == f"old-{batch['batch_sequence']}"
            else:
                assert batch[field] == expected[field]
        assert batch["duplicate"] is True
    assert "lat" not in response.text and "lon" not in response.text


def test_another_driver_cannot_read_trip_evidence(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    create_trip_ready_graph(
        db_sessionmaker,
        admin_email="admin2@example.com",
        advertiser_email="advertiser2@example.com",
        driver_email="driver2@example.com",
        plate_number="XYZ-987",
    )

    response = db_client.get(
        f"/api/v1/driver/trips/{trip_id}/evidence",
        headers=driver_headers(db_client, "driver2@example.com"),
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "TRIP_NOT_FOUND"


def test_fresh_device_ends_trip_with_server_receipts_and_keeps_received_miles(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    for index in range(3):
        payload = make_batch_payload(f"old-{index}", batch_sequence=index)
        assert post_batch(db_client, trip_id, payload).status_code == http_status.HTTP_200_OK

    held = db_client.get(
        f"/api/v1/driver/trips/{trip_id}/evidence", headers=driver_headers(db_client)
    ).json()["batches"]
    fresh_payload = make_batch_payload("fresh-0", batch_sequence=len(held))
    assert post_batch(db_client, trip_id, fresh_payload).status_code == 200
    entries = [
        TripEvidenceManifestEntryCreate(
            batch_sequence=batch["batch_sequence"],
            idempotency_key=batch["idempotency_key"],
            payload_hash_version=2,
            payload_hash=batch["payload_hash"],
            submitted_count=batch["submitted_count"],
        )
        for batch in held
    ] + [batch_descriptor(fresh_payload)]
    ping_count = sum(entry.submitted_count for entry in entries)

    ended = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={
            "end_reason": "driver_ended",
            "evidence_manifest": {
                "version": 2,
                "root_sha256": manifest_root(
                    trip_id=UUID(trip_id), entries=entries, ping_count=ping_count
                ),
                "ping_count": ping_count,
                "complete": True,
                "entries": [entry.model_dump() for entry in entries],
            },
        },
    )

    assert ended.status_code == http_status.HTTP_200_OK
    assert ended.json()["status"] == TripSessionStatus.SEALED.value
    assert counts(db_sessionmaker, trip_id) == (4, 4)
    assert ended.json()["ping_count"] == 4
