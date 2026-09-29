import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from pydantic import ValidationError
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import (
    InvoiceIssuerProfile,
    IssuerVerificationStatus,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.organization import AdvertiserOrganization
from app.models.user import UserRole
from app.schemas.billing import IssuerProfileCreate
from app.services import billing as billing_service
from app.services.billing import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    create_invoice_draft,
    invoice_payment_status,
    issue_invoice,
    reconcile_payment_receipt,
    record_invoice_issuer_profile,
    record_payment_receipt,
    record_quotation_revision,
    request_custom_quote,
)


def _fixture(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="invoice-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="invoice-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=admin.id
    )
    return admin, owner, organization, campaign


async def _issuer(
    session, admin, verification_status, reference, settings, *, numbering_prefix="CV"
):
    return await record_invoice_issuer_profile(
        session,
        actor_user_id=admin.id,
        legal_name="Terrax Media",
        tax_identification_number="TEST-TIN-ONLY",
        registered_address="Test fixture address, Abuja",
        country_code="NG",
        invoice_wording="VAT-inclusive test fixture invoice",
        numbering_prefix=numbering_prefix,
        verification_status=verification_status,
        external_input_reference=reference,
        settings=settings,
    )


def test_vat_invoice_issues_from_frozen_terms_and_verified_issuer_facts(
    db_sessionmaker, settings
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="INV-Q1",
                amount="100000.00",
                tax_rate="0.075",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            assert draft.customer_snapshot["name"] == organization.name
            assert draft.net_amount == Decimal("100000.00")
            assert draft.tax_rate == Decimal("0.075")
            assert draft.tax_amount == Decimal("7500.00")
            assert draft.gross_amount == Decimal("107500.00")
            with pytest.raises(AppError) as untrusted_verified:
                await _issuer(
                    session,
                    admin,
                    IssuerVerificationStatus.VERIFIED,
                    "UNREGISTERED-Q28",
                    settings,
                )
            assert untrusted_verified.value.code == "VERIFIED_ISSUER_GATE_REQUIRED"
            synthetic = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-Q28-TEST",
                settings,
            )
            production_settings = settings.model_copy(update={"environment": "production"})
            with pytest.raises(AppError) as blocked:
                await issue_invoice(
                    session,
                    invoice_id=draft.id,
                    issuer_profile_id=synthetic.id,
                    actor_user_id=admin.id,
                    settings=production_settings,
                )
            assert blocked.value.code == "VERIFIED_ISSUER_FACTS_REQUIRED"
            current_organization = await session.get(AdvertiserOrganization, organization.id)
            assert current_organization is not None
            current_organization.name = "Current bill-to name"
            await session.flush()
            issued = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=synthetic.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            assert issued.invoice_number is not None
            issued_at = issued.issued_at
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=UTC)
            assert issued.invoice_number.startswith(
                f"TEST-CV-{issued_at.astimezone(billing_service.LAGOS_TZ).year}-000001"
            )
            assert issued.issuer_snapshot["legal_name"] == "Terrax Media"
            assert issued.issuer_snapshot["synthetic_test_authority"] is True
            assert issued.customer_snapshot["name"] == "Current bill-to name"
            assert issued.line_items == terms.line_items
            assert await invoice_payment_status(session, issued) == ("unpaid", Decimal("0"))

    asyncio.run(scenario())


