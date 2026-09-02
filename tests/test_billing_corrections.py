import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from test_financial_authority import _funded_terms
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    InvoiceCorrectionType,
    IssuerVerificationStatus,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import UserRole
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.services import billing, campaign_cancellations
from app.services.billing import (
    EXPEDITED_WAIVER_WORDING,
    EXPEDITED_WAIVER_WORDING_HASH,
    EXPEDITED_WAIVER_WORDING_VERSION,
    accept_quotation_revision,
    adjusted_invoice_obligation,
    allocate_payment_receipt,
    assert_campaign_production_authorized,
    confirm_payment_receipt,
    create_invoice_draft,
    invoice_payment_status,
    issue_invoice,
    reconcile_payment_receipt,
    record_credit_contract_settlement,
    record_expedited_production_waiver,
    record_invoice_correction,
    record_payment_receipt,
    record_prepaid_cash_authorization,
    record_production_start,
    record_quotation_revision,
    record_refund_settlement,
    request_custom_quote,
    reverse_payment_receipt,
)
from app.services.campaign_cancellations import request_campaign_cancellation


def _fixture(db_sessionmaker, suffix: str):
    admin = create_test_user(db_sessionmaker, email=f"correction-admin-{suffix}@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email=f"correction-owner-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    return admin, owner, organization, campaign


async def _cancel_for_refund(
    session,
    *,
    campaign,
    owner,
    cutoff,
    monkeypatch,
    reason: str,
):
    current = await session.get(Campaign, campaign.id)
    current.status = CampaignStatus.ACTIVE.value

    async def fixed_cutoff(_session):
        return cutoff

    monkeypatch.setattr(campaign_cancellations, "database_clock", fixed_cutoff)
    return await request_campaign_cancellation(
        session,
        actor_user_id=owner.id,
        campaign_id=campaign.id,
        payload=CampaignCancellationCreate(client_request_id=uuid4(), reason=reason),
    )


def test_invoice_corrections_are_itemised_append_only_and_bounded(
    db_sessionmaker, settings
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "invoice")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="CORRECTION-INVOICE",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-CORRECTION",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            credit = await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="correction-invoice-credit",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="20.00",
                tax_amount="0.00",
                reason="approved scope reduction",
            )
            assert credit.correction_number.endswith("-001")
            assert str(await adjusted_invoice_obligation(session, invoice.id)) == "80.00"
            assert str(invoice.gross_amount) == "100.00"
            with pytest.raises(AppError) as excessive:
                await record_invoice_correction(
                    session,
                    invoice_id=invoice.id,
                    actor_user_id=admin.id,
                    correction_reference="correction-invoice-excess",
                    correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                    net_amount="81.00",
                    tax_amount="0.00",
                    reason="invalid excess",
                )
            assert excessive.value.code == "INVOICE_CREDIT_EXCEEDS_OBLIGATION"
            await session.commit()

    asyncio.run(scenario())


def test_effective_invoice_obligation_drives_allocation_status_and_production(
    db_sessionmaker, settings, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "projection")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="PROJECTION-INVOICE",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-PROJECTION",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="projection-credit",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="20.00",
                tax_amount="0.00",
                reason="approved scope reduction",
            )
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="PROJECTION-PAYMENT",
                amount="100.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="PROJECTION-EVIDENCE",
                observed_at=datetime.now(UTC),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(
                session, receipt_id=receipt.id, actor_user_id=admin.id
            )
            with pytest.raises(AppError) as overfunding:
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms.id,
                    actor_user_id=admin.id,
                    amount="80.01",
                )
            assert overfunding.value.code == "OBLIGATION_OVERFUNDING"
            allocation = await allocate_payment_receipt(
                session,
                receipt_id=receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="80.00",
            )
            assert await invoice_payment_status(session, invoice) == (
                "paid",
                allocation.amount,
            )
            await record_prepaid_cash_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                max_driver_liability="60.00",
                reason="corrected obligation funded",
            )

            async def at_boundary(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(billing, "database_clock", at_boundary)
            production = await record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id
            )
            assert production.fully_funded_at == allocation.allocated_at
            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="projection-debit",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="10.00",
                tax_amount="0.00",
                reason="approved scope increase",
            )
            with pytest.raises(AppError) as underfunded:
                await assert_campaign_production_authorized(
                    session, campaign_id=campaign.id
                )
            assert underfunded.value.code == "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED"
            await session.commit()

    asyncio.run(scenario())


