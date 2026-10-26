import secrets
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.campaign import CampaignCreative
from app.models.campaign_engagement import ArtworkLink, ArtworkScanDay
from app.schemas.campaign_engagement import (
    ArtworkLinkRead,
    CampaignScansRead,
    ScanDayRead,
    validated_website,
)
from app.services.audit import create_audit_event
from app.services.campaigns import (
    get_advertiser_campaign,
    get_campaign_creative,
    get_required_advertiser_context,
)
from app.services.payout_rule_serialization import database_clock


async def scan_days(session: AsyncSession, creative_ids) -> list[ScanDayRead]:
    rows = await session.execute(
        select(ArtworkScanDay.day, func.sum(ArtworkScanDay.scans))
        .where(ArtworkScanDay.creative_id.in_(creative_ids))
        .group_by(ArtworkScanDay.day)
        .order_by(ArtworkScanDay.day)
    )
    return [ScanDayRead(day=day, scans=count) for day, count in rows]


async def read_artwork_link(
    session: AsyncSession, *, user_id: UUID, campaign_id: UUID, creative_id: UUID
) -> ArtworkLinkRead:
    await get_campaign_creative(
        session, user_id=user_id, campaign_id=campaign_id, creative_id=creative_id
    )
    link = await session.get(ArtworkLink, creative_id)
    days = await scan_days(session, [creative_id])
    return ArtworkLinkRead(
        creative_id=creative_id,
        destination=link.destination if link else None,
        short_path=f"/q/{link.code}" if link else None,
        scans=sum(day.scans for day in days),
        days=days,
    )


async def save_artwork_link(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    creative_id: UUID,
    destination: str,
) -> ArtworkLinkRead:
    await get_required_advertiser_context(session, user_id, require_write=True)
    await get_campaign_creative(
        session,
        user_id=user_id,
        campaign_id=campaign_id,
        creative_id=creative_id,
        lock_creative=True,
    )
    await session.execute(
        insert(ArtworkLink)
        .values(
            creative_id=creative_id,
            code=secrets.token_hex(16),
            destination=validated_website(destination),
        )
        .on_conflict_do_update(
            index_elements=[ArtworkLink.creative_id],
            set_={"destination": validated_website(destination), "updated_at": func.now()},
        )
    )
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="creative.website_updated",
        entity_type="campaign_creative",
        entity_id=str(creative_id),
        metadata={"campaign_id": str(campaign_id)},
    )
    await session.commit()
    return await read_artwork_link(
        session, user_id=user_id, campaign_id=campaign_id, creative_id=creative_id
    )


async def campaign_scans(
    session: AsyncSession, *, user_id: UUID, campaign_id: UUID
) -> CampaignScansRead:
    await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    creative_ids = select(CampaignCreative.id).where(CampaignCreative.campaign_id == campaign_id)
    days = await scan_days(session, creative_ids)
    return CampaignScansRead(
        campaign_id=campaign_id, scans=sum(day.scans for day in days), days=days
    )


async def stored_destination(session: AsyncSession, *, code: str, count_scan: bool) -> str:
    link = await session.scalar(select(ArtworkLink).where(ArtworkLink.code == code))
    if link is None:
        raise AppError("QR_LINK_NOT_FOUND", "This advert link is unavailable", status_code=404)
    try:
        destination = validated_website(link.destination)
    except ValueError as exc:
        raise AppError(
            "QR_LINK_UNAVAILABLE", "This advert link is unavailable", status_code=404
        ) from exc
    if count_scan:
        now: datetime = await database_clock(session)
        day = now.astimezone(ZoneInfo("Africa/Lagos")).date()
        await session.execute(
            insert(ArtworkScanDay)
            .values(creative_id=link.creative_id, day=day, scans=1)
            .on_conflict_do_update(
                index_elements=[ArtworkScanDay.creative_id, ArtworkScanDay.day],
                set_={"scans": ArtworkScanDay.scans + 1},
            )
        )
        # Never send a counted-success redirect before the increment is durable.
        await session.commit()
    return destination
