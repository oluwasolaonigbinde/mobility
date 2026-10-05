import asyncio
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

import app.services.billing as billing_service
from app.adapters.budget import BudgetPolicyContext, FixedBudgetPolicyAdapter
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import (
    AcceptanceMethod,
    BudgetCampaignTransition,
    BudgetPolicyEvaluation,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.notification import Notification, NotificationType
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


async def accepted_terms(session, *, campaign, admin, owner, line_items=None, tax_rate="0"):
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
        line_items=line_items
        or [
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
        tax_rate=tax_rate,
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
            with pytest.raises(AppError) as missing_reason:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason=" ",
                )
            assert missing_reason.value.code == "BUDGET_RESUME_REASON_REQUIRED"
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
            with pytest.raises(AppError) as changed_resume:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="different resume evidence",
                )
            assert changed_resume.value.code == "BUDGET_RESUME_ALREADY_RECORDED"
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.ACTIVE
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 3
            )
            # Funding, alert, pause, and resume all share the existing outbox; the
            # in-platform quotation also told the advertiser to review it.
            notice_types = list(await session.scalars(select(Notification.type_key)))
            quotation_notices = [
                type_key
                for type_key in notice_types
                if type_key == NotificationType.QUOTATION_READY.value
            ]
            assert len(quotation_notices) == 2
            # The active admin also receives the alert and pause in the app (client answer #3).
            assert len(notice_types) - len(quotation_notices) == 12

            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-BUDGET-NEW-EPOCH-1000",
                amount="1000.00",
            )
            post_resume_breach = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            post_resume_retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            assert post_resume_breach.id != paused.id
            assert post_resume_retry.id == post_resume_breach.id
            assert post_resume_breach.state == "pause_threshold"
            assert post_resume_breach.pause_applied is True
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 4
            )
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 3
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(Notification)
                        .where(
                            Notification.type_key.in_(
                                {
                                    NotificationType.BUDGET_ALERT.value,
                                    NotificationType.CAMPAIGN_BUDGET_PAUSED.value,
                                    NotificationType.CAMPAIGN_BUDGET_RESUMED.value,
                                }
                            )
                        )
                    )
                    or 0
                )
                == 11
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "billing.budget_policy.evaluated")
                )
                == 4
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "billing.budget_policy.resumed")
                )
                == 1
            )
            with pytest.raises(AppError) as threshold_resume:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="threshold remains breached",
                )
            assert threshold_resume.value.code == "BUDGET_RESUME_NOT_AUTHORIZED"
            await session.commit()

    asyncio.run(scenario())


def test_resume_epoch_uses_causal_time_not_uuid_or_later_pause(
    db_sessionmaker, monkeypatch
) -> None:
    admin = create_test_user(db_sessionmaker, email="budget-epoch-admin@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email="budget-epoch-owner@example.com",
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
    fixed_resume_time = datetime(2030, 1, 1, tzinfo=UTC)
    later_pause_time = datetime(2030, 1, 2, tzinfo=UTC)
    high_resume_id = UUID("ffffffff-ffff-ffff-ffff-fffffffffff1")
    low_resume_id = UUID("00000000-0000-0000-0000-000000000002")
    original_transition_init = BudgetCampaignTransition.__init__

    async def resume_with_id(session, *, evaluation_reason: str, transition_id: UUID):
        async def fixed_clock(_session):
            return fixed_resume_time

        def transition_init(instance, **kwargs):
            original_transition_init(instance, **kwargs)
            if kwargs.get("action") == "resume":
                instance.id = transition_id

        with monkeypatch.context() as patch:
            patch.setattr(billing_service, "database_clock", fixed_clock)
            patch.setattr(BudgetCampaignTransition, "__init__", transition_init)
            return await resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason=evaluation_reason,
            )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await accepted_terms(session, campaign=campaign, admin=admin, owner=owner)
            first_receipt = await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-EPOCH-FIRST",
                amount="1000.00",
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await reverse_payment_receipt(
                session,
                receipt_id=first_receipt.id,
                actor_user_id=admin.id,
                reason="first epoch headroom",
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            first_resume = await resume_with_id(
                session,
                evaluation_reason="first causal resume",
                transition_id=high_resume_id,
            )
            assert first_resume.id == high_resume_id
            blocked_before = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)

            second_receipt = await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-EPOCH-SECOND",
                amount="1000.00",
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await reverse_payment_receipt(
                session,
                receipt_id=second_receipt.id,
                actor_user_id=admin.id,
                reason="second epoch headroom",
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            second_resume = await resume_with_id(
                session,
                evaluation_reason="second causal resume",
                transition_id=low_resume_id,
            )
            assert second_resume.id == low_resume_id

            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-EPOCH-THIRD",
                amount="1000.00",
            )

            async def later_clock(_session):
                return later_pause_time

            with monkeypatch.context() as patch:
                patch.setattr(billing_service, "database_clock", later_clock)
                latest_pause = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=policy(),
                    synthetic_test_authority=True,
                )
            blocked_after = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            assert blocked_after.id != blocked_before.id
            assert second_resume.created_at > first_resume.created_at
            latest_pause_transition = await session.scalar(
                select(BudgetCampaignTransition).where(
                    BudgetCampaignTransition.evaluation_id == latest_pause.id,
                    BudgetCampaignTransition.action == "pause",
                )
            )
            assert latest_pause_transition is not None
            assert billing_service._stored_aware_utc(
                latest_pause_transition.created_at
            ) > billing_service._stored_aware_utc(second_resume.created_at)
            assert blocked_after.state == "blocked_external_policy"
            await session.commit()

        async with db_sessionmaker() as session:
            blocked_retry = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            assert blocked_retry.id == blocked_after.id
            with pytest.raises(AppError) as unauthorized:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="blocked policy cannot authorize resume",
                )
            assert unauthorized.value.code == "BUDGET_RESUME_NOT_AUTHORIZED"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(BudgetCampaignTransition)
                    .where(BudgetCampaignTransition.action == "resume")
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "billing.budget_policy.blocked")
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == NotificationType.CAMPAIGN_BUDGET_PAUSED.value)
                )
                == 9
            )
            await session.commit()

    asyncio.run(scenario())


