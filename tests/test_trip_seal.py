"""Trip finality protocol (RM3/RM4/RM5): seal lifecycle + post-seal quarantine.

Covers: watermark fast-seal at end, late-batch seal, grace-expiry sweep seal,
sealed-only money chain, post-seal quarantine (ACK semantics + idempotency
across the seal boundary), the audited admin apply/discard path, the post-end
recorded_at bound, and the ended-window assignment-gate skip.
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from starlette import status as http_status
from test_trips import (
    create_trip_ready_graph,
    driver_headers,
    ping_payload,
    start_trip,
    update_assignment_status,
)

from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.trip import (
    LocationPing,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.models.trip_analytics import TripAnalytics
from app.schemas.trips import LocationPingBatchCreate, TripEvidenceManifestEntryCreate
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trip_evidence import batch_payload_hash, manifest_root
from app.services.trip_processing import (
    find_unprocessed_trips,
    process_ended_trip,
    seal_due_trips,
)

PASSWORD = "long-secure-password"
BATCH_DESCRIPTORS: dict[str, dict[str, TripEvidenceManifestEntryCreate]] = {}


def admin_headers(db_client, email: str = "admin@example.com"):
    from test_trips import auth_headers

    return auth_headers(db_client, email, PASSWORD)


def end_trip(db_client, trip_id, *, watermark: dict | None = None, email=None):
    body = {"end_reason": "driver_ended", "metadata": {}}
    descriptors = sorted(
        BATCH_DESCRIPTORS.get(str(trip_id), {}).values(),
        key=lambda entry: entry.batch_sequence,
    )
    complete = bool((watermark or {}).get("client_complete", False))
    ping_count = sum(entry.submitted_count for entry in descriptors)
    body["evidence_manifest"] = {
        "version": 2,
        "root_sha256": manifest_root(
            trip_id=UUID(str(trip_id)), entries=descriptors, ping_count=ping_count
        ),
        "ping_count": ping_count,
        "complete": complete,
        "entries": [entry.model_dump() for entry in descriptors],
    }
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client, email or "driver@example.com"),
        json=body,
    )


def batch_descriptor(payload: dict) -> TripEvidenceManifestEntryCreate:
    parsed = LocationPingBatchCreate.model_validate(payload)
    return TripEvidenceManifestEntryCreate(
        batch_sequence=parsed.batch_sequence,
        idempotency_key=parsed.idempotency_key,
        payload_hash_version=2,
        payload_hash=batch_payload_hash(parsed),
        submitted_count=len(parsed.pings),
    )


def make_batch_payload(key, *, recorded_at=None, lat=6.45, batch_sequence=None):
    payload = ping_payload(recorded_at=recorded_at, idempotency_key=key)
    payload["pings"][0]["lat"] = lat
    timestamp = datetime.fromisoformat(payload["pings"][0]["recorded_at"])
    timestamp = timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)
    payload["pings"][0]["recorded_at"] = timestamp.isoformat()
    if batch_sequence is None:
        match = re.search(r"(\d+)$", key)
        batch_sequence = max(0, int(match.group(1)) - 1) if match else 0
    payload["batch_sequence"] = batch_sequence
    return payload


def remember_batch(trip_id, payload) -> None:
    descriptor = batch_descriptor(payload)
    BATCH_DESCRIPTORS.setdefault(str(trip_id), {})[descriptor.idempotency_key] = descriptor


def send_batch(
    db_client,
    trip_id,
    key,
    *,
    recorded_at=None,
    email=None,
    lat=6.45,
    batch_sequence=None,
):
    payload = make_batch_payload(
        key, recorded_at=recorded_at, lat=lat, batch_sequence=batch_sequence
    )
    remember_batch(trip_id, payload)
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client, email or "driver@example.com"),
        json=payload,
    )


def fetch_trip(db_sessionmaker, trip_id):
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.get(TripSession, UUID(str(trip_id)))

    return asyncio.run(fetch())


def fetch_all(db_sessionmaker, model):
    async def fetch():
        async with db_sessionmaker() as session:
            return list((await session.execute(select(model))).scalars().all())

    return asyncio.run(fetch())


def audit_actions(db_sessionmaker) -> list[str]:
    return [event.action for event in fetch_all(db_sessionmaker, AuditEvent)]


def test_exact_complete_manifest_fast_seals(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    assert send_batch(db_client, trip_id, "b1").status_code == http_status.HTTP_200_OK

    response = end_trip(
        db_client,
        trip_id,
        watermark={"client_batch_count": 1, "client_ping_count": 1, "client_complete": True},
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "sealed"
    assert body["sealed_at"] is not None
    assert body["seal_reason"] == TripSealReason.CLIENT_COMPLETE.value
    assert "trip.sealed" in audit_actions(db_sessionmaker)

    # Guarded active->ended transition: a second end request (the loser of a
    # race) must map to a clean 400, never overwrite the seal or surface a
    # constraint violation as a 500.
    second = end_trip(db_client, trip_id)
    assert second.status_code == http_status.HTTP_400_BAD_REQUEST
    assert second.json()["error"]["code"] == "TRIP_ALREADY_ENDED"
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.SEALED.value


def test_incomplete_end_requires_late_batch_and_reconcile(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    # The client commits both cut descriptors but has delivered only the first.
    assert send_batch(db_client, trip_id, "b1").status_code == http_status.HTTP_200_OK
    b2_payload = make_batch_payload("b2", batch_sequence=1)
    remember_batch(trip_id, b2_payload)
    response = end_trip(
        db_client,
        trip_id,
        watermark={"client_batch_count": 2, "client_ping_count": 2, "client_complete": False},
    )
    assert response.json()["status"] == "ended"
    assert response.json()["sealed_at"] is None

    late = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=b2_payload,
    )
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["evidence_scope"] == "manifest"
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value
    reconcile = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert reconcile.status_code == http_status.HTTP_200_OK
    trip = fetch_trip(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert trip.seal_reason == TripSealReason.LATE_DATA_COMPLETE.value


def test_grace_expiry_marks_but_never_seals(db_client, db_sessionmaker, settings) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    assert end_trip(db_client, trip_id).json()["status"] == "ended"

    async def run_sweep(now):
        async with db_sessionmaker() as session:
            sealed = await seal_due_trips(session, settings=settings, now=now)
            await session.commit()
            return sealed

    trip = fetch_trip(db_sessionmaker, trip_id)
    before_cutoff = trip.ended_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.trip_seal_grace_seconds - 60
    )
    after_cutoff = trip.ended_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.trip_seal_grace_seconds + 60
    )

    assert asyncio.run(run_sweep(before_cutoff)) == []
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value
    marked_ids = asyncio.run(run_sweep(after_cutoff))
    assert [str(marked_id) for marked_id in marked_ids] == [trip_id]
    trip = fetch_trip(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.ENDED.value
    assert trip.sealed_at is None
    assert trip.grace_expired_at is not None
    assert asyncio.run(run_sweep(after_cutoff)) == []
    assert audit_actions(db_sessionmaker).count("trip.evidence_grace_expired") == 1


def test_money_chain_blocks_until_sealed_and_sweep_selects_sealed_only(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    end_trip(db_client, trip_id)  # no watermark -> stays ended

    async def process():
        async with db_sessionmaker() as session:
            result = await process_ended_trip(session, trip_id=UUID(trip_id), settings=settings)
            await session.commit()
            return result

    result = asyncio.run(process())
    assert result.overall == "blocked"
    assert result.stages[0].reason == "trip_not_sealed"

    async def due():
        async with db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    assert asyncio.run(due()) == []  # ended-but-unsealed is never due work


def test_post_end_recorded_at_bound_rejects_points_after_trip(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    too_late = datetime.now(UTC) + timedelta(seconds=settings.location_ping_end_skew_seconds + 30)
    after_payload = make_batch_payload("after-end", recorded_at=too_late, batch_sequence=0)
    within = datetime.now(UTC) + timedelta(seconds=settings.location_ping_end_skew_seconds - 30)
    within_payload = make_batch_payload("within-skew", recorded_at=within, batch_sequence=1)
    remember_batch(trip_id, after_payload)
    remember_batch(trip_id, within_payload)
    end_trip(db_client, trip_id)
    rejected = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=after_payload,
    )
    assert rejected.status_code == http_status.HTTP_400_BAD_REQUEST
    assert rejected.json()["error"]["code"] == "INVALID_RECORDED_AT"

    accepted = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=within_payload,
    )
    assert accepted.status_code == http_status.HTTP_200_OK


def test_ended_window_ingest_skips_assignment_active_gate(db_client, db_sessionmaker) -> None:
    # Evidence recorded during the trip must remain deliverable even if the
    # assignment is deactivated right after the trip ends (RM3 review point 4).
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload("post-deactivation")
    remember_batch(trip_id, payload)
    end_trip(db_client, trip_id)
    update_assignment_status(db_sessionmaker, assignment.id, CampaignAssignmentStatus.CANCELLED)

    late = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["evidence_scope"] == "manifest"


def test_preseal_analytics_is_recomputed_before_money(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    """Finding: analytics computed during the recovery window (pre-seal) must
    never be reused for the write-once money chain — the sealed ping set may
    contain late batches the analytics never saw."""
    admin, campaign, driver, profile, vehicle, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker, eligibility_settings=settings
    )
    trip_id = start_trip(postgis_db_client, assignment.id).json()["id"]
    recorded = datetime.now(UTC)
    assert send_batch(postgis_db_client, trip_id, "b1", recorded_at=recorded).status_code == 200
    b2_payload = make_batch_payload("b2", recorded_at=recorded, batch_sequence=1)
    remember_batch(trip_id, b2_payload)
    # The exact manifest commits b1+b2 while only b1 is delivered.
    end_trip(
        postgis_db_client,
        trip_id,
        watermark={"client_batch_count": 2, "client_ping_count": 2, "client_complete": False},
    )
    assert fetch_trip(postgis_db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value

    # Analytics computed DURING the recovery window (sees only batch b1).
    async def compute_preseal():
        async with postgis_db_sessionmaker() as session:
            computation = await recompute_trip_analytics(
                session, trip_id=UUID(trip_id), metadata={}, settings=settings
            )
            await session.commit()
            return computation.analytics.computed_at

    preseal_computed_at = asyncio.run(compute_preseal())

    # The missing exact descriptor arrives, then explicit reconcile seals.
    late = postgis_db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(postgis_db_client),
        json=b2_payload,
    )
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["evidence_scope"] == "manifest"
    assert fetch_trip(postgis_db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value
    reconciled = postgis_db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(postgis_db_client),
    )
    assert reconciled.status_code == http_status.HTTP_200_OK
    trip = fetch_trip(postgis_db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert preseal_computed_at.replace(tzinfo=UTC) < trip.sealed_at.replace(tzinfo=UTC)

    async def process():
        async with postgis_db_sessionmaker() as session:
            result = await process_ended_trip(session, trip_id=UUID(trip_id), settings=settings)
            await session.commit()
            return result

    result = asyncio.run(process())
    analytics_stage = next(stage for stage in result.stages if stage.stage == "analytics")
    assert analytics_stage.outcome == "created"
    assert analytics_stage.reason == "preseal_analytics_recomputed"

    async def fetch_analytics():
        async with postgis_db_sessionmaker() as session:
            return await session.scalar(
                select(TripAnalytics).where(TripAnalytics.trip_session_id == UUID(trip_id))
            )

    analytics = asyncio.run(fetch_analytics())
    # Recomputed over the sealed ping set: both batches counted, stamp advanced.
    assert analytics.ping_count == 2
    assert analytics.computed_at.replace(tzinfo=UTC) >= trip.sealed_at.replace(tzinfo=UTC)

    # A second run reuses (no perpetual recompute churn).
    second = asyncio.run(process())
    second_stage = next(stage for stage in second.stages if stage.stage == "analytics")
    assert second_stage.outcome == "reused"


def test_post_seal_late_data_is_automatic_and_keeps_original_manifest(db_client, db_sessionmaker):
    from app.core.config import get_settings
    from app.models.trip import LocationPingBatch
    from app.services.trip_evidence import verify_batch_receipt

    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    recorded = datetime.now(UTC)
    live = send_batch(db_client, trip_id, "live-1", recorded_at=recorded)
    assert live.status_code == 200, live.text
    ended = end_trip(db_client, trip_id, watermark={"client_complete": True})
    assert ended.status_code == 200, ended.text
    original = fetch_trip(db_sessionmaker, trip_id)
    before = len(fetch_all(db_sessionmaker, LocationPing))
    late = send_batch(db_client, trip_id, "late-2", recorded_at=recorded, lat=6.4501)
    assert late.status_code == 200, late.text
    assert late.json()["evidence_scope"] == "late" and late.json()["outcome"] == "accepted"
    assert late.json()["accepted_count"] == 1
    assert len(fetch_all(db_sessionmaker, LocationPing)) == before + 1
    retry = send_batch(db_client, trip_id, "late-2", recorded_at=recorded, lat=6.4501)
    assert retry.json() == {**late.json(), "duplicate": True}
    conflict = send_batch(db_client, trip_id, "late-2", recorded_at=recorded, lat=6.46)
    assert conflict.status_code == 409
    sealed = fetch_trip(db_sessionmaker, trip_id)
    assert sealed.evidence_manifest_root_sha256 == original.evidence_manifest_root_sha256
    assert (
        sealed.evidence_manifest_receipt_signature == original.evidence_manifest_receipt_signature
    )
    batch = next(
        row
        for row in fetch_all(db_sessionmaker, LocationPingBatch)
        if str(row.id) == late.json()["batch_id"]
    )
    assert verify_batch_receipt(batch, get_settings())
    replay = send_batch(db_client, trip_id, "live-1", recorded_at=recorded)
    assert replay.json() == {**live.json(), "duplicate": True}
