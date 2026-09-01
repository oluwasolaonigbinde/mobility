from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication, DriverApplicationStatus
from app.models.user import User, UserRole
from app.schemas.drivers import (
    DriverProfileAdminUpdate,
    DriverProfileCreate,
    DriverProfileSelfUpdate,
    normalize_optional_country_code,
    normalize_optional_text,
)
from app.services.driver_applications import terminalize_driver_application
from app.services.users import get_user_by_id


async def get_driver_profile_by_user_id(
    session: AsyncSession,
    user_id: UUID,
) -> DriverProfile | None:
    result = await session.execute(select(DriverProfile).where(DriverProfile.user_id == user_id))
    return result.scalar_one_or_none()


async def get_driver_profile_with_user_by_user_id(
    session: AsyncSession,
    user_id: UUID,
) -> tuple[DriverProfile, User] | None:
    result = await session.execute(
        select(DriverProfile, User)
        .join(User, DriverProfile.user_id == User.id)
        .where(DriverProfile.user_id == user_id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def get_driver_profile_with_user(
    session: AsyncSession,
    driver_profile_id: UUID,
) -> tuple[DriverProfile, User] | None:
    result = await session.execute(
        select(DriverProfile, User)
        .join(User, DriverProfile.user_id == User.id)
        .where(DriverProfile.id == driver_profile_id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def get_required_driver_profile_with_user_by_user_id(
    session: AsyncSession,
    user_id: UUID,
) -> tuple[DriverProfile, User]:
    row = await get_driver_profile_with_user_by_user_id(session, user_id)
    if row is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row


async def create_driver_profile(
    session: AsyncSession,
    user_id: UUID,
    payload: DriverProfileCreate,
) -> tuple[DriverProfile, User]:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)
    if user.role != UserRole.DRIVER:
        raise AppError(
            "USER_IS_NOT_DRIVER",
            "Driver profile can only be created for a driver user",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if await get_driver_profile_by_user_id(session, user_id):
        raise AppError(
            "DUPLICATE_DRIVER_PROFILE",
            "Driver profile already exists for this user",
            status_code=status.HTTP_409_CONFLICT,
        )

    profile = DriverProfile(
        user_id=user.id,
        onboarding_status=payload.onboarding_status,
        license_number=payload.license_number,
        service_city=payload.service_city,
        country_code=payload.country_code,
        profile_metadata=payload.metadata,
    )
    session.add(profile)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "DUPLICATE_DRIVER_PROFILE",
            "Driver profile already exists for this user",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await session.refresh(profile)
    return profile, user


async def list_driver_profiles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    onboarding_status: str | None,
    country_code: str | None,
    service_city: str | None,
) -> tuple[list[tuple[DriverProfile, User]], int]:
    filters = []
    if onboarding_status is not None:
        filters.append(DriverProfile.onboarding_status == onboarding_status)
    normalized_country_code = normalize_optional_country_code(country_code)
    if normalized_country_code is not None:
        filters.append(DriverProfile.country_code == normalized_country_code)
    normalized_service_city = normalize_optional_text(service_city)
    if normalized_service_city is not None:
        filters.append(DriverProfile.service_city == normalized_service_city)

    statement = select(DriverProfile, User).join(User, DriverProfile.user_id == User.id)
    count_statement = select(func.count()).select_from(DriverProfile)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(DriverProfile.created_at.desc(), DriverProfile.id)
        .limit(limit)
        .offset(offset)
    )
    return [(row[0], row[1]) for row in result.all()], int(total or 0)


async def update_driver_profile(
    session: AsyncSession,
    driver_profile_id: UUID,
    payload: DriverProfileAdminUpdate,
    *,
    actor_user_id: UUID,
) -> tuple[DriverProfile, User, list[str]]:
    update_values = payload.model_dump(exclude_unset=True)
    terminal_rejection = update_values.get("onboarding_status") == "rejected"
    application = None
    if terminal_rejection:
        application = await session.scalar(
            select(DriverApplication)
            .where(DriverApplication.driver_profile_id == driver_profile_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await session.execute(
            select(DriverProfile, User)
            .join(User, DriverProfile.user_id == User.id)
            .where(DriverProfile.id == driver_profile_id)
            .with_for_update(of=DriverProfile)
            .execution_options(populate_existing=True)
        )
        row = result.first()
        row = (row[0], row[1]) if row is not None else None
    else:
        row = await get_driver_profile_with_user(session, driver_profile_id)
    if row is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    profile, user = row
    changed_fields = list(update_values)
    if update_values.get("onboarding_status") is None and "onboarding_status" in update_values:
        raise AppError(
            "INVALID_ONBOARDING_STATUS",
            "Onboarding status cannot be null",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if update_values.get("onboarding_status") == "active":
        public_application_id = await session.scalar(
            select(DriverApplication.id).where(DriverApplication.driver_profile_id == profile.id)
        )
        if public_application_id is not None:
            raise AppError(
                "DRIVER_WORK_ELIGIBILITY_INCOMPLETE",
                "Public applicants require approved person/payee and active vehicle evidence",
                status_code=status.HTTP_409_CONFLICT,
            )
    if "metadata" in update_values:
        metadata = update_values.pop("metadata")
        if metadata is None:
            raise AppError(
                "INVALID_METADATA",
                "Metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        profile.profile_metadata = metadata

    for field, value in update_values.items():
        setattr(profile, field, value)
    if application is not None:
        await terminalize_driver_application(
            session,
            application=application,
            terminal_status=DriverApplicationStatus.REJECTED,
            actor_user_id=actor_user_id,
            source_entity_type="driver_profile",
            source_entity_id=profile.id,
        )
    await session.flush()
    await session.refresh(profile)
    return profile, user, changed_fields


async def update_current_driver_profile(
    session: AsyncSession,
    user_id: UUID,
    payload: DriverProfileSelfUpdate,
) -> tuple[DriverProfile, User]:
    profile, user = await get_required_driver_profile_with_user_by_user_id(session, user_id)
    update_values = payload.model_dump(exclude_unset=True)
    for field, value in update_values.items():
        setattr(profile, field, value)
    await session.flush()
    await session.refresh(profile)
    return profile, user