def test_postgres_resume_evaluation_overlap_applies_one_new_epoch_pause(
    postgis_db_sessionmaker, monkeypatch
) -> None:
    admin = create_test_user(postgis_db_sessionmaker, email="budget-resume-race-admin@example.com")
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="budget-resume-race-owner@example.com",
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

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            terms = await accepted_terms(session, campaign=campaign, admin=admin, owner=owner)
            first_receipt = await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-RESUME-RACE-FIRST",
                amount="1000.00",
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await reverse_payment_receipt(
                session,
                receipt_id=first_receipt.id,
                actor_user_id=admin.id,
                reason="resume race headroom",
            )
            resume_evaluation = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-RESUME-RACE-REFILL",
                amount="1000.00",
            )
            await session.commit()

        original_lock = billing_service.acquire_campaign_terms_lock
        resume_has_lock = asyncio.Event()
        evaluation_attempted_lock = asyncio.Event()
        release_resume = asyncio.Event()

        async def controlled_lock(session, campaign_id):
            task = asyncio.current_task()
            task_name = task.get_name() if task is not None else ""
            if task_name == "r24-overlap-evaluation":
                evaluation_attempted_lock.set()
            await original_lock(session, campaign_id)
            if task_name == "r24-overlap-resume":
                resume_has_lock.set()
                await release_resume.wait()

        monkeypatch.setattr(billing_service, "acquire_campaign_terms_lock", controlled_lock)

        async def resume() -> UUID:
            async with postgis_db_sessionmaker() as session:
                transition = await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="serialized resume race",
                )
                await session.commit()
                return transition.id

        async def evaluate() -> UUID:
            async with postgis_db_sessionmaker() as session:
                evaluation = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=policy(),
                    synthetic_test_authority=True,
                )
                await session.commit()
                return evaluation.id

        resume_task = asyncio.create_task(resume(), name="r24-overlap-resume")
        await asyncio.wait_for(resume_has_lock.wait(), timeout=5)
        evaluation_task = asyncio.create_task(evaluate(), name="r24-overlap-evaluation")
        await asyncio.wait_for(evaluation_attempted_lock.wait(), timeout=5)
        await asyncio.sleep(0)
        assert evaluation_task.done() is False
        release_resume.set()
        _, post_resume_evaluation_id = await asyncio.wait_for(
            asyncio.gather(resume_task, evaluation_task), timeout=10
        )
        assert post_resume_evaluation_id != resume_evaluation.id

        async with postgis_db_sessionmaker() as session:
            retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            assert retry.id == post_resume_evaluation_id
            assert retry.state == "pause_threshold"
            assert retry.pause_applied is True
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 3
            )
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 3
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "billing.budget_policy.evaluated")
                )
                == 3
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "billing.budget_policy.resumed")
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == NotificationType.CAMPAIGN_BUDGET_PAUSED.value)
                )
                == 6
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == NotificationType.CAMPAIGN_BUDGET_RESUMED.value)
                )
                == 2
            )
            with pytest.raises(AppError) as unauthorized:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="breach cannot resume",
                )
            assert unauthorized.value.code == "BUDGET_RESUME_NOT_AUTHORIZED"
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


