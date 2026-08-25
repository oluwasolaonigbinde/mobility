from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, AdvertiserUserDependency, SessionDependency
from app.core.errors import AppError
from app.models.campaign import (
    Campaign,
    CampaignCreative,
    CampaignReviewEvent,
    CampaignStatus,
    CreativeStatus,
    CreativeType,
)
from app.models.organization import AdvertiserOrganization
from app.schemas.campaigns import (
    AdminCampaignListResponse,
    AdminCampaignOrganizationSummary,
    AdminCampaignRead,
    CampaignCreate,
    CampaignListResponse,
    CampaignRead,
    CampaignReviewEventListResponse,
    CampaignReviewEventRead,
    CampaignReviewReject,
    CampaignUpdate,
    CreativeCreate,
    CreativeListResponse,
    CreativeRead,
    CreativeUpdate,
    ensure_timezone_aware,
)
from app.services.audit import create_audit_event
from app.services.campaigns import (
    create_campaign,
    create_campaign_creative,
    decide_campaign_review,
    get_admin_campaign,
    get_advertiser_campaign,
    get_campaign_creative,
    list_admin_campaigns,
    list_advertiser_campaign_review_events,
    list_advertiser_campaigns,
    list_campaign_creatives,
    list_campaign_review_events,
    submit_campaign_for_review,
    update_advertiser_campaign,
    update_campaign_creative,
)

router = APIRouter(tags=["Campaigns"])


def ensure_campaign_query_datetime(value: datetime | None, field_name: str) -> datetime | None:
    try:
        return ensure_timezone_aware(value)
    except ValueError as exc:
        raise AppError(
            "VALIDATION_ERROR",
            "Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"errors": [{"loc": ["query", field_name], "msg": str(exc)}]},
        ) from exc


