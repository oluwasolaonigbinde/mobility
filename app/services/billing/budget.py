"""Billing: budget domain operations."""

import hashlib
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
    DisabledBudgetPolicyAdapter,
)
from app.adapters.budget.provider import (
    BLOCKED_BUDGET_POLICY_STATE,
    MISSING_BUDGET_POLICY_GATE,
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
from app.services.billing.common import LAGOS_TZ, MONEY_QUANTUM, _campaign, _stored_aware_utc
from app.services.billing.queries import (
    _active_cash_allocations,
    _commercial_terms_for_campaign,
    effective_invoice_obligation,
)
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


def _blocked_budget_evaluation_key(campaign: Campaign, *, evaluation_epoch_id: UUID | None) -> str:
    source = "|".join(
        (
            str(campaign.id),
            str(evaluation_epoch_id or "initial"),
            str(campaign.budget_amount),
            str(campaign.daily_budget_amount),
            campaign.currency,
            MISSING_BUDGET_POLICY_GATE,
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()


async def _campaign_billing_spend(
    session: AsyncSession, *, campaign_id: UUID, now: datetime
) -> tuple[Decimal, Decimal, str]:
    """Return advertiser billing authority only; driver payout rows are intentionally absent."""
    terms = await _commercial_terms_for_campaign(session, campaign_id, lock=True)
    if terms is None:
        return Decimal("0.00"), Decimal("0.00"), "confirmed_funding"
    production = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    if production is not None:
        obligation = (
            await effective_invoice_obligation(session, commercial_terms_id=terms.id)
        ).quantize(MONEY_QUANTUM)
        daily = (
            obligation
            if _stored_aware_utc(production.started_at).astimezone(LAGOS_TZ).date()
            == now.astimezone(LAGOS_TZ).date()
            else Decimal("0.00")
        )
        return obligation, daily, "production_obligation"
    allocations = await _active_cash_allocations(session, terms.id)
    total = sum((Decimal(row.amount) for row in allocations), Decimal("0.00")).quantize(
        MONEY_QUANTUM
    )
    today = now.astimezone(LAGOS_TZ).date()
    daily = sum(
        (
            Decimal(row.amount)
            for row in allocations
            if _stored_aware_utc(row.allocated_at).astimezone(LAGOS_TZ).date() == today
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANTUM)
    return total, daily, "confirmed_funding"


def _budget_evaluation_key(
    campaign: Campaign,
    *,
    evaluation_epoch_id: UUID | None,
    decision,
    billing_fact_source: str,
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
            # Appended only when set, so two-level decisions keep their existing keys.
            *(
                (str(decision.urgent_threshold_amount),)
                if decision.urgent_threshold_amount is not None
                else ()
            ),
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()


def _validate_budget_decision(decision, *, synthetic_test_authority: bool) -> None:
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
            Decimal("0") <= resume <= alert < pause
            and spend >= 0
            and (urgent is None or alert < urgent < pause)
        )
        expected_state = (
            BudgetPolicyEvaluationState.PAUSE_THRESHOLD.value
            if spend >= pause
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
        or decision.budget_basis not in {"total", "daily"}
        or not thresholds_valid
        or decision.state != expected_state
        or decision.external_gate
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
    configured_budgets = [
        Decimal(value)
        for value in (campaign.budget_amount, campaign.daily_budget_amount)
        if value is not None
    ]
    if not configured_budgets:
        raise AppError(
            "CAMPAIGN_BUDGET_REQUIRED",
            "Budget policy evaluation requires a configured total or daily campaign budget",
            status_code=status.HTTP_409_CONFLICT,
        )
    selected_adapter = adapter or DisabledBudgetPolicyAdapter()
    if any(value <= 0 for value in configured_budgets) and not isinstance(
        selected_adapter, DisabledBudgetPolicyAdapter
    ):
        raise AppError(
            "CAMPAIGN_BUDGET_REQUIRED",
            "Authorized threshold evaluation requires positive configured budgets",
            status_code=status.HTTP_409_CONFLICT,
        )
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
    total_spend, daily_spend, billing_fact_source = await _campaign_billing_spend(
        session, campaign_id=campaign.id, now=now
    )
    decision = await selected_adapter.evaluate(
        BudgetPolicyContext(
            campaign_id=campaign.id,
            currency=campaign.currency,
            configured_budget_amount=(
                Decimal(campaign.budget_amount) if campaign.budget_amount is not None else None
            ),
            configured_daily_budget_amount=(
                Decimal(campaign.daily_budget_amount)
                if campaign.daily_budget_amount is not None
                else None
            ),
            total_billing_spend_amount=total_spend,
            daily_billing_spend_amount=daily_spend,
        )
    )
    blocked = decision.state == BLOCKED_BUDGET_POLICY_STATE
    if blocked:
        if any(
            (
                decision.external_gate != MISSING_BUDGET_POLICY_GATE,
                decision.policy_id is not None,
                decision.policy_revision is not None,
                decision.policy_source is not None,
                decision.budget_basis is not None,
                decision.billing_spend_amount is not None,
                decision.alert_threshold_amount is not None,
                decision.urgent_threshold_amount is not None,
                decision.pause_threshold_amount is not None,
                decision.resume_threshold_amount is not None,
                decision.should_pause,
                decision.resume_allowed,
            )
        ):
            raise AppError(
                "BUDGET_POLICY_NOT_AUTHORIZED",
                "EXT-BUDGET-POLICY is missing; threshold and pause decisions are disabled",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        evaluation_key = _blocked_budget_evaluation_key(
            campaign, evaluation_epoch_id=evaluation_epoch_id
        )
    else:
        _validate_budget_decision(decision, synthetic_test_authority=synthetic_test_authority)
        evaluation_key = _budget_evaluation_key(
            campaign,
            evaluation_epoch_id=evaluation_epoch_id,
            decision=decision,
            billing_fact_source=billing_fact_source,
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
        external_gate=decision.external_gate,
        campaign_budget_amount=campaign.budget_amount,
        campaign_daily_budget_amount=campaign.daily_budget_amount,
        currency=campaign.currency,
        policy_id=decision.policy_id,
        policy_revision=decision.policy_revision,
        policy_source=decision.policy_source,
        budget_basis=decision.budget_basis,
        billing_fact_source=None if blocked else billing_fact_source,
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
        action=("billing.budget_policy.blocked" if blocked else "billing.budget_policy.evaluated"),
        entity_type="budget_policy_evaluation",
        entity_id=str(evaluation.id),
        metadata={
            "campaign_id": str(campaign.id),
            "external_gate": decision.external_gate or None,
            "policy_id": decision.policy_id,
            "policy_revision": decision.policy_revision,
            "policy_source": decision.policy_source,
            "budget_basis": decision.budget_basis,
            "billing_fact_source": None if blocked else billing_fact_source,
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
    if not blocked:
        from app.services.notifications import create_budget_policy_notices

        await create_budget_policy_notices(session, campaign=campaign, evaluation=evaluation)
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
    evaluation = await session.scalar(
        select(BudgetPolicyEvaluation)
        .where(BudgetPolicyEvaluation.campaign_id == campaign_id)
        .order_by(BudgetPolicyEvaluation.evaluated_at.desc(), BudgetPolicyEvaluation.id.desc())
        .limit(1)
        .with_for_update()
    )
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
    if campaign.status != CampaignStatus.PAUSED.value:
        raise AppError(
            "CAMPAIGN_NOT_BUDGET_PAUSED",
            "Campaign is not paused",
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


async def sweep_budget_policy_evaluations(
    session: AsyncSession,
    *,
    adapter: BudgetPolicyAdapter | None = None,
    synthetic_test_authority: bool = False,
) -> list[BudgetPolicyEvaluation]:
    campaign_ids = list(
        await session.scalars(
            select(Campaign.id)
            .where(
                (Campaign.budget_amount.is_not(None)) | (Campaign.daily_budget_amount.is_not(None))
            )
            .order_by(Campaign.id)
        )
    )
    return [
        await evaluate_campaign_budget_policy(
            session,
            campaign_id=campaign_id,
            adapter=adapter,
            synthetic_test_authority=synthetic_test_authority,
        )
        for campaign_id in campaign_ids
    ]
