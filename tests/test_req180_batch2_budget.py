import asyncio
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_budget_enforcement_w2_01e import (
    accepted_terms,
    correct,
    fund,
    in_production,
    raised_budget_in_production,
)

from app.core.errors import AppError
from app.models.billing import BudgetCampaignTransition
from app.models.campaign import Campaign
from app.models.notification import Notification
from app.models.user import UserRole
from app.services.billing import budget

BUDGET_NOTICE_TYPES = ("budget_alert", "budget_urgent_alert", "campaign_budget_paused")


def actors(maker, *, total="1000.00", daily=None, tag="d92"):
    admin = create_test_user(maker, email=f"{tag}-admin@example.com")
    owner = create_test_user(maker, email=f"{tag}-owner@example.com", role=UserRole.ADVERTISER)
    organization, _ = create_test_organization(maker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        maker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status="active",
        budget_amount=total,
        daily_budget_amount=daily,
    )
    return admin, owner, organization, campaign


async def budget_notices(session):
    return await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.type_key.in_(BUDGET_NOTICE_TYPES))
    )


def media(amount):
    return {"code": "MEDIA", "description": "Media", "kind": "media", "amount": amount}


@pytest.mark.parametrize(
    ("budget_amount", "daily", "lines", "tax", "agreed"),
    [
        # A: VAT and a printing line on a media-only budget.
        (
            "1000000.00",
            None,
            [
                media("1000000.00"),
                {
                    "code": "PRINT",
                    "description": "Print",
                    "kind": "production",
                    "amount": "50000.00",
                },
            ],
            "0.075",
            "1128750.00",
        ),
        # B: the seed shape, gross exactly equal to the budget.
        ("1000000.00", None, [media("930232.56")], "0.075", "1000000.00"),
        # C: a daily budget with the whole prepayment on one day.
        ("1000000.00", "50000.00", [media("500000.00")], "0", "1000000.00"),
    ],
    ids=["vat-and-fixed-lines", "gross-equals-budget", "daily-budget-one-payment"],
)
def test_normal_fixed_price_campaign_never_warns_or_pauses(
    db_sessionmaker, settings, budget_amount, daily, lines, tax, agreed
):
    admin, owner, organization, campaign = actors(
        db_sessionmaker, total=budget_amount, daily=daily, tag="d104-normal"
    )

    async def exercise():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, line_items=lines, tax_rate=tax
            )
            row = await session.get(Campaign, campaign.id)
            assert row.budget_amount == Decimal(agreed)
            # Staged deposit then the balance, as a normal advertiser pays.
            deposit = (terms.gross_amount / 2).quantize(Decimal("0.01"))
            for reference, amount in (("DEP", deposit), ("BAL", terms.gross_amount - deposit)):
                await fund(
                    session,
                    terms=terms,
                    organization=organization,
                    admin=admin,
                    reference=f"D104-{reference}",
                    amount=str(amount),
                )
                evaluation = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
                assert evaluation.state == "within_budget"
            assert evaluation.billing_spend_amount == terms.gross_amount
            assert await budget_notices(session) == 0
            assert row.status == "active"
            await session.commit()

    asyncio.run(exercise())


