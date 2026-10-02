from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
)
from app.schemas.campaign_changes import (
    CampaignChangeCreate,
    CampaignChangeDecision,
    CampaignChangeList,
    CampaignChangePreviewCreate,
    CampaignChangePreviewRead,
    CampaignChangeRead,
)
from app.services.campaign_changes import (
    decide_campaign_change,
    list_advertiser_campaign_changes,
    preview_campaign_change,
    request_campaign_change,
)

router = APIRouter()


@router.post(
    "/advertiser/campaigns/{campaign_id}/change-preview",
    response_model=CampaignChangePreviewRead,
)
async def advertiser_preview_campaign_change(
    campaign_id: UUID,
    payload: CampaignChangePreviewCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignChangePreviewRead:
    return await preview_campaign_change(
        session, actor_user_id=user.id, campaign_id=campaign_id, payload=payload
    )


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
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, pattern="^(pending_admin|pending_funding)$"),
    campaign_id: UUID | None = None,
) -> CampaignChangeList:
    from sqlalchemy import func, select

    from app.models.campaign_change import CampaignChangeRequest
    from app.services.admin_worklist_reads import staff_names

    query = select(CampaignChangeRequest).where(
        CampaignChangeRequest.status.in_(("pending_admin", "pending_funding"))
    )
    if status is not None:
        query = query.where(CampaignChangeRequest.status == status)
    if campaign_id is not None:
        query = query.where(CampaignChangeRequest.campaign_id == campaign_id)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    items = list(
        (
            await session.scalars(
                query.order_by(CampaignChangeRequest.created_at, CampaignChangeRequest.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    _, names = await staff_names(session, set(), {row.campaign_id for row in items})
    return CampaignChangeList(
        items=[
            CampaignChangeRead.model_validate(item).model_copy(
                update={"campaign_name": names.get(item.campaign_id)}
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


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