def test_standard_production_and_later_debit_cannot_reopen_refund_eligibility(
    db_sessionmaker, settings, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "refund-frozen-start")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, first_allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-FROZEN-START",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-REFUND-FROZEN-START",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )

            async def at_standard_boundary(_session):
                return first_allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(billing, "database_clock", at_standard_boundary)
            production = await record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id
            )
            assert production.fully_funded_at == first_allocation.allocated_at

            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="refund-frozen-start-debit",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="50.00",
                tax_amount="0.00",
                reason="later approved scope increase",
            )

            async def after_debit(_session):
                return first_allocation.allocated_at + timedelta(hours=25)

            monkeypatch.setattr(billing, "database_clock", after_debit)
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="REFUND-FROZEN-START-DEBIT",
                amount="50.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="refund frozen start debit",
                observed_at=first_allocation.allocated_at + timedelta(hours=25),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="50.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
            await allocate_payment_receipt(
                session,
                receipt_id=receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="50.00",
            )

            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=first_allocation.allocated_at + timedelta(hours=26),
                monkeypatch=monkeypatch,
                reason="Cancel after standard production started",
            )
            assert cancellation.disposition == "cash_refund_not_due"
            assert cancellation.refundable_amount == 0

    asyncio.run(scenario())


def test_late_refund_booking_uses_frozen_cancellation_and_exact_retry_identity(
    db_sessionmaker, settings, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "refund-frozen-cancel")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-FROZEN-CANCEL",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-REFUND-FROZEN-CANCEL",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=allocation.allocated_at + timedelta(hours=2),
                monkeypatch=monkeypatch,
                reason="Cancel inside the refund window",
            )
            assert cancellation.disposition == "cash_refund_due"
            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="refund-frozen-cancel-debit",
                correction_type=InvoiceCorrectionType.DEBIT_NOTE,
                net_amount="50.00",
                tax_amount="0.00",
                reason="scope increase after cancellation",
            )
            later_receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="REFUND-FROZEN-CANCEL-LATER",
                amount="50.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="post-cancellation debit funding",
                observed_at=allocation.allocated_at + timedelta(hours=25),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=later_receipt.id,
                actor_user_id=admin.id,
                expected_amount="50.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(
                session, receipt_id=later_receipt.id, actor_user_id=admin.id
            )
            await allocate_payment_receipt(
                session,
                receipt_id=later_receipt.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                amount="50.00",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="settle frozen cancellation",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=later_receipt.id,
                actor_user_id=admin.id,
                reason="post-cancellation cash is outside frozen authority",
            )

            async def after_wall_clock_expiry(_session):
                return allocation.allocated_at + timedelta(hours=26)

            monkeypatch.setattr(billing, "database_clock", after_wall_clock_expiry)
            kwargs = {
                "commercial_terms_id": terms.id,
                "receipt_id": allocation.receipt_id,
                "actor_user_id": admin.id,
                "amount": "100.00",
                "settlement_provider": "bank",
                "external_reference": "REFUND-FROZEN-CANCEL-001",
                "reason": "book frozen advertiser refund",
            }
            settlement = await record_refund_settlement(session, **kwargs)
            replay = await record_refund_settlement(session, **kwargs)
            assert replay.id == settlement.id
            assert settlement.cancellation_id == cancellation.id
            assert settlement.eligibility_evaluated_at == cancellation.cutoff_at
            assert settlement.recorded_at > settlement.eligibility_ends_at

            with pytest.raises(AppError) as changed:
                await record_refund_settlement(
                    session, **(kwargs | {"reason": "changed retry evidence"})
                )
            assert changed.value.code == "REFUND_REFERENCE_CONFLICT"

            with pytest.raises(AppError) as aggregate_cap:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms.id,
                    receipt_id=later_receipt.id,
                    actor_user_id=admin.id,
                    amount="1.00",
                    settlement_provider="bank",
                    external_reference="REFUND-FROZEN-CANCEL-OVER-CAP",
                    reason="must not expand frozen cancellation authority",
                )
            assert aggregate_cap.value.code == "REFUND_EXCEEDS_CANCELLATION_AUTHORITY"

    asyncio.run(scenario())


