import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

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
from app.services.billing import budget as billing_budget
from app.services.billing import common as billing_common
from app.services.billing import invoices as billing_invoices
from app.services.billing import settlements as billing_settlements
from app.services.billing.budget import (
    evaluate_campaign_budget_policy,
    resume_campaign_after_budget_pause,
)
from app.services.billing.quotes import (
    accept_quotation_revision,
    record_quotation_revision,
    request_custom_quote,
)
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    reconcile_payment_receipt,
    record_payment_receipt,
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


async def accepted_terms(
    session, *, campaign, admin, owner, line_items=None, tax_rate="0", quote_reference="BUDGET-Q1"
):
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
        quote_reference=quote_reference,
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


async def in_production(session, *, campaign, terms, organization, admin, owner, settings):
    """Fully fund, start production and issue the invoice, as a normal campaign does."""
    from test_invoices import _issuer

    from app.models.billing import IssuerVerificationStatus
    from app.services.billing.authority import (
        record_expedited_production_waiver,
        record_prepaid_cash_authorization,
        record_production_start,
    )

    await fund(
        session,
        terms=terms,
        organization=organization,
        admin=admin,
        reference=f"FULL-{campaign.id.hex[:8]}",
        amount=str(terms.gross_amount),
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
        wording_version=billing_common.EXPEDITED_WAIVER_WORDING_VERSION,
        accepted_wording=billing_common.EXPEDITED_WAIVER_WORDING,
        accepted_wording_hash=billing_common.EXPEDITED_WAIVER_WORDING_HASH,
    )
    await record_production_start(
        session, campaign_id=campaign.id, actor_user_id=admin.id, waiver_id=waiver.id
    )
    invoice = await billing_invoices.create_invoice_draft(
        session, commercial_terms_id=terms.id, actor_user_id=admin.id
    )
    issuer = await _issuer(
        session,
        admin,
        IssuerVerificationStatus.SYNTHETIC,
        f"ISSUER-{campaign.id.hex[:8]}",
        settings,
    )
    await billing_invoices.issue_invoice(
        session,
        invoice_id=invoice.id,
        issuer_profile_id=issuer.id,
        actor_user_id=admin.id,
        settings=settings,
    )
    return invoice


async def correct(session, *, invoice, admin, reference, amount, credit=False):
    """An itemised debit (an extra charge) or credit note on the issued invoice."""
    from app.models.billing import InvoiceCorrectionType

    return await billing_settlements.record_invoice_correction(
        session,
        invoice_id=invoice.id,
        actor_user_id=admin.id,
        correction_reference=reference,
        correction_type=(
            InvoiceCorrectionType.CREDIT_NOTE if credit else InvoiceCorrectionType.DEBIT_NOTE
        ),
        net_amount=amount,
        tax_amount="0.00",
        reason=f"synthetic {reference}",
    )


HALF_QUOTE = [{"code": "MEDIA", "description": "Media", "kind": "media", "amount": "500.00"}]


async def raised_budget_in_production(session, *, campaign, admin, owner, organization, settings):
    """A 500 agreed total under the advertiser's larger budget, so extra charges have headroom."""
    budget_before = (await session.get(Campaign, campaign.id)).budget_amount
    terms = await accepted_terms(
        session, campaign=campaign, admin=admin, owner=owner, line_items=HALF_QUOTE
    )
    # D104: acceptance never shrinks a budget set above the agreed total.
    assert (await session.get(Campaign, campaign.id)).budget_amount == budget_before
    invoice = await in_production(
        session,
        campaign=campaign,
        terms=terms,
        organization=organization,
        admin=admin,
        owner=owner,
        settings=settings,
    )
    return terms, invoice


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