def test_invoice_sequence_year_uses_lagos_civil_time_and_preserves_retry(
    db_sessionmaker, settings, monkeypatch
) -> None:
    admin, owner, organization, before_boundary_campaign = _fixture(db_sessionmaker)
    at_boundary_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Lagos new-year boundary campaign",
    )
    ordinary_date_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Ordinary Lagos date campaign",
    )
    alternate_prefix_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Alternate invoice prefix campaign",
    )
    clock = {"now": datetime(2026, 12, 31, 22, 59, 59, tzinfo=UTC)}

    async def frozen_database_clock(_session):
        return clock["now"]

    monkeypatch.setattr(billing_service, "database_clock", frozen_database_clock)

    async def issue_at(session, *, campaign, reference, issuer, at):
        clock["now"] = at
        terms = await _accepted_terms(
            session,
            campaign=campaign,
            admin=admin,
            owner=owner,
            reference=reference,
            amount="100.00",
        )
        draft = await create_invoice_draft(
            session, commercial_terms_id=terms.id, actor_user_id=admin.id
        )
        return await issue_invoice(
            session,
            invoice_id=draft.id,
            issuer_profile_id=issuer.id,
            actor_user_id=admin.id,
            settings=settings,
        )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            cv_issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-R27-CV",
                settings,
            )
            alt_issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-R27-ALT",
                settings,
                numbering_prefix="ALT",
            )
            before_boundary = await issue_at(
                session,
                campaign=before_boundary_campaign,
                reference="INV-R27-BEFORE",
                issuer=cv_issuer,
                at=datetime(2026, 12, 31, 22, 59, 59, tzinfo=UTC),
            )
            at_boundary = await issue_at(
                session,
                campaign=at_boundary_campaign,
                reference="INV-R27-BOUNDARY",
                issuer=cv_issuer,
                at=datetime(2026, 12, 31, 23, 0, tzinfo=UTC),
            )
            ordinary_date = await issue_at(
                session,
                campaign=ordinary_date_campaign,
                reference="INV-R27-ORDINARY",
                issuer=cv_issuer,
                at=datetime(2027, 6, 1, 12, 0, tzinfo=UTC),
            )
            alternate_prefix = await issue_at(
                session,
                campaign=alternate_prefix_campaign,
                reference="INV-R27-ALT",
                issuer=alt_issuer,
                at=datetime(2027, 6, 1, 12, 0, tzinfo=UTC),
            )
            at_boundary_id = at_boundary.id
            at_boundary_number = at_boundary.invoice_number
            at_boundary_issued_at = at_boundary.issued_at
            assert before_boundary.invoice_number == "TEST-CV-2026-000001"
            assert at_boundary_number == "TEST-CV-2027-000001"
            assert ordinary_date.invoice_number == "TEST-CV-2027-000002"
            assert alternate_prefix.invoice_number == "TEST-ALT-2027-000001"
            await session.commit()

        clock["now"] = datetime(2028, 1, 1, tzinfo=UTC)
        async with db_sessionmaker() as retry_session:
            retried = await issue_invoice(
                retry_session,
                invoice_id=at_boundary_id,
                issuer_profile_id=cv_issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            assert retried.invoice_number == at_boundary_number
            persisted_issued_at = retried.issued_at
            if persisted_issued_at.tzinfo is None:
                persisted_issued_at = persisted_issued_at.replace(tzinfo=UTC)
            assert persisted_issued_at.astimezone(UTC) == at_boundary_issued_at

    asyncio.run(scenario())


def test_issuer_provenance_replay_must_be_exact(db_sessionmaker, settings) -> None:
    admin, _, _, _ = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            first = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-Q28-REPLAY",
                settings,
            )
            same = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-Q28-REPLAY",
                settings,
            )
            assert same.id == first.id
            with pytest.raises(AppError) as conflict:
                await record_invoice_issuer_profile(
                    session,
                    actor_user_id=admin.id,
                    legal_name="Different issuer",
                    tax_identification_number="TEST-TIN-ONLY",
                    registered_address="Test fixture address, Abuja",
                    country_code="NG",
                    invoice_wording="VAT-inclusive test fixture invoice",
                    numbering_prefix="CV",
                    verification_status=IssuerVerificationStatus.SYNTHETIC,
                    external_input_reference="SYNTHETIC-Q28-REPLAY",
                    settings=settings,
                )
            assert conflict.value.code == "ISSUER_PROVENANCE_CONFLICT"

    asyncio.run(scenario())


CONTACT_AND_BANK = {
    "company_registration_number": "TEST-RC-ONLY",
    "contact_phone": "TEST-PHONE-ONLY",
    "contact_email": "invoices@example.com",
    "bank_name": "Test Bank",
    "bank_account_name": "Test Account Name",
    "bank_account_number": "TEST-ACCOUNT-ONLY",
}


async def _profile(session, admin, settings, reference, verification_status, **facts):
    return await record_invoice_issuer_profile(
        session,
        actor_user_id=admin.id,
        legal_name="Terrax Media",
        tax_identification_number="TEST-TIN-ONLY",
        registered_address="Test fixture address, Abuja",
        country_code="NG",
        invoice_wording="VAT-inclusive test fixture invoice",
        numbering_prefix="CV",
        verification_status=verification_status,
        external_input_reference=reference,
        settings=settings,
        **facts,
    )


