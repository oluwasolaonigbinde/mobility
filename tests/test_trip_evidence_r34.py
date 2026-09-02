import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from conftest import create_test_trip_session
from sqlalchemy import func, select, update
from starlette import status as http_status
from test_trip_seal import (
    batch_descriptor,
    driver_headers,
    end_trip,
    make_batch_payload,
    remember_batch,
)
from test_trips import create_trip_ready_graph, start_trip

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.trip import LocationPingBatch, TripSession, TripSessionStatus
from app.schemas.trips import (
    LocationPingBatchCreate,
    TripEndRequest,
    TripEvidenceManifestCreate,
    TripEvidenceManifestEntryCreate,
)
from app.services.trip_evidence import (
    BATCH_RECEIPT_DOMAIN,
    batch_payload_hash,
    batch_receipt_value,
    canonical_bytes,
    manifest_root,
    validate_manifest,
    verify_signature,
)
from app.services.trip_processing import process_ended_trip, seal_due_trips
from app.services.trips import (
    end_driver_trip,
    ingest_location_ping_batch,
    reconcile_trip_evidence,
)


def test_python_matches_shared_typescript_golden_vector() -> None:
    vector = json.loads(
        Path("frontend/src/lib/trips/trip-evidence-v2-vectors.json").read_text()
    )
    payload = LocationPingBatchCreate.model_validate(
        {
            "idempotency_key": vector["batch"]["idempotency_key"],
            "batch_sequence": vector["batch"]["batch_sequence"],
            "pings": vector["batch"]["pings"],
        }
    )
    digest = batch_payload_hash(payload)
    entry = TripEvidenceManifestEntryCreate(
        batch_sequence=payload.batch_sequence,
        idempotency_key=payload.idempotency_key,
        payload_hash_version=2,
        payload_hash=digest,
        submitted_count=len(payload.pings),
    )

    assert digest == vector["batch"]["payload_hash"]
    assert manifest_root(
        trip_id=UUID(vector["trip_id"]), entries=[entry], ping_count=1
    ) == vector["manifest_root"]


def test_legacy_v1_trip_cannot_originate_new_money(
    db_sessionmaker, settings
) -> None:
    _, _, driver, profile, vehicle, assignment = create_trip_ready_graph(db_sessionmaker)
    ended_at = datetime.now(UTC)
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.SEALED,
        ended_at=ended_at,
    )

    async def run():
        async with db_sessionmaker() as session:
            return await process_ended_trip(session, trip_id=trip.id, settings=settings)

    result = asyncio.run(run())

    assert result.overall == "blocked"
    assert result.stages[0].reason == "legacy_money_origination_prohibited"


def fetch_trip(db_sessionmaker, trip_id: str) -> TripSession:
    async def fetch() -> TripSession:
        async with db_sessionmaker() as session:
            return await session.get(TripSession, UUID(trip_id))

    return asyncio.run(fetch())


def fetch_batch(db_sessionmaker, batch_id: str) -> LocationPingBatch:
    async def fetch() -> LocationPingBatch:
        async with db_sessionmaker() as session:
            return await session.get(LocationPingBatch, UUID(batch_id))

    return asyncio.run(fetch())


def manifest_for(trip_id: str, entries, *, complete=True, ping_count=None) -> dict:
    count = sum(entry.submitted_count for entry in entries) if ping_count is None else ping_count
    return {
        "version": 2,
        "root_sha256": manifest_root(
            trip_id=UUID(trip_id), entries=entries, ping_count=count
        ),
        "ping_count": count,
        "complete": complete,
        "entries": [entry.model_dump() for entry in entries],
    }


