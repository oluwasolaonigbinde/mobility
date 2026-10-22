import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select

from app.models.billing import (
    AcceptanceMethod,
    BudgetCampaignTransition,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import UserRole
from app.services.billing import budget as billing_budget
from app.services.billing import common as billing_common
from app.services.billing import invoices as billing_invoices
from app.services.billing import settlements as billing_settlements
from app.services.billing.budget import (
    enforce_campaign_budget,
)
from app.services.billing.quotes import (
    accept_quotation_revision,
    record_quotation_revision,
    request_custom_quote,
)
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    record_payment_receipt,
    reverse_payment_receipt,
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
    await confirm_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=admin.id,
        expected_amount=amount,
        expected_currency="NGN",
    )
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
                await enforce_campaign_budget(
                    session,
                    campaign_id=campaign.id,
                )
                await session.commit()

        await asyncio.wait_for(asyncio.gather(allocate(), evaluate()), timeout=10)
        async with postgis_db_sessionmaker() as session:
            final = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
            )
            await session.commit()
            assert final.state == "pause_threshold"
            assert (await session.get(Campaign, campaign.id)).status == CampaignStatus.PAUSED
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 1
            )

    asyncio.run(scenario())


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
                result = await enforce_campaign_budget(
                    session,
                    campaign_id=campaign.id,
                )
                retry = await enforce_campaign_budget(
                    session,
                    campaign_id=campaign.id,
                )
                assert result.state == retry.state == state
                assert result.billing_spend_amount == Decimal(spend)
            assert not result.pause_applied and not result.alert_applied
            for receipt in receipts:
                await reverse_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    reason="synthetic reversal",
                )
            below = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
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
            result = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
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
            corrected = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
            )
            retry = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
            )
            assert corrected.billing_spend_amount == Decimal("967.50")
            assert corrected.state == retry.state == "within_budget"
            assert corrected.evaluation_key != result.evaluation_key
            assert retry.id == corrected.id
            # An extra charge beyond a budget equal to the agreed total pauses at once.
            await correct(
                session, invoice=invoice, admin=admin, reference="FIXED-EXTRA", amount="200.00"
            )
            extra = await enforce_campaign_budget(
                session,
                campaign_id=campaign.id,
            )
            assert extra.billing_spend_amount == Decimal("1167.50")
            assert extra.state == "pause_threshold" and extra.pause_applied is True
            assert terms.line_items == frozen
            assert terms.gross_amount == Decimal("1075.00")

    asyncio.run(scenario())
