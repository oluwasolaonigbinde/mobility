from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.campaign import Campaign
from app.models.campaign_assignment import (
    CampaignActivationEvent,
    CampaignAssignment,
    CampaignAssignmentStatus,
)
from app.models.driver import DriverProfile
from app.models.vehicle import Vehicle
from app.schemas.campaign_assignments import (
    ActiveCampaignAssignmentResponse,
    AssignmentCampaignSummary,
    AssignmentDriverProfileSummary,
    AssignmentVehicleSummary,
    CampaignActivationEventRead,
    CampaignAssignmentCancel,
    CampaignAssignmentCreate,
    CampaignAssignmentListResponse,
    CampaignAssignmentRead,
    CampaignAssignmentTransition,
)
from app.services.audit import create_audit_event
from app.services.campaign_assignments import (
    accept_driver_assignment,
    activate_driver_assignment,
    cancel_admin_assignment,
    create_campaign_assignment,
    deactivate_driver_assignment,
    get_admin_assignment,
    get_assignment_context,
    get_current_active_driver_assignment,
    get_driver_assignment,
    list_admin_assignments,
    list_assignment_events,
    list_driver_assignments,
)

router = APIRouter(tags=["Campaign Assignments"])


def campaign_summary(campaign: Campaign | None) -> AssignmentCampaignSummary | None:
    if campaign is None:
        return None
    return AssignmentCampaignSummary(
        id=campaign.id,
        name=campaign.name,
        status=campaign.status,
        start_at=campaign.start_at,
        end_at=campaign.end_at,
    )


def driver_profile_summary(
    driver_profile: DriverProfile | None,
) -> AssignmentDriverProfileSummary | None:
    if driver_profile is None:
        return None
    return AssignmentDriverProfileSummary(
        id=driver_profile.id,
        user_id=driver_profile.user_id,
        onboarding_status=driver_profile.onboarding_status,
    )


def vehicle_summary(vehicle: Vehicle | None) -> AssignmentVehicleSummary | None:
    if vehicle is None:
        return None
    return AssignmentVehicleSummary(
        id=vehicle.id,
        plate_number=vehicle.plate_number,
        plate_country_code=vehicle.plate_country_code,
        vehicle_type=vehicle.vehicle_type,
        status=vehicle.status,
    )


def event_response(event: CampaignActivationEvent) -> CampaignActivationEventRead:
    return CampaignActivationEventRead(
        id=event.id,
        assignment_id=event.assignment_id,
        actor_user_id=event.actor_user_id,
        event_type=event.event_type,
        previous_status=event.previous_status,
        new_status=event.new_status,
        occurred_at=event.occurred_at,
        metadata=event.event_metadata,
    )


async def assignment_response(
    session: SessionDependency,
    assignment: CampaignAssignment,
    *,
    include_events: bool = False,
) -> CampaignAssignmentRead:
    campaign, driver_profile, vehicle, _assigned_by = await get_assignment_context(
        session,
        assignment,
    )
    events = await list_assignment_events(session, assignment.id) if include_events else None
    return CampaignAssignmentRead(
        id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        assigned_by_user_id=assignment.assigned_by_user_id,
        status=assignment.status,
        offered_at=assignment.offered_at,
        accepted_at=assignment.accepted_at,
        activated_at=assignment.activated_at,
        deactivated_at=assignment.deactivated_at,
        cancelled_at=assignment.cancelled_at,
        completed_at=assignment.completed_at,
        notes=assignment.notes,
        metadata=assignment.assignment_metadata,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        campaign=campaign_summary(campaign),
        driver_profile=driver_profile_summary(driver_profile),
        vehicle=vehicle_summary(vehicle),
        events=[event_response(event) for event in events] if events is not None else None,
    )