def test_signed_batch_receipt_is_content_bound_and_duplicate_stable(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload("receipt-1", batch_sequence=0)
    remember_batch(trip_id, payload)

    first = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )
    replay = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )

    assert first.status_code == http_status.HTTP_200_OK
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json() == {**first.json(), "duplicate": True}
    row = fetch_batch(db_sessionmaker, first.json()["batch_id"])
    assert verify_signature(
        BATCH_RECEIPT_DOMAIN,
        batch_receipt_value(row),
        settings.trip_evidence_signing_keys[row.receipt_key_version],
        row.receipt_signature,
    )

    tampered = {**payload, "pings": [{**payload["pings"][0], "lat": 7.1}]}
    conflict = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=tampered,
    )
    assert conflict.status_code == http_status.HTTP_409_CONFLICT
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_v2_batch_requires_sequence_and_exact_millisecond_timestamp(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    missing_sequence = make_batch_payload("missing-sequence")
    missing_sequence.pop("batch_sequence", None)

    missing = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=missing_sequence,
    )
    assert missing.status_code == http_status.HTTP_409_CONFLICT
    assert missing.json()["error"]["code"] == "TRIP_EVIDENCE_BATCH_SEQUENCE_REQUIRED"

    sub_millisecond = make_batch_payload("sub-millisecond", batch_sequence=0)
    sub_millisecond["pings"][0]["recorded_at"] = datetime.now(UTC).replace(
        microsecond=123456
    ).isoformat()
    rejected = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=sub_millisecond,
    )
    assert rejected.status_code == http_status.HTTP_400_BAD_REQUEST
    assert rejected.json()["error"]["code"] == "TRIP_EVIDENCE_TIMESTAMP_PRECISION_INVALID"


def test_tampered_batch_receipt_cannot_complete_manifest(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload("tamper-receipt", batch_sequence=0)
    remember_batch(trip_id, payload)
    ended = end_trip(db_client, trip_id, watermark={"client_complete": False})
    assert ended.json()["status"] == TripSessionStatus.ENDED.value
    uploaded = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )
    assert uploaded.status_code == http_status.HTTP_200_OK

    async def tamper() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                update(LocationPingBatch)
                .where(LocationPingBatch.id == UUID(uploaded.json()["batch_id"]))
                .values(receipt_signature="tampered")
            )
            await session.commit()

    asyncio.run(tamper())
    reconcile = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert reconcile.status_code == http_status.HTTP_409_CONFLICT
    assert reconcile.json()["error"]["code"] == "TRIP_EVIDENCE_INCOMPLETE"
    assert reconcile.json()["error"]["details"]["mismatched_batch_count"] == 1
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value


@pytest.mark.parametrize("mutation", ["reorder", "duplicate", "under", "over", "tamper"])
def test_manifest_rejects_order_count_duplicate_and_tamper(mutation: str) -> None:
    trip_id = UUID("34000000-0000-0000-0000-000000000001")
    entries = [
        TripEvidenceManifestEntryCreate(
            batch_sequence=index,
            idempotency_key=f"batch-{index}",
            payload_hash_version=2,
            payload_hash=f"{index + 1:064x}",
            submitted_count=1,
        )
        for index in range(2)
    ]
    ping_count = 2
    root = manifest_root(trip_id=trip_id, entries=entries, ping_count=ping_count)
    if mutation == "reorder":
        entries = list(reversed(entries))
    elif mutation == "duplicate":
        entries[1] = entries[1].model_copy(update={"idempotency_key": "batch-0"})
    elif mutation == "under":
        ping_count = 1
    elif mutation == "over":
        ping_count = 3
    else:
        root = "f" * 64
    manifest = TripEvidenceManifestCreate(
        version=2,
        root_sha256=root,
        ping_count=ping_count,
        complete=True,
        entries=entries,
    )
    with pytest.raises(AppError) as exc_info:
        validate_manifest(trip_id, manifest)
    assert exc_info.value.code == "TRIP_EVIDENCE_MANIFEST_INVALID"


def test_false_complete_and_undeclared_late_batch_cannot_seal(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    missing_payload = make_batch_payload("missing-1", batch_sequence=0)
    entry = batch_descriptor(missing_payload)
    manifest = manifest_for(trip_id, [entry], complete=True)

    ended = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={"evidence_manifest": manifest, "metadata": {}},
    )
    assert ended.status_code == http_status.HTTP_200_OK
    assert ended.json()["status"] == TripSessionStatus.ENDED.value
    assert ended.json()["evidence_manifest_complete"] is False

    incomplete = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert incomplete.status_code == http_status.HTTP_409_CONFLICT
    assert incomplete.json()["error"]["code"] == "TRIP_EVIDENCE_INCOMPLETE"
    assert incomplete.json()["error"]["details"] == {
        "missing_batch_count": 1,
        "mismatched_batch_count": 0,
        "undeclared_batch_count": 0,
    }

    undeclared = make_batch_payload("other-1", batch_sequence=0)
    response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=undeclared,
    )
    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "TRIP_EVIDENCE_BATCH_UNDECLARED"
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value


