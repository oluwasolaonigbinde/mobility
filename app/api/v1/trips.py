from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
    TripEnqueuerDependency,
)
from app.schemas.trips import (
    CurrentTripResponse,
    LocationPingBatchCreate,
    LocationPingBatchResponse,
    QuarantineApplyResponse,
    QuarantinedPingBatchListResponse,
    QuarantinedPingBatchRead,
    QuarantineResolveRequest,
    TripEndRequest,
    TripRead,
    TripStartRequest,
)
from app.services.audit import create_audit_event
from app.services.trips import (
    TripSummary,
    apply_quarantined_ping_batch,
    discard_quarantined_ping_batch,
    end_driver_trip,
    get_current_driver_trip,
    get_driver_trip,
    ingest_location_ping_batch,
    list_quarantined_ping_batches,
    start_driver_trip,
    summarize_trip,
)

router = APIRouter(prefix="/driver/trips", tags=["Trips"])
admin_router = APIRouter(prefix="/admin/trips", tags=["Trips Admin"])


def trip_response(summary: TripSummary) -> TripRead:
    trip = summary.trip
    return TripRead(
        id=trip.id,
        assignment_id=trip.assignment_id,
        campaign_id=trip.campaign_id,
        driver_profile_id=trip.driver_profile_id,
        vehicle_id=trip.vehicle_id,
        display_proof_id=trip.display_proof_id,
        status=trip.status,
        started_at=trip.started_at,
        ended_at=trip.ended_at,
        end_reason=trip.end_reason,
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
    result = await ingest_location_ping_batch(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        payload=payload,
        settings=settings,
    )
    if result.quarantine is not None and not result.duplicate:
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="trip.ping_batch.quarantined",
            entity_type="quarantined_ping_batch",
            entity_id=str(result.quarantine.id),
            metadata={
                "trip_session_id": str(trip_id),
                "ping_count": result.quarantine.ping_count,
            },
        )
    await session.commit()
    if result.sealed_now:
        # Fail-open latency optimization; the sweep is the guaranteed path (§14.3.2).
        await enqueuer.enqueue_trip_processing(trip_id)
    if result.quarantine is not None:
        return LocationPingBatchResponse(
            batch_id=result.quarantine.id,
            trip_id=result.quarantine.trip_session_id,
            accepted_count=0,
            duplicate=result.duplicate,
            quarantined=True,
        )
    return LocationPingBatchResponse(
        batch_id=result.batch.id,
        trip_id=result.batch.trip_session_id,
        accepted_count=result.batch.pings_accepted,
        duplicate=result.duplicate,
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
    enqueuer: TripEnqueuerDependency,
) -> TripRead:
    result = await end_driver_trip(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        payload=payload,
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
            "client_batch_count": trip.client_batch_count,
            "client_ping_count": trip.client_ping_count,
            "client_complete": trip.client_complete,
            "sealed_now": result.sealed_now,
        },
    )
    await session.commit()
    if result.sealed_now:
        # Fail-open latency optimization; the sweep is the guaranteed path
        # (§14.3.2). Unsealed ends wait for late data or the grace sweep —
        # the money chain must never see an unsealed trip (RM3).
        await enqueuer.enqueue_trip_processing(trip.id)
    return trip_response(await summarize_trip(session, trip))


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


# --- admin: post-seal quarantine review (RM3 controlled reopen) ---------------


def quarantine_response(row) -> QuarantinedPingBatchRead:
    return QuarantinedPingBatchRead(
        id=row.id,
        trip_session_id=row.trip_session_id,
        idempotency_key=row.idempotency_key,
        ping_count=row.ping_count,
        received_at=row.received_at,
        status=row.status,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
        resolution_note=row.resolution_note,
        applied_batch_id=row.applied_batch_id,
        created_at=row.created_at,
    )


@admin_router.get(
    "/quarantined-batches",
    response_model=QuarantinedPingBatchListResponse,
    summary="List quarantined ping batches",
)
async def admin_list_quarantined_batches(
    current_user: AdminUserDependency,
    session: SessionDependency,
    trip_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> QuarantinedPingBatchListResponse:
    items, total = await list_quarantined_ping_batches(
        session,
        trip_id=trip_id,
        batch_status=status_filter,
        limit=limit,
        offset=offset,
    )
    return QuarantinedPingBatchListResponse(
        items=[quarantine_response(row) for row in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/{trip_id}/quarantined-batches/{quarantine_id}/apply",
    response_model=QuarantineApplyResponse,
    summary="Apply a quarantined ping batch as live trip evidence",
)
async def admin_apply_quarantined_batch(
    trip_id: UUID,
    quarantine_id: UUID,
    payload: QuarantineResolveRequest,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> QuarantineApplyResponse:
    result = await apply_quarantined_ping_batch(
        session,
        trip_id=trip_id,
        quarantine_id=quarantine_id,
        admin_user_id=current_user.id,
        note=payload.note,
        settings=settings,
    )
    await session.commit()
    return QuarantineApplyResponse(
        quarantine_id=result.quarantine.id,
        trip_id=trip_id,
        applied_batch_id=result.batch.id,
        accepted_count=result.batch.pings_accepted,
        affected_lagos_days=result.affected_lagos_days,
    )


@admin_router.post(
    "/{trip_id}/quarantined-batches/{quarantine_id}/discard",
    response_model=QuarantinedPingBatchRead,
    summary="Discard a quarantined ping batch",
)
async def admin_discard_quarantined_batch(
    trip_id: UUID,
    quarantine_id: UUID,
    payload: QuarantineResolveRequest,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> QuarantinedPingBatchRead:
    quarantine = await discard_quarantined_ping_batch(
        session,
        trip_id=trip_id,
        quarantine_id=quarantine_id,
        admin_user_id=current_user.id,
        note=payload.note,
    )
    await session.commit()
    return quarantine_response(quarantine)
