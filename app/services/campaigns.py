import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignCreative, CampaignReviewEvent, CampaignStatus
from app.models.organization import (
    AdvertiserOrganization,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.schemas.campaigns import CampaignCreate, CampaignUpdate, CreativeCreate, CreativeUpdate
from app.services.audit import create_audit_event
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
    if payload.status != CampaignStatus.DRAFT:
        raise AppError(
            "CAMPAIGN_REVIEW_STATE_CONFLICT",
            "Campaigns must be created as drafts and submitted through review",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": None, "target_status": payload.status.value},
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

    if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.REJECTED.value}:
        raise review_state_conflict(campaign.status, None)

    for required_field in ["name", "status", "currency"]:
        if required_field in update_values and update_values[required_field] is None:
            raise AppError(
                "INVALID_CAMPAIGN_UPDATE",
                f"{required_field} cannot be null",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    requested_currency = update_values.get("currency")
    if requested_currency is not None:
        from app.models.billing import CommercialTerms
        from app.services.payout_rule_serialization import acquire_campaign_terms_lock

        await acquire_campaign_terms_lock(session, campaign.id)
        campaign = await session.scalar(
            select(Campaign)
            .where(
                Campaign.id == campaign_id,
                Campaign.organization_id == campaign.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if campaign is None:
            raise AppError(
                "CAMPAIGN_NOT_FOUND",
                "Campaign was not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if requested_currency != campaign.currency:
            accepted_terms_id = await session.scalar(
                select(CommercialTerms.id).where(CommercialTerms.campaign_id == campaign.id)
            )
            if accepted_terms_id is not None:
                raise AppError(
                    "CAMPAIGN_CURRENCY_IMMUTABLE",
                    "Campaign currency cannot change after commercial terms are accepted",
                    status_code=status.HTTP_409_CONFLICT,
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

    if "status" in update_values:
        target_status = update_values["status"]
        if target_status in {
            CampaignStatus.PENDING_REVIEW,
            CampaignStatus.APPROVED,
            CampaignStatus.REJECTED,
            CampaignStatus.SCHEDULED,
            CampaignStatus.ACTIVE,
        }:
            raise review_state_conflict(campaign.status, target_status.value)

    for field, value in update_values.items():
        setattr(campaign, field, value)

    await session.flush()
    await session.refresh(campaign)
    return campaign, changed_fields


def review_state_conflict(current_status: str, target_status: str | None) -> AppError:
    return AppError(
        "CAMPAIGN_REVIEW_STATE_CONFLICT",
        "Campaign review state does not allow this operation",
        status_code=status.HTTP_409_CONFLICT,
        details={"current_status": current_status, "target_status": target_status},
    )


def _snapshot_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return comparable_campaign_datetime(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def campaign_review_snapshot(campaign: Campaign) -> dict[str, object]:
    return {
        "campaign_id": str(campaign.id),
        "organization_id": str(campaign.organization_id),
        "name": campaign.name,
        "description": campaign.description,
        "start_at": _snapshot_datetime(campaign.start_at),
        "end_at": _snapshot_datetime(campaign.end_at),
        "budget_amount": (
            str(campaign.budget_amount) if campaign.budget_amount is not None else None
        ),
        "daily_budget_amount": (
            str(campaign.daily_budget_amount) if campaign.daily_budget_amount is not None else None
        ),
        "currency": campaign.currency,
        "metadata": campaign.campaign_metadata,
    }


def campaign_review_snapshot_digest(snapshot: dict[str, object]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _locked_advertiser_campaign(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
) -> Campaign:
    organization, _ = await get_required_advertiser_context(session, user_id, require_write=True)
    campaign = await session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.organization_id == organization.id)
        .with_for_update()
    )
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


async def _locked_campaign(session: AsyncSession, campaign_id: UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id).with_for_update()
    )
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


async def submit_campaign_for_review(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
) -> Campaign:
    campaign = await _locked_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    prior_status = campaign.status
    if prior_status not in {CampaignStatus.DRAFT.value, CampaignStatus.REJECTED.value}:
        raise review_state_conflict(prior_status, CampaignStatus.PENDING_REVIEW.value)

    snapshot = campaign_review_snapshot(campaign)
    snapshot_digest = campaign_review_snapshot_digest(snapshot)
    reviewed_at = datetime.now(UTC)
    campaign.status = CampaignStatus.PENDING_REVIEW.value
    event = CampaignReviewEvent(
        campaign_id=campaign.id,
        actor_user_id=user_id,
        prior_status=prior_status,
        new_status=CampaignStatus.PENDING_REVIEW.value,
        reviewed_snapshot=snapshot,
        reviewed_snapshot_sha256=snapshot_digest,
        created_at=reviewed_at,
    )
    session.add(event)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="advertiser.campaign.submitted_for_review",
        entity_type="campaign",
        entity_id=str(campaign.id),
        metadata={
            "organization_id": str(campaign.organization_id),
            "status_before": prior_status,
            "status_after": campaign.status,
            "review_event_id": str(event.id),
            "reviewed_snapshot_sha256": snapshot_digest,
        },
    )
    await session.refresh(campaign)
    return campaign


async def _current_submission_event(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignReviewEvent | None:
    return await session.scalar(
        select(CampaignReviewEvent)
        .where(
            CampaignReviewEvent.campaign_id == campaign_id,
            CampaignReviewEvent.new_status == CampaignStatus.PENDING_REVIEW.value,
        )
        .order_by(CampaignReviewEvent.created_at.desc(), CampaignReviewEvent.id.desc())
        .limit(1)
        .with_for_update()
    )


async def decide_campaign_review(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    campaign_id: UUID,
    target_status: CampaignStatus,
    rejection_reason: str | None = None,
) -> Campaign:
    campaign = await _locked_campaign(session, campaign_id)
    if target_status not in {CampaignStatus.APPROVED, CampaignStatus.REJECTED}:
        raise review_state_conflict(campaign.status, target_status.value)
    if campaign.status != CampaignStatus.PENDING_REVIEW.value:
        raise review_state_conflict(campaign.status, target_status.value)

    normalized_reason = rejection_reason.strip() if rejection_reason is not None else None
    if target_status is CampaignStatus.REJECTED and not normalized_reason:
        raise AppError(
            "CAMPAIGN_REJECTION_REASON_REQUIRED",
            "A nonblank rejection reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if target_status is CampaignStatus.APPROVED and normalized_reason is not None:
        raise AppError(
            "INVALID_CAMPAIGN_REVIEW_DECISION",
            "Approval does not accept a rejection reason",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    submission_event = await _current_submission_event(session, campaign.id)
    if submission_event is None or submission_event.reviewed_snapshot_sha256 is None:
        raise review_state_conflict(campaign.status, target_status.value)

    prior_status = campaign.status
    reviewed_at = datetime.now(UTC)
    campaign.status = target_status.value
    event = CampaignReviewEvent(
        campaign_id=campaign.id,
        actor_user_id=admin_user_id,
        prior_status=prior_status,
        new_status=target_status.value,
        rejection_reason=normalized_reason,
        submission_event_id=submission_event.id,
        created_at=reviewed_at,
    )
    session.add(event)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=admin_user_id,
        action=(
            "admin.campaign.approved"
            if target_status is CampaignStatus.APPROVED
            else "admin.campaign.rejected"
        ),
        entity_type="campaign",
        entity_id=str(campaign.id),
        metadata={
            "organization_id": str(campaign.organization_id),
            "status_before": prior_status,
            "status_after": campaign.status,
            "review_event_id": str(event.id),
            "submission_event_id": str(submission_event.id),
            "reviewed_snapshot_sha256": submission_event.reviewed_snapshot_sha256,
            "rejection_reason": normalized_reason,
        },
    )
    await session.refresh(campaign)
    return campaign


async def list_advertiser_campaign_review_events(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[CampaignReviewEvent], int]:
    campaign = await get_advertiser_campaign(session, user_id=user_id, campaign_id=campaign_id)
    return await list_campaign_review_events(
        session, campaign_id=campaign.id, limit=limit, offset=offset
    )


async def list_campaign_review_events(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[CampaignReviewEvent], int]:
    filters = [CampaignReviewEvent.campaign_id == campaign_id]
    total = await session.scalar(
        select(func.count()).select_from(CampaignReviewEvent).where(*filters)
    )
    result = await session.execute(
        select(CampaignReviewEvent)
        .where(*filters)
        .order_by(CampaignReviewEvent.created_at.desc(), CampaignReviewEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def list_admin_campaigns(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    organization_id: UUID | None,
    campaign_status: str | None,
    lock_campaigns: bool = False,
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
    if lock_campaigns:
        statement = statement.with_for_update(of=Campaign)
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
