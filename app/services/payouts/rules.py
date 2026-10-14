"""Payouts: rules domain operations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.payout import (
    CampaignPayoutRule,
    CampaignPayoutRuleRevision,
    CampaignPayoutRuleStatus,
)
from app.schemas.payouts import (
    CampaignPayoutV4RevisionCreate,
)
from app.services.payout_eligibility import (
    D39_STOP_OVERLAY,
)
from app.services.payout_rule_serialization import (
    acquire_campaign_terms_lock,
    database_clock,
)
from app.services.payouts.common import (
    PAYOUT_V4,
    RULE_REVISION_UNIQUE_CONSTRAINTS,
    invalid_rule_revision,
    payout_v4_policy_unavailable,
    rule_not_found,
    rule_revision_conflict,
    validate_currency_code,
)


async def get_campaign(session: AsyncSession, campaign_id: UUID) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise AppError(
            "CAMPAIGN_NOT_FOUND",
            "Campaign was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return campaign


async def list_campaign_payout_rules(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    limit: int,
    offset: int,
    rule_status: str | None,
) -> tuple[list[CampaignPayoutRule], int]:
    await get_campaign(session, campaign_id)
    filters = [CampaignPayoutRule.campaign_id == campaign_id]
    if rule_status is not None:
        filters.append(CampaignPayoutRule.status == rule_status)

    statement = select(CampaignPayoutRule).where(*filters)
    count_statement = select(func.count()).select_from(CampaignPayoutRule).where(*filters)
    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(CampaignPayoutRule.created_at.desc(), CampaignPayoutRule.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_campaign_payout_rule(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
) -> CampaignPayoutRule:
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.id == rule_id,
            CampaignPayoutRule.campaign_id == campaign_id,
        )
    )
    if rule is None:
        raise rule_not_found()
    return rule


def _is_rule_revision_unique_conflict(exc: IntegrityError) -> bool:
    message = str(exc.orig) if exc.orig is not None else str(exc)
    return any(name in message for name in RULE_REVISION_UNIQUE_CONSTRAINTS)


def _ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def latest_payout_rule_revision(
    session: AsyncSession,
    campaign_id: UUID,
) -> CampaignPayoutRuleRevision | None:
    return await session.scalar(
        select(CampaignPayoutRuleRevision)
        .where(CampaignPayoutRuleRevision.campaign_id == campaign_id)
        .order_by(CampaignPayoutRuleRevision.revision_number.desc())
        .limit(1)
    )


async def publish_payout_v4_revision(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    payload: CampaignPayoutV4RevisionCreate,
    actor_user_id: UUID,
    settings: Settings,
) -> tuple[
    CampaignPayoutRuleRevision, CampaignPayoutRuleRevision | None, CampaignPayoutRule | None
]:
    """Append one audited daily-rate (payout_v4, D39) revision.

    Fails closed before any lock or write while PAYOUT_V4_PUBLISHING_ENABLED is
    off. A campaign without an active rule gets a rate-less payout_v4 rule in
    the same transaction. Revisions serialize with acceptance under the campaign
    terms lock. The stop rule is fixed by the server.
    Returns (revision, previous, created_rule).
    """
    # An unknown campaign is 404 whether or not publishing is on.
    await get_campaign(session, campaign_id)
    if not settings.payout_v4_publishing_enabled:
        raise payout_v4_policy_unavailable()
    await acquire_campaign_terms_lock(session, campaign_id)
    db_now = await database_clock(session)
    campaign = await get_campaign(session, campaign_id)
    rule = await session.scalar(
        select(CampaignPayoutRule).where(
            CampaignPayoutRule.campaign_id == campaign_id,
            CampaignPayoutRule.status == CampaignPayoutRuleStatus.ACTIVE.value,
        )
    )
    if rule is not None and rule.formula_version != PAYOUT_V4:
        raise invalid_rule_revision(
            f"this campaign is governed by a {rule.formula_version} rule; a daily-rate"
            " revision cannot extend it"
        )
    latest = await latest_payout_rule_revision(session, campaign_id)
    if latest is not None and payload.effective_from <= _ensure_utc_aware(latest.effective_from):
        raise invalid_rule_revision(
            "effective_from must be strictly after the latest revision's"
            " effective_from; retroactive changes require a correction order"
        )
    if payload.effective_from < _ensure_utc_aware(db_now):
        raise invalid_rule_revision("effective_from must not be before the database clock")

    created_rule = None
    if rule is None:
        rule = CampaignPayoutRule(
            campaign_id=campaign_id,
            created_by_user_id=actor_user_id,
            formula_version=PAYOUT_V4,
            status=CampaignPayoutRuleStatus.ACTIVE.value,
            currency=validate_currency_code(campaign.currency),
            rule_metadata={},
        )
        session.add(rule)
        await session.flush()
        await session.refresh(rule)
        created_rule = rule

    revision = CampaignPayoutRuleRevision(
        campaign_id=campaign_id,
        payout_rule_id=rule.id,
        revision_number=(latest.revision_number + 1) if latest is not None else 1,
        effective_from=payload.effective_from,
        daily_rate_naira=payload.daily_rate_naira,
        daily_target_miles=payload.daily_target_miles,
        shortfall_strategy=payload.shortfall_strategy,
        deduction_per_mile_naira=payload.deduction_per_mile_naira,
        minimum_miles=payload.minimum_miles,
        outside_area_weight=payload.outside_area_weight,
        currency=rule.currency,
        eligibility_params=dict(D39_STOP_OVERLAY),
        formula_version=PAYOUT_V4,
        reason=payload.reason,
        created_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(revision)
            await session.flush()
    except IntegrityError as exc:
        if _is_rule_revision_unique_conflict(exc):
            raise rule_revision_conflict() from exc
        raise
    await session.refresh(revision)
    return revision, latest, created_rule


async def list_payout_rule_revisions(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    rule_id: UUID,
    limit: int,
    offset: int,
    effective_before: datetime | None = None,
) -> tuple[list[CampaignPayoutRuleRevision], int]:
    await get_campaign_payout_rule(session, campaign_id=campaign_id, rule_id=rule_id)
    conditions = [CampaignPayoutRuleRevision.campaign_id == campaign_id]
    if effective_before is not None:
        conditions.append(CampaignPayoutRuleRevision.effective_from <= effective_before)
    total = await session.scalar(
        select(func.count()).select_from(CampaignPayoutRuleRevision).where(*conditions)
    )
    result = await session.execute(
        select(CampaignPayoutRuleRevision)
        .where(*conditions)
        .order_by(
            CampaignPayoutRuleRevision.effective_from.desc(),
            CampaignPayoutRuleRevision.revision_number.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