def test_extra_charge_alert_pause_credit_and_audited_resume_converge(
    db_sessionmaker, settings
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
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            within = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            assert within.state == "within_budget"
            await correct(
                session, invoice=invoice, admin=admin, reference="EXTRA-350", amount="350.00"
            )
            alert = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            assert retry.id == alert.id
            assert alert.state == "alert_threshold"
            assert alert.billing_fact_source == "production_obligation"
            assert alert.billing_spend_amount == Decimal("850.00")
            assert alert.policy_revision == "D92"
            assert alert.alert_applied is True
            assert alert.pause_applied is False

            await correct(
                session, invoice=invoice, admin=admin, reference="EXTRA-150.01", amount="150.01"
            )
            paused = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            assert paused.state == "pause_threshold"
            assert paused.pause_applied is True
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
            )

            await correct(
                session,
                invoice=invoice,
                admin=admin,
                reference="CREDIT-500.01",
                amount="500.01",
                credit=True,
            )
            below = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            assert below.state == "within_budget"
            assert below.billing_spend_amount == Decimal("500.00")
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
                reason="confirmed credit note restored headroom",
            )
            same_resume = await resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason="confirmed credit note restored headroom",
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
            # The credit restores the exact pre-charge facts, so it replays the first evaluation.
            assert below.id == within.id
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 3
            )
            budget_notices = (
                NotificationType.BUDGET_ALERT.value,
                NotificationType.BUDGET_URGENT_ALERT.value,
                NotificationType.CAMPAIGN_BUDGET_PAUSED.value,
                NotificationType.CAMPAIGN_BUDGET_RESUMED.value,
            )
            # The active admin also receives the alert and pause in the app (client answer #3).
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key.in_(budget_notices))
                )
                == 8
            )

            await correct(
                session, invoice=invoice, admin=admin, reference="EXTRA-AGAIN", amount="500.01"
            )
            post_resume_breach = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            post_resume_retry = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
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
    db_sessionmaker, monkeypatch, settings
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
            patch.setattr(billing_budget, "database_clock", fixed_clock)
            patch.setattr(BudgetCampaignTransition, "__init__", transition_init)
            return await resume_campaign_after_budget_pause(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                reason=evaluation_reason,
            )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await correct(
                session, invoice=invoice, admin=admin, reference="EPOCH-1", amount="500.01"
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await correct(
                session,
                invoice=invoice,
                admin=admin,
                reference="EPOCH-1-CREDIT",
                amount="500.01",
                credit=True,
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

            await correct(
                session, invoice=invoice, admin=admin, reference="EPOCH-2", amount="500.01"
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=policy(),
                synthetic_test_authority=True,
            )
            await correct(
                session,
                invoice=invoice,
                admin=admin,
                reference="EPOCH-2-CREDIT",
                amount="500.01",
                credit=True,
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

            await correct(
                session, invoice=invoice, admin=admin, reference="EPOCH-3", amount="500.01"
            )

            async def later_clock(_session):
                return later_pause_time

            with monkeypatch.context() as patch:
                patch.setattr(billing_budget, "database_clock", later_clock)
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
            assert billing_common._stored_aware_utc(
                latest_pause_transition.created_at
            ) > billing_common._stored_aware_utc(second_resume.created_at)
            assert blocked_after.state == "pause_threshold"
            await session.commit()

        async with db_sessionmaker() as session:
            blocked_retry = await evaluate_campaign_budget_policy(session, campaign_id=campaign.id)
            assert blocked_retry.id == blocked_after.id
            with pytest.raises(AppError) as unauthorized:
                await resume_campaign_after_budget_pause(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    reason="spend above the budget cannot authorize resume",
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
                == 0
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


def test_postgres_resume_overlap_rechecks_refill_without_opening_a_new_epoch(
    postgis_db_sessionmaker, monkeypatch, settings
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
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await correct(
                session, invoice=invoice, admin=admin, reference="RACE-1", amount="500.01"
            )
            await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            await correct(
                session,
                invoice=invoice,
                admin=admin,
                reference="RACE-1-CREDIT",
                amount="500.01",
                credit=True,
            )
            resume_evaluation = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
            )
            # A different breach from the first pause, so the evaluation facts are new.
            await correct(
                session, invoice=invoice, admin=admin, reference="RACE-REFILL", amount="500.02"
            )
            await session.commit()

        original_lock = billing_budget.acquire_campaign_terms_lock
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

        monkeypatch.setattr(billing_budget, "acquire_campaign_terms_lock", controlled_lock)

        async def resume() -> None:
            async with postgis_db_sessionmaker() as session:
                # The refill invalidates earlier headroom before resume acquires its lock.
                with pytest.raises(AppError) as denied:
                    await resume_campaign_after_budget_pause(
                        session,
                        campaign_id=campaign.id,
                        actor_user_id=admin.id,
                        reason="serialized resume race",
                    )
                assert denied.value.code == "BUDGET_RESUME_NOT_AUTHORIZED"
                await session.rollback()

        async def evaluate() -> UUID:
            async with postgis_db_sessionmaker() as session:
                evaluation = await evaluate_campaign_budget_policy(
                    session,
                    campaign_id=campaign.id,
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
            )
            assert retry.id == post_resume_evaluation_id
            assert retry.state == "pause_threshold"
            assert retry.pause_applied is False
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetPolicyEvaluation)) == 3
            )
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
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
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == NotificationType.CAMPAIGN_BUDGET_PAUSED.value)
                )
                == 3
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == NotificationType.CAMPAIGN_BUDGET_RESUMED.value)
                )
                == 0
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