@router.post(
    "/admin/campaign-assignments",
    response_model=CampaignAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign assignment",
)
async def admin_create_campaign_assignment(
    payload: CampaignAssignmentCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await create_campaign_assignment(
        session,
        admin_user_id=current_user.id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.campaign_assignment.created",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={
            "campaign_id": str(assignment.campaign_id),
            "driver_profile_id": str(assignment.driver_profile_id),
            "vehicle_id": str(assignment.vehicle_id),
        },
    )
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.get(
    "/admin/campaign-assignments",
    response_model=CampaignAssignmentListResponse,
    summary="List campaign assignments",
)
async def admin_list_campaign_assignments(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignAssignmentStatus | None = None,
    campaign_id: UUID | None = None,
    driver_profile_id: UUID | None = None,
    vehicle_id: UUID | None = None,
) -> CampaignAssignmentListResponse:
    del current_user
    assignments, total = await list_admin_assignments(
        session,
        limit=limit,
        offset=offset,
        assignment_status=status,
        campaign_id=campaign_id,
        driver_profile_id=driver_profile_id,
        vehicle_id=vehicle_id,
    )
    return CampaignAssignmentListResponse(
        items=[await assignment_response(session, assignment) for assignment in assignments],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/campaign-assignments/{assignment_id}",
    response_model=CampaignAssignmentRead,
    summary="Get a campaign assignment",
)
async def admin_get_campaign_assignment(
    assignment_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    del current_user
    assignment = await get_admin_assignment(session, assignment_id)
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/admin/campaign-assignments/{assignment_id}/cancel",
    response_model=CampaignAssignmentRead,
    summary="Cancel a campaign assignment",
)
async def admin_cancel_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentCancel,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await cancel_admin_assignment(
        session,
        admin_user_id=current_user.id,
        assignment_id=assignment_id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.campaign_assignment.cancelled",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={
            "campaign_id": str(assignment.campaign_id),
            "vehicle_id": str(assignment.vehicle_id),
            "reason": payload.reason,
        },
    )
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.get(
    "/driver/campaign-assignments",
    response_model=CampaignAssignmentListResponse,
    summary="List current driver campaign assignments",
)
async def driver_list_campaign_assignments(
    current_user: DriverUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignAssignmentStatus | None = None,
) -> CampaignAssignmentListResponse:
    assignments, total = await list_driver_assignments(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        assignment_status=status,
    )
    return CampaignAssignmentListResponse(
        items=[await assignment_response(session, assignment) for assignment in assignments],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/driver/campaign-assignments/active",
    response_model=ActiveCampaignAssignmentResponse,
    summary="Get current active campaign assignment",
)
async def driver_get_active_campaign_assignment(
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> ActiveCampaignAssignmentResponse:
    assignment = await get_current_active_driver_assignment(session, user_id=current_user.id)
    if assignment is None:
        return ActiveCampaignAssignmentResponse(assignment=None)
    return ActiveCampaignAssignmentResponse(
        assignment=await assignment_response(session, assignment),
    )


@router.get(
    "/driver/campaign-assignments/{assignment_id}",
    response_model=CampaignAssignmentRead,
    summary="Get current driver campaign assignment",
)
async def driver_get_campaign_assignment(
    assignment_id: UUID,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await get_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
    )
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/driver/campaign-assignments/{assignment_id}/accept",
    response_model=CampaignAssignmentRead,
    summary="Accept a campaign assignment",
)
async def driver_accept_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    current_user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignAssignmentRead:
    assignment = await accept_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
        payload=payload,
        settings=settings,
    )
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/driver/campaign-assignments/{assignment_id}/activate",
    response_model=CampaignAssignmentRead,
    summary="Activate a campaign assignment",
)
async def driver_activate_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await activate_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
        payload=payload,
    )
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/driver/campaign-assignments/{assignment_id}/deactivate",
    response_model=CampaignAssignmentRead,
    summary="Deactivate a campaign assignment",
)
async def driver_deactivate_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await deactivate_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
        payload=payload,
    )
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)
