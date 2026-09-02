from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, SessionDependency, SettingsDependency
from app.models.user import UserRole, UserStatus
from app.schemas.driver_applications import (
    DriverApplicationAdminListResponse,
    DriverApplicationAdminRead,
)
from app.schemas.driver_onboarding import (
    AdminPersonPayeeStageRead,
    AdminVehicleStageRead,
    PersonPayeeReviewDecisionCreate,
    VehicleReviewDecisionCreate,
)
from app.schemas.organizations import AdminOrganizationCreateResponse, AdvertiserOrganizationCreate
from app.schemas.users import UserCreate, UserListResponse, UserRead, UserUpdate
from app.services.audit import create_audit_event
from app.services.driver_applications import list_driver_applications
from app.services.driver_onboarding import (
    application_person_payee_view,
    review_application_person_payee,
)
from app.services.organizations import create_advertiser_organization
from app.services.users import create_user, list_users, update_user
from app.services.vehicle_onboarding import (
    VehicleStageView,
    application_vehicle_view,
    review_application_vehicle,
)

router = APIRouter(prefix="/admin", tags=["Admin Users"])


def _admin_person_payee_response(view) -> AdminPersonPayeeStageRead:
    submission = view.submission
    decision = view.decision
    if submission is None:
        return AdminPersonPayeeStageRead(status="not_submitted")
    return AdminPersonPayeeStageRead(
        status=submission.status,
        submission_id=submission.id,
        version=submission.version,
        masked_nin=f"*******{submission.nin_last_four}",
        bank_account_verified=view.bank_account_verified,
        reason_code=decision.reason_code if decision else None,
        created_at=submission.created_at,
        decided_at=decision.created_at if decision else None,
        document_file_ids=view.document_file_ids,
        bank_account_version_id=submission.bank_account_version_id,
        encryption_algorithm=submission.encryption_algorithm,
        encryption_key_version=submission.encryption_key_version,
        decided_by_user_id=decision.decided_by_user_id if decision else None,
    )


def _admin_vehicle_response(view: VehicleStageView) -> AdminVehicleStageRead:
    vehicle = view.vehicle
    submission = view.submission
    decision = view.decision
    if vehicle is None or submission is None:
        return AdminVehicleStageRead()
    return AdminVehicleStageRead(
        status=submission.status,
        vehicle_id=vehicle.id,
        submission_id=submission.id,
        version=submission.version,
        plate_number=submission.plate_number_snapshot,
        plate_country_code=submission.plate_country_code_snapshot,
        vehicle_type=submission.vehicle_type_snapshot,
        make=submission.make_snapshot,
        model=submission.model_snapshot,
        year=submission.year_snapshot,
        color=submission.color_snapshot,
        valid_until=decision.valid_until if decision else None,
        reason_code=decision.reason_code if decision else None,
        created_at=submission.created_at,
        decided_at=decision.created_at if decision else None,
        document_file_ids=view.document_file_ids,
        decided_by_user_id=decision.decided_by_user_id if decision else None,
    )


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


@router.get(
    "/driver-applications",
    response_model=DriverApplicationAdminListResponse,
    summary="List pending public driver applications",
)
async def admin_list_driver_applications(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DriverApplicationAdminListResponse:
    applications, total = await list_driver_applications(
        session,
        admin_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    items = []
    for application in applications:
        person_payee = await application_person_payee_view(session, application=application)
        vehicle = await application_vehicle_view(session, application=application)
        items.append(
            DriverApplicationAdminRead.model_validate(application).model_copy(
                update={
                    "person_payee": _admin_person_payee_response(person_payee),
                    "vehicle": _admin_vehicle_response(vehicle),
                }
            )
        )
    return DriverApplicationAdminListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/driver-applications/{application_id}/person-payee-decision",
    response_model=AdminPersonPayeeStageRead,
)
async def admin_review_driver_person_payee(
    application_id: UUID,
    payload: PersonPayeeReviewDecisionCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminPersonPayeeStageRead:
    view = await review_application_person_payee(
        session,
        application_id=application_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    await session.commit()
    return _admin_person_payee_response(view)


@router.post(
    "/driver-applications/{application_id}/vehicles/{vehicle_id}/submissions/"
    "{submission_id}/decision",
    response_model=AdminVehicleStageRead,
)
async def admin_review_driver_vehicle(
    application_id: UUID,
    vehicle_id: UUID,
    submission_id: UUID,
    payload: VehicleReviewDecisionCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminVehicleStageRead:
    view = await review_application_vehicle(
        session,
        application_id=application_id,
        vehicle_id=vehicle_id,
        submission_id=submission_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    await session.commit()
    return _admin_vehicle_response(view)


@router.patch("/users/{user_id}", response_model=UserRead, summary="Update a user")
async def admin_update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> UserRead:
    result = await update_user(session, user_id, payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.user.updated",
        entity_type="user",
        entity_id=str(result.user.id),
        metadata={
            "changed_fields": result.changed_fields,
            "sessions_revoked": result.sessions_revoked,
        },
    )
    await session.commit()
    return UserRead.model_validate(result.user)


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