def test_verified_issuer_needs_rc_contact_and_bank_facts_and_the_accountant_gate(
    db_sessionmaker, settings
) -> None:
    admin, _, _, _ = _fixture(db_sessionmaker)
    gated = settings.model_copy(update={"invoice_issuer_external_input_reference": "ACCOUNTANT-OK"})

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            for missing in CONTACT_AND_BANK:
                facts = {**CONTACT_AND_BANK, missing: "   "}
                with pytest.raises(AppError) as incomplete:
                    await _profile(
                        session,
                        admin,
                        gated,
                        "ACCOUNTANT-OK",
                        IssuerVerificationStatus.VERIFIED,
                        **facts,
                    )
                assert incomplete.value.code == "INCOMPLETE_ISSUER_FACTS", missing
            # The accountant's confirmation is the configured reference; blank refuses.
            with pytest.raises(AppError) as ungated:
                await _profile(
                    session,
                    admin,
                    settings,
                    "ACCOUNTANT-OK",
                    IssuerVerificationStatus.VERIFIED,
                    **CONTACT_AND_BANK,
                )
            assert ungated.value.code == "VERIFIED_ISSUER_GATE_REQUIRED"
            verified = await _profile(
                session,
                admin,
                gated,
                "ACCOUNTANT-OK",
                IssuerVerificationStatus.VERIFIED,
                **CONTACT_AND_BANK,
            )
            assert verified.company_registration_number == "TEST-RC-ONLY"
            assert verified.bank_account_number == "TEST-ACCOUNT-ONLY"

            # Synthetic profiles may leave the new facts blank; blanks normalise to None,
            # so a replay sending "" converges with one that omitted the fields.
            synthetic = await _profile(
                session, admin, settings, "SYNTHETIC-BLANK", IssuerVerificationStatus.SYNTHETIC
            )
            assert synthetic.bank_account_number is None
            replay = await _profile(
                session,
                admin,
                settings,
                "SYNTHETIC-BLANK",
                IssuerVerificationStatus.SYNTHETIC,
                bank_account_number="",
            )
            assert replay.id == synthetic.id
            with pytest.raises(AppError) as changed:
                await _profile(
                    session,
                    admin,
                    settings,
                    "SYNTHETIC-BLANK",
                    IssuerVerificationStatus.SYNTHETIC,
                    bank_account_number="TEST-OTHER",
                )
            assert changed.value.code == "ISSUER_PROVENANCE_CONFLICT"

    asyncio.run(scenario())


def test_issuer_profile_request_bounds_the_new_facts() -> None:
    base = {
        "legal_name": "Terrax Media",
        "tax_identification_number": "TEST-TIN-ONLY",
        "registered_address": "Test fixture address, Abuja",
        "country_code": "NG",
        "invoice_wording": "Wording",
        "numbering_prefix": "CV",
        "verification_status": "synthetic",
        "external_input_reference": "SYNTHETIC-BOUNDS",
    }
    assert IssuerProfileCreate(**base, contact_email="").contact_email == ""
    assert IssuerProfileCreate(**base, **CONTACT_AND_BANK).bank_account_number == (
        "TEST-ACCOUNT-ONLY"
    )
    for field, value in (
        ("contact_email", "not-an-email"),
        ("bank_account_number", "1" * 65),
        ("company_registration_number", "R" * 129),
    ):
        with pytest.raises(ValidationError):
            IssuerProfileCreate(**base, **{field: value})