def test_refund_rejects_missing_and_mismatched_cancellation_authority(
    db_sessionmaker, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "refund-authority")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-AUTHORITY",
            )
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="exercise frozen authority validation",
            )
            kwargs = {
                "commercial_terms_id": terms.id,
                "receipt_id": allocation.receipt_id,
                "actor_user_id": admin.id,
                "amount": "1.00",
                "settlement_provider": "bank",
                "external_reference": "REFUND-AUTHORITY-001",
                "reason": "authority validation",
            }
            with pytest.raises(AppError) as missing:
                await record_refund_settlement(session, **kwargs)
            assert missing.value.code == "REFUND_CANCELLATION_REQUIRED"

            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=allocation.allocated_at + timedelta(hours=1),
                monkeypatch=monkeypatch,
                reason="create matching immutable authority",
            )
            cancellation.currency = "USD"
            with pytest.raises(AppError) as mismatched:
                await record_refund_settlement(session, **kwargs)
            assert mismatched.value.code == "REFUND_CANCELLATION_MISMATCH"

    asyncio.run(scenario())


def test_corrected_obligation_reanchors_window_without_rewriting_cash_authority(
    db_sessionmaker, settings, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "refund-projection")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-PROJECTION",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-REFUND-PROJECTION",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await record_invoice_correction(
                session,
                invoice_id=invoice.id,
                actor_user_id=admin.id,
                correction_reference="refund-projection-credit",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="20.00",
                tax_amount="0.00",
                reason="approved scope reduction",
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=allocation.allocated_at + timedelta(hours=23),
                monkeypatch=monkeypatch,
                reason="cancel after approved scope reduction",
            )
            assert cancellation.refundable_amount == allocation.amount
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="advertiser cancellation",
            )

            async def before_boundary(_session):
                return allocation.allocated_at + timedelta(hours=23)

            monkeypatch.setattr(billing, "database_clock", before_boundary)
            settlement = await record_refund_settlement(
                session,
                commercial_terms_id=terms.id,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                amount="100.00",
                settlement_provider="bank",
                external_reference="REFUND-PROJECTION-FULL-CASH",
                reason="refund allocated cash after corrected invoice",
            )
            assert settlement.funding_authorized_at == allocation.allocated_at
            assert settlement.amount == allocation.amount

    asyncio.run(scenario())


