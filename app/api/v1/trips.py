from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import DriverUserDependency, SessionDependency, SettingsDependency
from app.schemas.trips import (
    CurrentTripResponse,
    LocationPingBatchCreate,
    LocationPingBatchResponse,
    TripEndRequest,
    TripRead,
    TripStartRequest,
)
from app.services.trips import (
    TripSummary,
    end_driver_trip,
    get_current_driver_trip,
    get_driver_trip,
    ingest_location_ping_batch,
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
) -> TripRead:
    trip = await start_driver_trip(session, user_id=current_user.id, payload=payload)
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
) -> LocationPingBatchResponse:
    result = await ingest_location_ping_batch(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        payload=payload,
        settings=settings,
    )
    await session.commit()
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
) -> TripRead:
    trip = await end_driver_trip(
        session,
        user_id=current_user.id,
        trip_id=trip_id,
        payload=payload,
    )
    await session.commit()
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
