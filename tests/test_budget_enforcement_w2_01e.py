import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

from app.adapters.budget import FixedBudgetPolicyAdapter
from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    BudgetCampaignTransition,
    BudgetPolicyEvaluation,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.notification import Notification
from app.models.user import UserRole
from app.services.billing import (
    accept_quotation_revision,
    allocate_payment_receipt,
    confirm_payment_receipt,
    evaluate_campaign_budget_policy,
    reconcile_payment_receipt,
    record_payment_receipt,
    record_quotation_revision,
    request_custom_quote,
    resume_campaign_after_budget_pause,
    reverse_payment_receipt,
)


def policy() -> FixedBudgetPolicyAdapter:
    return FixedBudgetPolicyAdapter(
        policy_id="synthetic-budget-policy",
        policy_revision="synthetic-test-r1",
        policy_source="synthetic_test",
        alert_ratio=Decimal("0.80"),
        pause_ratio=Decimal("1.00"),
        resume_ratio=Decimal("0.70"),
    )


async def accepted_terms(session, *, campaign, admin, owner):
    request = await request_custom_quote(
        session,
        campaign_id=campaign.id,
        actor_user_id=owner.id,
        source=QuoteRequestSource.IN_PLATFORM,
        request_details={},
    )
    revision = await record_quotation_revision(
        session,
        quote_request_id=request.id,
        actor_user_id=admin.id,
        quote_reference="BUDGET-Q1",
        currency="NGN",
        line_items=[
            {
                "code": "MEDIA",
                "description": "Synthetic media funding",
                "kind": "media",
                "amount": "1000.00",
            }
        ],
        production_scope={"synthetic_test": True},
        payment_class=PaymentClass.STANDARD_PREPAID,
        payment_terms={"synthetic_test": True},
        tax_rate="0",
    )
    return await accept_quotation_revision(
        session,
        quotation_revision_id=revision.id,
        actor_user_id=owner.id,
        acceptance_method=AcceptanceMethod.IN_PLATFORM,
    )


async def fund(session, *, terms, organization, admin, reference, amount):
    receipt = await record_payment_receipt(
        session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        method=ReceiptMethod.MANUAL_TRANSFER,
        provider="synthetic-test-bank",
        external_transaction_id=reference,
        amount=amount,
        currency="NGN",
        payer_name="Synthetic Advertiser",
        evidence_reference=f"synthetic:{reference}",
        observed_at=datetime.now(UTC),
    )
    await reconcile_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=admin.id,
        expected_amount=amount,
        expected_currency="NGN",
    )
    await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
    await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=terms.id,
        actor_user_id=admin.id,
        amount=amount,
    )
    return receipt


def test_synthetic_policy_requires_explicit_test_authority(db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="budget-auth-admin@example.com")
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=admin.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1000.00",
    )

    async def scenario():
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as blocked:
                await evaluate_campaign_budget_policy(
                    session, campaign_id=campaign.id, adapter=policy()
                )
            assert blocked.value.code == "SYNTHETIC_BUDGET_POLICY_FORBIDDEN"

    asyncio.run(scenario())


def test_billing_funding_alert_pause_reversal_and_audited_resume_converge(
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="budget-flow-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="budget-flow-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1000.00",
        daily_budget_amount=None,
    )

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(session, campaign=campaign, admin=admin, owner=owner)
            first_receipt = await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-BUDGET-850",
                amount="850.00",
            )
            alert = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            assert retry.id == alert.id
            assert alert.state == "alert_threshold"
            assert alert.billing_fact_source == "confirmed_funding"
            assert alert.billing_spend_amount == Decimal("850.00")
            assert alert.policy_revision == "synthetic-test-r1"
            assert alert.alert_applied is True
            assert alert.pause_applied is False

            second_receipt = await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-BUDGET-150",
                amount="150.00",
            )
            paused = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            assert paused.state == "pause_threshold"
            assert paused.pause_applied is True
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
            )

            await reverse_payment_receipt(
                session,
                receipt_id=first_receipt.id,
                actor_user_id=admin.id,
                reason="synthetic reversal one",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=second_receipt.id,
                actor_user_id=admin.id,
                reason="synthetic reversal two",
            )
            below = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            assert below.state == "within_budget"
            assert below.billing_spend_amount == Decimal("0.00")
            assert below.resume_allowed is True
            resumed = await resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason="confirmed funding reversal restored headroom",
            )
            same_resume = await resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason="confirmed funding reversal restored headroom",
            )
            assert same_resume.id == resumed.id
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.ACTIVE
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 3
            )
            # Funding, alert, pause, and resume all share the existing outbox.
            assert (
                int(await session.scalar(select(func.count()).select_from(Notification)) or 0) == 10
            )
            await session.commit()

    asyncio.run(scenario())


def test_concurrent_funding_and_budget_worker_converge_to_one_pause(
    postgis_db_sessionmaker,
) -> None:
    admin = create_test_user(postgis_db_sessionmaker, email="budget-race-admin@example.com")
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="budget-race-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(postgis_db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1000.00",
        daily_budget_amount=None,
    )

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            terms = await accepted_terms(session, campaign=campaign, admin=admin, owner=owner)
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="synthetic-test-bank",
                external_transaction_id="SYNTHETIC-BUDGET-RACE",
                amount="1000.00",
                currency="NGN",
                payer_name="Synthetic Advertiser",
                evidence_reference="synthetic:budget-race",
                observed_at=datetime.now(UTC),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="1000.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
            await session.commit()
            return terms.id, receipt.id

    async def scenario():
        terms_id, receipt_id = await prepare()

        async def allocate():
            async with postgis_db_sessionmaker() as session:
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt_id,
                    commercial_terms_id=terms_id,
                    actor_user_id=admin.id,
                    amount="1000.00",
                )
                await session.commit()

        async def evaluate():
            async with postgis_db_sessionmaker() as session:
                await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=policy(),
                    synthetic_test_authority=True,
                )
                await session.commit()

        await asyncio.wait_for(asyncio.gather(allocate(), evaluate()), timeout=10)
        async with postgis_db_sessionmaker() as session:
            final = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await session.commit()
            assert final.state == "pause_threshold"
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
            )

    asyncio.run(scenario())
