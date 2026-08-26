from uuid import UUID

from fastapi import APIRouter

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
)
from app.schemas.campaign_changes import (
    CampaignChangeCreate,
    CampaignChangeDecision,
    CampaignChangeList,
    CampaignChangeRead,
)
from app.services.campaign_changes import (
    decide_campaign_change,
    list_advertiser_campaign_changes,
    list_pending_campaign_changes,
    request_campaign_change,
)

router = APIRouter()


@router.post(
    "/advertiser/campaigns/{campaign_id}/change-requests",
    response_model=CampaignChangeRead,
    status_code=201,
)
async def advertiser_request_campaign_change(
    campaign_id: UUID,
    payload: CampaignChangeCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignChangeRead:
    request = await request_campaign_change(
        session, actor_user_id=user.id, campaign_id=campaign_id, payload=payload
    )
    await session.commit()
    return CampaignChangeRead.model_validate(request)


@router.get(
    "/advertiser/campaigns/{campaign_id}/change-requests",
    response_model=CampaignChangeList,
)
async def advertiser_list_campaign_change_requests(
    campaign_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignChangeList:
    items = await list_advertiser_campaign_changes(
        session, actor_user_id=user.id, campaign_id=campaign_id
    )
    return CampaignChangeList(items=[CampaignChangeRead.model_validate(item) for item in items])


@router.get("/admin/campaign-change-requests/pending", response_model=CampaignChangeList)
async def admin_list_pending_campaign_change_requests(
    _user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignChangeList:
    items = await list_pending_campaign_changes(session)
    return CampaignChangeList(items=[CampaignChangeRead.model_validate(item) for item in items])


@router.post(
    "/admin/campaign-change-requests/{request_id}/approve",
    response_model=CampaignChangeRead,
)
async def admin_approve_campaign_change_request(
    request_id: UUID,
    payload: CampaignChangeDecision,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignChangeRead:
    request = await decide_campaign_change(
        session,
        actor_user_id=user.id,
        request_id=request_id,
        approve=True,
        reason=payload.reason,
    )
    await session.commit()
    return CampaignChangeRead.model_validate(request)


@router.post(
    "/admin/campaign-change-requests/{request_id}/reject",
    response_model=CampaignChangeRead,
)
async def admin_reject_campaign_change_request(
    request_id: UUID,
    payload: CampaignChangeDecision,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignChangeRead:
    request = await decide_campaign_change(
        session,
        actor_user_id=user.id,
        request_id=request_id,
        approve=False,
        reason=payload.reason,
    )
    await session.commit()
    return CampaignChangeRead.model_validate(request)