def three_level_policy() -> FixedBudgetPolicyAdapter:
    return FixedBudgetPolicyAdapter(
        policy_id="synthetic-budget-policy",
        policy_revision="synthetic-test-r2",
        policy_source="synthetic_test",
        alert_ratio=Decimal("0.80"),
        urgent_ratio=Decimal("0.95"),
        pause_ratio=Decimal("1.00"),
        resume_ratio=Decimal("0.70"),
    )


def test_urgent_level_alerts_advertiser_members_and_admins_before_the_pause(
    db_sessionmaker,
) -> None:
    admin = create_test_user(db_sessionmaker, email="budget-urgent-admin@example.com")
    second_admin = create_test_user(db_sessionmaker, email="budget-urgent-admin2@example.com")
    owner = create_test_user(
        db_sessionmaker, email="budget-urgent-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1000.00",
    )

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(session, campaign=campaign, admin=admin, owner=owner)
            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="SYNTHETIC-URGENT-960",
                amount="960.00",
            )
            urgent = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=three_level_policy(),
                synthetic_test_authority=True,
            )
            retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=three_level_policy(),
                synthetic_test_authority=True,
            )
            assert retry.id == urgent.id
            assert urgent.state == "urgent_threshold"
            assert urgent.urgent_threshold_amount == Decimal("950.00")
            assert urgent.alert_applied is True
            assert urgent.pause_applied is False
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.ACTIVE
            recipients = list(
                await session.execute(
                    select(Notification.recipient_user_id, Notification.channel).where(
                        Notification.type_key == NotificationType.BUDGET_URGENT_ALERT.value
                    )
                )
            )
            # The owner gets in-app and email; each active admin gets one in-app notice,
            # and a retried evaluation adds nothing.
            assert sorted((str(user), channel) for user, channel in recipients) == sorted(
                [
                    (str(owner.id), "in_app"),
                    (str(owner.id), "transactional_email"),
                    (str(admin.id), "in_app"),
                    (str(second_admin.id), "in_app"),
                ]
            )

    asyncio.run(scenario())


def test_two_level_decisions_keep_their_evaluation_key() -> None:
    campaign = Campaign(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        budget_amount=Decimal("1000.00"),
        daily_budget_amount=None,
        currency="NGN",
    )
    context = BudgetPolicyContext(
        campaign_id=campaign.id,
        currency="NGN",
        configured_budget_amount=Decimal("1000.00"),
        configured_daily_budget_amount=None,
        total_billing_spend_amount=Decimal("850.00"),
        daily_billing_spend_amount=Decimal("0.00"),
    )
    decision = asyncio.run(policy().evaluate(context))
    assert decision.urgent_threshold_amount is None
    key = billing_service._budget_evaluation_key(
        campaign,
        evaluation_epoch_id=None,
        decision=decision,
        billing_fact_source="confirmed_funding",
    )
    # Recorded before the urgent level existed; must not change for two-level policies.
    legacy = hashlib.sha256(
        "|".join(
            (
                str(campaign.id),
                "initial",
                "1000.00",
                "None",
                "NGN",
                "synthetic-budget-policy",
                "synthetic-test-r1",
                "synthetic_test",
                "total",
                "confirmed_funding",
                "850.00",
                "800.00",
                "1000.00",
                "700.00",
                "alert_threshold",
            )
        ).encode()
    ).hexdigest()
    assert key == legacy


def test_three_level_thresholds_are_ordered_and_tiny_budgets_fail_closed() -> None:
    with pytest.raises(ValueError, match="invalid_budget_policy_threshold_order"):
        FixedBudgetPolicyAdapter(
            policy_id="p",
            policy_revision="r",
            policy_source="synthetic_test",
            alert_ratio=Decimal("0.80"),
            urgent_ratio=Decimal("0.80"),
            pause_ratio=Decimal("1.00"),
            resume_ratio=Decimal("0.70"),
        )
    # A 0.05 budget rounds warning, urgent and pause to the same cent; the service
    # refuses the collapsed decision instead of recording it.
    context = BudgetPolicyContext(
        campaign_id=UUID("00000000-0000-4000-8000-000000000002"),
        currency="NGN",
        configured_budget_amount=Decimal("0.05"),
        configured_daily_budget_amount=None,
        total_billing_spend_amount=Decimal("0.05"),
        daily_billing_spend_amount=Decimal("0.00"),
    )
    decision = asyncio.run(three_level_policy().evaluate(context))
    with pytest.raises(AppError) as invalid:
        billing_service._validate_budget_decision(decision, synthetic_test_authority=True)
    assert invalid.value.code == "INVALID_BUDGET_POLICY_DECISION"


