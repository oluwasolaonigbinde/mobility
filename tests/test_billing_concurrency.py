import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_receipt_allocations import _accepted_terms

import app.services.billing as billing_service
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import (
    InvoiceCorrection,
    InvoiceCorrectionType,
    IssuerVerificationStatus,
    ReceiptAllocation,
    ReceiptMethod,
)
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import UserRole
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.services.billing import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    create_invoice_draft,
    invoice_payment_status,
    issue_invoice,
    reconcile_payment_receipt,
    record_invoice_correction,
    record_invoice_issuer_profile,
    record_payment_receipt,
    record_refund_settlement,
    reverse_payment_receipt,
)
from app.services.campaign_cancellations import request_campaign_cancellation


async def _parallel(*awaitables):
    return await asyncio.gather(*awaitables)


def test_invoice_credit_and_allocation_overlap_respects_corrected_obligation(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    correction_admin = create_test_user(
        postgis_db_sessionmaker, email="correction-overlap-admin@example.com"
    )
    allocation_admin = create_test_user(
        postgis_db_sessionmaker, email="allocation-overlap-admin@example.com"
    )
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="correction-overlap-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(postgis_db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=correction_admin.id,
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=correction_admin,
                owner=owner,
                reference="CORRECTION-ALLOCATION-OVERLAP",
                amount="100.00",
            )
            issuer = await record_invoice_issuer_profile(
                session,
                actor_user_id=correction_admin.id,
                legal_name="Synthetic overlap issuer",
                tax_identification_number="TEST",
                registered_address="Test",
                country_code="NG",
                invoice_wording="Synthetic",
                numbering_prefix="CAO",
                verification_status=IssuerVerificationStatus.SYNTHETIC,
                external_input_reference="SYNTHETIC-CORRECTION-ALLOCATION-OVERLAP",
                settings=settings,
            )
            draft = await create_invoice_draft(
                session,
                commercial_terms_id=terms.id,
                actor_user_id=correction_admin.id,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=correction_admin.id,
                settings=settings,
            )
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=allocation_admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank",
                external_transaction_id="CORRECTION-ALLOCATION-OVERLAP-RECEIPT",
                amount="100.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="correction-allocation-overlap",
                observed_at=datetime.now(UTC),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=allocation_admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(
                session, receipt_id=receipt.id, actor_user_id=allocation_admin.id
            )
            await session.commit()
            return terms.id, invoice.id, receipt.id

    terms_id, invoice_id, receipt_id = asyncio.run(setup())

    async def overlap():
        correction_at_insert = asyncio.Event()
        release_correction = asyncio.Event()
        allocation_read_obligation = asyncio.Event()
        original_clock = billing_service.database_clock
        original_obligation = billing_service.effective_invoice_obligation
        correction_task = None
        allocation_task = None

        async def controlled_clock(session):
            if asyncio.current_task() is correction_task:
                correction_at_insert.set()
                await release_correction.wait()
            return await original_clock(session)

        async def observed_obligation(session, *, commercial_terms_id):
            obligation = await original_obligation(session, commercial_terms_id=commercial_terms_id)
            if asyncio.current_task() is allocation_task:
                allocation_read_obligation.set()
            return obligation

        monkeypatch.setattr(billing_service, "database_clock", controlled_clock)
        monkeypatch.setattr(billing_service, "effective_invoice_obligation", observed_obligation)

        async def correct():
            async with postgis_db_sessionmaker() as session:
                correction = await record_invoice_correction(
                    session,
                    invoice_id=invoice_id,
                    actor_user_id=correction_admin.id,
                    correction_reference="correction-allocation-overlap-credit",
                    correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                    net_amount="40.00",
                    tax_amount="0.00",
                    reason="approved scope reduction during allocation",
                )
                await session.commit()
                return str(correction.id)

        async def allocate():
            async with postgis_db_sessionmaker() as session:
                try:
                    allocation = await allocate_payment_receipt(
                        session,
                        receipt_id=receipt_id,
                        commercial_terms_id=terms_id,
                        actor_user_id=allocation_admin.id,
                        amount="100.00",
                    )
                    await session.commit()
                    return str(allocation.id)
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        correction_task = asyncio.create_task(correct())
        await asyncio.wait_for(correction_at_insert.wait(), timeout=5)
        allocation_task = asyncio.create_task(allocate())
        try:
            await asyncio.wait_for(allocation_read_obligation.wait(), timeout=0.5)
        except TimeoutError:
            pass
        if allocation_read_obligation.is_set():
            await asyncio.wait_for(allocation_task, timeout=5)
        release_correction.set()
        correction_result, allocation_result = await asyncio.wait_for(
            asyncio.gather(correction_task, allocation_task), timeout=5
        )
        return correction_result, allocation_result

    correction_result, allocation_result = asyncio.run(overlap())
    assert correction_result not in {
        "INVOICE_CORRECTION_REFERENCE_CONFLICT",
        "INVOICE_CREDIT_EXCEEDS_OBLIGATION",
    }
    assert allocation_result == "OBLIGATION_OVERFUNDING"

    async def effect_counts() -> tuple[int, int, int, int]:
        async with postgis_db_sessionmaker() as session:
            correction_count = await session.scalar(
                select(func.count())
                .select_from(InvoiceCorrection)
                .where(InvoiceCorrection.invoice_id == invoice_id)
            )
            allocation_count = await session.scalar(
                select(func.count())
                .select_from(ReceiptAllocation)
                .where(ReceiptAllocation.commercial_terms_id == terms_id)
            )
            correction_audits = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "billing.invoice.corrected")
            )
            allocation_audits = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "billing.receipt.allocated")
            )
            return (
                int(correction_count or 0),
                int(allocation_count or 0),
                int(correction_audits or 0),
                int(allocation_audits or 0),
            )

    assert asyncio.run(effect_counts()) == (1, 0, 1, 0)