@pytest.mark.parametrize("pause_origin", ["active", "historical_scheduled"])
def test_extra_charges_warn_then_pause_and_resume_after_a_budget_increase(
    db_sessionmaker, settings, pause_origin
):
    admin, owner, organization, campaign = actors(db_sessionmaker)

    async def exercise():
        async with db_sessionmaker() as session:
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            notice_counts = []
            for index, (amount, state) in enumerate(
                [
                    ("300.00", "alert_threshold"),
                    ("50.00", "alert_threshold"),
                    ("100.00", "urgent_threshold"),
                    # Exactly 100% is within the budget; only spend above it pauses.
                    ("50.00", "urgent_threshold"),
                    ("0.01", "pause_threshold"),
                ]
            ):
                await correct(
                    session, invoice=invoice, admin=admin, reference=f"D92-{index}", amount=amount
                )
                decision = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
                assert decision.state == state
                retry = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
                assert retry.state == decision.state
                notice_counts.append(await budget_notices(session))
            assert notice_counts == [3, 3, 6, 6, 9]
            assert decision.billing_spend_amount == Decimal("1000.01")
            assert (await session.get(Campaign, campaign.id)).status == "paused"
            with pytest.raises(AppError) as unchanged:
                await budget.resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="No confirmed changes",
                )
            assert unchanged.value.code == "BUDGET_RESUME_NOT_AUTHORIZED"
            if pause_origin == "historical_scheduled":
                historical = await session.scalar(
                    select(BudgetCampaignTransition).where(
                        BudgetCampaignTransition.campaign_id == campaign.id,
                        BudgetCampaignTransition.action == "pause",
                    )
                )
                # Metadata fixture has no immutable DB trigger: represent a row
                # genuinely written before0114, never mutate one in production.
                historical.prior_status = "scheduled"
                await session.flush()
            row = await session.get(Campaign, campaign.id)
            row.budget_amount = Decimal("1200.00")
            await session.flush()
            resumed = await budget.resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason="Confirmed budget increase",
            )
            assert resumed.new_status == (
                "approved" if pause_origin == "historical_scheduled" else "active"
            )
            if pause_origin == "historical_scheduled":
                assert historical.prior_status == "scheduled"
            assert (
                await budget.resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="Confirmed budget increase",
                )
            ).id == resumed.id
            # 1000.01 of 1200 is above 80%: the resume's own fresh evaluation warns, and the
            # first evaluation of the new epoch warns again (existing behaviour, recorded gap).
            again = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
            assert again.state == "alert_threshold" and again.alert_applied is True
            assert await budget_notices(session) == 12
            await session.commit()

    asyncio.run(exercise())


def test_budget_above_the_quote_warns_only_when_extra_charges_exceed_the_agreed_total(
    db_sessionmaker, settings
):
    # Budget 1.5m set above a 1m quote to leave room; extra charges take booked to 1.4m.
    admin, owner, organization, campaign = actors(
        db_sessionmaker, total="1500000.00", tag="d104-room"
    )

    async def exercise():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                line_items=[media("1000000.00")],
            )
            assert (await session.get(Campaign, campaign.id)).budget_amount == Decimal("1500000.00")
            invoice = await in_production(
                session,
                campaign=campaign,
                terms=terms,
                organization=organization,
                admin=admin,
                owner=owner,
                settings=settings,
            )
            within = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
            assert within.state == "within_budget" and await budget_notices(session) == 0
            steps = [
                ("400000.00", "alert_threshold"),
                ("30000.00", "urgent_threshold"),
                ("70000.01", "pause_threshold"),
            ]
            for index, (amount, state) in enumerate(steps):
                await correct(
                    session, invoice=invoice, admin=admin, reference=f"ROOM-{index}", amount=amount
                )
                decision = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
                assert decision.state == state
            assert decision.billing_spend_amount == Decimal("1500000.01")
            assert (await session.get(Campaign, campaign.id)).status == "paused"
            await session.commit()

    asyncio.run(exercise())


def test_enforcement_rechecks_new_scheduling_and_ignores_stored_daily_budgets(
    db_sessionmaker, settings
):
    admin, owner, organization, campaign = actors(db_sessionmaker)
    draft = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status="draft",
        budget_amount="100.00",
        daily_budget_amount="0.00",
    )
    tiny = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status="active",
        budget_amount="0.01",
        daily_budget_amount=None,
    )
    create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status="draft",
        budget_amount=None,
        daily_budget_amount="50.00",
    )

    async def exercise():
        async with db_sessionmaker() as session:
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await correct(session, invoice=invoice, admin=admin, reference="SCHED", amount="500.01")
            row = await session.get(Campaign, campaign.id)
            row.status = "draft"
            await session.flush()
            before = await budget.enforce_campaign_budget(session, campaign_id=campaign.id)
            assert before.state == "pause_threshold" and before.pause_applied is False
            row.status = "approved"
            await session.flush()
            evaluations = await budget.sweep_campaign_budgets(session)
            # A daily-only draft has no enforced budget and is not swept.
            assert {item.campaign_id for item in evaluations} == {campaign.id, tiny.id, draft.id}
            after = next(item for item in evaluations if item.campaign_id == campaign.id)
            assert before.pause_applied is False and after.pause_applied is True
            assert row.status == "paused"
            assert all(
                item.state == "within_budget"
                for item in evaluations
                if item.campaign_id != campaign.id
            )
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
            )
            await session.commit()

    asyncio.run(exercise())
