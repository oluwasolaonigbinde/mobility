from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdPlatformAdapterDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.schemas.audience_delivery import (
    AudienceActivationRead,
    AudienceDeliveryRequest,
    AudienceExportRead,
    RecommendationsRead,
)
from app.services.audience_delivery import (
    activate_exposure_segment,
    export_exposure_segment,
    recommendations_for_link,
)

router = APIRouter(tags=["Audience Recommendations and Delivery"])
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
]


@router.get(
    "/advertiser/retargeting-source-links/{link_id}/recommendations",
    response_model=RecommendationsRead,
)
async def advertiser_recommendations(
    link_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RecommendationsRead:
    return await recommendations_for_link(
        session,
        settings=settings,
        actor_user_id=user.id,
        source_link_id=link_id,
    )


@router.get(
    "/admin/retargeting-source-links/{link_id}/recommendations",
    response_model=RecommendationsRead,
)
async def admin_recommendations(
    link_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RecommendationsRead:
    return await recommendations_for_link(
        session,
        settings=settings,
        actor_user_id=user.id,
        source_link_id=link_id,
        admin=True,
    )


@router.post(
    "/advertiser/exposure-segments/{segment_id}/exports",
    response_model=AudienceExportRead,
    status_code=status.HTTP_201_CREATED,
)
async def export_segment(
    segment_id: UUID,
    _payload: AudienceDeliveryRequest,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> AudienceExportRead:
    delivery = await export_exposure_segment(
        session,
        settings=settings,
        actor_user_id=user.id,
        segment_id=segment_id,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return delivery


@router.post(
    "/admin/exposure-segments/{segment_id}/activations",
    response_model=AudienceActivationRead,
    status_code=status.HTTP_201_CREATED,
)
async def activate_segment(
    segment_id: UUID,
    _payload: AudienceDeliveryRequest,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
    adapter: AdPlatformAdapterDependency,
) -> AudienceActivationRead:
    delivery = await activate_exposure_segment(
        session,
        settings=settings,
        actor_user_id=user.id,
        segment_id=segment_id,
        idempotency_key=idempotency_key,
        adapter=adapter,
    )
    await session.commit()
    return delivery
