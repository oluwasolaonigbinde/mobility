import asyncio
from datetime import UTC, datetime, timedelta

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
from app.models.user import UserRole
from app.services import billing
from app.services.billing import (
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
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="20.00",
                tax_amount="0.00",
                reason="approved scope reduction",
            )
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


def test_refund_window_is_exact_and_waiver_acceptance_alone_does_not_close_it(
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
                wording_version="refund-v1",
                accepted_wording="I accept the expedited refund effect if production starts.",
            )
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
            with pytest.raises(AppError) as closed:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms.id,
                    receipt_id=allocation.receipt_id,
                    actor_user_id=admin.id,
                    amount="1.00",
                    settlement_provider="bank",
                    external_reference="REFUND-AT-BOUNDARY",
                    reason="too late",
                )
            assert closed.value.code == "REFUND_WINDOW_CLOSED"
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
                wording_version="refund-v1",
                accepted_wording="I accept the expedited refund effect if production starts.",
            )
            production = await record_production_start(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver.id,
            )
            await reverse_payment_receipt(
                session,
                receipt_id=allocation.receipt_id,
                actor_user_id=admin.id,
                reason="post-start correction",
            )

            async def after_start(_session):
                return production.started_at + timedelta(microseconds=1)

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
            assert closed.value.code == "REFUND_WINDOW_CLOSED"

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
