import asyncio
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

from app.adapters.budget import BudgetPolicyContext, BudgetPolicyDecision
from app.core.errors import AppError
from app.models.billing import BudgetPolicyEvaluation
from app.models.campaign import Campaign, CampaignStatus
from app.services.billing import (
    evaluate_campaign_budget_policy,
    sweep_blocked_budget_policy_evaluations,
)


def _campaign(
    db_sessionmaker,
    suffix: str,
    *,
    budget_amount: str | None = "1000.00",
    daily_budget_amount: str | None = "100.00",
):
    admin = create_test_user(db_sessionmaker, email=f"budget-admin-{suffix}@example.com")
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=admin.id,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount=budget_amount,
        daily_budget_amount=daily_budget_amount,
    )
    return campaign


def test_missing_policy_is_visible_idempotent_and_never_pauses(db_sessionmaker) -> None:
    campaign = _campaign(db_sessionmaker, "blocked")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            first = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            second = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            assert first.id == second.id
            assert first.state == "blocked_external_policy"
            assert first.external_gate == "EXT-BUDGET-POLICY"
            assert first.campaign_budget_amount == Decimal("1000.00")
            assert first.billing_spend_amount is None
            assert first.alert_threshold_amount is None
            assert first.pause_threshold_amount is None
            assert first.pause_applied is False
            reloaded_campaign = await session.get(Campaign, campaign.id)
            assert reloaded_campaign.status == CampaignStatus.ACTIVE
            count = await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation))
            assert count == 1
            await session.commit()

    asyncio.run(scenario())


def test_sweep_skips_campaigns_without_configured_budget(db_sessionmaker) -> None:
    budgeted = _campaign(db_sessionmaker, "sweep-budgeted")
    daily_only = _campaign(
        db_sessionmaker,
        "sweep-daily-only",
        budget_amount=None,
        daily_budget_amount="100.00",
    )
    unbudgeted = _campaign(
        db_sessionmaker,
        "sweep-unbudgeted",
        budget_amount=None,
        daily_budget_amount=None,
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            evaluations = await sweep_blocked_budget_policy_evaluations(session)
            assert {evaluation.campaign_id for evaluation in evaluations} == {
                budgeted.id,
                daily_only.id,
            }
            daily_evaluation = next(
                evaluation for evaluation in evaluations if evaluation.campaign_id == daily_only.id
            )
            assert daily_evaluation.campaign_budget_amount is None
            assert daily_evaluation.campaign_daily_budget_amount == Decimal("100.00")
            with pytest.raises(AppError) as missing:
                await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=unbudgeted.id,
                )
            assert missing.value.code == "CAMPAIGN_BUDGET_REQUIRED"

    asyncio.run(scenario())


def test_nonblocked_policy_decision_is_rejected_while_gate_is_missing(db_sessionmaker) -> None:
    campaign = _campaign(db_sessionmaker, "unauthorized")

    class UnauthorizedAdapter:
        async def evaluate(self, context: BudgetPolicyContext) -> BudgetPolicyDecision:
            return BudgetPolicyDecision(
                state="pause_threshold",
                external_gate="",
                policy_version="invented-v1",
                alert_threshold_amount=Decimal("800.00"),
                pause_threshold_amount=Decimal("1000.00"),
                should_pause=True,
            )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as blocked:
                await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=UnauthorizedAdapter(),
                )
            assert blocked.value.code == "BUDGET_POLICY_NOT_AUTHORIZED"
            reloaded_campaign = await session.get(Campaign, campaign.id)
            assert reloaded_campaign.status == CampaignStatus.ACTIVE

    asyncio.run(scenario())


def test_concurrent_blocked_evaluation_converges_to_one_row(postgis_db_sessionmaker) -> None:
    campaign = _campaign(postgis_db_sessionmaker, "race")

    async def scenario() -> None:
        async def evaluate() -> str:
            async with postgis_db_sessionmaker() as session:
                result = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                )
                await session.commit()
                return str(result.id)

        ids = await asyncio.gather(evaluate(), evaluate())
        assert ids[0] == ids[1]
        async with postgis_db_sessionmaker() as session:
            count = await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation))
            assert count == 1

    asyncio.run(scenario())
