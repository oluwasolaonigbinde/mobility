from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.models.user import UserRole, UserStatus
from app.schemas.organizations import AdminOrganizationCreateResponse, AdvertiserOrganizationCreate
from app.schemas.users import UserCreate, UserListResponse, UserRead, UserUpdate
from app.services.audit import create_audit_event
from app.services.organizations import create_advertiser_organization
from app.services.users import create_user, list_users, update_user

router = APIRouter(prefix="/admin", tags=["Admin Users"])


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
)
async def admin_create_user(
    payload: UserCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> UserRead:
    user = await create_user(session, payload, settings)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.user.created",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"email": user.email, "role": user.role, "status": user.status},
    )
    await session.commit()
    return UserRead.model_validate(user)


@router.get("/users", response_model=UserListResponse, summary="List users")
async def admin_list_users(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    role: UserRole | None = None,
    status: UserStatus | None = None,
) -> UserListResponse:
    del current_user
    users, total = await list_users(
        session,
        limit=limit,
        offset=offset,
        role=role,
        user_status=status,
    )
    return UserListResponse(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}", response_model=UserRead, summary="Update a user")
async def admin_update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> UserRead:
    user, changed_fields = await update_user(session, user_id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.user.updated",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"changed_fields": changed_fields},
    )
    await session.commit()
    return UserRead.model_validate(user)


@router.post(
    "/advertiser-organizations",
    response_model=AdminOrganizationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an advertiser organization",
)
async def admin_create_advertiser_organization(
    payload: AdvertiserOrganizationCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminOrganizationCreateResponse:
    organization, owner_membership = await create_advertiser_organization(
        session,
        payload,
        settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.advertiser_organization.created",
        entity_type="advertiser_organization",
        entity_id=str(organization.id),
        metadata={
            "name": organization.name,
            "owner_user_id": str(payload.owner_user_id) if payload.owner_user_id else None,
        },
    )
    await session.commit()
    return AdminOrganizationCreateResponse(
        organization=organization,
        owner_membership=owner_membership,
    )
