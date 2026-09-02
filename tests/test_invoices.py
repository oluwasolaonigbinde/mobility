import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import IssuerVerificationStatus, ReceiptMethod
from app.models.organization import AdvertiserOrganization
from app.models.user import UserRole
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
