"""Grouped projections over an already authorized page, never unbounded row reads."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.organization import OrganizationMembership


async def grouped_counts(session: AsyncSession, column, identities: list[UUID], *filters) -> dict:
    if not identities:
        return {}
    rows = await session.execute(
        select(column, func.count()).where(column.in_(identities), *filters).group_by(column)
    )
    return dict(rows.all())


async def campaign_list_counts(session: AsyncSession, identities: list[UUID]) -> dict:
    assignments = await grouped_counts(session, CampaignAssignment.campaign_id, identities)
    zones = await grouped_counts(
        session, CampaignZone.campaign_id, identities, CampaignZone.zone_type == "target"
    )
    return {
        identity: {
            "assignment_count": assignments.get(identity, 0),
            "target_zone_count": zones.get(identity, 0),
        }
        for identity in identities
    }


async def organization_list_counts(session: AsyncSession, identities: list[UUID]) -> dict:
    members = await grouped_counts(session, OrganizationMembership.organization_id, identities)
    campaigns = await grouped_counts(
        session, Campaign.organization_id, identities, Campaign.status.in_(["active", "paused"])
    )
    return {
        identity: {
            "member_count": members.get(identity, 0),
            "live_campaign_count": campaigns.get(identity, 0),
        }
        for identity in identities
    }
