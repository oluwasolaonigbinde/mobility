from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignCreative
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.schemas.campaigns import CampaignCreate, CampaignUpdate, CreativeCreate, CreativeUpdate
from app.services.organizations import get_advertiser_organization_for_user


def comparable_campaign_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value


async def get_required_advertiser_context(
    session: AsyncSession,
    user_id: UUID,
    *,
    require_write: bool = False,
) -> tuple[AdvertiserOrganization, OrganizationMembership]:
    context = await get_advertiser_organization_for_user(session, user_id)
    if context is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found for the current user",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    organization, membership = context
    if require_write and (
        membership.status != MembershipStatus.ACTIVE
        or membership.role not in {MembershipRole.OWNER, MembershipRole.MANAGER}
    ):
        raise AppError(
            "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN",
            "Advertiser organization membership does not allow this write",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return organization, membership


def ensure_campaign_rules(
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    budget_amount: Decimal | None,
    daily_budget_amount: Decimal | None,
) -> None:
    if (
        budget_amount is not None
        and daily_budget_amount is not None
        and daily_budget_amount > budget_amount
    ):
        raise AppError(
            "INVALID_CAMPAIGN_BUDGET",
            "Daily budget must not exceed total budget",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if (
        start_at is not None
        and end_at is not None
        and comparable_campaign_datetime(start_at) >= comparable_campaign_datetime(end_at)
    ):
        raise AppError(
            "INVALID_CAMPAIGN_DATES",
            "Campaign start_at must be before end_at",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def create_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    payload: CampaignCreate,
) -> Campaign:
    if payload.status == "active":
        raise AppError(
            "CAMPAIGN_ACTIVE_CREATE_FORBIDDEN",
            "A campaign must be funded and authorized before it can become active",
            status_code=status.HTTP_409_CONFLICT,
        )
    organization, _ = await get_required_advertiser_context(
        session,
        user_id,
        require_write=True,
    )
    campaign = Campaign(
        organization_id=organization.id,
        created_by_user_id=user_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        start_at=payload.start_at,
        end_at=payload.end_at,
        budget_amount=payload.budget_amount,
        daily_budget_amount=payload.daily_budget_amount,
        currency=(payload.currency or organization.currency).upper(),
        campaign_metadata=payload.metadata,
    )
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def list_advertiser_campaigns(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    offset: int,
    campaign_status: str | None,
    start_at_from: datetime | None,
    start_at_to: datetime | None,
) -> tuple[list[Campaign], int]:
    organization, _ = await get_required_advertiser_context(session, user_id)
    filters = [Campaign.organization_id == organization.id]
    if campaign_status is not None:
        filters.append(Campaign.status == campaign_status)
    if start_at_from is not None:
        filters.append(Campaign.start_at >= start_at_from)
    if start_at_to is not None:
        filters.append(Campaign.start_at <= start_at_to)

    statement = select(Campaign)
    count_statement = select(func.count()).select_from(Campaign)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(Campaign.created_at.desc(), Campaign.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_advertiser_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
) -> Campaign:
    organization, _ = await get_required_advertiser_context(session, user_id)
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


async def update_advertiser_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    payload: CampaignUpdate,
) -> tuple[Campaign, list[str]]:
    await get_required_advertiser_context(session, user_id, require_write=True)
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    update_values = payload.model_dump(exclude_unset=True)
    changed_fields = list(update_values)

    for required_field in ["name", "status", "currency"]:
        if required_field in update_values and update_values[required_field] is None:
            raise AppError(
                "INVALID_CAMPAIGN_UPDATE",
                f"{required_field} cannot be null",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if "metadata" in update_values:
        metadata = update_values.pop("metadata")
        if metadata is None:
            raise AppError(
                "INVALID_METADATA",
                "Metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        campaign.campaign_metadata = metadata

    prospective = {
        "start_at": update_values.get("start_at", campaign.start_at),
        "end_at": update_values.get("end_at", campaign.end_at),
        "budget_amount": update_values.get("budget_amount", campaign.budget_amount),
        "daily_budget_amount": update_values.get(
            "daily_budget_amount",
            campaign.daily_budget_amount,
        ),
    }
    ensure_campaign_rules(**prospective)

    if update_values.get("status") == "active":
        from app.services.billing import assert_campaign_production_authorized

        await assert_campaign_production_authorized(session, campaign_id=campaign.id)

    for field, value in update_values.items():
        setattr(campaign, field, value)

    await session.flush()
    await session.refresh(campaign)
    return campaign, changed_fields


async def list_admin_campaigns(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    organization_id: UUID | None,
    campaign_status: str | None,
) -> tuple[list[tuple[Campaign, AdvertiserOrganization]], int]:
    filters = []
    if organization_id is not None:
        filters.append(Campaign.organization_id == organization_id)
    if campaign_status is not None:
        filters.append(Campaign.status == campaign_status)

    statement = select(Campaign, AdvertiserOrganization).join(
        AdvertiserOrganization,
        Campaign.organization_id == AdvertiserOrganization.id,
    )
    count_statement = select(func.count()).select_from(Campaign)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(Campaign.created_at.desc(), Campaign.id).limit(limit).offset(offset)
    )
    return [(row[0], row[1]) for row in result.all()], int(total or 0)


async def get_admin_campaign(
    session: AsyncSession,
    campaign_id: UUID,
) -> tuple[Campaign, AdvertiserOrganization] | None:
    result = await session.execute(
        select(Campaign, AdvertiserOrganization)
        .join(AdvertiserOrganization, Campaign.organization_id == AdvertiserOrganization.id)
        .where(Campaign.id == campaign_id)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def create_campaign_creative(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    payload: CreativeCreate,
) -> CampaignCreative:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    await get_required_advertiser_context(session, user_id, require_write=True)
    creative = CampaignCreative(
        campaign_id=campaign.id,
        name=payload.name,
        creative_type=payload.creative_type,
        placement=payload.placement,
        asset_url=payload.asset_url,
        mime_type=payload.mime_type,
        width_px=payload.width_px,
        height_px=payload.height_px,
        duration_seconds=payload.duration_seconds,
        checksum=payload.checksum,
        status=payload.status,
        creative_metadata=payload.metadata,
    )
    session.add(creative)
    await session.flush()
    await session.refresh(creative)
    return creative


async def list_campaign_creatives(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    limit: int,
    offset: int,
    creative_status: str | None,
    creative_type: str | None,
) -> tuple[list[CampaignCreative], int]:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    filters = [CampaignCreative.campaign_id == campaign.id]
    if creative_status is not None:
        filters.append(CampaignCreative.status == creative_status)
    if creative_type is not None:
        filters.append(CampaignCreative.creative_type == creative_type)

    statement = select(CampaignCreative)
    count_statement = select(func.count()).select_from(CampaignCreative)
    for filter_expression in filters:
        statement = statement.where(filter_expression)
        count_statement = count_statement.where(filter_expression)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignCreative.created_at.desc(), CampaignCreative.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_campaign_creative(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    creative_id: UUID,
) -> CampaignCreative:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    result = await session.execute(
        select(CampaignCreative).where(
            CampaignCreative.id == creative_id,
            CampaignCreative.campaign_id == campaign.id,
        )
    )
    creative = result.scalar_one_or_none()
    if creative is None:
        raise AppError(
            "CAMPAIGN_CREATIVE_NOT_FOUND",
            "Campaign creative was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return creative


async def update_campaign_creative(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    creative_id: UUID,
    payload: CreativeUpdate,
) -> tuple[CampaignCreative, list[str]]:
    await get_required_advertiser_context(session, user_id, require_write=True)
    creative = await get_campaign_creative(
        session,
        user_id=user_id,
        campaign_id=campaign_id,
        creative_id=creative_id,
    )
    update_values = payload.model_dump(exclude_unset=True)
    changed_fields = list(update_values)

    for required_field in ["name", "creative_type", "placement", "status"]:
        if required_field in update_values and update_values[required_field] is None:
            raise AppError(
                "INVALID_CAMPAIGN_CREATIVE_UPDATE",
                f"{required_field} cannot be null",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if "metadata" in update_values:
        metadata = update_values.pop("metadata")
        if metadata is None:
            raise AppError(
                "INVALID_METADATA",
                "Metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        creative.creative_metadata = metadata

    for field, value in update_values.items():
        setattr(creative, field, value)

    await session.flush()
    await session.refresh(creative)
    return creative, changed_fields
