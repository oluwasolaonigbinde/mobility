"""The client's fixed total-budget warnings and funded admin resume (D104)."""

import hashlib
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.billing import BudgetCampaignTransition, ProductionStart
from app.models.campaign import Campaign, CampaignStatus
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import MONEY_QUANTUM, _campaign, _stored_aware_utc
from app.services.billing.queries import (
    _active_cash_allocations,
    _commercial_terms_for_campaign,
    effective_invoice_obligation,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

logger = logging.getLogger(__name__)


async def _funding_fingerprint(session, *, campaign_id, total_spend, source):
    """Confirmed economic facts, independent of daily clocks and selected basis."""
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=False)
    facts = [source, str(total_spend), str(terms.id) if terms else "none"]
    if terms is not None and source == "confirmed_funding":
        facts.extend(
            f"{row.id}:{row.receipt_id}:{row.amount}"
            for row in await _active_cash_allocations(session, terms.id)
        )
    return hashlib.sha256("|".join(facts).encode()).hexdigest()


async def _campaign_billing_spend(
    session: AsyncSession, *, campaign_id: UUID, lock: bool = True
) -> tuple[Decimal, str]:
    """Return advertiser billing authority only; driver payout rows are intentionally absent.

    D104: there is no daily figure. Prepaid funding and the invoice obligation are booked
    in lumps, so a daily limit would pause every normal campaign on its payment day.
    """
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=lock)
    if terms is None:
        return Decimal("0.00"), "confirmed_funding"
    production = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    if production is not None:
        obligation = (
            await effective_invoice_obligation(session, commercial_terms_id=terms.id)
        ).quantize(MONEY_QUANTUM)
        return obligation, "production_obligation"
    allocations = await _active_cash_allocations(session, terms.id)
    total = sum((Decimal(row.amount) for row in allocations), Decimal("0.00")).quantize(
        MONEY_QUANTUM
    )
    return total, "confirmed_funding"


async def campaign_budget_used(session: AsyncSession, *, campaign: Campaign, now: datetime) -> dict:
    """Read-only D103 display: the booked total behind the alerts, never a daily figure."""
    total, source = await _campaign_billing_spend(session, campaign_id=campaign.id, lock=False)
    return {
        "amount": total,
        "budget_amount": campaign.budget_amount if (campaign.budget_amount or 0) > 0 else None,
        "currency": campaign.currency,
        "basis": "invoice" if source == "production_obligation" else "funding",
        "as_of": now,
    }


@dataclass(frozen=True)
class BudgetCheck:
    campaign_id: UUID
    state: str
    campaign_budget_amount: Decimal
    currency: str
    billing_spend_amount: Decimal
    resume_allowed: bool
    funding_fingerprint: str
    evaluated_at: datetime
    pause_applied: bool = False

    @property
    def alert_applied(self) -> bool:
        return self.state in {"alert_threshold", "urgent_threshold", "pause_threshold"}


def budget_state(*, booked: Decimal, budget: Decimal, agreed: Decimal | None) -> str:
    if agreed is not None and booked <= agreed:
        return "within_budget"
    if booked > budget:
        return "pause_threshold"
    if booked >= budget * Decimal("0.95"):
        return "urgent_threshold"
    if booked >= budget * Decimal("0.80"):
        return "alert_threshold"
    return "within_budget"


async def campaign_budget_check(session: AsyncSession, *, campaign: Campaign) -> BudgetCheck | None:
    if not campaign.budget_amount or Decimal(campaign.budget_amount) <= 0:
        return None
    booked, source = await _campaign_billing_spend(session, campaign_id=campaign.id, lock=False)
    terms = await _commercial_terms_for_campaign(session, campaign.id, lock=False)
    budget = Decimal(campaign.budget_amount)
    return BudgetCheck(
        campaign_id=campaign.id,
        state=budget_state(
            booked=booked, budget=budget, agreed=Decimal(terms.gross_amount) if terms else None
        ),
        campaign_budget_amount=budget,
        currency=campaign.currency,
        billing_spend_amount=booked,
        resume_allowed=booked <= budget,
        funding_fingerprint=await _funding_fingerprint(
            session, campaign_id=campaign.id, total_spend=booked, source=source
        ),
        evaluated_at=await database_clock(session),
    )