def test_forced_overlap_receipt_allocation_reversal_and_numbering(
    postgis_db_sessionmaker, settings
) -> None:
    admin = create_test_user(postgis_db_sessionmaker, email="overlap-admin@example.com")
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="overlap-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(postgis_db_sessionmaker, owner_user_id=owner.id)
    campaigns = [
        create_test_campaign(
            postgis_db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Overlap campaign {index}",
        )
        for index in range(1, 4)
    ]

    async def setup():
        async with postgis_db_sessionmaker() as session:
            terms = [
                await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"OVERLAP-Q{index}",
                    amount="100.00",
                )
                for index, campaign in enumerate(campaigns, start=1)
            ]
            issuer = await record_invoice_issuer_profile(
                session,
                actor_user_id=admin.id,
                legal_name="Synthetic Terrax",
                tax_identification_number="TEST",
                registered_address="Test",
                country_code="NG",
                invoice_wording="Synthetic",
                numbering_prefix="OVR",
                verification_status=IssuerVerificationStatus.SYNTHETIC,
                external_input_reference="SYNTHETIC-CONCURRENCY",
                settings=settings,
            )
            drafts = [
                await create_invoice_draft(
                    session, commercial_terms_id=terms[index].id, actor_user_id=admin.id
                )
                for index in (0, 1, 2)
            ]
            await session.commit()
            return terms, issuer, drafts

    terms, issuer, drafts = asyncio.run(setup())
    observed_at = datetime.now(UTC)

    async def concurrent_receipt():
        async with postgis_db_sessionmaker() as session:
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank",
                external_transaction_id="OVERLAP-RECEIPT",
                amount="100.00",
                currency="NGN",
                payer_name="Payer",
                evidence_reference="line-overlap",
                observed_at=observed_at,
            )
            await session.commit()
            return receipt.id

    first_id, second_id = asyncio.run(_parallel(concurrent_receipt(), concurrent_receipt()))
    assert first_id == second_id

    async def issue(draft_id):
        async with postgis_db_sessionmaker() as session:
            invoice = await issue_invoice(
                session,
                invoice_id=draft_id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            return invoice.invoice_number

    invoice_numbers = asyncio.run(_parallel(*(issue(draft.id) for draft in drafts)))
    assert sorted(number[-6:] for number in invoice_numbers) == ["000001", "000002", "000003"]

    async def confirmed_receipt(external_id: str, amount: str):
        async with postgis_db_sessionmaker() as session:
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank",
                external_transaction_id=external_id,
                amount=amount,
                currency="NGN",
                payer_name="Payer",
                evidence_reference=external_id,
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
            await session.commit()
            return receipt.id

    bounded_receipt_id = asyncio.run(confirmed_receipt("OVERLAP-BOUND", "100.00"))

    async def allocate(receipt_id, terms_id, amount):
        async with postgis_db_sessionmaker() as session:
            try:
                allocation = await allocate_payment_receipt(
                    session,
                    receipt_id=receipt_id,
                    commercial_terms_id=terms_id,
                    actor_user_id=admin.id,
                    amount=amount,
                )
                await session.commit()
                return str(allocation.id)
            except AppError as exc:
                await session.rollback()
                return exc.code

    same_receipt_results = asyncio.run(
        _parallel(
            allocate(bounded_receipt_id, terms[0].id, "60.00"),
            allocate(bounded_receipt_id, terms[1].id, "60.00"),
        )
    )
    assert "RECEIPT_OVERALLOCATION" in same_receipt_results

    first_terms_receipt = asyncio.run(confirmed_receipt("OVERLAP-TERMS-1", "60.00"))
    second_terms_receipt = asyncio.run(confirmed_receipt("OVERLAP-TERMS-2", "60.00"))
    same_terms_results = asyncio.run(
        _parallel(
            allocate(first_terms_receipt, terms[2].id, "60.00"),
            allocate(second_terms_receipt, terms[2].id, "60.00"),
        )
    )
    assert "OBLIGATION_OVERFUNDING" in same_terms_results

    reversal_receipt = asyncio.run(confirmed_receipt("OVERLAP-REVERSAL", "40.00"))

    async def reverse():
        async with postgis_db_sessionmaker() as session:
            await reverse_payment_receipt(
                session,
                receipt_id=reversal_receipt,
                actor_user_id=admin.id,
                reason="forced overlap",
            )
            await session.commit()

    asyncio.run(
        _parallel(
            reverse(),
            allocate(reversal_receipt, terms[2].id, "40.00"),
        )
    )

    async def assert_reversed_funding():
        async with postgis_db_sessionmaker() as session:
            invoice = await session.get(type(drafts[2]), drafts[2].id)
            assert invoice is not None
            # The reversed receipt can never contribute to an invoice balance.
            status_name, funded = await invoice_payment_status(session, invoice)
            assert status_name == "partially_paid"
            assert str(funded) == "60.00"

    asyncio.run(assert_reversed_funding())


def test_concurrent_refund_reference_conflict_is_stable_across_campaigns(
    postgis_db_sessionmaker, monkeypatch
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker, email="refund-reference-race-admin@example.com"
    )
    second_admin = create_test_user(
        postgis_db_sessionmaker, email="refund-reference-race-admin-2@example.com"
    )
    refund_admins = (admin, second_admin)
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="refund-reference-race-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(postgis_db_sessionmaker, owner_user_id=owner.id)
    campaigns = [
        create_test_campaign(
            postgis_db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Refund reference race {index}",
        )
        for index in (1, 2)
    ]

    async def setup():
        async with postgis_db_sessionmaker() as session:
            authorities = []
            for index, campaign in enumerate(campaigns, start=1):
                terms = await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"REFUND-REFERENCE-RACE-{index}",
                    amount="100.00",
                )
                receipt = await record_payment_receipt(
                    session,
                    organization_id=organization.id,
                    actor_user_id=admin.id,
                    method=ReceiptMethod.MANUAL_TRANSFER,
                    provider="bank",
                    external_transaction_id=f"REFUND-REFERENCE-RACE-PAYMENT-{index}",
                    amount="100.00",
                    currency="NGN",
                    payer_name="Advertiser",
                    evidence_reference=f"refund-reference-race-{index}",
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
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms.id,
                    actor_user_id=admin.id,
                    amount="100.00",
                )
                current = await session.get(Campaign, campaign.id)
                current.status = CampaignStatus.ACTIVE.value
                cancellation = await request_campaign_cancellation(
                    session,
                    actor_user_id=owner.id,
                    campaign_id=campaign.id,
                    payload=CampaignCancellationCreate(
                        client_request_id=uuid4(),
                        reason="authorize cross-campaign refund race",
                    ),
                )
                assert cancellation.disposition == "cash_refund_due"
                await reverse_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    reason="exercise global refund reference identity",
                )
                authorities.append((terms.id, receipt.id, refund_admins[index - 1].id))
            await session.commit()
            return authorities

    authorities = asyncio.run(setup())

    async def attempt(terms_id, receipt_id, actor_user_id):
        async with postgis_db_sessionmaker() as session:
            try:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms_id,
                    receipt_id=receipt_id,
                    actor_user_id=actor_user_id,
                    amount="100.00",
                    settlement_provider="bank",
                    external_reference="REFUND-GLOBAL-REFERENCE-RACE",
                    reason="same reference with different authority",
                )
                await session.commit()
                return "recorded"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def overlap():
        arrivals = 0
        release = asyncio.Event()

        async def synchronize_after_reference_lookup(_session):
            nonlocal arrivals
            arrivals += 1
            if arrivals == len(authorities):
                release.set()
            await release.wait()
            return datetime.now(UTC)

        monkeypatch.setattr(billing_service, "database_clock", synchronize_after_reference_lookup)
        return await _parallel(*(attempt(*authority) for authority in authorities))

    outcomes = asyncio.run(overlap())
    assert sorted(outcomes) == ["REFUND_REFERENCE_CONFLICT", "recorded"]
