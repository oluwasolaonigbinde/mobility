from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, DriverUserDependency, SessionDependency
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleStatus, VehicleType
from app.schemas.vehicles import (
    AdminVehicleListResponse,
    AdminVehicleRead,
    VehicleCreate,
    VehicleDriverSummary,
    VehicleListResponse,
    VehicleRead,
    VehicleUpdate,
)
from app.services.audit import create_audit_event
from app.services.vehicles import (
    create_vehicle_for_driver_user,
    get_driver_vehicle,
    get_vehicle_with_driver,
    list_admin_vehicles,
    list_driver_vehicles,
    update_vehicle,
)

router = APIRouter(tags=["Vehicles"])


def vehicle_response(vehicle: Vehicle) -> VehicleRead:
    return VehicleRead(
        id=vehicle.id,
        driver_profile_id=vehicle.driver_profile_id,
        plate_number=vehicle.plate_number,
        plate_number_normalized=vehicle.plate_number_normalized,
        plate_country_code=vehicle.plate_country_code,
        vehicle_type=vehicle.vehicle_type,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        color=vehicle.color,
        status=vehicle.status,
        created_at=vehicle.created_at,
        updated_at=vehicle.updated_at,
    )


def admin_vehicle_response(
    vehicle: Vehicle,
    driver_profile: DriverProfile,
    user: User,
) -> AdminVehicleRead:
    return AdminVehicleRead(
        **vehicle_response(vehicle).model_dump(),
        metadata=vehicle.vehicle_metadata,
        driver_profile=VehicleDriverSummary(
            id=driver_profile.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
        ),
    )


@router.get(
    "/driver/vehicles",
    response_model=VehicleListResponse,
    summary="List current driver vehicles",
)
async def driver_list_vehicles(
    current_user: DriverUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: VehicleStatus | None = None,
) -> VehicleListResponse:
    vehicles, total = await list_driver_vehicles(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        vehicle_status=status,
    )
    return VehicleListResponse(
        items=[vehicle_response(vehicle) for vehicle in vehicles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/driver/vehicles/{vehicle_id}",
    response_model=VehicleRead,
    summary="Get current driver vehicle",
)
async def driver_get_vehicle(
    vehicle_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> VehicleRead:
    vehicle = await get_driver_vehicle(session, user_id=current_user.id, vehicle_id=vehicle_id)
    return vehicle_response(vehicle)


@router.post(
    "/admin/drivers/{user_id}/vehicles",
    response_model=AdminVehicleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a vehicle for a driver",
)
async def admin_create_vehicle(
    user_id: UUID,
    payload: VehicleCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminVehicleRead:
    vehicle, driver_profile, user = await create_vehicle_for_driver_user(session, user_id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.vehicle.created",
        entity_type="vehicle",
        entity_id=str(vehicle.id),
        metadata={
            "driver_profile_id": str(driver_profile.id),
            "plate_country_code": vehicle.plate_country_code,
            "plate_number_normalized": vehicle.plate_number_normalized,
        },
    )
    await session.commit()
    return admin_vehicle_response(vehicle, driver_profile, user)


@router.get(
    "/admin/vehicles",
    response_model=AdminVehicleListResponse,
    summary="List vehicles",
)
async def admin_list_vehicles(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: VehicleStatus | None = None,
    vehicle_type: VehicleType | None = None,
    plate_country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    driver_profile_id: UUID | None = None,
) -> AdminVehicleListResponse:
    del current_user
    vehicles, total = await list_admin_vehicles(
        session,
        limit=limit,
        offset=offset,
        vehicle_status=status,
        vehicle_type=vehicle_type,
        plate_country_code=plate_country_code,
        driver_profile_id=driver_profile_id,
    )
    return AdminVehicleListResponse(
        items=[
            admin_vehicle_response(vehicle, driver_profile, user)
            for vehicle, driver_profile, user in vehicles
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/vehicles/{vehicle_id}",
    response_model=AdminVehicleRead,
    summary="Get a vehicle",
)
async def admin_get_vehicle(
    vehicle_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminVehicleRead:
    del current_user
    row = await get_vehicle_with_driver(session, vehicle_id)
    if row is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    vehicle, driver_profile, user = row
    return admin_vehicle_response(vehicle, driver_profile, user)


@router.patch(
    "/admin/vehicles/{vehicle_id}",
    response_model=AdminVehicleRead,
    summary="Update a vehicle",
)
async def admin_update_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminVehicleRead:
    vehicle, driver_profile, user, changed_fields = await update_vehicle(
        session,
        vehicle_id,
        payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.vehicle.updated",
        entity_type="vehicle",
        entity_id=str(vehicle.id),
        metadata={"changed_fields": changed_fields},
    )
    await session.commit()
    return admin_vehicle_response(vehicle, driver_profile, user)
