"""REQ-314: cancellation cash basis (F1), credit-note floor (F2), server VAT (F3), budget (N3)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import auth_headers, create_test_user
from invoice_helpers import issue_test_invoice
from sqlalchemy import select
from test_billing_corrections import _cancel_for_refund, _fixture
from test_financial_authority import _funded_terms
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import Invoice, InvoiceCorrection, InvoiceCorrectionType, ReceiptMethod
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import UserRole
from app.services.billing import receipts as billing_receipts
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    record_payment_receipt,
    reverse_payment_receipt,
)
from app.services.billing.settlements import record_invoice_correction, record_refund_settlement

PASSWORD = "CorrectHorse123!"


async def _invoice(session, terms):
    return await session.scalar(select(Invoice).where(Invoice.commercial_terms_id == terms.id))


async def _pay(session, *, organization, admin, terms, reference, amount, observed_at):
    receipt = await record_payment_receipt(
        session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        method=ReceiptMethod.MANUAL_TRANSFER,
        provider="bank-transfer",
        external_transaction_id=reference,
        amount=amount,
        currency="NGN",
        payer_name="Advertiser",
        evidence_reference=f"{reference}-EVIDENCE",
        observed_at=observed_at,
    )
    await confirm_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=admin.id,
        expected_amount=amount,
        expected_currency="NGN",
    )
    return await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=terms.id,
        actor_user_id=admin.id,
        amount=amount,
    )


# --- F1 ---------------------------------------------------------------------


def test_f1_reverse_then_cancel_records_no_cash_refund(db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "f1-reverse-first")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="F1-REVERSE-FIRST",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="transfer returned before cancellation",
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=allocation.allocated_at + timedelta(hours=1),
                monkeypatch=monkeypatch,
                reason="cancel after the only receipt was reversed",
            )
            assert cancellation.disposition == "cash_refund_not_due"
            assert cancellation.refundable_amount == Decimal("0.00")
            with pytest.raises(AppError) as refused:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms.id,
                    receipt_id=allocation.receipt_id,
                    actor_user_id=admin.id,
                    amount="100.00",
                    settlement_provider="bank",
                    external_reference="F1-REVERSE-FIRST-REFUND",
                    reason="must not refund reversed cash",
                )
            assert refused.value.code == "REFUND_CANCELLATION_NOT_DUE"

    asyncio.run(scenario())


def test_f1_refund_window_starts_at_the_replacement_receipt(db_sessionmaker, monkeypatch):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "f1-replacement")

    async def scenario():
        async with db_sessionmaker() as session:
            terms, first, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="F1-REPLACEMENT",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=first.receipt_id,
                actor_user_id=admin.id,
                reason="first transfer bounced",
            )
            replaced_at = first.allocated_at + timedelta(hours=10)

            async def replacement_clock(_session):
                return replaced_at

            monkeypatch.setattr(billing_receipts, "database_clock", replacement_clock)
            replacement = await _pay(
                session,
                organization=organization,
                admin=admin,
                terms=terms,
                reference="F1-REPLACEMENT-2",
                amount="100.00",
                observed_at=replaced_at,
            )
            assert replacement.allocated_at == replaced_at
            # 25 h after the bounced receipt, 15 h after the replacement.
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                admin=admin,
                cutoff=first.allocated_at + timedelta(hours=25),
                monkeypatch=monkeypatch,
                reason="cancel inside the replacement's window",
            )
            assert cancellation.disposition == "cash_refund_due"
            assert cancellation.funding_authorized_at == replaced_at
            assert cancellation.refund_eligibility_ends_at == replaced_at + timedelta(hours=24)
            # Only the active replacement cash, not the bounced receipt as well.
            assert cancellation.refundable_amount == Decimal("100.00")

    asyncio.run(scenario())


# --- F2 / F3 ----------------------------------------------------------------


def test_f2_credit_note_cannot_take_the_invoice_below_funded_cash(db_sessionmaker, settings):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "f2-floor")

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="F2-FLOOR",
                issued=True,
            )
            invoice = await _invoice(session, terms)
            await _pay(
                session,
                organization=organization,
                admin=admin,
                terms=terms,
                reference="F2-FLOOR-PAY",
                amount="60.00",
                observed_at=datetime.now(UTC),
            )
            base = dict(invoice_id=invoice.id, actor_user_id=admin.id, reason="scope change")
            with pytest.raises(AppError) as below:
                await record_invoice_correction(
                    session,
                    correction_reference="f2-floor-credit-41",
                    correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                    net_amount="40.01",
                    **base,
                )
            assert below.value.code == "INVOICE_CREDIT_BELOW_FUNDED"
            assert below.value.status_code == 409
            # Exactly down to the funded amount is allowed.
            credit = await record_invoice_correction(
                session,
                correction_reference="f2-floor-credit-40",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="40.00",
                **base,
            )
            assert credit.gross_amount == Decimal("40.00")
            # Debit notes are never limited by funding.
            debit = await record_invoice_correction(
                session,
                correction_reference="f2-floor-debit",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="500.00",
                **base,
            )
            assert debit.gross_amount == Decimal("500.00")

    asyncio.run(scenario())


def test_f3_correction_vat_is_derived_from_the_running_total(db_sessionmaker):
    from app.services.billing.common import vat_half_up

    admin, owner, _organization, campaign = _fixture(db_sessionmaker, "f3-vat")

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="F3-VAT",
                amount="1000.00",
                tax_rate="0.075",
                issued=True,
            )
            invoice = await _invoice(session, terms)
            assert (invoice.net_amount, invoice.tax_amount) == (
                Decimal("1000.00"),
                Decimal("75.00"),
            )
            base = dict(invoice_id=invoice.id, actor_user_id=admin.id, reason="scope change")
            # 666.67 x 7.5% = 50.00025 -> 50.00, so this credit carries 25.00 VAT.
            credit = await record_invoice_correction(
                session,
                correction_reference="f3-vat-credit",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="333.33",
                **base,
            )
            assert (credit.net_amount, credit.tax_amount, credit.gross_amount) == (
                Decimal("333.33"),
                Decimal("25.00"),
                Decimal("358.33"),
            )
            # 666.73 x 7.5% = 50.00475 -> 50.00: a debit too small to move the VAT line.
            small = await record_invoice_correction(
                session,
                correction_reference="f3-vat-debit-small",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="0.06",
                **base,
            )
            assert small.tax_amount == Decimal("0.00")
            # 666.74 x 7.5% = 50.0055 -> 50.01 (half-up).
            tipping = await record_invoice_correction(
                session,
                correction_reference="f3-vat-debit-tip",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="0.01",
                **base,
            )
            assert tipping.tax_amount == Decimal("0.01")
            rows = list(
                await session.scalars(
                    select(InvoiceCorrection).where(InvoiceCorrection.invoice_id == invoice.id)
                )
            )
            sign = {InvoiceCorrectionType.CREDIT_NOTE: -1, InvoiceCorrectionType.DEBIT_NOTE: 1}
            net = invoice.net_amount + sum(sign[r.correction_type] * r.net_amount for r in rows)
            tax = invoice.tax_amount + sum(sign[r.correction_type] * r.tax_amount for r in rows)
            # The corrected VAT line is always exactly rate x corrected net.
            assert tax == vat_half_up(net, invoice.tax_rate) == Decimal("50.01")
            # Exact replay returns the same row even though the running total moved.
            replay = await record_invoice_correction(
                session,
                correction_reference="f3-vat-credit",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="333.33",
                **base,
            )
            assert replay.id == credit.id

    asyncio.run(scenario())


def test_f3_inconsistent_prior_vat_fails_closed(db_sessionmaker):
    admin, owner, _organization, campaign = _fixture(db_sessionmaker, "f3-legacy")

    async def scenario():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="F3-LEGACY",
                amount="1000.00",
                tax_rate="0.075",
                issued=True,
            )
            invoice = await _invoice(session, terms)
            # A row written before REQ-314 with hand-entered VAT far above the rule.
            session.add(
                InvoiceCorrection(
                    invoice_id=invoice.id,
                    sequence_number=1,
                    correction_number=f"COR-{invoice.invoice_number}-001",
                    correction_reference="f3-legacy-old",
                    request_fingerprint="0" * 64,
                    correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                    currency="NGN",
                    net_amount=Decimal("10.00"),
                    tax_amount=Decimal("50.00"),
                    gross_amount=Decimal("60.00"),
                    reason="legacy hand-entered VAT",
                    created_by_user_id=admin.id,
                    created_at=datetime.now(UTC),
                )
            )
            await session.flush()
            with pytest.raises(AppError) as caught:
                await record_invoice_correction(
                    session,
                    invoice_id=invoice.id,
                    actor_user_id=admin.id,
                    correction_reference="f3-legacy-debit",
                    correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                    net_amount="1.00",
                    reason="would need negative VAT",
                )
            assert caught.value.code == "INVOICE_CORRECTION_VAT_INCONSISTENT"
            assert caught.value.status_code == 409

    asyncio.run(scenario())


def test_f3_correction_api_takes_net_only(db_client, db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="f3-api-admin@example.com", password=PASSWORD)
    _a, owner, _organization, campaign = _fixture(db_sessionmaker, "f3-api")

    async def setup():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="F3-API",
                amount="200.00",
                tax_rate="0.075",
            )
            invoice = await issue_test_invoice(session, terms=terms, admin=admin)
            await session.commit()
            return invoice.id

    invoice_id = asyncio.run(setup())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    path = f"/api/v1/admin/invoices/{invoice_id}/corrections"
    body = {
        "correction_reference": "f3-api-credit",
        "correction_type": "credit_note",
        "net_amount": "100.00",
        "reason": "scope reduction",
    }
    stale = db_client.post(path, json={**body, "tax_amount": "7.50"}, headers=headers)
    assert stale.status_code == 422, stale.text
    created = db_client.post(path, json=body, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["tax_amount"] == "7.50"
    assert created.json()["gross_amount"] == "107.50"


def test_vat_half_up_rounds_half_kobo_up():
    from app.services.billing.common import vat_half_up

    assert vat_half_up(Decimal("0.10"), Decimal("0.075")) == Decimal("0.01")
    assert vat_half_up(Decimal("0.06"), Decimal("0.075")) == Decimal("0.00")
    assert vat_half_up(Decimal("666.74"), Decimal("0.075")) == Decimal("50.01")


# --- N3 ---------------------------------------------------------------------


def test_n3_draft_budget_cannot_drop_below_the_accepted_total(db_client, db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="n3-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="n3-owner@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    from conftest import create_test_campaign, create_test_organization

    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=owner.id
    )
    other = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="N3 no terms",
    )

    async def setup():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="N3-TERMS",
                amount="1000.00",
                tax_rate="0.075",
            )
            row = await session.get(Campaign, campaign.id)
            row.status = CampaignStatus.DRAFT.value
            await session.commit()
            return terms.gross_amount

    gross = asyncio.run(setup())
    assert gross == Decimal("1075.00")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    path = f"/api/v1/advertiser/campaigns/{campaign.id}"

    below = db_client.patch(path, json={"budget_amount": "1074.99"}, headers=headers)
    assert below.status_code == 409, below.text
    assert below.json()["error"]["code"] == "CAMPAIGN_BUDGET_BELOW_ACCEPTED_TOTAL"
    cleared = db_client.patch(path, json={"budget_amount": None}, headers=headers)
    assert cleared.status_code == 409, cleared.text
    assert cleared.json()["error"]["code"] == "CAMPAIGN_BUDGET_BELOW_ACCEPTED_TOTAL"
    equal = db_client.patch(path, json={"budget_amount": "1075.00"}, headers=headers)
    assert equal.status_code == 200, equal.text
    assert equal.json()["budget_amount"] == "1075.00"
    # Without accepted terms the draft budget stays free.
    free = db_client.patch(
        f"/api/v1/advertiser/campaigns/{other.id}", json={"budget_amount": "1.00"}, headers=headers
    )
    assert free.status_code == 200, free.text


def test_n3_budget_update_takes_the_terms_lock_before_the_campaign_row(
    db_sessionmaker, monkeypatch
):
    from app.schemas.campaigns import CampaignUpdate
    from app.services import campaigns as campaign_service

    owner = create_test_user(
        db_sessionmaker, email="n3-order@example.com", role=UserRole.ADVERTISER
    )
    from conftest import create_test_campaign, create_test_organization

    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=owner.id
    )
    order = []
    real_lock = campaign_service.acquire_campaign_terms_lock

    async def lock(session, campaign_id):
        order.append("terms")
        await real_lock(session, campaign_id)

    monkeypatch.setattr(campaign_service, "acquire_campaign_terms_lock", lock)
    real_execute = None

    async def scenario():
        nonlocal real_execute
        async with db_sessionmaker() as session:
            real_scalar = session.scalar

            async def scalar(statement, *args, **kwargs):
                descriptions = getattr(statement, "column_descriptions", None) or [{}]
                if (
                    getattr(statement, "_for_update_arg", None) is not None
                    and descriptions[0].get("entity") is Campaign
                ):
                    order.append("campaign_row")
                return await real_scalar(statement, *args, **kwargs)

            session.scalar = scalar
            await campaign_service.update_advertiser_campaign(
                session,
                user_id=owner.id,
                campaign_id=campaign.id,
                payload=CampaignUpdate(budget_amount=Decimal("5.00")),
            )

    asyncio.run(scenario())
    assert order[:2] == ["terms", "campaign_row"], order
