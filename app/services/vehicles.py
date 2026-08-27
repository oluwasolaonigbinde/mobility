from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication
from app.models.user import User, UserRole
from app.models.vehicle import Vehicle
from app.schemas.vehicles import VehicleCreate, VehicleUpdate, normalize_plate_country_code
from app.services.drivers import get_driver_profile_by_user_id
from app.services.users import get_user_by_id


def normalize_plate_number(plate_number: str) -> str:
    normalized = "".join(
        character
        for character in plate_number.upper()
        if not character.isspace() and character != "-"
    )
    if not normalized:
        raise AppError(
            "INVALID_PLATE_NUMBER",
            "Plate number must contain at least one non-separator character",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized


async def ensure_unique_plate(
    session: AsyncSession,
    *,
    plate_country_code: str,
    plate_number_normalized: str,
    exclude_vehicle_id: UUID | None = None,
) -> None:
    statement = select(Vehicle.id).where(
        Vehicle.plate_country_code == plate_country_code,
        Vehicle.plate_number_normalized == plate_number_normalized,
    )
    if exclude_vehicle_id is not None:
        statement = statement.where(Vehicle.id != exclude_vehicle_id)
    existing_vehicle_id = await session.scalar(statement)
    if existing_vehicle_id is not None:
        raise AppError(
            "DUPLICATE_VEHICLE_PLATE",
            "A vehicle with this normalized plate already exists in this country",
            status_code=status.HTTP_409_CONFLICT,
        )


async def get_vehicle_with_driver(
    session: AsyncSession,
    vehicle_id: UUID,
) -> tuple[Vehicle, DriverProfile, User] | None:
    result = await session.execute(
        select(Vehicle, DriverProfile, User)
        .join(DriverProfile, Vehicle.driver_profile_id == DriverProfile.id)
        .join(User, DriverProfile.user_id == User.id)
        .where(Vehicle.id == vehicle_id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1], row[2]


async def create_vehicle_for_driver_user(
    session: AsyncSession,
    user_id: UUID,
    payload: VehicleCreate,
) -> tuple[Vehicle, DriverProfile, User]:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)
    if user.role != UserRole.DRIVER:
        raise AppError(
            "USER_IS_NOT_DRIVER",
            "Vehicle can only be created for a driver user",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    driver_profile = await get_driver_profile_by_user_id(session, user_id)
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found for this user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if payload.status == "active" and await session.scalar(
        select(DriverApplication.id).where(DriverApplication.driver_profile_id == driver_profile.id)
    ):
        raise AppError(
            "VEHICLE_APPROVAL_REQUIRED",
            "Public applicant vehicles become active only through current evidence approval",
            status_code=status.HTTP_409_CONFLICT,
        )

    plate_number_normalized = normalize_plate_number(payload.plate_number)
    await ensure_unique_plate(
        session,
        plate_country_code=payload.plate_country_code,
        plate_number_normalized=plate_number_normalized,
    )
    vehicle = Vehicle(
        driver_profile_id=driver_profile.id,
        plate_number=payload.plate_number,
        plate_number_normalized=plate_number_normalized,
        plate_country_code=payload.plate_country_code,
        vehicle_type=payload.vehicle_type,
        make=payload.make,
        model=payload.model,
        year=payload.year,
        color=payload.color,
        status=payload.status,
        vehicle_metadata=payload.metadata,
    )
    session.add(vehicle)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "DUPLICATE_VEHICLE_PLATE",
            "A vehicle with this normalized plate already exists in this country",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await session.refresh(vehicle)
    return vehicle, driver_profile, user


async def list_admin_vehicles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    vehicle_status: str | None,
    vehicle_type: str | None,
    plate_country_code: str | None,
    driver_profile_id: UUID | None,
) -> tuple[list[tuple[Vehicle, DriverProfile, User]], int]:
    filters = []
    if vehicle_status is not None:
        filters.append(Vehicle.status == vehicle_status)
    if vehicle_type is not None:
        filters.append(Vehicle.vehicle_type == vehicle_type)
    if plate_country_code is not None:
        filters.append(
            Vehicle.plate_country_code == normalize_plate_country_code(plate_country_code)
        )
    if driver_profile_id is not None:
        filters.append(Vehicle.driver_profile_id == driver_profile_id)

    statement = (
        select(Vehicle, DriverProfile, User)
        .join(DriverProfile, Vehicle.driver_profile_id == DriverProfile.id)
        .join(User, DriverProfile.user_id == User.id)
    )
    count_statement = select(func.count()).select_from(Vehicle)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(Vehicle.created_at.desc(), Vehicle.id).limit(limit).offset(offset)
    )
    return [(row[0], row[1], row[2]) for row in result.all()], int(total or 0)


