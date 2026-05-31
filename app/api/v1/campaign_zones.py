from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.v1.dependencies import (
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.campaign_zone import CampaignZoneType
from app.schemas.campaign_zones import (
    CampaignZoneCreate,
    CampaignZoneListResponse,
    CampaignZoneRead,
    CampaignZoneUpdate,
)
from app.services.audit import create_audit_event
from app.services.campaign_zones import (
    CampaignZoneView,
    create_campaign_zone,
    delete_campaign_zone,
    get_campaign_zone,
    list_campaign_zones,
    update_campaign_zone,
)

router = APIRouter(tags=["campaign-zones"])


def campaign_zone_response(view: CampaignZoneView) -> CampaignZoneRead:
    return CampaignZoneRead(
        id=view.zone.id,
        campaign_id=view.zone.campaign_id,
        name=view.zone.name,
        description=view.zone.description,
        zone_type=view.zone.zone_type,
        geometry=view.geometry,
        area_sq_m=str(view.area_sq_m),
        metadata=view.zone.zone_metadata,
        created_at=view.zone.created_at,
        updated_at=view.zone.updated_at,
    )


@router.post(
    "/advertiser/campaigns/{campaign_id}/zones",
    response_model=CampaignZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create campaign zone",
)
async def advertiser_create_campaign_zone(
    campaign_id: UUID,
    payload: CampaignZoneCreate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignZoneRead:
    view = await create_campaign_zone(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        payload=payload,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign_zone.created",
        entity_type="campaign_zone",
        entity_id=str(view.zone.id),
        metadata={"campaign_id": str(campaign_id), "zone_type": view.zone.zone_type},
    )
    await session.commit()
    return campaign_zone_response(view)


@router.get(
    "/advertiser/campaigns/{campaign_id}/zones",
    response_model=CampaignZoneListResponse,
    summary="List campaign zones",
)
async def advertiser_list_campaign_zones(
    campaign_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    zone_type: CampaignZoneType | None = None,
) -> CampaignZoneListResponse:
    zones, total = await list_campaign_zones(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
        zone_type=zone_type,
    )
    return CampaignZoneListResponse(
        items=[campaign_zone_response(zone) for zone in zones],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/advertiser/campaigns/{campaign_id}/zones/{zone_id}",
    response_model=CampaignZoneRead,
    summary="Get campaign zone",
)
async def advertiser_get_campaign_zone(
    campaign_id: UUID,
    zone_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignZoneRead:
    view = await get_campaign_zone(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        zone_id=zone_id,
    )
    return campaign_zone_response(view)


@router.patch(
    "/advertiser/campaigns/{campaign_id}/zones/{zone_id}",
    response_model=CampaignZoneRead,
    summary="Update campaign zone",
)
async def advertiser_update_campaign_zone(
    campaign_id: UUID,
    zone_id: UUID,
    payload: CampaignZoneUpdate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CampaignZoneRead:
    view, changed_fields = await update_campaign_zone(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        zone_id=zone_id,
        payload=payload,
        settings=settings,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign_zone.updated",
        entity_type="campaign_zone",
        entity_id=str(view.zone.id),
        metadata={"campaign_id": str(campaign_id), "changed_fields": changed_fields},
    )
    await session.commit()
    return campaign_zone_response(view)


@router.delete(
    "/advertiser/campaigns/{campaign_id}/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete campaign zone",
)
async def advertiser_delete_campaign_zone(
    campaign_id: UUID,
    zone_id: UUID,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> Response:
    view = await delete_campaign_zone(
        session,
        user_id=current_user.id,
        campaign_id=campaign_id,
        zone_id=zone_id,
    )
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="advertiser.campaign_zone.deleted",
        entity_type="campaign_zone",
        entity_id=str(view.zone.id),
        metadata={"campaign_id": str(campaign_id), "zone_type": view.zone.zone_type},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
