import asyncio
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

from app.models.campaign import CampaignStatus
from app.services.billing.budget import (
    enforce_campaign_budget,
    sweep_campaign_budgets,
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


@pytest.mark.parametrize(
    "booked,budget,agreed,state",
    [
        ("1000", "1000", "1000", "within_budget"),
        ("1075", "1000", "1075", "within_budget"),
        ("799.99", "1000", "500", "within_budget"),
        ("800", "1000", "500", "alert_threshold"),
        ("950", "1000", "500", "urgent_threshold"),
        ("1000", "1000", "500", "urgent_threshold"),
        ("1000.01", "1000", "500", "pause_threshold"),
        ("0.0095", "0.01", None, "urgent_threshold"),
    ],
)
def test_fixed_d104_thresholds(booked, budget, agreed, state):
    from app.services.billing.budget import budget_state

    assert (
        budget_state(
            booked=Decimal(booked),
            budget=Decimal(budget),
            agreed=Decimal(agreed) if agreed else None,
        )
        == state
    )


def test_read_check_is_current_without_stored_evaluations(db_sessionmaker):
    from app.models.billing import BudgetCampaignTransition

    campaign = _campaign(db_sessionmaker, "direct")

    async def exercise():
        async with db_sessionmaker() as session:
            first = await enforce_campaign_budget(session, campaign_id=campaign.id)
            second = await enforce_campaign_budget(session, campaign_id=campaign.id)
            assert first.state == second.state == "within_budget"
            assert first.billing_spend_amount == 0
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 0
            )

    asyncio.run(exercise())


def test_sweep_ignores_daily_only_budgets(db_sessionmaker):
    campaign = _campaign(db_sessionmaker, "total")
    _campaign(db_sessionmaker, "daily", budget_amount=None)

    async def exercise():
        async with db_sessionmaker() as session:
            checks = await sweep_campaign_budgets(session)
            assert [check.campaign_id for check in checks] == [campaign.id]

    asyncio.run(exercise())