async def list_driver_vehicles(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
    vehicle_status: str | None,
) -> tuple[list[Vehicle], int]:
    driver_profile = await get_driver_profile_by_user_id(session, user_id)
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    filters = [Vehicle.driver_profile_id == driver_profile.id]
    if vehicle_status is not None:
        filters.append(Vehicle.status == vehicle_status)

    statement = select(Vehicle)
    count_statement = select(func.count()).select_from(Vehicle)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(Vehicle.created_at.desc(), Vehicle.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_driver_vehicle(
    session: AsyncSession,
    *,
    user_id: UUID,
    vehicle_id: UUID,
) -> Vehicle:
    driver_profile = await get_driver_profile_by_user_id(session, user_id)
    if driver_profile is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    result = await session.execute(
        select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.driver_profile_id == driver_profile.id,
        )
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return vehicle


async def update_vehicle(
    session: AsyncSession,
    vehicle_id: UUID,
    payload: VehicleUpdate,
) -> tuple[Vehicle, DriverProfile, User, list[str]]:
    row = await get_vehicle_with_driver(session, vehicle_id)
    if row is None:
        raise AppError(
            "VEHICLE_NOT_FOUND",
            "Vehicle was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    vehicle, driver_profile, user = row
    update_values = payload.model_dump(exclude_unset=True)
    changed_fields = list(update_values)
    if update_values.get("status") == "active" and await session.scalar(
        select(DriverApplication.id).where(DriverApplication.driver_profile_id == driver_profile.id)
    ):
        raise AppError(
            "VEHICLE_APPROVAL_REQUIRED",
            "Public applicant vehicles become active only through current evidence approval",
            status_code=status.HTTP_409_CONFLICT,
        )

    for required_field in ["plate_number", "plate_country_code", "vehicle_type", "status"]:
        if required_field in update_values and update_values[required_field] is None:
            raise AppError(
                "INVALID_VEHICLE_UPDATE",
                f"{required_field} cannot be null",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if "metadata" in update_values:
        metadata = update_values.pop("metadata")
        if metadata is None:
            raise AppError(
                "INVALID_METADATA",
                "Metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        vehicle.vehicle_metadata = metadata

    plate_number = update_values.get("plate_number", vehicle.plate_number)
    plate_country_code = update_values.get("plate_country_code", vehicle.plate_country_code)
    if "plate_number" in update_values or "plate_country_code" in update_values:
        plate_number_normalized = normalize_plate_number(plate_number)
        await ensure_unique_plate(
            session,
            plate_country_code=plate_country_code,
            plate_number_normalized=plate_number_normalized,
            exclude_vehicle_id=vehicle.id,
        )
        vehicle.plate_number = plate_number
        vehicle.plate_country_code = plate_country_code
        vehicle.plate_number_normalized = plate_number_normalized
        update_values.pop("plate_number", None)
        update_values.pop("plate_country_code", None)

    for field, value in update_values.items():
        setattr(vehicle, field, value)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "DUPLICATE_VEHICLE_PLATE",
            "A vehicle with this normalized plate already exists in this country",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await session.refresh(vehicle)
    return vehicle, driver_profile, user, changed_fields
