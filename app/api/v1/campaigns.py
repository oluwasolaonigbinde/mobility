from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import AdminUserDependency, AdvertiserUserDependency, SessionDependency
from app.core.errors import AppError
from app.models.campaign import (
    Campaign,
    CampaignCreative,
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
    CampaignUpdate,
    CreativeCreate,
    CreativeListResponse,
    CreativeRead,
    CreativeUpdate,
)
from app.services.audit import create_audit_event
from app.services.campaigns import (
    create_campaign,
    create_campaign_creative,
    get_admin_campaign,
    get_advertiser_campaign,
    get_campaign_creative,
    list_admin_campaigns,
    list_advertiser_campaigns,
    list_campaign_creatives,
    update_advertiser_campaign,
    update_campaign_creative,
)

router = APIRouter(tags=["campaigns"])


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