def test_issued_snapshot_carries_contact_and_bank_and_incomplete_verified_is_refused(
    db_sessionmaker, settings
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker)
    gated = settings.model_copy(
        update={
            "invoice_issuer_external_input_reference": "LEGACY-VERIFIED",
            "environment": "production",
        }
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="INV-D42"
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            # A verified row recorded before 0095 (no contact or bank facts) cannot issue.
            legacy = InvoiceIssuerProfile(
                legal_name="Terrax Media",
                tax_identification_number="TEST-TIN-ONLY",
                registered_address="Test fixture address, Abuja",
                country_code="NG",
                invoice_wording="Legacy verified row",
                numbering_prefix="CV",
                verification_status=IssuerVerificationStatus.VERIFIED,
                external_input_reference="LEGACY-VERIFIED",
                recorded_by_user_id=admin.id,
                recorded_at=datetime.now(UTC),
            )
            session.add(legacy)
            await session.flush()
            with pytest.raises(AppError) as refused:
                await issue_invoice(
                    session,
                    invoice_id=draft.id,
                    issuer_profile_id=legacy.id,
                    actor_user_id=admin.id,
                    settings=gated,
                )
            assert refused.value.code == "VERIFIED_ISSUER_FACTS_REQUIRED"

            synthetic = await _profile(
                session,
                admin,
                settings,
                "SYNTHETIC-D42",
                IssuerVerificationStatus.SYNTHETIC,
                **CONTACT_AND_BANK,
            )
            issued = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=synthetic.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            for field, value in CONTACT_AND_BANK.items():
                assert issued.issuer_snapshot[field] == value
            assert issued.gross_amount == terms.gross_amount

    asyncio.run(scenario())


def test_quotation_lines_accept_quantity_and_unit_price_and_campaign_dates(
    db_sessionmaker,
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )

            async def revise(line_items, production_scope=None):
                return await record_quotation_revision(
                    session,
                    quote_request_id=request.id,
                    actor_user_id=admin.id,
                    quote_reference="Q-QTY",
                    currency="NGN",
                    line_items=line_items,
                    production_scope=production_scope or {"vehicle_count": 1},
                    payment_class=PaymentClass.STANDARD_PREPAID,
                    payment_terms={},
                    tax_rate="0.075",
                )

            line = {"code": "MEDIA", "description": "Campaign", "kind": "media"}
            revision = await revise(
                [
                    {**line, "quantity": 3, "unit_amount": "100000.00"},
                    {
                        **line,
                        "code": "DESIGN",
                        "quantity": 2,
                        "unit_amount": "0.50",
                        "amount": "1.00",
                    },
                    {**line, "code": "LEGACY", "amount": "70000.00"},
                ],
                {
                    "vehicle_count": 1,
                    "campaign_start_date": "2026-10-01",
                    "campaign_end_date": "2026-10-31",
                },
            )
            assert revision.line_items[0]["amount"] == "300000.00"
            assert revision.line_items[0]["quantity"] == 3
            assert revision.line_items[0]["unit_amount"] == "100000.00"
            assert revision.line_items[1]["amount"] == "1.00"
            # A line entered without a quantity keeps its earlier canonical shape.
            assert set(revision.line_items[2]) == {
                "code",
                "description",
                "kind",
                "amount",
                "metadata",
            }
            assert revision.net_amount == Decimal("370001.00")
            assert revision.tax_amount == Decimal("27750.08")
            assert revision.gross_amount == Decimal("397751.08")
            assert revision.production_scope["campaign_end_date"] == "2026-10-31"

            for bad in (
                {**line, "quantity": 0, "unit_amount": "1.00"},
                {**line, "quantity": True, "unit_amount": "1.00"},
                {**line, "quantity": "2", "unit_amount": "1.00"},
                {**line, "quantity": 2},
                {**line, "unit_amount": "1.00"},
                {**line, "quantity": 2, "unit_amount": "1.00", "amount": "3.00"},
            ):
                with pytest.raises(AppError) as invalid_line:
                    await revise([bad])
                assert invalid_line.value.code == "INVALID_COMMERCIAL_LINE_ITEM", bad
            for scope in (
                {"vehicle_count": 1, "campaign_start_date": "2026-10-01"},
                {
                    "vehicle_count": 1,
                    "campaign_start_date": "01/10/2026",
                    "campaign_end_date": "2026-10-31",
                },
                {
                    # Python accepts compact ISO dates; the invoice cannot show them.
                    "vehicle_count": 1,
                    "campaign_start_date": "20261001",
                    "campaign_end_date": "2026-10-31",
                },
                {
                    "vehicle_count": 1,
                    "campaign_start_date": "2026-10-31",
                    "campaign_end_date": "2026-10-01",
                },
            ):
                with pytest.raises(AppError) as invalid_scope:
                    await revise([{**line, "amount": "1.00"}], scope)
                assert invalid_scope.value.code == "INVALID_PRODUCTION_SCOPE", scope

    asyncio.run(scenario())


def test_invoice_numbering_is_scope_sequential_and_payment_status_is_allocation_derived(
    db_sessionmaker, settings
) -> None:
    admin, owner, organization, first_campaign = _fixture(db_sessionmaker)
    second_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Invoice campaign two",
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-Q28-SEQUENCE",
                settings,
            )
            first_terms = await _accepted_terms(
                session,
                campaign=first_campaign,
                admin=admin,
                owner=owner,
                reference="INV-Q2",
                amount="100.00",
            )
            second_terms = await _accepted_terms(
                session,
                campaign=second_campaign,
                admin=admin,
                owner=owner,
                reference="INV-Q3",
                amount="100.00",
            )
            first = await issue_invoice(
                session,
                invoice_id=(
                    await create_invoice_draft(
                        session, commercial_terms_id=first_terms.id, actor_user_id=admin.id
                    )
                ).id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            second = await issue_invoice(
                session,
                invoice_id=(
                    await create_invoice_draft(
                        session, commercial_terms_id=second_terms.id, actor_user_id=admin.id
                    )
                ).id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            assert first.invoice_number.endswith("000001")
            assert second.invoice_number.endswith("000002")

            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank-transfer",
                external_transaction_id="INV-PAY-1",
                amount="50.00",
                currency="NGN",
                payer_name="Acme",
                evidence_reference="line-50",
                observed_at=datetime.now(UTC),
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
                commercial_terms_id=first_terms.id,
                actor_user_id=admin.id,
                amount="50.00",
            )
            assert await invoice_payment_status(session, first) == (
                "partially_paid",
                Decimal("50.00"),
            )

    asyncio.run(scenario())