def ensure_campaign_list_date_range(
    start_at_from: datetime | None,
    start_at_to: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start_at_from = ensure_campaign_query_datetime(start_at_from, "start_at_from")
    start_at_to = ensure_campaign_query_datetime(start_at_to, "start_at_to")
    if start_at_from is not None and start_at_to is not None and start_at_from > start_at_to:
        raise AppError(
            "INVALID_DATE_RANGE",
            "start_at_from must be before or equal to start_at_to",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return start_at_from, start_at_to


def campaign_response(campaign: Campaign) -> CampaignRead:
    return CampaignRead(
        id=campaign.id,
        organization_id=campaign.organization_id,
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        start_at=campaign.start_at,
        end_at=campaign.end_at,
        budget_amount=campaign.budget_amount,
        daily_budget_amount=campaign.daily_budget_amount,
        currency=campaign.currency,
        metadata=campaign.campaign_metadata,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def organization_summary(
    organization: AdvertiserOrganization,
) -> AdminCampaignOrganizationSummary:
    return AdminCampaignOrganizationSummary(
        id=organization.id,
        name=organization.name,
        currency=organization.currency,
        status=organization.status,
    )


def admin_campaign_response(
    campaign: Campaign,
    organization: AdvertiserOrganization,
) -> AdminCampaignRead:
    return AdminCampaignRead(
        **campaign_response(campaign).model_dump(),
        organization=organization_summary(organization),
    )


def creative_response(creative: CampaignCreative) -> CreativeRead:
    return CreativeRead(
        id=creative.id,
        campaign_id=creative.campaign_id,
        name=creative.name,
        creative_type=creative.creative_type,
        placement=creative.placement,
        asset_url=creative.asset_url,
        mime_type=creative.mime_type,
        width_px=creative.width_px,
        height_px=creative.height_px,
        duration_seconds=creative.duration_seconds,
        checksum=creative.checksum,
        status=creative.status,
        metadata=creative.creative_metadata,
        created_at=creative.created_at,
        updated_at=creative.updated_at,
    )


def campaign_review_event_response(event: CampaignReviewEvent) -> CampaignReviewEventRead:
    return CampaignReviewEventRead(
        id=event.id,
        campaign_id=event.campaign_id,
        actor_user_id=event.actor_user_id,
        prior_status=event.prior_status,
        new_status=event.new_status,
        rejection_reason=event.rejection_reason,
        reviewed_snapshot=event.reviewed_snapshot,
        reviewed_snapshot_sha256=event.reviewed_snapshot_sha256,
        submission_event_id=event.submission_event_id,
        created_at=event.created_at,
    )


@router.post(
    "/advertiser/campaigns",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign",
)
async def advertiser_create_campaign(
    payload: CampaignCreate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignRead:
    campaign = await create_campaign(session, user_id=current_user.id, payload=payload)
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign.created",
        entity_type="campaign",
        entity_id=str(campaign.id),
        metadata={"organization_id": str(campaign.organization_id), "status": campaign.status},
    )
    await session.commit()
    return campaign_response(campaign)


@router.get(
    "/advertiser/campaigns",
    response_model=CampaignListResponse,
    summary="List current advertiser campaigns",
)
async def advertiser_list_campaigns(
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignStatus | None = None,
    start_at_from: datetime | None = None,
    start_at_to: datetime | None = None,
) -> CampaignListResponse:
    start_at_from, start_at_to = ensure_campaign_list_date_range(start_at_from, start_at_to)
    campaigns, total = await list_advertiser_campaigns(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        campaign_status=status,
        start_at_from=start_at_from,
        start_at_to=start_at_to,
    )
    return CampaignListResponse(
        items=[campaign_response(campaign) for campaign in campaigns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="Get current advertiser campaign",
)
async def advertiser_get_campaign(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignRead:
    campaign = await get_advertiser_campaign(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
    )
    return campaign_response(campaign)


@router.patch(
    "/advertiser/campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="Update current advertiser campaign",
)
async def advertiser_update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignRead:
    campaign, changed_fields = await update_advertiser_campaign(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        payload=payload,
    )
    if changed_fields:
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="advertiser.campaign.updated",
            entity_type="campaign",
            entity_id=str(campaign.id),
            metadata={"changed_fields": changed_fields},
        )
    await session.commit()
    return campaign_response(campaign)


@router.post(
    "/advertiser/campaigns/{campaign_id}/submit",
    response_model=CampaignRead,
    summary="Submit a campaign for admin review",
)
async def advertiser_submit_campaign_for_review(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignRead:
    campaign = await submit_campaign_for_review(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
    )
    await session.commit()
    return campaign_response(campaign)


@router.get(
    "/advertiser/campaigns/{campaign_id}/review-history",
    response_model=CampaignReviewEventListResponse,
    summary="List a campaign's review history",
)
async def advertiser_list_campaign_review_history(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignReviewEventListResponse:
    events, total = await list_advertiser_campaign_review_events(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
    )
    return CampaignReviewEventListResponse(
        items=[campaign_review_event_response(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/advertiser/campaigns/{campaign_id}/creatives",
    response_model=CreativeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create campaign creative metadata",
)
async def advertiser_create_campaign_creative(
    campaign_id: UUID,
    payload: CreativeCreate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CreativeRead:
    creative = await create_campaign_creative(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign_creative.created",
        entity_type="campaign_creative",
        entity_id=str(creative.id),
        metadata={"campaign_id": str(campaign_id), "status": creative.status},
    )
    await session.commit()
    return creative_response(creative)


@router.get(
    "/advertiser/campaigns/{campaign_id}/creatives",
    response_model=CreativeListResponse,
    summary="List campaign creative metadata",
)
async def advertiser_list_campaign_creatives(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CreativeStatus | None = None,
    creative_type: CreativeType | None = None,
) -> CreativeListResponse:
    creatives, total = await list_campaign_creatives(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
        creative_status=status,
        creative_type=creative_type,
    )
    return CreativeListResponse(
        items=[creative_response(creative) for creative in creatives],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/creatives/{creative_id}",
    response_model=CreativeRead,
    summary="Get campaign creative metadata",
)
async def advertiser_get_campaign_creative(
    campaign_id: UUID,
    creative_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CreativeRead:
    creative = await get_campaign_creative(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        creative_id=creative_id,
    )
    return creative_response(creative)


@router.patch(
    "/advertiser/campaigns/{campaign_id}/creatives/{creative_id}",
    response_model=CreativeRead,
    summary="Update campaign creative metadata",
)
async def advertiser_update_campaign_creative(
    campaign_id: UUID,
    creative_id: UUID,
    payload: CreativeUpdate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CreativeRead:
    creative, changed_fields = await update_campaign_creative(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        creative_id=creative_id,
        payload=payload,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign_creative.updated",
        entity_type="campaign_creative",
        entity_id=str(creative.id),
        metadata={"changed_fields": changed_fields},
    )
    await session.commit()
    return creative_response(creative)


@router.get(
    "/admin/campaigns",
    response_model=AdminCampaignListResponse,
    summary="List campaigns across organizations",
)
async def admin_list_campaigns_endpoint(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    organization_id: UUID | None = None,
    status: CampaignStatus | None = None,
) -> AdminCampaignListResponse:
    del current_user
    campaigns, total = await list_admin_campaigns(
        session,
        limit=limit,
        offset=offset,
        organization_id=organization_id,
        campaign_status=status,
    )
    return AdminCampaignListResponse(
        items=[
            admin_campaign_response(campaign, organization)
            for campaign, organization in campaigns
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/campaigns/pending-review",
    response_model=AdminCampaignListResponse,
    summary="List campaigns pending admin review",
)
async def admin_list_pending_campaign_reviews(
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminCampaignListResponse:
    del current_user
    campaigns, total = await list_admin_campaigns(
        session,
        limit=limit,
        offset=offset,
        organization_id=None,
        campaign_status=CampaignStatus.PENDING_REVIEW.value,
        lock_campaigns=True,
    )
    return AdminCampaignListResponse(
        items=[
            admin_campaign_response(campaign, organization)
            for campaign, organization in campaigns
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/campaigns/{campaign_id}/approve",
    response_model=AdminCampaignRead,
    summary="Approve a pending campaign review",
)
async def admin_approve_campaign_review(
    campaign_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminCampaignRead:
    campaign = await decide_campaign_review(
        session,
        admin_user_id=current_user.id,
        campaign_id=campaign_id,
        target_status=CampaignStatus.APPROVED,
    )
    organization = await session.get(AdvertiserOrganization, campaign.organization_id)
    assert organization is not None
    await session.commit()
    return admin_campaign_response(campaign, organization)


@router.post(
    "/admin/campaigns/{campaign_id}/reject",
    response_model=AdminCampaignRead,
    summary="Reject a pending campaign review",
)
async def admin_reject_campaign_review(
    campaign_id: UUID,
    payload: CampaignReviewReject,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminCampaignRead:
    campaign = await decide_campaign_review(
        session,
        admin_user_id=current_user.id,
        campaign_id=campaign_id,
        target_status=CampaignStatus.REJECTED,
        rejection_reason=payload.reason,
    )
    organization = await session.get(AdvertiserOrganization, campaign.organization_id)
    assert organization is not None
    await session.commit()
    return admin_campaign_response(campaign, organization)


@router.get(
    "/admin/campaigns/{campaign_id}/review-history",
    response_model=CampaignReviewEventListResponse,
    summary="List review history across organizations",
)
async def admin_list_campaign_review_history(
    campaign_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CampaignReviewEventListResponse:
    del current_user
    if await get_admin_campaign(session, campaign_id) is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    events, total = await list_campaign_review_events(
        session,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
    )
    return CampaignReviewEventListResponse(
        items=[campaign_review_event_response(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )
@router.get(
    "/admin/campaigns/{campaign_id}",
    response_model=AdminCampaignRead,
    summary="Get a campaign across organizations",
)
async def admin_get_campaign_endpoint(
    campaign_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminCampaignRead:
    del current_user
    row = await get_admin_campaign(session, campaign_id)
    if row is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    campaign, organization = row
    return admin_campaign_response(campaign, organization)
