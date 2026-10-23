"""An ephemeral delayed view, without a car identifier or historical query API."""

import hashlib
import json
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.trip import LocationPing, TripSession
from app.schemas.campaign_engagement import AnonymousPosition, LivePositionsRead
from app.services.campaigns import get_advertiser_campaign
from app.services.disclosure import (
    DisclosureQuery,
    record_disclosure,
    require_governed_advertiser_output,
)
from app.services.payout_rule_serialization import database_clock

ROUTE = "advertiser.campaign.live_positions"
POLICY = "delayed_in_area_dots_v1"


async def live_positions(
    session: AsyncSession, *, user_id: UUID, campaign_id: UUID, settings: Settings
) -> LivePositionsRead:
    tenant_id = await require_governed_advertiser_output(
        session, settings=settings, route_id=ROUTE, user_id=user_id
    )
    await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    now = await database_clock(session)
    cutoff, oldest = now - timedelta(minutes=15), now - timedelta(minutes=30)
    positions = await _delayed_points(
        session, campaign_id=campaign_id, now=now, cutoff=cutoff, oldest=oldest
    )
    # Random salt prevents low-entropy coordinate hashes in audit history being reversible.
    result_hash = hashlib.sha256(
        secrets.token_bytes(32)
        + json.dumps([p.model_dump() for p in positions], sort_keys=True).encode()
    ).hexdigest()
    await record_disclosure(
        session,
        query=DisclosureQuery(
            route_id=ROUTE,
            principal_id=user_id,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            start_at=oldest,
            end_at=cutoff,
            filters={"policy": POLICY},
        ),
        settings=settings,
        has_releasable_cells=True,  # D124 explicitly approves individual delayed in-area dots.
        result_hash=result_hash,
    )
    secrets.SystemRandom().shuffle(positions)
    return LivePositionsRead(campaign_id=campaign_id, positions=positions)


async def _delayed_points(session: AsyncSession, *, campaign_id: UUID, now, cutoff, oldest):
    latest = (
        select(
            LocationPing.longitude,
            LocationPing.latitude,
            LocationPing.geom,
            LocationPing.recorded_at,
            LocationPing.speed_mps,
            func.row_number()
            .over(
                partition_by=TripSession.vehicle_id,
                order_by=(
                    LocationPing.recorded_at.desc(),
                    LocationPing.received_at.desc(),
                    LocationPing.id.desc(),
                ),
            )
            .label("rank"),
        )
        .join(TripSession, LocationPing.trip_session_id == TripSession.id)
        .join(CampaignAssignment, TripSession.assignment_id == CampaignAssignment.id)
        .join(Campaign, Campaign.id == TripSession.campaign_id)
        .where(
            Campaign.status == "active",
            or_(Campaign.start_at.is_(None), Campaign.start_at <= now),
            or_(Campaign.end_at.is_(None), Campaign.end_at > now),
            TripSession.campaign_id == campaign_id,
            TripSession.status == "active",
            CampaignAssignment.campaign_id == campaign_id,
            CampaignAssignment.status == "active",
            LocationPing.recorded_at <= cutoff,
            LocationPing.received_at <= cutoff,
        )
        .subquery()
    )
    inside_target = exists(
        select(CampaignZone.id).where(
            CampaignZone.campaign_id == campaign_id,
            CampaignZone.zone_type == "target",
            func.ST_Covers(CampaignZone.geom, latest.c.geom),
        )
    )
    inside_exclusion = exists(
        select(CampaignZone.id).where(
            CampaignZone.campaign_id == campaign_id,
            CampaignZone.zone_type == "exclusion",
            func.ST_Covers(CampaignZone.geom, latest.c.geom),
        )
    )
    rows = await session.execute(
        select(latest.c.longitude, latest.c.latitude).where(
            latest.c.rank == 1,
            latest.c.recorded_at >= oldest,
            latest.c.speed_mps > 0,
            inside_target,
            ~inside_exclusion,
        )
    )
    return [AnonymousPosition(longitude=lon, latitude=lat) for lon, lat in rows]