async def enforce_campaign_budget(
    session: AsyncSession, *, campaign_id: UUID
) -> BudgetCheck | None:
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    check = await campaign_budget_check(session, campaign=campaign)
    if check is None:
        return None
    epoch_id = await session.scalar(
        select(BudgetCampaignTransition.id)
        .where(
            BudgetCampaignTransition.campaign_id == campaign.id,
            BudgetCampaignTransition.action == "resume",
        )
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    if check.state == "pause_threshold" and campaign.status in {"approved", "active"}:
        prior = campaign.status
        campaign.status = CampaignStatus.PAUSED.value
        transition = BudgetCampaignTransition(
            campaign_id=campaign.id,
            action="pause",
            prior_status=prior,
            new_status="paused",
            actor_user_id=None,
            reason="Booked charges exceed the total budget and accepted price",
            budget_amount=check.campaign_budget_amount,
            funding_fingerprint=check.funding_fingerprint,
            created_at=check.evaluated_at,
        )
        session.add(transition)
        await session.flush()
        await create_audit_event(
            session,
            actor_user_id=None,
            action="billing.budget.paused",
            entity_type="budget_campaign_transition",
            entity_id=str(transition.id),
            metadata={
                "campaign_id": str(campaign.id),
                "booked": str(check.billing_spend_amount),
                "budget": str(check.campaign_budget_amount),
            },
        )
        check = replace(check, pause_applied=True)
    from app.services.notifications import create_budget_policy_notices

    await create_budget_policy_notices(
        session, campaign=campaign, evaluation=check, epoch_id=epoch_id
    )
    return check


async def resume_campaign_after_budget_pause(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> BudgetCampaignTransition:
    await require_active_admin(session, actor_user_id)
    await acquire_campaign_terms_lock(session, campaign_id)
    reason = reason.strip()
    if not reason:
        raise AppError(
            "BUDGET_RESUME_REASON_REQUIRED", "A budget-resume reason is required", status_code=400
        )
    campaign = await _campaign(session, campaign_id, lock=True)
    latest = await session.scalar(
        select(BudgetCampaignTransition)
        .where(
            BudgetCampaignTransition.campaign_id == campaign_id,
        )
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    if campaign.status != "paused":
        if (
            latest
            and latest.action == "resume"
            and ("approved" if latest.new_status == "scheduled" else latest.new_status)
            == campaign.status
        ):
            if latest.actor_user_id == actor_user_id and latest.reason == reason:
                return latest
            raise AppError(
                "BUDGET_RESUME_ALREADY_RECORDED",
                "This campaign already has resume authority",
                status_code=409,
            )
        raise AppError("CAMPAIGN_NOT_BUDGET_PAUSED", "Campaign is not paused", status_code=409)
    if latest is None or latest.action != "pause":
        raise AppError(
            "BUDGET_PAUSE_AUTHORITY_MISSING",
            "Campaign pause is not owned by budget enforcement",
            status_code=409,
        )
    check = await campaign_budget_check(session, campaign=campaign)
    if (
        check is None
        or not check.resume_allowed
        or (
            latest.budget_amount == check.campaign_budget_amount
            and latest.funding_fingerprint == check.funding_fingerprint
        )
    ):
        raise AppError(
            "BUDGET_RESUME_NOT_AUTHORIZED",
            "Confirm the budget increase or payment before restarting this campaign",
            status_code=409,
        )
    now = max(check.evaluated_at, _stored_aware_utc(latest.created_at) + timedelta(microseconds=1))
    # Historical transitions are immutable; translate their old live-state name.
    resumed_status = "approved" if latest.prior_status == "scheduled" else latest.prior_status
    transition = BudgetCampaignTransition(
        campaign_id=campaign.id,
        pause_transition_id=latest.id,
        action="resume",
        prior_status="paused",
        new_status=resumed_status,
        actor_user_id=actor_user_id,
        reason=reason,
        budget_amount=check.campaign_budget_amount,
        funding_fingerprint=check.funding_fingerprint,
        created_at=now,
    )
    campaign.status = resumed_status
    session.add(transition)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.budget.resumed",
        entity_type="budget_campaign_transition",
        entity_id=str(transition.id),
        metadata={
            "campaign_id": str(campaign.id),
            "pause_transition_id": str(latest.id),
            "reason": reason,
        },
    )
    from app.services.notifications import create_budget_resume_notices

    await create_budget_resume_notices(session, campaign=campaign, transition=transition)
    return transition


async def sweep_campaign_budgets(session: AsyncSession) -> list[BudgetCheck]:
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id)
            .where(
                Campaign.budget_amount > 0,
            )
            .order_by(Campaign.id)
        )
    )
    checks = []
    for campaign_id in campaign_ids:
        try:
            async with session.begin_nested():
                check = await enforce_campaign_budget(session, campaign_id=campaign_id)
            if check is not None:
                checks.append(check)
        except Exception:
            logger.error("budget_campaign_check_failed", extra={"campaign_id": str(campaign_id)})
    return checks
