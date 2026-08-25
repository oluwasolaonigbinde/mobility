from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.assignment_activity import AssignmentActivityFlag, AssignmentActivityFlagEvent
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
    AssignmentActivityFlagRead,
    AssignmentCampaignSummary,
    AssignmentDriverProfileSummary,
    AssignmentVehicleSummary,
    CampaignActivationEventRead,
    CampaignAssignmentCancel,
    CampaignAssignmentCreate,
    CampaignAssignmentListResponse,
    CampaignAssignmentRead,
    CampaignAssignmentRecommendationListResponse,
    CampaignAssignmentTransition,
)
from app.services.assignment_activity import list_assignment_activity_flags
from app.services.audit import create_audit_event
from app.services.campaign_assignments import (
    OfferExpiredError,
    accept_driver_assignment,
    activate_admin_assignment,
    cancel_admin_assignment,
    create_campaign_assignment,
    deactivate_driver_assignment,
    decline_driver_assignment,
    expire_assignment_offer,
    expire_due_assignment_offers,
    get_admin_assignment,
    get_assignment_context,
    get_current_active_driver_assignment,
    get_driver_assignment,
    list_admin_assignments,
    list_assignment_events,
    list_assignment_recommendations,
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
        offer_terms_sha256=event.offer_terms_sha256,
    )


async def assignment_response(
    session: SessionDependency,
    assignment: CampaignAssignment,
    *,
    include_events: bool = False,
    include_activity_flags: bool = False,
) -> CampaignAssignmentRead:
    campaign, driver_profile, vehicle, _assigned_by = await get_assignment_context(
        session,
        assignment,
    )
    events = await list_assignment_events(session, assignment.id) if include_events else None
    activity_flags = None
    if include_activity_flags:
        activity_flags = [
            await activity_flag_response(session, flag)
            for flag in await list_assignment_activity_flags(
                session,
                assignment_id=assignment.id,
            )
        ]
    return CampaignAssignmentRead(
        id=assignment.id,
        campaign_id=assignment.campaign_id,
        driver_profile_id=assignment.driver_profile_id,
        vehicle_id=assignment.vehicle_id,
        assigned_by_user_id=assignment.assigned_by_user_id,
        status=assignment.status,
        offered_at=assignment.offered_at,
        expires_at=assignment.expires_at,
        accepted_at=assignment.accepted_at,
        declined_at=assignment.declined_at,
        expired_at=assignment.expired_at,
        activated_at=assignment.activated_at,
        deactivated_at=assignment.deactivated_at,
        cancelled_at=assignment.cancelled_at,
        completed_at=assignment.completed_at,
        notes=assignment.notes,
        metadata=assignment.assignment_metadata,
        offer_terms=assignment.offer_terms,
        offer_terms_sha256=assignment.offer_terms_sha256,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        campaign=campaign_summary(campaign),
        driver_profile=driver_profile_summary(driver_profile),
        vehicle=vehicle_summary(vehicle),
        events=[event_response(event) for event in events] if events is not None else None,
        activity_flags=activity_flags,
    )


