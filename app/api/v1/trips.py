from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import (
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
    TripEnqueuerDependency,
)
from app.core.gps_health import GPSAttempt, record_gps_attempt
from app.schemas.trips import (
    CurrentTripResponse,
    LocationPingBatchCreate,
    LocationPingBatchResponse,
    PingSampleResult,
    TripEndRequest,
    TripEvidenceReconcileResponse,
    TripRead,
    TripStartRequest,
)
from app.services.audit import create_audit_event
from app.services.trip_evidence import manifest_sample_results
from app.services.trips import (
    TripSummary,
    end_driver_trip,
    get_current_driver_trip,
    get_driver_trip,
    ingest_location_ping_batch,
    reconcile_trip_evidence,
    start_driver_trip,
    summarize_trip,
)

router = APIRouter(prefix="/driver/trips", tags=["Trips"])


def trip_response(summary: TripSummary) -> TripRead:
    trip = summary.trip
    return TripRead(
        id=trip.id,
        assignment_id=trip.assignment_id,
        campaign_id=trip.campaign_id,
        driver_profile_id=trip.driver_profile_id,
        vehicle_id=trip.vehicle_id,
        status=trip.status,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        end_reason=trip.end_reason,
        evidence_protocol_version=trip.evidence_protocol_version,
        evidence_manifest_root_sha256=trip.evidence_manifest_root_sha256,
        evidence_manifest_complete=trip.evidence_manifest_complete,
        evidence_manifest_verified_at=trip.evidence_manifest_verified_at,
        sealed_at=trip.sealed_at,
        seal_reason=trip.seal_reason,
        ping_count=summary.ping_count,
        first_ping_at=summary.first_ping_at,
        last_ping_at=summary.last_ping_at,
        metadata=trip.trip_metadata,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


@router.post(
    "/start",
    response_model=TripRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a driver trip",
)
async def driver_start_trip(
    payload: TripStartRequest,
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> TripRead:
    trip = await start_driver_trip(
        session, user_id=current_user.id, payload=payload, settings=settings
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="driver.trip.started",
        entity_type="trip_session",
        entity_id=str(trip.id),
        metadata={
            "assignment_id": str(trip.assignment_id),
            "campaign_id": str(trip.campaign_id),
        },
    )
    await session.commit()
    return trip_response(await summarize_trip(session, trip))


@router.get(
    "/current",
    response_model=CurrentTripResponse,
    summary="Get current active driver trip",
)
async def driver_get_current_trip(
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> CurrentTripResponse:
    trip = await get_current_driver_trip(session, user_id=current_user.id)
    if trip is None:
        return CurrentTripResponse(trip=None)
    return CurrentTripResponse(trip=trip_response(await summarize_trip(session, trip)))


@router.post(
    "/{trip_id}/pings",
    response_model=LocationPingBatchResponse,
    summary="Ingest a batch of driver location pings",
)
async def driver_ingest_location_pings(
    trip_id: UUID,
    payload: LocationPingBatchCreate,
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    enqueuer: TripEnqueuerDependency,
) -> LocationPingBatchResponse:
    telemetry = GPSAttempt()
    try:
        result = await ingest_location_ping_batch(
            session,
            user_id=current_user.id,
            trip_id=trip_id,
            payload=payload,
            settings=settings,
            telemetry=telemetry,
        )
    finally:
        await record_gps_attempt(settings, telemetry)
    await session.commit()
    row = result.batch
    if not result.duplicate and row.evidence_scope == "late" and row.pings_accepted:
        await enqueuer.enqueue_trip_processing(trip_id)
    return LocationPingBatchResponse(
        batch_id=row.id,
        trip_id=row.trip_session_id,
        accepted_count=row.pings_accepted,
        submitted_count=row.pings_submitted,
        rejected_count=row.pings_rejected,
        batch_sequence=row.batch_sequence,
        payload_hash_version=row.payload_hash_version,
        payload_hash=row.payload_hash,
        outcome=row.receipt_outcome,
        evidence_scope=cast(Literal["manifest", "late", "late_dropped"], row.evidence_scope),
        receipt_format_version=row.receipt_format_version,
        receipt_key_version=row.receipt_key_version,
        receipt_signature=row.receipt_signature,
        duplicate=result.duplicate,
        # Replayed from the stored manifest, so a retry of a partially
        # accepted batch returns byte-identical dispositions.
        sample_results=[
            PingSampleResult(**entry) for entry in manifest_sample_results(row.rejection_manifest)
        ],
    )


@router.post(
    "/{trip_id}/end",
    response_model=TripRead,
    summary="End a driver trip",
)
async def driver_end_trip(
    trip_id: UUID,
    payload: TripEndRequest,
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    enqueuer: TripEnqueuerDependency,
) -> TripRead:
    result = await end_driver_trip(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        payload=payload,
        settings=settings,
    )
    trip = result.trip
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="driver.trip.ended",
        entity_type="trip_session",
        entity_id=str(trip.id),
        metadata={
            "end_reason": trip.end_reason,
            "evidence_manifest_batch_count": trip.evidence_manifest_batch_count,
            "evidence_manifest_ping_count": trip.evidence_manifest_ping_count,
            "evidence_manifest_complete": trip.evidence_manifest_complete,
            "sealed_now": result.sealed_now,
        },
    )
    await session.commit()
    if result.sealed_now:
        # Fail-open latency optimization; the sweep is the guaranteed path
        # (Â§14.3.2). Unsealed v2 ends wait for exact late data and reconcile;
        # grace records an audit marker but never opens the money chain (D25).
        await enqueuer.enqueue_trip_processing(trip.id)
    return trip_response(await summarize_trip(session, trip))


@router.post(
    "/{trip_id}/evidence/reconcile",
    response_model=TripEvidenceReconcileResponse,
    summary="Reconcile and seal exact trip evidence",
)
async def driver_reconcile_trip_evidence(
    trip_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    enqueuer: TripEnqueuerDependency,
) -> TripEvidenceReconcileResponse:
    result = await reconcile_trip_evidence(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        settings=settings,
    )
    trip = result.trip
    if result.adjudicated and not result.duplicate:
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="trip.evidence_adjudicated_incomplete",
            entity_type="trip_session",
            entity_id=str(trip.id),
            metadata={
                "outcome": trip.evidence_adjudication_outcome,
                "manifest_root_sha256": trip.evidence_manifest_root_sha256,
                "evidence_protocol_version": trip.evidence_protocol_version,
            },
        )
    await session.commit()
    # An adjudicated trip is never sealed, so there is no money chain to run.
    if not result.duplicate and not result.adjudicated:
        await enqueuer.enqueue_trip_processing(trip_id)
    return TripEvidenceReconcileResponse(
        trip_id=trip.id,
        status=trip.status,
        manifest_root_sha256=trip.evidence_manifest_root_sha256,
        manifest_complete=trip.evidence_manifest_complete,
        manifest_verified_at=trip.evidence_manifest_verified_at,
        adjudication_outcome=trip.evidence_adjudication_outcome,
        adjudicated_at=trip.evidence_adjudicated_at,
        receipt_format_version=(
            trip.evidence_adjudication_receipt_format_version
            if result.adjudicated
            else trip.evidence_manifest_receipt_format_version
        ),
        receipt_key_version=(
            trip.evidence_adjudication_receipt_key_version
            if result.adjudicated
            else trip.evidence_manifest_receipt_key_version
        ),
        receipt_signature=(
            trip.evidence_adjudication_receipt_signature
            if result.adjudicated
            else trip.evidence_manifest_receipt_signature
        ),
        duplicate=result.duplicate,
    )


@router.get(
    "/{trip_id}",
    response_model=TripRead,
    summary="Get a driver trip summary",
)
async def driver_get_trip(
    trip_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> TripRead:
    trip = await get_driver_trip(session, user_id=current_user.id, trip_id=trip_id)
    return trip_response(await summarize_trip(session, trip))
