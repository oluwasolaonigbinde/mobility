from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, DriverUserDependency, SessionDependency
from app.core.errors import AppError
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.user import User
from app.schemas.drivers import (
    AdminDriverProfileRead,
    DriverProfileAdminUpdate,
    DriverProfileCreate,
    DriverProfileListResponse,
    DriverProfileRead,
    DriverProfileSelfUpdate,
)
from app.services.audit import create_audit_event
from app.services.drivers import (
    create_driver_profile,
    get_driver_profile_with_user,
    get_required_driver_profile_with_user_by_user_id,
    list_driver_profiles,
    update_current_driver_profile,
    update_driver_profile,
)

router = APIRouter(tags=["Drivers"])


def driver_profile_response(profile: DriverProfile, user: User) -> DriverProfileRead:
    return DriverProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        onboarding_status=profile.onboarding_status,
        license_number=profile.license_number,
        service_city=profile.service_city,
        country_code=profile.country_code,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def admin_driver_profile_response(profile: DriverProfile, user: User) -> AdminDriverProfileRead:
    return AdminDriverProfileRead(
        **driver_profile_response(profile, user).model_dump(),
        metadata=profile.profile_metadata,
    )


@router.get(
    "/driver/profile",
    response_model=DriverProfileRead,
    summary="Get current driver profile",
)
async def get_current_driver_profile(
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> DriverProfileRead:
    profile, user = await get_required_driver_profile_with_user_by_user_id(
        session,
        current_user.id,
    )
    return driver_profile_response(profile, user)


@router.patch(
    "/driver/profile",
    response_model=DriverProfileRead,
    summary="Update current driver profile",
)
async def patch_current_driver_profile(
    payload: DriverProfileSelfUpdate,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> DriverProfileRead:
    profile, user = await update_current_driver_profile(session, current_user.id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="driver.profile.updated",
        entity_type="driver_profile",
        entity_id=str(profile.id),
        metadata={"changed_fields": list(payload.model_dump(exclude_unset=True))},
    )
    await session.commit()
    return driver_profile_response(profile, user)


@router.post(
    "/admin/drivers/{user_id}/profile",
    response_model=AdminDriverProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a driver profile",
)
async def admin_create_driver_profile(
    user_id: UUID,
    payload: DriverProfileCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminDriverProfileRead:
    profile, user = await create_driver_profile(session, user_id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.driver_profile.created",
        entity_type="driver_profile",
        entity_id=str(profile.id),
        metadata={"user_id": str(user.id), "onboarding_status": profile.onboarding_status},
    )
    await session.commit()
    return admin_driver_profile_response(profile, user)


@router.get(
    "/admin/drivers",
    response_model=DriverProfileListResponse,
    summary="List driver profiles",
)
async def admin_list_driver_profiles(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    onboarding_status: DriverOnboardingStatus | None = None,
    country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    service_city: str | None = None,
) -> DriverProfileListResponse:
    del current_user
    profiles, total = await list_driver_profiles(
        session,
        limit=limit,
        offset=offset,
        onboarding_status=onboarding_status,
        country_code=country_code,
        service_city=service_city,
    )
    return DriverProfileListResponse(
        items=[admin_driver_profile_response(profile, user) for profile, user in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/drivers/{driver_profile_id}",
    response_model=AdminDriverProfileRead,
    summary="Get a driver profile",
)
async def admin_get_driver_profile(
    driver_profile_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminDriverProfileRead:
    del current_user
    row = await get_driver_profile_with_user(session, driver_profile_id)
    if row is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    profile, user = row
    return admin_driver_profile_response(profile, user)


@router.patch(
    "/admin/drivers/{driver_profile_id}",
    response_model=AdminDriverProfileRead,
    summary="Update a driver profile",
)
async def admin_update_driver_profile(
    driver_profile_id: UUID,
    payload: DriverProfileAdminUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminDriverProfileRead:
    profile, user, changed_fields = await update_driver_profile(session, driver_profile_id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.driver_profile.updated",
        entity_type="driver_profile",
        entity_id=str(profile.id),
        metadata={"changed_fields": changed_fields},
    )
    await session.commit()
    return admin_driver_profile_response(profile, user)