async def activity_flag_response(
    session: SessionDependency, flag: AssignmentActivityFlag
) -> AssignmentActivityFlagRead:
    event_count = int(
        await session.scalar(
            select(func.count())
            .select_from(AssignmentActivityFlagEvent)
            .where(AssignmentActivityFlagEvent.flag_id == flag.id)
        )
        or 0
    )
    evidence = flag.current_evidence if isinstance(flag.current_evidence, dict) else {}
    raw_trip_count = evidence.get("eligible_trip_count", 0)
    try:
        eligible_trip_count = max(0, int(raw_trip_count))
    except (TypeError, ValueError):
        eligible_trip_count = 0
    return AssignmentActivityFlagRead(
        id=flag.id,
        assignment_id=flag.assignment_id,
        campaign_id=flag.campaign_id,
        driver_profile_id=flag.driver_profile_id,
        vehicle_id=flag.vehicle_id,
        flag_type=flag.flag_type,
        status=flag.status,
        window_start=flag.window_start,
        window_end=flag.window_end,
        threshold_seconds=flag.threshold_seconds,
        observed_seconds=flag.observed_seconds,
        last_verified_activity_at=flag.last_verified_activity_at,
        first_detected_at=flag.first_detected_at,
        last_evaluated_at=flag.last_evaluated_at,
        recovered_at=flag.recovered_at,
        eligible_trip_count=eligible_trip_count,
        evidence_event_count=event_count,
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
    settings: SettingsDependency,
) -> CampaignAssignmentRead:
    assignment = await create_campaign_assignment(
        session,
        admin_user_id=current_user.id,
        payload=payload,
        settings=settings,
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
    return await assignment_response(
        session, assignment, include_events=True, include_activity_flags=True
    )


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
    await expire_due_assignment_offers(session)
    await session.commit()
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
        items=[
            await assignment_response(
                session,
                assignment,
                include_events=True,
                include_activity_flags=True,
            )
            for assignment in assignments
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/campaign-assignments/recommendations",
    response_model=CampaignAssignmentRecommendationListResponse,
    summary="List ranked car assignment recommendations",
)
async def admin_list_assignment_recommendations(
    campaign_id: UUID,
    service_city: str,
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignAssignmentRecommendationListResponse:
    del current_user
    candidates, total = await list_assignment_recommendations(
        session,
        campaign_id=campaign_id,
        service_city=service_city,
        limit=limit,
        offset=offset,
    )
    return CampaignAssignmentRecommendationListResponse(
        items=candidates,
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
    await expire_assignment_offer(session, assignment_id)
    await session.commit()
    assignment = await get_admin_assignment(session, assignment_id)
    return await assignment_response(
        session, assignment, include_events=True, include_activity_flags=True
    )


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
    try:
        assignment = await cancel_admin_assignment(
            session,
            admin_user_id=current_user.id,
            assignment_id=assignment_id,
            payload=payload,
        )
    except OfferExpiredError:
        await session.commit()
        raise
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
    return await assignment_response(
        session, assignment, include_events=True, include_activity_flags=True
    )


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
    await expire_due_assignment_offers(session)
    await session.commit()
    assignments, total = await list_driver_assignments(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        assignment_status=status,
    )
    return CampaignAssignmentListResponse(
        items=[
            await assignment_response(session, assignment, include_events=True)
            for assignment in assignments
        ],
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
    await expire_due_assignment_offers(session)
    await session.commit()
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
    await get_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
    )
    await expire_assignment_offer(session, assignment_id)
    await session.commit()
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
    await get_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
    )
    await expire_assignment_offer(session, assignment_id)
    await session.commit()
    try:
        assignment = await accept_driver_assignment(
            session,
            user_id=current_user.id,
            assignment_id=assignment_id,
            payload=payload,
            settings=settings,
        )
    except OfferExpiredError:
        await session.commit()
        raise
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/driver/campaign-assignments/{assignment_id}/decline",
    response_model=CampaignAssignmentRead,
    summary="Decline a campaign assignment offer",
)
async def driver_decline_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    await get_driver_assignment(
        session,
        user_id=current_user.id,
        assignment_id=assignment_id,
    )
    await expire_assignment_offer(session, assignment_id)
    await session.commit()
    try:
        assignment = await decline_driver_assignment(
            session, user_id=current_user.id, assignment_id=assignment_id, payload=payload
        )
    except OfferExpiredError:
        await session.commit()
        raise
    await session.commit()
    return await assignment_response(session, assignment, include_events=True)


@router.post(
    "/admin/campaign-assignments/{assignment_id}/activate",
    response_model=CampaignAssignmentRead,
    summary="Activate an accepted campaign assignment",
)
async def admin_activate_campaign_assignment(
    assignment_id: UUID,
    payload: CampaignAssignmentTransition,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignAssignmentRead:
    assignment = await activate_admin_assignment(
        session,
        admin_user_id=current_user.id,
        assignment_id=assignment_id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="admin.campaign_assignment.activated",
        entity_type="campaign_assignment",
        entity_id=str(assignment.id),
        metadata={"campaign_id": str(assignment.campaign_id)},
    )
    await session.commit()
    return await assignment_response(
        session, assignment, include_events=True, include_activity_flags=True
    )


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
