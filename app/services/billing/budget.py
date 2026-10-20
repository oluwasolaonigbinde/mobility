"""Billing: budget domain operations."""

import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.adapters.budget import (
    BudgetPolicyAdapter,
    BudgetPolicyContext,
    build_budget_policy_adapter,
)
from app.core.errors import AppError
from app.models.billing import (
    BudgetCampaignTransition,
    BudgetCampaignTransitionAction,
    BudgetPolicyEvaluation,
    BudgetPolicyEvaluationState,
    ProductionStart,
)
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
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
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


def _budget_evaluation_key(
    campaign: Campaign,
    *,
    evaluation_epoch_id: UUID | None,
    decision,
    billing_fact_source: str,
    funding_fingerprint: str,
) -> str:
    source = "|".join(
        (
            str(campaign.id),
            str(evaluation_epoch_id or "initial"),
            str(campaign.budget_amount),
            str(campaign.daily_budget_amount),
            campaign.currency,
            str(decision.policy_id),
            str(decision.policy_revision),
            str(decision.policy_source),
            str(decision.budget_basis),
            billing_fact_source,
            str(decision.billing_spend_amount),
            str(decision.alert_threshold_amount),
            str(decision.pause_threshold_amount),
            str(decision.resume_threshold_amount),
            decision.state,
            funding_fingerprint,
            "enforceable"
            if campaign.status in {"scheduled", "active", "paused"}
            else campaign.status,
            *(
                (str(decision.urgent_threshold_amount),)
                if decision.urgent_threshold_amount is not None
                else ()
            ),
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()


def _validate_budget_decision(
    decision, *, synthetic_test_authority: bool, agreed_total: Decimal | None
) -> None:
    if decision.policy_source == "synthetic_test" and not synthetic_test_authority:
        raise AppError(
            "SYNTHETIC_BUDGET_POLICY_FORBIDDEN",
            "Synthetic budget policy values are allowed only by explicit test authority",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if decision.policy_source not in {"external_approved", "synthetic_test"}:
        raise AppError(
            "BUDGET_POLICY_NOT_AUTHORIZED",
            "Budget policy does not carry approved revision authority",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    required = (
        decision.policy_id,
        decision.policy_revision,
        decision.budget_basis,
        decision.billing_spend_amount,
        decision.alert_threshold_amount,
        decision.pause_threshold_amount,
        decision.resume_threshold_amount,
    )
    missing = any(value is None for value in required)
    expected_state = None
    thresholds_valid = False
    expected_resume_allowed = False
    if not missing:
        spend = Decimal(decision.billing_spend_amount)
        alert = Decimal(decision.alert_threshold_amount)
        urgent = (
            Decimal(decision.urgent_threshold_amount)
            if decision.urgent_threshold_amount is not None
            else None
        )
        pause = Decimal(decision.pause_threshold_amount)
        resume = Decimal(decision.resume_threshold_amount)
        thresholds_valid = (
            Decimal("0") <= resume <= pause
            and alert < pause
            and spend >= 0
            and (urgent is None or alert < urgent < pause)
        )
        expected_state = (
            BudgetPolicyEvaluationState.WITHIN_BUDGET.value
            if agreed_total is not None and spend <= agreed_total
            else BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value
            if spend > pause
            else BudgetPolicyEvaluationState.URGENT_THRESHOLD.value
            if urgent is not None and spend >= urgent
            else BudgetPolicyEvaluationState.ALERT_THRESHOLD.value
            if spend >= alert
            else BudgetPolicyEvaluationState.WITHIN_BUDGET.value
        )
        expected_resume_allowed = spend <= resume
    if (
        decision.state
        not in {
            BudgetPolicyEvaluationState.WITHIN_BUDGET.value,
            BudgetPolicyEvaluationState.ALERT_THRESHOLD.value,
            BudgetPolicyEvaluationState.URGENT_THRESHOLD.value,
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value,
        }
        or missing
        or not str(decision.policy_id).strip()
        or not str(decision.policy_revision).strip()
        or decision.budget_basis != "total"
        or not thresholds_valid
        or decision.state != expected_state
        or decision.should_pause
        != (decision.state == BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value)
        or decision.resume_allowed != expected_resume_allowed
    ):
        raise AppError(
            "INVALID_BUDGET_POLICY_DECISION",
            "Budget policy decision is internally inconsistent",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def evaluate_campaign_budget_policy(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    adapter: BudgetPolicyAdapter | None = None,
    synthetic_test_authority: bool = False,
) -> BudgetPolicyEvaluation:
    """Persist one serialized advertiser-spend decision and any campaign pause."""
    await acquire_campaign_terms_lock(session, campaign_id)
    campaign = await _campaign(session, campaign_id, lock=True)
    # D104: only the total budget is enforced; a stored daily budget never pauses.
    if campaign.budget_amount is None or Decimal(campaign.budget_amount) <= 0:
        raise AppError(
            "CAMPAIGN_BUDGET_REQUIRED",
            "Budget policy evaluation requires a positive total campaign budget",
            status_code=status.HTTP_409_CONFLICT,
        )
    selected_adapter = adapter or build_budget_policy_adapter()
    evaluation_epoch_id = await session.scalar(
        select(BudgetCampaignTransition.id)
        .where(
            BudgetCampaignTransition.campaign_id == campaign.id,
            BudgetCampaignTransition.action == BudgetCampaignTransitionAction.RESUME.value,
        )
        .order_by(BudgetCampaignTransition.created_at.desc())
        .limit(1)
    )
    now = await database_clock(session)
    total_spend, billing_fact_source = await _campaign_billing_spend(
        session, campaign_id=campaign.id
    )
    funding_fingerprint = await _funding_fingerprint(
        session, campaign_id=campaign.id, total_spend=total_spend, source=billing_fact_source
    )
    terms = await _commercial_terms_for_campaign(session, campaign.id, lock=True)
    agreed_total = Decimal(terms.gross_amount) if terms is not None else None
    decision = await selected_adapter.evaluate(
        BudgetPolicyContext(
            campaign_id=campaign.id,
            currency=campaign.currency,
            configured_budget_amount=Decimal(campaign.budget_amount),
            total_billing_spend_amount=total_spend,
            agreed_total_amount=agreed_total,
        )
    )
    _validate_budget_decision(
        decision, synthetic_test_authority=synthetic_test_authority, agreed_total=agreed_total
    )
    evaluation_key = _budget_evaluation_key(
        campaign,
        evaluation_epoch_id=evaluation_epoch_id,
        decision=decision,
        billing_fact_source=billing_fact_source,
        funding_fingerprint=funding_fingerprint,
    )
    existing = await session.scalar(
        select(BudgetPolicyEvaluation).where(
            BudgetPolicyEvaluation.campaign_id == campaign.id,
            BudgetPolicyEvaluation.evaluation_key == evaluation_key,
        )
    )
    if existing is not None:
        return existing

    pause_will_apply = decision.should_pause and campaign.status in {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.ACTIVE.value,
    }
    evaluation = BudgetPolicyEvaluation(
        campaign_id=campaign.id,
        evaluation_key=evaluation_key,
        state=decision.state,
        campaign_budget_amount=campaign.budget_amount,
        campaign_daily_budget_amount=campaign.daily_budget_amount,
        currency=campaign.currency,
        policy_id=decision.policy_id,
        policy_revision=decision.policy_revision,
        policy_source=decision.policy_source,
        budget_basis=decision.budget_basis,
        billing_fact_source=billing_fact_source,
        funding_fingerprint=funding_fingerprint,
        billing_spend_amount=decision.billing_spend_amount,
        alert_threshold_amount=decision.alert_threshold_amount,
        urgent_threshold_amount=decision.urgent_threshold_amount,
        pause_threshold_amount=decision.pause_threshold_amount,
        resume_threshold_amount=decision.resume_threshold_amount,
        alert_applied=decision.state
        in {
            BudgetPolicyEvaluationState.ALERT_THRESHOLD.value,
            BudgetPolicyEvaluationState.URGENT_THRESHOLD.value,
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value,
        },
        pause_applied=pause_will_apply,
        resume_allowed=decision.resume_allowed,
        evaluated_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(evaluation)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(BudgetPolicyEvaluation).where(
                BudgetPolicyEvaluation.campaign_id == campaign.id,
                BudgetPolicyEvaluation.evaluation_key == evaluation_key,
            )
        )
        if existing is None:
            raise
        return existing
    transition = None
    if pause_will_apply:
        prior_status = campaign.status
        campaign.status = CampaignStatus.PAUSED.value
        transition = BudgetCampaignTransition(
            campaign_id=campaign.id,
            evaluation_id=evaluation.id,
            action=BudgetCampaignTransitionAction.PAUSE.value,
            prior_status=prior_status,
            new_status=CampaignStatus.PAUSED.value,
            actor_user_id=None,
            reason="configured advertiser-spend pause threshold reached",
            created_at=now,
        )
        session.add(transition)
        await session.flush()
    await create_audit_event(
        session,
        actor_user_id=None,
        action="billing.budget_policy.evaluated",
        entity_type="budget_policy_evaluation",
        entity_id=str(evaluation.id),
        metadata={
            "campaign_id": str(campaign.id),
            "policy_id": decision.policy_id,
            "policy_revision": decision.policy_revision,
            "policy_source": decision.policy_source,
            "budget_basis": decision.budget_basis,
            "billing_fact_source": billing_fact_source,
            "billing_spend_amount": (
                f"{decision.billing_spend_amount:.2f}"
                if decision.billing_spend_amount is not None
                else None
            ),
            "state": decision.state,
            "campaign_status": campaign.status,
            "pause_transition_id": str(transition.id) if transition is not None else None,
        },
    )
    from app.services.notifications import create_budget_policy_notices

    await create_budget_policy_notices(
        session, campaign=campaign, evaluation=evaluation, epoch_id=evaluation_epoch_id
    )
    return evaluation


async def resume_campaign_after_budget_pause(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> BudgetCampaignTransition:
    await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AppError(
            "BUDGET_RESUME_REASON_REQUIRED",
            "A budget-resume reason is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    campaign = await _campaign(session, campaign_id, lock=True)
    if campaign.status != CampaignStatus.PAUSED.value:
        return await _existing_budget_resume(session, campaign, actor_user_id, normalized_reason)
    evaluation = await evaluate_campaign_budget_policy(session, campaign_id=campaign_id)
    existing_resume = (
        await session.scalar(
            select(BudgetCampaignTransition).where(
                BudgetCampaignTransition.evaluation_id == evaluation.id,
                BudgetCampaignTransition.action == BudgetCampaignTransitionAction.RESUME.value,
            )
        )
        if evaluation is not None
        else None
    )
    if existing_resume is not None:
        if (
            existing_resume.actor_user_id == actor_user_id
            and existing_resume.reason == normalized_reason
        ):
            return existing_resume
        raise AppError(
            "BUDGET_RESUME_ALREADY_RECORDED",
            "This budget evaluation already has resume authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if evaluation is None or not evaluation.resume_allowed:
        raise AppError(
            "BUDGET_RESUME_NOT_AUTHORIZED",
            "The latest authoritative budget evaluation does not permit resume",
            status_code=status.HTTP_409_CONFLICT,
        )
    pause = await session.scalar(
        select(BudgetCampaignTransition)
        .where(
            BudgetCampaignTransition.campaign_id == campaign_id,
            BudgetCampaignTransition.action == BudgetCampaignTransitionAction.PAUSE.value,
        )
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    if pause is None:
        raise AppError(
            "BUDGET_PAUSE_AUTHORITY_MISSING",
            "Campaign pause is not owned by budget enforcement",
            status_code=status.HTTP_409_CONFLICT,
        )
    paused_evaluation = await session.get(BudgetPolicyEvaluation, pause.evaluation_id)
    facts = ("campaign_budget_amount", "funding_fingerprint")
    if (
        paused_evaluation is None
        or paused_evaluation.funding_fingerprint is None
        or all(getattr(paused_evaluation, key) == getattr(evaluation, key) for key in facts)
    ):
        raise AppError(
            "BUDGET_RESUME_NOT_AUTHORIZED",
            "Confirm the budget increase or payment before restarting this campaign",
            status_code=409,
        )
    target = pause.prior_status
    now = await database_clock(session)
    latest_transition_at = await session.scalar(
        select(func.max(BudgetCampaignTransition.created_at)).where(
            BudgetCampaignTransition.campaign_id == campaign_id
        )
    )
    if latest_transition_at is not None:
        now = max(
            now,
            _stored_aware_utc(latest_transition_at) + timedelta(microseconds=1),
        )
    transition = BudgetCampaignTransition(
        campaign_id=campaign.id,
        evaluation_id=evaluation.id,
        action=BudgetCampaignTransitionAction.RESUME.value,
        prior_status=campaign.status,
        new_status=target,
        actor_user_id=actor_user_id,
        reason=normalized_reason,
        created_at=now,
    )
    campaign.status = target
    session.add(transition)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.budget_policy.resumed",
        entity_type="budget_campaign_transition",
        entity_id=str(transition.id),
        metadata={
            "campaign_id": str(campaign.id),
            "evaluation_id": str(evaluation.id),
            "policy_id": evaluation.policy_id,
            "policy_revision": evaluation.policy_revision,
            "status_before": CampaignStatus.PAUSED.value,
            "status_after": target,
            "reason": normalized_reason,
        },
    )
    from app.services.notifications import create_budget_resume_notices

    await create_budget_resume_notices(session, campaign=campaign, transition=transition)
    return transition


async def _existing_budget_resume(session, campaign, actor_user_id, reason):
    replay = await session.scalar(
        select(BudgetCampaignTransition)
        .where(BudgetCampaignTransition.campaign_id == campaign.id)
        .order_by(BudgetCampaignTransition.created_at.desc(), BudgetCampaignTransition.id.desc())
        .limit(1)
    )
    if (
        replay is not None
        and replay.action == BudgetCampaignTransitionAction.RESUME.value
        and replay.new_status == campaign.status
    ):
        if replay.actor_user_id == actor_user_id and replay.reason == reason:
            return replay
        raise AppError(
            "BUDGET_RESUME_ALREADY_RECORDED",
            "This budget evaluation already has resume authority",
            status_code=409,
        )
    raise AppError("CAMPAIGN_NOT_BUDGET_PAUSED", "Campaign is not paused", status_code=409)


async def sweep_budget_policy_evaluations(
    session: AsyncSession,
    *,
    adapter: BudgetPolicyAdapter | None = None,
    synthetic_test_authority: bool = False,
) -> list[BudgetPolicyEvaluation]:
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id).where(Campaign.budget_amount > 0).order_by(Campaign.id)
        )
    )
    evaluations = []
    for campaign_id in campaign_ids:
        try:
            async with session.begin_nested():
                evaluation = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign_id,
                    adapter=adapter,
                    synthetic_test_authority=synthetic_test_authority,
                )
            evaluations.append(evaluation)
        except Exception:
            # One incomplete draft or corrupt campaign must not roll back other
            # campaigns' enforcement. Do not log economic facts or exception text.
            logger.error(
                "budget_campaign_evaluation_failed", extra={"campaign_id": str(campaign_id)}
            )
    return evaluations
