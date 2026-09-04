"""R37 / OFF-006: deactivation drain and final evidence adjudication."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from starlette import status as http_status
from test_trip_seal import (
    admin_headers,
    batch_descriptor,
    make_batch_payload,
    remember_batch,
)
from test_trips import create_trip_ready_graph, driver_headers, start_trip

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignActivationEventType,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.trip import LocationPingBatch, QuarantinedPingBatch, TripSession
from app.schemas.trips import (
    LocationPingBatchCreate,
    TripEndRequest,
    TripEvidenceManifestCreate,
    TripStartRequest,
)
from app.services import trips as trips_service
from app.services.trip_evidence import manifest_root, verify_adjudication_receipt
from app.services.trip_processing import seal_due_trips
from app.services.trips import end_driver_trip, start_driver_trip


def fetch_trip(db_sessionmaker, trip_id) -> TripSession:
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.get(TripSession, UUID(str(trip_id)))

    return asyncio.run(fetch())


def deactivate_assignment(db_sessionmaker, assignment_id, *, at=None) -> datetime:
    """Deactivate the way the real service does: status plus its timestamp."""
    moment = at or (datetime.now(UTC) + timedelta(seconds=5))

    async def deactivate() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, UUID(str(assignment_id)))
            previous_status = assignment.status
            assignment.status = CampaignAssignmentStatus.DEACTIVATED.value
            assignment.deactivated_at = moment
            session.add(
                CampaignActivationEvent(
                    assignment_id=assignment.id,
                    actor_user_id=None,
                    event_type=CampaignActivationEventType.DEACTIVATED.value,
                    previous_status=previous_status,
                    new_status=CampaignAssignmentStatus.DEACTIVATED.value,
                    occurred_at=moment,
                )
            )
            await session.commit()

    asyncio.run(deactivate())
    return moment


def reactivate_assignment(db_sessionmaker, assignment_id, *, at=None) -> datetime:
    moment = at or datetime.now(UTC)

    async def reactivate() -> None:
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, UUID(str(assignment_id)))
            previous_status = assignment.status
            assignment.status = CampaignAssignmentStatus.ACTIVE.value
            assignment.activated_at = moment
            session.add(
                CampaignActivationEvent(
                    assignment_id=assignment.id,
                    actor_user_id=None,
                    event_type=CampaignActivationEventType.ACTIVATED.value,
                    previous_status=previous_status,
                    new_status=CampaignAssignmentStatus.ACTIVE.value,
                    occurred_at=moment,
                )
            )
            await session.commit()

    asyncio.run(reactivate())
    return moment


def expire_grace(db_sessionmaker, trip_id) -> None:
    """Stand in for the server-owned evidence-grace sweep marker."""

    async def mark() -> None:
        async with db_sessionmaker() as session:
            trip = await session.get(TripSession, UUID(str(trip_id)))
            trip.grace_expired_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(mark())


def audit_actions(db_sessionmaker) -> list[str]:
    async def fetch():
        async with db_sessionmaker() as session:
            return [
                row.action
                for row in (await session.execute(select(AuditEvent))).scalars().all()
            ]

    return asyncio.run(fetch())


def at_ms(moment: datetime) -> str:
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000).isoformat()


def multi_sample_payload(key, moments, *, batch_sequence=0) -> dict:
    return {
        "idempotency_key": key,
        "batch_sequence": batch_sequence,
        "pings": [
            {
                "recorded_at": at_ms(moment),
                "lat": 6.45,
                "lon": 3.39,
                "accuracy_m": 12.5,
                "speed_mps": 8.3,
                "heading_degrees": 180.0,
                "altitude_m": 42.0,
                "sequence_number": index,
                "metadata": {"source": "gps"},
            }
            for index, moment in enumerate(moments)
        ],
        "metadata": {"device": "phone"},
    }


def send(db_client, trip_id, payload):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings",
        headers=driver_headers(db_client),
        json=payload,
    )


def end_with_manifest(db_client, trip_id, descriptors, *, complete: bool):
    return db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=driver_headers(db_client),
        json={
            "end_reason": "driver_ended",
            "evidence_manifest": manifest_body(trip_id, descriptors, complete=complete),
            "metadata": {},
        },
    )


def manifest_body(trip_id, descriptors, *, complete: bool) -> dict:
    ping_count = sum(entry.submitted_count for entry in descriptors)
    return {
        "version": 2,
        "root_sha256": manifest_root(
            trip_id=UUID(str(trip_id)), entries=descriptors, ping_count=ping_count
        ),
        "ping_count": ping_count,
        "complete": complete,
        "entries": [entry.model_dump() for entry in descriptors],
    }


def test_captured_evidence_survives_deactivation_and_lands_after_end(
    db_client, db_sessionmaker
) -> None:
    """Deactivate mid-trip, then End: already captured evidence still lands."""
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload("captured-before-deactivation", batch_sequence=0)
    descriptor = batch_descriptor(payload)

    deactivate_assignment(db_sessionmaker, assignment.id)

    # New capture is still refused while the trip is active — the assignment
    # authority is gone — but the refusal must be recoverable, not terminal.
    blocked = send(db_client, trip_id, payload)
    assert blocked.status_code == http_status.HTTP_400_BAD_REQUEST
    assert blocked.json()["error"]["code"] == "CAMPAIGN_ASSIGNMENT_NOT_ACTIVE"

    ended = end_with_manifest(db_client, trip_id, [descriptor], complete=True)
    assert ended.status_code == http_status.HTTP_200_OK
    assert ended.json()["status"] == "ended"

    # Ended-policy authority now accepts the exact precommitted descriptor.
    delivered = send(db_client, trip_id, payload)
    assert delivered.status_code == http_status.HTTP_200_OK
    assert delivered.json()["accepted_count"] == 1
    assert delivered.json()["quarantined"] is False

    reconciled = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert reconciled.status_code == http_status.HTTP_200_OK
    assert reconciled.json()["status"] == "sealed"
    assert reconciled.json()["manifest_complete"] is True
    assert reconciled.json()["adjudication_outcome"] is None


def test_samples_captured_after_deactivation_are_refused_even_after_end(
    db_client, db_sessionmaker
) -> None:
    """D25: delivery after deactivation is allowed; capture after it is not."""
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    now = datetime.now(UTC).replace(microsecond=0)
    lapsed_at = now + timedelta(seconds=5)
    payload = multi_sample_payload(
        "straddles-deactivation", [now, lapsed_at + timedelta(seconds=5)]
    )
    descriptor = batch_descriptor(LocationPingBatchCreate.model_validate(payload))
    deactivate_assignment(db_sessionmaker, assignment.id, at=lapsed_at)
    end_with_manifest(db_client, trip_id, [descriptor], complete=True)

    delivered = send(db_client, trip_id, payload)

    assert delivered.status_code == http_status.HTTP_200_OK
    body = delivered.json()
    # The sample captured while authority still held is kept; the one captured
    # after it lapsed is durably refused, not laundered in by the ended window.
    assert (body["accepted_count"], body["rejected_count"]) == (1, 1)
    assert [entry["status"] for entry in body["sample_results"]] == ["accepted", "rejected"]
    assert body["sample_results"][1]["rejection_code"] == "INVALID_ASSIGNMENT_AUTHORITY"


def test_reactivation_does_not_launder_samples_captured_during_the_lapse(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    now = datetime.now(UTC).replace(microsecond=0)
    first_lapse = now + timedelta(seconds=2)
    first_resume = now + timedelta(seconds=8)
    second_lapse = now + timedelta(seconds=12)
    second_resume = now + timedelta(seconds=18)
    deactivate_assignment(db_sessionmaker, assignment.id, at=first_lapse)
    reactivate_assignment(db_sessionmaker, assignment.id, at=first_resume)
    deactivate_assignment(db_sessionmaker, assignment.id, at=second_lapse)
    reactivate_assignment(db_sessionmaker, assignment.id, at=second_resume)

    response = send(
        db_client,
        trip_id,
        multi_sample_payload(
            "spans-the-lapse",
            [
                now,
                first_lapse,
                first_resume + timedelta(seconds=1),
                second_lapse + timedelta(seconds=1),
                second_resume + timedelta(seconds=1),
            ],
        ),
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    # Every historical gap is refused, including the exact deactivation
    # boundary; reactivation restores authority only from its own timestamp.
    assert [entry["status"] for entry in body["sample_results"]] == [
        "accepted",
        "rejected",
        "accepted",
        "rejected",
        "accepted",
    ]
    assert body["sample_results"][1]["rejection_code"] == "INVALID_ASSIGNMENT_AUTHORITY"
    assert body["sample_results"][3]["rejection_code"] == "INVALID_ASSIGNMENT_AUTHORITY"
    assert (body["accepted_count"], body["rejected_count"]) == (3, 2)


def test_incomplete_evidence_is_not_final_while_the_grace_window_is_open(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    undelivered = batch_descriptor(make_batch_payload("never-delivered", batch_sequence=0))
    end_with_manifest(db_client, trip_id, [undelivered], complete=False)

    response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )

    assert response.status_code == http_status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "TRIP_EVIDENCE_INCOMPLETE"
    assert fetch_trip(db_sessionmaker, trip_id).evidence_adjudicated_at is None


def test_server_grace_sweep_signs_final_incomplete_adjudication_without_client_return(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    undelivered = batch_descriptor(make_batch_payload("never-delivered", batch_sequence=0))
    end_with_manifest(db_client, trip_id, [undelivered], complete=False)
    trip = fetch_trip(db_sessionmaker, trip_id)
    sweep_at = trip.ended_at.replace(tzinfo=UTC) + timedelta(
        seconds=settings.trip_seal_grace_seconds + 1
    )

    async def sweep() -> list[UUID]:
        async with db_sessionmaker() as session:
            result = await seal_due_trips(session, settings=settings, now=sweep_at)
            await session.commit()
            return result

    assert asyncio.run(sweep()) == [UUID(str(trip_id))]
    adjudicated = fetch_trip(db_sessionmaker, trip_id)
    assert adjudicated.status == "ended"
    assert adjudicated.sealed_at is None
    assert adjudicated.evidence_manifest_verified_at is None
    assert adjudicated.evidence_adjudication_outcome == "incomplete_grace_expired"
    assert verify_adjudication_receipt(adjudicated, settings)
    assert audit_actions(db_sessionmaker).count("trip.evidence_adjudicated_incomplete") == 1
    replay = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json()["duplicate"] is True
    assert replay.json()["receipt_signature"] == adjudicated.evidence_adjudication_receipt_signature
    assert asyncio.run(sweep()) == []


def test_expired_grace_produces_a_signed_final_adjudication_without_money(
    db_client, db_sessionmaker, settings
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    undelivered = batch_descriptor(make_batch_payload("never-delivered", batch_sequence=0))
    end_with_manifest(db_client, trip_id, [undelivered], complete=False)
    expire_grace(db_sessionmaker, trip_id)

    response = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )

    assert response.status_code == http_status.HTTP_200_OK
    body = response.json()
    assert body["adjudication_outcome"] == "incomplete_grace_expired"
    assert body["adjudicated_at"] is not None
    assert body["manifest_complete"] is False
    assert body["manifest_verified_at"] is None
    assert body["receipt_signature"]
    assert body["duplicate"] is False

    trip = fetch_trip(db_sessionmaker, trip_id)
    # D25: adjudication is not a seal and never authenticates the manifest, so
    # the money chain stays closed.
    assert trip.status == "ended"
    assert trip.sealed_at is None
    assert trip.evidence_manifest_verified_at is None
    assert trip.evidence_manifest_complete is False
    assert verify_adjudication_receipt(trip, settings)
    assert "trip.evidence_adjudicated_incomplete" in audit_actions(db_sessionmaker)

    replay = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json()["duplicate"] is True
    assert replay.json()["receipt_signature"] == body["receipt_signature"]
    assert replay.json()["adjudicated_at"] == body["adjudicated_at"]


def test_concurrent_reconciles_adjudicate_exactly_once_postgres(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    """Two racing reconciles must not both adjudicate or both audit."""
    _, _, driver, profile, vehicle, assignment = create_trip_ready_graph(
        postgis_db_sessionmaker
    )
    undelivered = batch_descriptor(make_batch_payload("never-delivered", batch_sequence=0))

    async def prepare() -> UUID:
        async with postgis_db_sessionmaker() as session:
            trip = await start_driver_trip(
                session,
                user_id=driver.id,
                payload=TripStartRequest(assignment_id=assignment.id, evidence_protocol_version=2),
                settings=settings,
            )
            await end_driver_trip(
                session,
                user_id=driver.id,
                trip_id=trip.id,
                payload=TripEndRequest(
                    end_reason="driver_ended",
                    evidence_manifest=TripEvidenceManifestCreate.model_validate(
                        manifest_body(trip.id, [undelivered], complete=False)
                    ),
                ),
                settings=settings,
            )
            trip.grace_expired_at = datetime.now(UTC)
            await session.commit()
            return trip.id

    trip_id = asyncio.run(prepare())

    original_lock = trips_service.acquire_campaign_terms_lock
    both_at_lock = asyncio.Event()
    lock_calls = 0

    async def barrier_lock(session, campaign_id):
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 2:
            both_at_lock.set()
        await both_at_lock.wait()
        await original_lock(session, campaign_id)

    monkeypatch.setattr(trips_service, "acquire_campaign_terms_lock", barrier_lock)

    async def reconcile() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                result = await trips_service.reconcile_trip_evidence(
                    session, user_id=driver.id, trip_id=trip_id, settings=settings
                )
                await session.commit()
                return "duplicate" if result.duplicate else "adjudicated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def race():
        return await asyncio.wait_for(asyncio.gather(reconcile(), reconcile()), timeout=20)

    outcomes = asyncio.run(race())

    assert lock_calls == 2
    # Exactly one transaction may write and audit the final adjudication.
    assert sorted(outcomes) == ["adjudicated", "duplicate"]

    async def fetch() -> TripSession:
        async with postgis_db_sessionmaker() as session:
            return await session.get(TripSession, trip_id)

    trip = asyncio.run(fetch())
    assert trip.evidence_adjudication_outcome == "incomplete_grace_expired"
    assert trip.status == "ended" and trip.sealed_at is None
    assert verify_adjudication_receipt(trip, settings)


def test_evidence_arriving_after_adjudication_is_preserved_not_discarded(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = make_batch_payload("late-after-adjudication", batch_sequence=0)
    remember_batch(trip_id, payload)
    descriptor = batch_descriptor(payload)
    end_with_manifest(db_client, trip_id, [descriptor], complete=False)
    expire_grace(db_sessionmaker, trip_id)
    db_client.post(
        f"/api/v1/driver/trips/{trip_id}/evidence/reconcile",
        headers=driver_headers(db_client),
    )

    late = send(db_client, trip_id, payload)

    assert late.status_code == http_status.HTTP_200_OK
    assert late.json()["quarantined"] is True
    assert late.json()["accepted_count"] == 0
    # A quarantine is a preservation, not a per-sample adjudication.
    assert late.json()["sample_results"] == []

    async def counts():
        async with db_sessionmaker() as session:
            quarantined = list(
                (await session.execute(select(QuarantinedPingBatch))).scalars().all()
            )
            live = list((await session.execute(select(LocationPingBatch))).scalars().all())
            return len(quarantined), len(live)

    quarantined_count, live_count = asyncio.run(counts())
    assert (quarantined_count, live_count) == (1, 0)

    # An adjudicated trip was never sealed, so it has no money to correct: the
    # admin reopen path refuses rather than originating a payout from it.
    applied = db_client.post(
        f"/api/v1/admin/trips/{trip_id}/quarantined-batches/"
        f"{late.json()['batch_id']}/apply",
        headers=admin_headers(db_client),
        json={"note": "driver reported a missing stretch"},
    )
    assert applied.status_code == http_status.HTTP_409_CONFLICT
    assert applied.json()["error"]["code"] == "QUARANTINE_APPLY_BLOCKED"