def test_canonical_encoding_normalizes_negative_zero_and_orders_utf8_keys() -> None:
    assert canonical_bytes(-0.0) == canonical_bytes(0.0)
    assert canonical_bytes({"b": 1, "a": 2}) == canonical_bytes({"a": 2, "b": 1})
    assert canonical_bytes(1) != canonical_bytes(1.0)
    with pytest.raises(ValueError):
        canonical_bytes(float("nan"))


def test_reconcile_is_idempotent_after_exact_late_delivery(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload(
        "late-1", recorded_at=datetime.now(UTC).replace(microsecond=123000), batch_sequence=0
    )
    remember_batch(trip_id, payload)
    ended = end_trip(
        db_client,
        trip_id,
        watermark={"client_complete": False},
    )
    assert ended.json()["status"] == TripSessionStatus.ENDED.value
    assert db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    ).status_code == http_status.HTTP_200_OK

    first = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    second = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert first.status_code == second.status_code == http_status.HTTP_200_OK
    assert first.json()["duplicate"] is False
    assert second.json() == {**first.json(), "duplicate": True}


def test_postgres_end_upload_reconcile_and_grace_race_converges(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    _, _, driver, _, _, assignment = create_trip_ready_graph(postgis_db_sessionmaker)
    trip_id = start_trip(postgis_db_client, assignment.id).json()["id"]
    payload = LocationPingBatchCreate.model_validate(
        make_batch_payload("race-1", batch_sequence=0)
    )
    descriptor = TripEvidenceManifestEntryCreate(
        batch_sequence=0,
        idempotency_key=payload.idempotency_key,
        payload_hash_version=2,
        payload_hash=batch_payload_hash(payload),
        submitted_count=len(payload.pings),
    )
    end_payload = TripEndRequest.model_validate(
        {
            "metadata": {},
            "evidence_manifest": manifest_for(
                trip_id, [descriptor], complete=False
            ),
        }
    )
    trip_uuid = UUID(trip_id)

    async def end_once() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await end_driver_trip(
                    session,
                    user_id=driver.id,
                    trip_id=trip_uuid,
                    payload=end_payload,
                    settings=settings,
                )
                await session.commit()
                return "ended"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def upload_once() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await ingest_location_ping_batch(
                    session,
                    user_id=driver.id,
                    trip_id=trip_uuid,
                    payload=payload,
                    settings=settings,
                )
                await session.commit()
                return "uploaded"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def reconcile_once() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await reconcile_trip_evidence(
                    session,
                    user_id=driver.id,
                    trip_id=trip_uuid,
                    settings=settings,
                )
                await session.commit()
                return "reconciled"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def grace_once() -> str:
        async with postgis_db_sessionmaker() as session:
            marked = await seal_due_trips(
                session,
                settings=settings,
                now=datetime.now(UTC)
                + timedelta(seconds=settings.trip_seal_grace_seconds + 60),
            )
            await session.commit()
            return "grace_marked" if trip_uuid in marked else "grace_skipped"

    async def race() -> list[str]:
        return list(
            await asyncio.wait_for(
                asyncio.gather(
                    end_once(),
                    end_once(),
                    upload_once(),
                    reconcile_once(),
                    grace_once(),
                    grace_once(),
                ),
                timeout=10,
            )
        )

    outcomes = asyncio.run(race())
    assert outcomes.count("ended") == 1
    assert outcomes.count("TRIP_ALREADY_ENDED") == 1
    assert "uploaded" in outcomes
    assert set(outcomes[-2:]).issubset({"grace_marked", "grace_skipped"})
    assert outcomes.count("grace_marked") <= 1

    async def finish_and_inspect() -> tuple[TripSession, int, int]:
        async with postgis_db_sessionmaker() as session:
            await reconcile_trip_evidence(
                session,
                user_id=driver.id,
                trip_id=trip_uuid,
                settings=settings,
            )
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            trip = await session.get(TripSession, trip_uuid)
            seal_events = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "trip.sealed",
                        AuditEvent.entity_id == trip_id,
                    )
                )
                or 0
            )
            grace_events = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "trip.evidence_grace_expired",
                        AuditEvent.entity_id == trip_id,
                    )
                )
                or 0
            )
            return trip, seal_events, grace_events

    trip, seal_events, grace_events = asyncio.run(finish_and_inspect())
    assert trip.status == TripSessionStatus.SEALED.value
    assert trip.evidence_manifest_verified_at is not None
    assert seal_events == 1
    assert grace_events <= 1
