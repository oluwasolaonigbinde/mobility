from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.schemas.retargeting_source_links import (
    RetargetingSourceLinkCreate,
    RetargetingSourceLinkEventRead,
    RetargetingSourceLinkHistoryRead,
    RetargetingSourceLinkListRead,
    RetargetingSourceLinkRead,
)
from app.services.audience import (
    _link_access,
    create_retargeting_source_link,
    link_is_stale,
    list_retargeting_source_links,
    remove_retargeting_source_link,
    retargeting_source_link_history,
)

router = APIRouter(tags=["Retargeting Source Links"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


async def link_response(session: SessionDependency, link) -> RetargetingSourceLinkRead:
    return RetargetingSourceLinkRead(
        id=link.id,
        organization_id=link.organization_id,
        source_id=link.source_id,
        campaign_id=link.campaign_id,
        zone_id=link.zone_id,
        start_at=link.start_at,
        end_at=link.end_at,
        status=link.status,
        stale=await link_is_stale(session, link),
        snapshot=link.snapshot,
        snapshot_sha256=link.snapshot_sha256,
        created_at=link.created_at,
        removed_at=link.removed_at,
    )


async def history_response(session: SessionDependency, link) -> RetargetingSourceLinkHistoryRead:
    return RetargetingSourceLinkHistoryRead(
        link=await link_response(session, link),
        events=[
            RetargetingSourceLinkEventRead.model_validate(row, from_attributes=True)
            for row in await retargeting_source_link_history(session, link=link)
        ],
    )


@router.post(
    "/advertiser/retargeting-source-links",
    response_model=RetargetingSourceLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_link(
    payload: RetargetingSourceLinkCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RetargetingSourceLinkRead:
    link = await create_retargeting_source_link(
        session,
        settings=settings,
        actor_user_id=user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return await link_response(session, link)


@router.get("/advertiser/retargeting-source-links", response_model=RetargetingSourceLinkListRead)
async def list_links(
    user: AdvertiserUserDependency, session: SessionDependency, settings: SettingsDependency
) -> RetargetingSourceLinkListRead:
    links = await list_retargeting_source_links(session, settings=settings, actor_user_id=user.id)
    return RetargetingSourceLinkListRead(
        items=[await link_response(session, link) for link in links], total=len(links)
    )


@router.get(
    "/advertiser/retargeting-source-links/{link_id}", response_model=RetargetingSourceLinkRead
)
async def get_link(
    link_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceLinkRead:
    return await link_response(
        session,
        await _link_access(
            session, settings=settings, actor_user_id=user.id, link_id=link_id, write=False
        ),
    )


@router.get(
    "/advertiser/retargeting-source-links/{link_id}/history",
    response_model=RetargetingSourceLinkHistoryRead,
)
async def link_history(
    link_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceLinkHistoryRead:
    return await history_response(
        session,
        await _link_access(
            session, settings=settings, actor_user_id=user.id, link_id=link_id, write=False
        ),
    )


@router.post(
    "/advertiser/retargeting-source-links/{link_id}/remove",
    response_model=RetargetingSourceLinkRead,
)
async def remove_link(
    link_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RetargetingSourceLinkRead:
    link = await remove_retargeting_source_link(
        session,
        settings=settings,
        actor_user_id=user.id,
        link_id=link_id,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return await link_response(session, link)


@router.get("/admin/retargeting-source-links", response_model=RetargetingSourceLinkListRead)
async def admin_list_links(
    user: AdminUserDependency, session: SessionDependency, settings: SettingsDependency
) -> RetargetingSourceLinkListRead:
    links = await list_retargeting_source_links(
        session, settings=settings, actor_user_id=user.id, admin=True
    )
    return RetargetingSourceLinkListRead(
        items=[await link_response(session, link) for link in links], total=len(links)
    )


@router.get("/admin/retargeting-source-links/{link_id}", response_model=RetargetingSourceLinkRead)
async def admin_get_link(
    link_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceLinkRead:
    return await link_response(
        session,
        await _link_access(
            session,
            settings=settings,
            actor_user_id=user.id,
            link_id=link_id,
            write=False,
            admin=True,
        ),
    )


@router.get(
    "/admin/retargeting-source-links/{link_id}/history",
    response_model=RetargetingSourceLinkHistoryRead,
)
async def admin_link_history(
    link_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceLinkHistoryRead:
    return await history_response(
        session,
        await _link_access(
            session,
            settings=settings,
            actor_user_id=user.id,
            link_id=link_id,
            write=False,
            admin=True,
        ),
    )