def test_concurrent_extra_charge_and_budget_worker_converge_to_one_pause(
    postgis_db_sessionmaker, settings
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
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await session.commit()
            return invoice

    async def scenario():
        invoice = await prepare()

        async def allocate():
            async with postgis_db_sessionmaker() as session:
                await correct(
                    session, invoice=invoice, admin=admin, reference="RACE-EXTRA", amount="500.01"
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
    db_sessionmaker, settings
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
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await correct(
                session, invoice=invoice, admin=admin, reference="URGENT-460", amount="460.00"
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


def test_decision_identity_distinguishes_new_pause_eligibility() -> None:
    campaign = Campaign(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        budget_amount=Decimal("1000.00"),
        daily_budget_amount=None,
        currency="NGN",
        status=CampaignStatus.APPROVED.value,
    )
    context = BudgetPolicyContext(
        campaign_id=campaign.id,
        currency="NGN",
        configured_budget_amount=Decimal("1000.00"),
        total_billing_spend_amount=Decimal("850.00"),
    )
    decision = asyncio.run(policy().evaluate(context))
    assert decision.urgent_threshold_amount is None
    key = billing_budget._budget_evaluation_key(
        campaign,
        evaluation_epoch_id=None,
        decision=decision,
        billing_fact_source="confirmed_funding",
        funding_fingerprint="a" * 64,
    )
    assert len(key) == 64
    campaign.status = CampaignStatus.SCHEDULED.value
    assert (
        billing_budget._budget_evaluation_key(
            campaign,
            evaluation_epoch_id=None,
            decision=decision,
            billing_fact_source="confirmed_funding",
            funding_fingerprint="a" * 64,
        )
        != key
    )


def test_three_level_thresholds_are_ordered_without_cent_rounding_collapse() -> None:
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
    # Percentage thresholds need four decimals for valid budgets as small as a cent.
    context = BudgetPolicyContext(
        campaign_id=UUID("00000000-0000-4000-8000-000000000002"),
        currency="NGN",
        configured_budget_amount=Decimal("0.05"),
        total_billing_spend_amount=Decimal("0.05"),
    )
    decision = asyncio.run(three_level_policy().evaluate(context))
    billing_budget._validate_budget_decision(
        decision, synthetic_test_authority=True, agreed_total=None
    )
    assert decision.alert_threshold_amount == Decimal("0.0400")
    assert decision.urgent_threshold_amount == Decimal("0.0475")
    assert decision.pause_threshold_amount == Decimal("0.0500")


def test_fixed_client_rule_ignores_obsolete_deployment_knobs(monkeypatch) -> None:
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
    Settings(_env_file=None)
    adapter = build_budget_policy_adapter()
    assert isinstance(adapter, FixedBudgetPolicyAdapter)
    assert adapter.urgent_ratio == Decimal("0.95")

    def decide(spend: str):
        context = BudgetPolicyContext(
            campaign_id=UUID("00000000-0000-4000-8000-000000000003"),
            currency="NGN",
            configured_budget_amount=Decimal("1000.00"),
            total_billing_spend_amount=Decimal(spend),
        )
        return asyncio.run(adapter.evaluate(context))

    assert decide("850.00").state == "alert_threshold"
    assert decide("950.00").state == "urgent_threshold"
    # D104: spend equal to the budget is within it; only spend above it pauses.
    assert decide("1000.00").state == "urgent_threshold"
    paused = decide("1000.01")
    assert paused.state == "pause_threshold" and paused.should_pause is True

    for name, value in (("BUDGET_URGENT_RATIO", "0.80"), ("BUDGET_URGENT_RATIO", "")):
        monkeypatch.setenv(name, value)
        Settings(_env_file=None)
        assert build_budget_policy_adapter().urgent_ratio == Decimal("0.95")


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


def test_all_fixed_lines_count_once_in_funding_and_never_warn_within_agreed_total(
    db_sessionmaker,
):
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
                    # D104: staged payments up to the agreed total never warn or pause.
                    ("860.00", "860.00", "within_budget"),
                    ("161.25", "1021.25", "within_budget"),
                    ("53.75", "1075.00", "within_budget"),
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
            assert not result.pause_applied and not result.alert_applied
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


def test_production_obligation_raises_a_media_budget_and_only_extra_charges_pause(
    db_sessionmaker, settings
):
    admin = create_test_user(db_sessionmaker, email="fixed-prod-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="fixed-prod-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    # The advertiser entered a media-only budget below the VAT-inclusive quote.
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        campaign_status=CampaignStatus.ACTIVE,
        budget_amount="1000.00",
        daily_budget_amount="100.00",
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
            row = await session.get(Campaign, campaign.id)
            # D104: acceptance raises the budget to the agreed total; the daily budget stays.
            assert (row.budget_amount, row.daily_budget_amount) == (
                Decimal("1075.00"),
                Decimal("100.00"),
            )
            invoice = await in_production(
                session,
                campaign=campaign,
                terms=terms,
                organization=organization,
                admin=admin,
                owner=owner,
                settings=settings,
            )
            # The full accepted obligation already includes fixed charges and VAT.
            assert await billing_budget._campaign_billing_spend(
                session, campaign_id=campaign.id
            ) == (Decimal("1075.00"), "production_obligation")
            result = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            # The whole obligation lands on the production day; the daily budget never pauses.
            assert (result.state, result.budget_basis) == ("within_budget", "total")
            assert result.billing_spend_amount == Decimal("1075.00")
            await correct(
                session,
                invoice=invoice,
                admin=admin,
                reference="FIXED-CREDIT",
                amount="107.50",
                credit=True,
            )
            # 1075 - 107.50, without mutating the accepted quote.
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
            assert corrected.state == "within_budget"
            assert corrected.evaluation_key != result.evaluation_key
            assert retry.id == corrected.id
            # An extra charge beyond a budget equal to the agreed total pauses at once.
            await correct(
                session, invoice=invoice, admin=admin, reference="FIXED-EXTRA", amount="200.00"
            )
            extra = await evaluate_campaign_budget_policy(
                session,
                campaign_id=campaign.id,
                adapter=fixed_lines_policy(),
                synthetic_test_authority=True,
            )
            assert extra.billing_spend_amount == Decimal("1167.50")
            assert extra.state == "pause_threshold" and extra.pause_applied is True
            assert terms.line_items == frozen
            assert terms.gross_amount == Decimal("1075.00")

    asyncio.run(scenario())