def test_approved_settings_wire_all_three_levels_into_the_live_adapter(monkeypatch) -> None:
    from app.adapters.budget import build_budget_policy_adapter
    from app.core.config import Settings

    values = {
        "BUDGET_POLICY_EXTERNAL_APPROVED": "true",
        "BUDGET_POLICY_ID": "synthetic-settings-policy",
        "BUDGET_POLICY_REVISION": "synthetic-r1",
        "BUDGET_ALERT_RATIO": "0.80",
        "BUDGET_URGENT_RATIO": "0.95",
        "BUDGET_PAUSE_RATIO": "1.00",
        "BUDGET_RESUME_RATIO": "0.70",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    adapter = build_budget_policy_adapter(Settings(_env_file=None))
    assert isinstance(adapter, FixedBudgetPolicyAdapter)
    assert adapter.urgent_ratio == Decimal("0.95")

    def decide(spend: str):
        context = BudgetPolicyContext(
            campaign_id=UUID("00000000-0000-4000-8000-000000000003"),
            currency="NGN",
            configured_budget_amount=Decimal("1000.00"),
            configured_daily_budget_amount=None,
            total_billing_spend_amount=Decimal(spend),
            daily_billing_spend_amount=Decimal("0.00"),
        )
        return asyncio.run(adapter.evaluate(context))

    assert decide("850.00").state == "alert_threshold"
    assert decide("950.00").state == "urgent_threshold"
    paused = decide("1000.00")
    assert paused.state == "pause_threshold" and paused.should_pause is True

    for name, value in (("BUDGET_URGENT_RATIO", "0.80"), ("BUDGET_URGENT_RATIO", "")):
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError):
            Settings(_env_file=None)


def fixed_quote_lines():
    # Net 1000: media 400, printing 2x100, four fixed lines 100 each; VAT 75.
    return [
        {"code": "MEDIA", "description": "Media", "kind": "media", "amount": "400.00"},
        {
            "code": "PRINT",
            "description": "Printing",
            "kind": "production",
            "quantity": 2,
            "unit_amount": "100.00",
        },
        *[
            {"code": code, "description": code, "kind": kind, "amount": "100.00"}
            for code, kind in (
                ("INSTALL", "production"),
                ("PERMIT", "other"),
                ("DESIGN", "other"),
                ("FIXED_MISC", "other"),
            )
        ],
    ]


def fixed_lines_policy():
    return FixedBudgetPolicyAdapter(
        policy_id="synthetic-fixed-lines",
        policy_revision="r1",
        policy_source="synthetic_test",
        alert_ratio=Decimal("0.80"),
        urgent_ratio=Decimal("0.95"),
        pause_ratio=Decimal("1.00"),
        resume_ratio=Decimal("0.70"),
    )