def test_frozen_refund_survives_wall_clock_and_waiver_acceptance_alone_does_not_close_it(
    db_sessionmaker, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "refund")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-STANDARD",
            )
            await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version=EXPEDITED_WAIVER_WORDING_VERSION,
                accepted_wording=EXPEDITED_WAIVER_WORDING,
                accepted_wording_hash=EXPEDITED_WAIVER_WORDING_HASH,
            )
            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=allocation.allocated_at + timedelta(hours=23),
                monkeypatch=monkeypatch,
                reason="cancel before the refund boundary",
            )
            assert cancellation.disposition == "cash_refund_due"
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="advertiser cancellation",
            )

            async def before_boundary(_session):
                return allocation.allocated_at + timedelta(hours=23)

            monkeypatch.setattr(billing, "database_clock", before_boundary)
            settlement = await record_refund_settlement(
                session,
                commercial_terms_id=terms.id,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                amount="60.00",
                settlement_provider="bank",
                external_reference="REFUND-001",
                reason="manual refund confirmed",
            )
            assert str(settlement.amount) == "60.00"
            assert settlement.production_start_id is None
            with pytest.raises(AppError) as excessive:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms.id,
                    receipt_id=allocation.receipt_id,
                    actor_user_id=admin.id,
                    amount="41.00",
                    settlement_provider="bank",
                    external_reference="REFUND-EXCESS",
                    reason="exceeds allocated authority",
                )
            assert excessive.value.code == "REFUND_EXCEEDS_CASH_AUTHORITY"

            async def at_boundary(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(billing, "database_clock", at_boundary)
            later = await record_refund_settlement(
                session,
                commercial_terms_id=terms.id,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                amount="1.00",
                settlement_provider="bank",
                external_reference="REFUND-AT-BOUNDARY",
                reason="book frozen entitlement at the old boundary",
            )
            assert later.cancellation_id == cancellation.id
            await session.commit()

    asyncio.run(scenario())


def test_credit_without_cash_records_contract_settlement_not_refund(db_sessionmaker) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "credit")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={"credit_requested": True},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="CREDIT-SETTLEMENT",
                currency="NGN",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Media",
                        "kind": "media",
                        "amount": "100.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                payment_terms={"net_days": 30},
                tax_rate="0",
            )
            terms = await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            settlement = await record_credit_contract_settlement(
                session,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                settlement_provider="contract-ledger",
                external_reference="CREDIT-CLOSE-001",
                reason="credit termination settlement recorded",
            )
            assert str(settlement.amount) == "0.00"
            assert settlement.receipt_id is None
            assert settlement.eligibility_ends_at is None
            await session.commit()

    asyncio.run(scenario())


def test_actual_expedited_start_closes_refund_eligibility(db_sessionmaker, monkeypatch) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "started")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-STARTED",
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
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver.id,
            )

            async def after_start(_session):
                return production.started_at + timedelta(microseconds=1)

            cancellation = await _cancel_for_refund(
                session,
                campaign=campaign,
                owner=owner,
                cutoff=production.started_at + timedelta(microseconds=1),
                monkeypatch=monkeypatch,
                reason="cancel after production started",
            )
            assert cancellation.disposition == "cash_refund_not_due"
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="post-start correction",
            )

            monkeypatch.setattr(billing, "database_clock", after_start)
            with pytest.raises(AppError) as closed:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms.id,
                    receipt_id=allocation.receipt_id,
                    actor_user_id=admin.id,
                    amount="1.00",
                    settlement_provider="bank",
                    external_reference="REFUND-AFTER-START",
                    reason="not eligible",
                )
            assert closed.value.code == "REFUND_CANCELLATION_NOT_DUE"

    asyncio.run(scenario())


def test_concurrent_refunds_cannot_exceed_allocated_cash(postgis_db_sessionmaker) -> None:
    admin, owner, organization, campaign = _fixture(postgis_db_sessionmaker, "refund-race")

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            terms, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="REFUND-RACE",
            )
            current = await session.get(Campaign, campaign.id)
            current.status = CampaignStatus.ACTIVE.value
            cancellation = await request_campaign_cancellation(
                session,
                actor_user_id=owner.id,
                campaign_id=campaign.id,
                payload=CampaignCancellationCreate(
                    client_request_id=uuid4(),
                    reason="authorize concurrent refund proof",
                ),
            )
            assert cancellation.disposition == "cash_refund_due"
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="concurrent refund proof",
            )
            await session.commit()

        async def attempt(reference: str) -> str:
            async with postgis_db_sessionmaker() as session:
                try:
                    await record_refund_settlement(
                        session,
                        commercial_terms_id=terms.id,
                        receipt_id=allocation.receipt_id,
                        actor_user_id=admin.id,
                        amount="60.00",
                        settlement_provider="bank",
                        external_reference=reference,
                        reason="concurrent refund attempt",
                    )
                    await session.commit()
                    return "recorded"
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        outcomes = await asyncio.gather(attempt("REFUND-RACE-A"), attempt("REFUND-RACE-B"))
        assert sorted(outcomes) == ["REFUND_EXCEEDS_CASH_AUTHORITY", "recorded"]

    asyncio.run(scenario())
