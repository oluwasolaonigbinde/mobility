from uuid import UUID

from fastapi import APIRouter

from app.api.v1.dependencies import AdvertiserUserDependency, SessionDependency
from app.schemas.campaign_cancellations import (
    CampaignCancellationCreate,
    CampaignCancellationRead,
)
from app.services.campaign_cancellations import request_campaign_cancellation

router = APIRouter()


@router.post(
    "/advertiser/campaigns/{campaign_id}/cancel",
    response_model=CampaignCancellationRead,
    status_code=201,
)
async def advertiser_cancel_campaign(
    campaign_id: UUID,
    payload: CampaignCancellationCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignCancellationRead:
    cancellation = await request_campaign_cancellation(
        session,
        actor_user_id=user.id,
        campaign_id=campaign_id,
        payload=payload,
    )
    await session.commit()
    return CampaignCancellationRead.model_validate(cancellation)