def test_all_fixed_lines_count_once_in_funding_alerts_reversal_and_retry(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="fixed-funding-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="fixed-funding-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1075.00",
        daily_budget_amount=None,
    )

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                line_items=fixed_quote_lines(),
                tax_rate="0.075",
            )
            frozen = list(terms.line_items)
            assert terms.net_amount == Decimal("1000.00")
            assert terms.tax_amount == Decimal("75.00")
            assert terms.gross_amount == Decimal("1075.00")
            receipts = []
            for index, (increment, spend, state) in enumerate(
                [
                    ("860.00", "860.00", "alert_threshold"),
                    ("161.25", "1021.25", "urgent_threshold"),
                    ("53.75", "1075.00", "pause_threshold"),
                ]
            ):
                receipts.append(
                    await fund(
                        session,
                        terms=terms,
                        organization=organization,
                        admin=admin,
                        reference=f"FIXED-FUND-{index}",
                        amount=increment,
                    )
                )
                result = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=fixed_lines_policy(),
                    synthetic_test_authority=True,
                )
                retry = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
                    adapter=fixed_lines_policy(),
                    synthetic_test_authority=True,
                )
                assert result.id == retry.id
                assert result.state == state
                assert result.billing_spend_amount == Decimal(spend)
                assert result.billing_fact_source == "confirmed_funding"
            assert result.pause_applied
            for receipt in receipts:
                await reverse_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    reason="synthetic reversal",
                )
            below = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            assert below.billing_spend_amount == Decimal("0.00")
            assert below.resume_allowed
            assert terms.line_items == frozen
            assert terms.gross_amount == Decimal("1075.00")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("budget", "state"),
    [
        ("1343.75", "alert_threshold"),
        ("1131.58", "urgent_threshold"),
        ("1075.00", "pause_threshold"),
    ],
)
def test_full_fixed_quote_production_obligation_and_lagos_day(
    db_sessionmaker, settings, budget, state
):
    from datetime import timedelta

    from app.services.billing import (
        EXPEDITED_WAIVER_WORDING,
        EXPEDITED_WAIVER_WORDING_HASH,
        EXPEDITED_WAIVER_WORDING_VERSION,
        record_expedited_production_waiver,
        record_prepaid_cash_authorization,
        record_production_start,
    )

    admin = create_test_user(db_sessionmaker, email=f"fixed-prod-admin-{state}@example.com")
    owner = create_test_user(
        db_sessionmaker, email=f"fixed-prod-owner-{state}@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount=budget,
        daily_budget_amount=budget,
    )

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                line_items=fixed_quote_lines(),
                tax_rate="0.075",
            )
            frozen = list(terms.line_items)
            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference=f"FIXED-PROD-{state}",
                amount="1075.00",
            )
            await record_prepaid_cash_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                max_driver_liability="100.00",
                reason="synthetic authority",
            )
            waiver = await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version=EXPEDITED_WAIVER_WORDING_VERSION,
                accepted_wording=EXPEDITED_WAIVER_WORDING,
                accepted_wording_hash=EXPEDITED_WAIVER_WORDING_HASH,
            )
            production = await record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id, waiver_id=waiver.id
            )
            start = billing_service._stored_aware_utc(production.started_at)
            # The full accepted obligation already includes fixed charges and VAT.
            total, daily, source = await billing_service._campaign_billing_spend(
                session, campaign_id=campaign.id, now=start
            )
            assert (total, daily, source) == (
                Decimal("1075.00"),
                Decimal("1075.00"),
                "production_obligation",
            )
            result = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            assert result.state == state
            assert result.billing_spend_amount == Decimal("1075.00")
            # Midnight in Lagos is 23:00 UTC: attribution ends exactly there.
            midnight = (start + timedelta(days=1)).replace(
                hour=23, minute=0, second=0, microsecond=0
            )
            midnight = (
                start.replace(hour=23, minute=0, second=0, microsecond=0)
                if start.hour < 23
                else midnight
            )
            _, just_before, _ = await billing_service._campaign_billing_spend(
                session, campaign_id=campaign.id, now=midnight - timedelta(microseconds=1)
            )
            _, at_midnight, _ = await billing_service._campaign_billing_spend(
                session, campaign_id=campaign.id, now=midnight
            )
            assert just_before == Decimal("1075.00")
            assert at_midnight == Decimal("0.00")
            from test_invoices import _issuer

            from app.models.billing import InvoiceCorrectionType, IssuerVerificationStatus

            draft = await billing_service.create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session, admin, IssuerVerificationStatus.SYNTHETIC, "FIXED-TEST", settings
            )
            await billing_service.issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await billing_service.record_invoice_correction(
                session,
                invoice_id=draft.id,
                actor_user_id=admin.id,
                correction_reference="FIXED-CREDIT",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="100.00",
                tax_amount="7.50",
                reason="synthetic accepted correction",
            )
            # 1075 - (100 + 7.50), without mutating the accepted quote.
            total, daily, _ = await billing_service._campaign_billing_spend(
                session, campaign_id=campaign.id, now=start
            )
            assert (total, daily) == (Decimal("967.50"), Decimal("967.50"))
            _, later_daily, _ = await billing_service._campaign_billing_spend(
                session, campaign_id=campaign.id, now=midnight
            )
            assert later_daily == Decimal("0.00")
            corrected = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            assert corrected.billing_spend_amount == Decimal("967.50")
            assert corrected.evaluation_key != result.evaluation_key
            assert retry.id == corrected.id
            assert terms.line_items == frozen
            assert terms.gross_amount == Decimal("1075.00")

    asyncio.run(scenario())
