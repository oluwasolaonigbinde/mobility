from uuid import UUID

from fastapi import APIRouter

from app.api.v1.dependencies import AdminUserDependency, SessionDependency
from app.schemas.campaign_cancellations import (
    CampaignCancellationCreate,
    CampaignCancellationRead,
    StaffCampaignCancellationCreate,
)
from app.services.campaign_cancellations import request_campaign_cancellation

router = APIRouter(tags=["Campaign cancellation"])


@router.post(
    "/admin/campaigns/{campaign_id}/cancel",
    response_model=CampaignCancellationRead,
    status_code=201,
)
async def admin_cancel_campaign(
    campaign_id: UUID,
    payload: StaffCampaignCancellationCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CampaignCancellationRead:
    result = await request_campaign_cancellation(
        session,
        actor_user_id=user.id,
        actor_session_version=user.session_version,
        campaign_id=campaign_id,
        complaint_id=payload.complaint_id,
        payload=CampaignCancellationCreate(
            reason=payload.reason, client_request_id=payload.client_request_id
        ),
    )
    await session.commit()
    return CampaignCancellationRead.model_validate(result)
