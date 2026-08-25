from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.schemas.retargeting_sources import (
    RetargetingSourceCreate,
    RetargetingSourceEventRead,
    RetargetingSourceHistoryRead,
    RetargetingSourceListRead,
    RetargetingSourceRead,
)
from app.services.audience import (
    create_retargeting_source,
    deactivate_retargeting_source,
    get_admin_retargeting_source,
    get_advertiser_retargeting_source,
    list_admin_retargeting_sources,
    list_advertiser_retargeting_sources,
    retargeting_source_history,
    source_effective_status,
)

router = APIRouter(tags=["Retargeting Sources"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


async def source_response(session: SessionDependency, source) -> RetargetingSourceRead:
    return RetargetingSourceRead(
        id=source.id,
        organization_id=source.organization_id,
        source_type=source.source_type,
        snapshot=source.snapshot,
        snapshot_sha256=source.snapshot_sha256,
        status=await source_effective_status(session, source),
        expires_at=source.expires_at,
        created_at=source.created_at,
        deactivated_at=source.deactivated_at,
    )


async def history_response(session: SessionDependency, source) -> RetargetingSourceHistoryRead:
    return RetargetingSourceHistoryRead(
        source=await source_response(session, source),
        events=[
            RetargetingSourceEventRead.model_validate(event, from_attributes=True)
            for event in await retargeting_source_history(session, source=source)
        ],
    )


@router.post(
    "/advertiser/retargeting-sources",
    response_model=RetargetingSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_advertiser_retargeting_source(
    payload: RetargetingSourceCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RetargetingSourceRead:
    source = await create_retargeting_source(
        session,
        settings=settings,
        actor_user_id=user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return await source_response(session, source)


@router.get("/advertiser/retargeting-sources", response_model=RetargetingSourceListRead)
async def list_advertiser_sources(
    user: AdvertiserUserDependency, session: SessionDependency, settings: SettingsDependency
) -> RetargetingSourceListRead:
    sources = await list_advertiser_retargeting_sources(
        session, settings=settings, actor_user_id=user.id
    )
    return RetargetingSourceListRead(
        items=[await source_response(session, source) for source in sources], total=len(sources)
    )


@router.get("/advertiser/retargeting-sources/{source_id}", response_model=RetargetingSourceRead)
async def get_advertiser_source(
    source_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceRead:
    return await source_response(
        session,
        await get_advertiser_retargeting_source(
            session, settings=settings, actor_user_id=user.id, source_id=source_id
        ),
    )


@router.get(
    "/advertiser/retargeting-sources/{source_id}/history",
    response_model=RetargetingSourceHistoryRead,
)
async def advertiser_source_history(
    source_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceHistoryRead:
    return await history_response(
        session,
        await get_advertiser_retargeting_source(
            session, settings=settings, actor_user_id=user.id, source_id=source_id
        ),
    )


@router.post(
    "/advertiser/retargeting-sources/{source_id}/deactivate", response_model=RetargetingSourceRead
)
async def deactivate_advertiser_source(
    source_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: IdempotencyKey,
) -> RetargetingSourceRead:
    source = await deactivate_retargeting_source(
        session,
        settings=settings,
        actor_user_id=user.id,
        source_id=source_id,
        idempotency_key=idempotency_key,
    )
    await session.commit()
    return await source_response(session, source)


@router.get("/admin/retargeting-sources", response_model=RetargetingSourceListRead)
async def list_admin_sources(
    user: AdminUserDependency, session: SessionDependency, settings: SettingsDependency
) -> RetargetingSourceListRead:
    sources = await list_admin_retargeting_sources(
        session, settings=settings, actor_user_id=user.id
    )
    return RetargetingSourceListRead(
        items=[await source_response(session, source) for source in sources], total=len(sources)
    )


@router.get("/admin/retargeting-sources/{source_id}", response_model=RetargetingSourceRead)
async def get_admin_source(
    source_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceRead:
    return await source_response(
        session,
        await get_admin_retargeting_source(
            session, settings=settings, actor_user_id=user.id, source_id=source_id
        ),
    )


@router.get(
    "/admin/retargeting-sources/{source_id}/history", response_model=RetargetingSourceHistoryRead
)
async def admin_source_history(
    source_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> RetargetingSourceHistoryRead:
    return await history_response(
        session,
        await get_admin_retargeting_source(
            session, settings=settings, actor_user_id=user.id, source_id=source_id
        ),
    )
