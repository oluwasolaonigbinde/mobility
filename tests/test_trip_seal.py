"""Trip finality protocol (RM3/RM4/RM5): seal lifecycle + post-seal quarantine.

Covers: watermark fast-seal at end, late-batch seal, grace-expiry sweep seal,
sealed-only money chain, post-seal quarantine (ACK semantics + idempotency
across the seal boundary), the audited admin apply/discard path, the post-end
recorded_at bound, and the ended-window assignment-gate skip.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from conftest import create_test_payout_rule, create_test_trip_analytics
from sqlalchemy import select
from starlette import status as http_status
from test_trips import (
    create_trip_ready_graph,
    driver_headers,
    ping_payload,
    start_trip,
    update_assignment_status,
)

import app.services.trips as trips_service
from app.models.audit import AuditEvent
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.trip import (
    LocationPing,
    QuarantinedPingBatch,
    TripSealReason,
    TripSession,
    TripSessionStatus,
)
from app.models.trip_analytics import TripAnalytics
from app.services.trip_analytics import recompute_trip_analytics
from app.services.trip_processing import (
    find_unprocessed_trips,
    process_ended_trip,
    seal_due_trips,
)

PASSWORD = "long-secure-password"


def admin_headers(db_client, email: str = "admin@example.com"):
    from test_trips import auth_headers

    return auth_headers(db_client, email, PASSWORD)


def end_trip(db_client, trip_id, *, watermark: dict | None = None, email=None):
    body = {"end_reason": "driver_ended", "metadata": {}}
    if watermark is not None:
        body.update(watermark)
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client, email or "driver@example.com"),
        json=body,
    )


def send_batch(db_client, trip_id, key, *, recorded_at=None, email=None, lat=6.45):
    payload = ping_payload(recorded_at=recorded_at, idempotency_key=key)
    payload["pings"][0]["lat"] = lat
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


def test_end_with_satisfied_watermark_fast_seals(db_client, db_sessionmaker) -> None:
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


def test_incomplete_end_stays_ended_then_late_batch_seals(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]

    # Client cut 2 batches but only delivered 1 before ending.
    assert send_batch(db_client, trip_id, "b1").status_code == http_status.HTTP_200_OK
    response = end_trip(
        db_client,
        trip_id,
        watermark={"client_batch_count": 2, "client_ping_count": 2, "client_complete": False},
    )
    assert response.json()["status"] == "ended"
    assert response.json()["sealed_at"] is None

    # The missing batch arrives inside the recovery window: accepted as live
    # evidence AND completes the watermark -> seal without waiting for grace.
    late = send_batch(db_client, trip_id, "b2")
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["quarantined"] is False
    trip = fetch_trip(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert trip.seal_reason == TripSealReason.LATE_DATA_COMPLETE.value


def test_no_watermark_end_waits_for_grace_sweep(db_client, db_sessionmaker, settings) -> None:
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
    sealed_ids = asyncio.run(run_sweep(after_cutoff))
    assert [str(sealed_id) for sealed_id in sealed_ids] == [trip_id]
    trip = fetch_trip(db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert trip.seal_reason == TripSealReason.GRACE_EXPIRED.value
    # Idempotent: a second sweep run never re-seals or re-audits.
    assert asyncio.run(run_sweep(after_cutoff)) == []
    assert audit_actions(db_sessionmaker).count("trip.sealed") == 1


def test_money_chain_blocks_until_sealed_and_sweep_selects_sealed_only(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    end_trip(db_client, trip_id)  # no watermark -> stays ended

    async def process():
        async with db_sessionmaker() as session:
            result = await process_ended_trip(
                session, trip_id=UUID(trip_id), settings=settings
            )
            await session.commit()
            return result

    result = asyncio.run(process())
    assert result.overall == "blocked"
    assert result.stages[0].reason == "trip_not_sealed"

    async def due():
        async with db_sessionmaker() as session:
            return await find_unprocessed_trips(session, limit=10, settings=settings)

    assert asyncio.run(due()) == []  # ended-but-unsealed is never due work


def test_post_seal_batch_is_quarantined_with_ack_semantics(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    recorded = datetime.now(UTC)
    assert send_batch(db_client, trip_id, "live-1", recorded_at=recorded).status_code == 200
    end_trip(db_client, trip_id, watermark={"client_batch_count": 1, "client_complete": True})
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.SEALED.value
    pings_before = len(fetch_all(db_sessionmaker, LocationPing))

    # New batch after seal -> quarantined, no pings inserted, client must ACK.
    late = send_batch(db_client, trip_id, "late-1", recorded_at=recorded)
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["quarantined"] is True
    assert late.json()["accepted_count"] == 0
    assert len(fetch_all(db_sessionmaker, LocationPing)) == pings_before
    assert "trip.ping_batch.quarantined" in audit_actions(db_sessionmaker)

    # Retrying the same quarantined batch is idempotent (same ACK, one row).
    retry = send_batch(db_client, trip_id, "late-1", recorded_at=recorded)
    assert retry.json()["quarantined"] is True
    assert retry.json()["duplicate"] is True
    assert len(fetch_all(db_sessionmaker, QuarantinedPingBatch)) == 1

    # Same key, different payload -> conflict, exactly like live batches.
    conflict = send_batch(db_client, trip_id, "late-1", recorded_at=recorded, lat=6.5)
    assert conflict.status_code == http_status.HTTP_409_CONFLICT

    # A pre-seal batch retried post-seal returns its ORIGINAL live ACK,
    # never a quarantine row (RM4 replay across the seal boundary).
    replay = send_batch(db_client, trip_id, "live-1", recorded_at=recorded)
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json()["duplicate"] is True
    assert replay.json()["quarantined"] is False


def test_admin_applies_quarantined_batch_with_audit_and_lagos_days(
    db_client, db_sessionmaker, settings, monkeypatch
) -> None:
    async def authorize_legacy_trip(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(trips_service, "assert_new_work_authorized", authorize_legacy_trip)
    admin, campaign, driver, profile, vehicle, assignment = create_trip_ready_graph(
        db_sessionmaker, with_financial_authority=False
    )
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    recorded = datetime.now(UTC)
    end_trip(db_client, trip_id, watermark={"client_batch_count": 0, "client_complete": True})
    late = send_batch(db_client, trip_id, "late-apply", recorded_at=recorded)
    quarantine_id = late.json()["batch_id"]

    listing = db_client.get(
        "/api/v1/admin/trips/quarantined-batches",
        headers=admin_headers(db_client),
    )
    assert listing.status_code == http_status.HTTP_200_OK
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == quarantine_id

    # RBAC: drivers cannot review quarantine.
    forbidden = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply",
        headers=driver_headers(db_client),
        json={"note": "nope"},
    )
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN

    # Note is mandatory.
    missing_note = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply",
        headers=admin_headers(db_client),
        json={},
    )
    assert missing_note.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY

    # Apply is BLOCKED until the trip's initial (write-once) payout exists —
    # otherwise admin timing would decide whether the applied pings enter the
    # first computation or wait for recompute-day.
    blocked = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply",
        headers=admin_headers(db_client),
        json={"note": "too early"},
    )
    assert blocked.status_code == http_status.HTTP_409_CONFLICT
    assert blocked.json()["error"]["code"] == "QUARANTINE_APPLY_BLOCKED"

    # Give the sealed trip its initial processing: rule + pre-seeded analytics
    # (computed after the seal) let the pipeline produce the calculation.
    create_test_payout_rule(
        db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=10,
    )
    create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=fetch_trip(db_sessionmaker, trip_id).id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        formula_version=settings.route_analytics_formula_version,
        computed_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    async def process():
        async with db_sessionmaker() as session:
            result = await process_ended_trip(
                session, trip_id=UUID(trip_id), settings=settings
            )
            await session.commit()
            return result

    assert asyncio.run(process()).overall in {"completed", "partial"}

    pings_before = len(fetch_all(db_sessionmaker, LocationPing))
    applied = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply",
        headers=admin_headers(db_client),
        json={"note": "verified GPS evidence from support ticket 42"},
    )
    assert applied.status_code == http_status.HTTP_200_OK
    body = applied.json()
    assert body["accepted_count"] == 1
    assert body["affected_lagos_days"], "must name the days for recompute-day"
    assert len(fetch_all(db_sessionmaker, LocationPing)) == pings_before + 1
    assert "admin.trip.quarantined_batch.applied" in audit_actions(db_sessionmaker)
    # Trip stays sealed; money is corrected via recompute-day, never here.
    assert fetch_trip(db_sessionmaker, trip_id).status == TripSessionStatus.SEALED.value

    # A resolved row cannot be re-applied or discarded.
    again = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/discard",
        headers=admin_headers(db_client),
        json={"note": "late"},
    )
    assert again.status_code == http_status.HTTP_409_CONFLICT


def test_admin_discards_quarantined_batch(db_client, db_sessionmaker) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    end_trip(db_client, trip_id, watermark={"client_batch_count": 0, "client_complete": True})
    late = send_batch(db_client, trip_id, "late-discard")
    quarantine_id = late.json()["batch_id"]

    discarded = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/discard",
        headers=admin_headers(db_client),
        json={"note": "spoofed points, confirmed with driver"},
    )
    assert discarded.status_code == http_status.HTTP_200_OK
    assert discarded.json()["status"] == "discarded"
    assert discarded.json()["resolution_note"]
    assert "admin.trip.quarantined_batch.discarded" in audit_actions(db_sessionmaker)
    assert len(fetch_all(db_sessionmaker, LocationPing)) == 0


def test_post_end_recorded_at_bound_rejects_points_after_trip(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    end_trip(db_client, trip_id)  # ended, recovery window open

    trip = fetch_trip(db_sessionmaker, trip_id)
    too_late = trip.ended_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.location_ping_end_skew_seconds + 30
    )
    rejected = send_batch(db_client, trip_id, "after-end", recorded_at=too_late)
    assert rejected.status_code == http_status.HTTP_400_BAD_REQUEST
    assert rejected.json()["error"]["code"] == "INVALID_RECORDED_AT"

    within = trip.ended_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.location_ping_end_skew_seconds - 30
    )
    accepted = send_batch(db_client, trip_id, "within-skew", recorded_at=within)
    assert accepted.status_code == http_status.HTTP_200_OK


def test_ended_window_ingest_skips_assignment_active_gate(db_client, db_sessionmaker) -> None:
    # Evidence recorded during the trip must remain deliverable even if the
    # assignment is deactivated right after the trip ends (RM3 review point 4).
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    end_trip(db_client, trip_id)
    update_assignment_status(
        db_sessionmaker, assignment.id, CampaignAssignmentStatus.DEACTIVATED
    )

    late = send_batch(db_client, trip_id, "post-deactivation")
    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["quarantined"] is False


def test_preseal_analytics_is_recomputed_before_money(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    """Finding: analytics computed during the recovery window (pre-seal) must
    never be reused for the write-once money chain — the sealed ping set may
    contain late batches the analytics never saw."""
    async def authorize_legacy_trip(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(trips_service, "assert_new_work_authorized", authorize_legacy_trip)
    admin, campaign, driver, profile, vehicle, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker, with_financial_authority=False
    )
    trip_id = start_trip(postgis_db_client, assignment.id).json()["id"]
    recorded = datetime.now(UTC)
    assert (
        send_batch(postgis_db_client, trip_id, "b1", recorded_at=recorded).status_code == 200
    )
    # Incomplete end: 2 batches announced, 1 delivered -> stays `ended`.
    end_trip(
        postgis_db_client,
        trip_id,
        watermark={"client_batch_count": 2, "client_ping_count": 2, "client_complete": False},
    )
    assert (
        fetch_trip(postgis_db_sessionmaker, trip_id).status == TripSessionStatus.ENDED.value
    )

    # Analytics computed DURING the recovery window (sees only batch b1).
    async def compute_preseal():
        async with postgis_db_sessionmaker() as session:
            computation = await recompute_trip_analytics(
                session, trip_id=UUID(trip_id), metadata={}, settings=settings
            )
            await session.commit()
            return computation.analytics.computed_at

    preseal_computed_at = asyncio.run(compute_preseal())

    # The missing batch arrives and completes the watermark -> seal.
    late = send_batch(postgis_db_client, trip_id, "b2", recorded_at=recorded)
    assert late.json()["quarantined"] is False
    trip = fetch_trip(postgis_db_sessionmaker, trip_id)
    assert trip.status == TripSessionStatus.SEALED.value
    assert preseal_computed_at.replace(tzinfo=UTC) < trip.sealed_at.replace(tzinfo=UTC)

    create_test_payout_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        base_rate_per_km=10,
    )

    async def process():
        async with postgis_db_sessionmaker() as session:
            result = await process_ended_trip(
                session, trip_id=UUID(trip_id), settings=settings
            )
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
