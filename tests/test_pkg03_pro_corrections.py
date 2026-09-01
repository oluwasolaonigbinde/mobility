import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

import app.services.campaigns as campaign_services
from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    InvoiceCorrection,
    InvoiceCorrectionType,
    IssuerVerificationStatus,
    PaymentClass,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign import CampaignReviewEvent, CampaignStatus
from app.models.user import UserRole
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.schemas.campaigns import CampaignUpdate
from app.services.billing import (
    accept_quotation_revision,
    allocate_payment_receipt,
    confirm_payment_receipt,
    create_invoice_draft,
    issue_invoice,
    reconcile_payment_receipt,
    record_invoice_correction,
    record_invoice_issuer_profile,
    record_payment_receipt,
    record_quotation_revision,
    record_refund_settlement,
    request_custom_quote,
    reverse_payment_receipt,
)
from app.services.campaign_cancellations import request_campaign_cancellation
from app.services.campaigns import submit_campaign_for_review, update_advertiser_campaign
from app.services.payout_rule_serialization import acquire_campaign_terms_lock


def _fixture(db_sessionmaker, suffix: str):
    admin = create_test_user(db_sessionmaker, email=f"pro-admin-{suffix}@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email=f"pro-owner-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    return admin, owner, organization


async def _issued_invoice(session, *, admin, owner, organization, campaign, settings, suffix):
    terms = await _accepted_terms(
        session,
        campaign=campaign,
        admin=admin,
        owner=owner,
        reference=f"PRO-{suffix}",
        amount="100.00",
    )
    invoice = await create_invoice_draft(
        session, commercial_terms_id=terms.id, actor_user_id=admin.id
    )
    issuer = await _issuer(
        session,
        admin,
        IssuerVerificationStatus.SYNTHETIC,
        f"SYNTHETIC-PRO-{suffix}",
        settings,
    )
    return await issue_invoice(
        session,
        invoice_id=invoice.id,
        issuer_profile_id=issuer.id,
        actor_user_id=admin.id,
        settings=settings,
    )


def test_invoice_correction_reference_replays_conflicts_and_appends(
    db_sessionmaker, settings
) -> None:
    admin, owner, organization = _fixture(db_sessionmaker, "correction-retry")
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            invoice = await _issued_invoice(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                settings=settings,
                suffix="RETRY",
            )
            kwargs = {
                "invoice_id": invoice.id,
                "actor_user_id": admin.id,
                "correction_reference": "retry-reference-001",
                "correction_type": InvoiceCorrectionType.CREDIT_NOTE,
                "net_amount": "10.00",
                "tax_amount": "0.00",
                "reason": "approved reduction",
            }
            first = await record_invoice_correction(session, **kwargs)
            replay = await record_invoice_correction(session, **kwargs)
            assert replay.id == first.id
            assert (
                await session.scalar(
                    select(func.count()).select_from(InvoiceCorrection).where(
                        InvoiceCorrection.invoice_id == invoice.id
                    )
                )
                == 1
            )
            with pytest.raises(AppError) as conflict:
                await record_invoice_correction(
                    session, **(kwargs | {"reason": "different reduction"})
                )
            assert conflict.value.code == "INVOICE_CORRECTION_REFERENCE_CONFLICT"
            second = await record_invoice_correction(
                session,
                **(
                    kwargs
                    | {
                        "correction_reference": "retry-reference-002",
                        "correction_type": InvoiceCorrectionType.DEBIT_NOTE,
                    }
                ),
            )
            assert second.sequence_number == 2

    asyncio.run(scenario())


def test_concurrent_same_correction_reference_creates_one_delta(
    postgis_db_sessionmaker, settings
) -> None:
    admin, owner, organization = _fixture(postgis_db_sessionmaker, "correction-race")
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            invoice = await _issued_invoice(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                settings=settings,
                suffix="RACE",
            )
            await session.commit()
            return invoice.id

    invoice_id = asyncio.run(setup())

    async def attempt():
        async with postgis_db_sessionmaker() as session:
            row = await record_invoice_correction(
                session,
                invoice_id=invoice_id,
                actor_user_id=admin.id,
                correction_reference="concurrent-reference-001",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="10.00",
                tax_amount="0.00",
                reason="one immutable request",
            )
            await session.commit()
            return row.id

    async def race():
        return await asyncio.gather(attempt(), attempt())

    first, second = asyncio.run(race())
    assert first == second


def test_invoice_sequence_is_shared_by_rendered_prefix_and_year(
    db_sessionmaker, settings
) -> None:
    admin, owner, organization = _fixture(db_sessionmaker, "sequence")
    campaigns = [
        create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Sequence {index}",
        )
        for index in (1, 2)
    ]

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            issuers = []
            for index in (1, 2):
                issuers.append(
                    await record_invoice_issuer_profile(
                        session,
                        actor_user_id=admin.id,
                        legal_name="Terrax Media",
                        tax_identification_number=f"TEST-{index}",
                        registered_address="Test address",
                        country_code="NG",
                        invoice_wording="Synthetic",
                        numbering_prefix="SHARED",
                        verification_status=IssuerVerificationStatus.SYNTHETIC,
                        external_input_reference=f"SYNTHETIC-SHARED-{index}",
                        settings=settings,
                    )
                )
            numbers = []
            for index, campaign in enumerate(campaigns):
                terms = await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"SHARED-{index}",
                )
                draft = await create_invoice_draft(
                    session, commercial_terms_id=terms.id, actor_user_id=admin.id
                )
                issued = await issue_invoice(
                    session,
                    invoice_id=draft.id,
                    issuer_profile_id=issuers[index].id,
                    actor_user_id=admin.id,
                    settings=settings,
                )
                numbers.append(issued.invoice_number)
            assert [number[-6:] for number in numbers if number] == ["000001", "000002"]

    asyncio.run(scenario())


def test_different_profiles_with_shared_prefix_issue_concurrently_without_collision(
    postgis_db_sessionmaker, settings
) -> None:
    admin, owner, organization = _fixture(postgis_db_sessionmaker, "sequence-race")
    campaigns = [
        create_test_campaign(
            postgis_db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Sequence race {index}",
        )
        for index in (1, 2)
    ]

    async def setup():
        async with postgis_db_sessionmaker() as session:
            issuer_ids = []
            draft_ids = []
            for index, campaign in enumerate(campaigns, start=1):
                issuer = await record_invoice_issuer_profile(
                    session,
                    actor_user_id=admin.id,
                    legal_name="Terrax Media",
                    tax_identification_number=f"RACE-{index}",
                    registered_address="Test address",
                    country_code="NG",
                    invoice_wording="Synthetic",
                    numbering_prefix="RACE",
                    verification_status=IssuerVerificationStatus.SYNTHETIC,
                    external_input_reference=f"SYNTHETIC-RACE-{index}",
                    settings=settings,
                )
                terms = await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"RACE-{index}",
                )
                draft = await create_invoice_draft(
                    session, commercial_terms_id=terms.id, actor_user_id=admin.id
                )
                issuer_ids.append(issuer.id)
                draft_ids.append(draft.id)
            await session.commit()
            return issuer_ids, draft_ids

    issuer_ids, draft_ids = asyncio.run(setup())

    async def issue(index):
        async with postgis_db_sessionmaker() as session:
            invoice = await issue_invoice(
                session,
                invoice_id=draft_ids[index],
                issuer_profile_id=issuer_ids[index],
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            return invoice.invoice_number

    async def race():
        return await asyncio.gather(issue(0), issue(1))

    numbers = asyncio.run(race())
    assert sorted(number[-6:] for number in numbers if number) == ["000001", "000002"]


def test_max_length_synthetic_and_verified_rendered_prefixes_are_distinct(
    db_sessionmaker, settings
) -> None:
    admin, owner, organization = _fixture(db_sessionmaker, "sequence-max-prefix")
    campaigns = [
        create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Max prefix {index}",
        )
        for index in (1, 2)
    ]
    prefix = "X" * 32
    verified_settings = settings.model_copy(
        update={"invoice_issuer_external_input_reference": "VERIFIED-MAX-PREFIX"}
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            synthetic = await record_invoice_issuer_profile(
                session,
                actor_user_id=admin.id,
                legal_name="Terrax Media",
                tax_identification_number="SYNTHETIC",
                registered_address="Test",
                country_code="NG",
                invoice_wording="Synthetic",
                numbering_prefix=prefix,
                verification_status=IssuerVerificationStatus.SYNTHETIC,
                external_input_reference="SYNTHETIC-MAX-PREFIX",
                settings=settings,
            )
            verified = await record_invoice_issuer_profile(
                session,
                actor_user_id=admin.id,
                legal_name="Terrax Media",
                tax_identification_number="VERIFIED",
                registered_address="Test",
                country_code="NG",
                invoice_wording="Verified",
                numbering_prefix=prefix,
                verification_status=IssuerVerificationStatus.VERIFIED,
                external_input_reference="VERIFIED-MAX-PREFIX",
                settings=verified_settings,
            )
            numbers = []
            for campaign, issuer, authority_settings in (
                (campaigns[0], synthetic, settings),
                (campaigns[1], verified, verified_settings),
            ):
                terms = await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owner,
                    reference=f"MAX-{campaign.id}",
                )
                draft = await create_invoice_draft(
                    session, commercial_terms_id=terms.id, actor_user_id=admin.id
                )
                invoice = await issue_invoice(
                    session,
                    invoice_id=draft.id,
                    issuer_profile_id=issuer.id,
                    actor_user_id=admin.id,
                    settings=authority_settings,
                )
                numbers.append(invoice.invoice_number)
            assert numbers[0] is not None and numbers[0].startswith(f"TEST-{prefix}-")
            assert numbers[1] is not None and numbers[1].startswith(f"{prefix}-")
            assert numbers[0].endswith("000001") and numbers[1].endswith("000001")

    asyncio.run(scenario())


@pytest.mark.parametrize("refund_order", [("first", "second"), ("second", "first")])
def test_split_receipt_refunds_conserve_each_allocation(
    db_sessionmaker, refund_order
) -> None:
    admin, owner, organization = _fixture(db_sessionmaker, f"refund-{refund_order[0]}")
    campaigns = {
        key: create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Refund {key}",
        )
        for key in ("first", "second")
    }

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = {
                "first": await _accepted_terms(
                    session,
                    campaign=campaigns["first"],
                    admin=admin,
                    owner=owner,
                    reference=f"SPLIT-A-{refund_order[0]}",
                    amount="60.00",
                ),
                "second": await _accepted_terms(
                    session,
                    campaign=campaigns["second"],
                    admin=admin,
                    owner=owner,
                    reference=f"SPLIT-B-{refund_order[0]}",
                    amount="40.00",
                ),
            }
            receipt = await record_payment_receipt(
                session,
                organization_id=organization.id,
                actor_user_id=admin.id,
                method=ReceiptMethod.MANUAL_TRANSFER,
                provider="bank",
                external_transaction_id=f"SPLIT-{refund_order[0]}",
                amount="100.00",
                currency="NGN",
                payer_name="Advertiser",
                evidence_reference="split receipt",
                observed_at=datetime.now(UTC),
            )
            await reconcile_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                expected_amount="100.00",
                expected_currency="NGN",
            )
            await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
            for key, amount in (("first", "60.00"), ("second", "40.00")):
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=terms[key].id,
                    actor_user_id=admin.id,
                    amount=amount,
                )
            for key in ("first", "second"):
                current = await session.get(type(campaigns[key]), campaigns[key].id)
                current.status = CampaignStatus.ACTIVE.value
                cancellation = await request_campaign_cancellation(
                    session,
                    actor_user_id=owner.id,
                    campaign_id=campaigns[key].id,
                    payload=CampaignCancellationCreate(
                        client_request_id=uuid4(),
                        reason="authorize split-receipt refund",
                    ),
                )
                assert str(cancellation.refundable_amount) == (
                    "60.00" if key == "first" else "40.00"
                )
            await reverse_payment_receipt(
                session,
                receipt_id=receipt.id,
                actor_user_id=admin.id,
                reason="split refund",
            )
            amounts = {"first": "60.00", "second": "40.00"}
            for index, key in enumerate(refund_order):
                settlement = await record_refund_settlement(
                    session,
                    commercial_terms_id=terms[key].id,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    amount=amounts[key],
                    settlement_provider="bank",
                    external_reference=f"SPLIT-REFUND-{refund_order[0]}-{index}",
                    reason="refund selected allocation",
                )
                assert str(settlement.amount) == amounts[key]
                if index == 0:
                    replay = await record_refund_settlement(
                        session,
                        commercial_terms_id=terms[key].id,
                        receipt_id=receipt.id,
                        actor_user_id=admin.id,
                        amount=amounts[key],
                        settlement_provider="bank",
                        external_reference=f"SPLIT-REFUND-{refund_order[0]}-{index}",
                        reason="refund selected allocation",
                    )
                    assert replay.id == settlement.id
            with pytest.raises(AppError) as excess:
                await record_refund_settlement(
                    session,
                    commercial_terms_id=terms["first"].id,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    amount="0.01",
                    settlement_provider="bank",
                    external_reference=f"SPLIT-EXCESS-{refund_order[0]}",
                    reason="excess",
                )
            assert excess.value.code == "REFUND_EXCEEDS_CASH_AUTHORITY"

    asyncio.run(scenario())


def test_campaign_currency_and_accepted_terms_cannot_diverge(db_sessionmaker) -> None:
    admin, owner, organization = _fixture(db_sessionmaker, "currency")
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    stale_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Stale currency acceptance",
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            await update_advertiser_campaign(
                session,
                user_id=owner.id,
                campaign_id=campaign.id,
                payload=CampaignUpdate(currency="USD"),
            )
            current = await session.get(type(campaign), campaign.id)
            assert current is not None and current.currency == "USD"
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            matching = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="CURRENCY-USD",
                currency="USD",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Media",
                        "kind": "media",
                        "amount": "100.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0",
            )
            accepted = await accept_quotation_revision(
                session,
                quotation_revision_id=matching.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            assert accepted.currency == "USD"
            same_currency, _ = await update_advertiser_campaign(
                session,
                user_id=owner.id,
                campaign_id=campaign.id,
                payload=CampaignUpdate(currency="USD"),
            )
            assert same_currency.currency == "USD"
            with pytest.raises(AppError) as immutable:
                await update_advertiser_campaign(
                    session,
                    user_id=owner.id,
                    campaign_id=campaign.id,
                    payload=CampaignUpdate(currency="NGN"),
                )
            assert immutable.value.code == "CAMPAIGN_CURRENCY_IMMUTABLE"

            stale_request = await request_custom_quote(
                session,
                campaign_id=stale_campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            stale_revision = await record_quotation_revision(
                session,
                quote_request_id=stale_request.id,
                actor_user_id=admin.id,
                quote_reference="CURRENCY-STALE",
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
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0",
            )
            await update_advertiser_campaign(
                session,
                user_id=owner.id,
                campaign_id=stale_campaign.id,
                payload=CampaignUpdate(currency="USD"),
            )
            with pytest.raises(AppError) as mismatch:
                await accept_quotation_revision(
                    session,
                    quotation_revision_id=stale_revision.id,
                    actor_user_id=owner.id,
                    acceptance_method=AcceptanceMethod.IN_PLATFORM,
                )
            assert mismatch.value.code == "QUOTATION_CURRENCY_MISMATCH"

    asyncio.run(scenario())


def test_currency_update_and_acceptance_serialize_on_campaign_lock(
    postgis_db_sessionmaker,
) -> None:
    admin, owner, organization = _fixture(postgis_db_sessionmaker, "currency-race")
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
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
                quote_reference="CURRENCY-RACE",
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
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0",
            )
            await session.commit()
            return revision.id

    revision_id = asyncio.run(setup())

    async def race():
        locked = asyncio.Event()
        release = asyncio.Event()

        async def update_currency():
            async with postgis_db_sessionmaker() as session:
                await acquire_campaign_terms_lock(session, campaign.id)
                locked.set()
                await release.wait()
                updated, _ = await update_advertiser_campaign(
                    session,
                    user_id=owner.id,
                    campaign_id=campaign.id,
                    payload=CampaignUpdate(currency="USD"),
                )
                await session.commit()
                return updated.currency

        async def accept_old_currency():
            await locked.wait()
            async with postgis_db_sessionmaker() as session:
                try:
                    await accept_quotation_revision(
                        session,
                        quotation_revision_id=revision_id,
                        actor_user_id=owner.id,
                        acceptance_method=AcceptanceMethod.IN_PLATFORM,
                    )
                except AppError as exc:
                    await session.rollback()
                    return exc.code
                raise AssertionError("stale-currency acceptance unexpectedly succeeded")

        update_task = asyncio.create_task(update_currency())
        accept_task = asyncio.create_task(accept_old_currency())
        await locked.wait()
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(update_task, accept_task)

    assert asyncio.run(race()) == ["USD", "QUOTATION_CURRENCY_MISMATCH"]


def test_stale_same_currency_update_cannot_overwrite_accepted_currency(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    admin, owner, organization = _fixture(postgis_db_sessionmaker, "currency-stale-noop")
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def setup():
        async with postgis_db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            await session.commit()
            return request.id

    request_id = asyncio.run(setup())

    async def race():
        stale_read = asyncio.Event()
        release_stale = asyncio.Event()
        original_get = campaign_services.get_advertiser_campaign

        async def paused_get(*args, **kwargs):
            current = await original_get(*args, **kwargs)
            if asyncio.current_task().get_name() == "stale-same-currency-update":
                stale_read.set()
                await release_stale.wait()
            return current

        monkeypatch.setattr(campaign_services, "get_advertiser_campaign", paused_get)

        async def stale_same_currency_update():
            async with postgis_db_sessionmaker() as session:
                try:
                    await update_advertiser_campaign(
                        session,
                        user_id=owner.id,
                        campaign_id=campaign.id,
                        payload=CampaignUpdate(currency="NGN"),
                    )
                except AppError as exc:
                    await session.rollback()
                    return exc.code
                raise AssertionError("stale same-currency update unexpectedly succeeded")

        stale_task = asyncio.create_task(
            stale_same_currency_update(),
            name="stale-same-currency-update",
        )
        await stale_read.wait()

        async with postgis_db_sessionmaker() as session:
            updated, _ = await update_advertiser_campaign(
                session,
                user_id=owner.id,
                campaign_id=campaign.id,
                payload=CampaignUpdate(currency="USD"),
            )
            assert updated.currency == "USD"
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            revision = await record_quotation_revision(
                session,
                quote_request_id=request_id,
                actor_user_id=admin.id,
                quote_reference="CURRENCY-STALE-NOOP",
                currency="USD",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Media",
                        "kind": "media",
                        "amount": "100.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0",
            )
            accepted = await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            assert accepted.currency == "USD"
            await session.commit()

        release_stale.set()
        result = await stale_task
        async with postgis_db_sessionmaker() as session:
            current = await session.get(type(campaign), campaign.id)
            assert current is not None and current.currency == "USD"
        return result

    assert asyncio.run(race()) == "CAMPAIGN_CURRENCY_IMMUTABLE"


def test_stale_currency_update_cannot_mutate_submitted_review_snapshot(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    admin, owner, organization = _fixture(postgis_db_sessionmaker, "currency-review-race")
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )

    async def race() -> tuple[str, str, str]:
        stale_read = asyncio.Event()
        release_stale = asyncio.Event()
        original_get = campaign_services.get_advertiser_campaign

        async def paused_get(*args, **kwargs):
            current = await original_get(*args, **kwargs)
            if asyncio.current_task().get_name() == "stale-review-currency-update":
                stale_read.set()
                await release_stale.wait()
            return current

        monkeypatch.setattr(campaign_services, "get_advertiser_campaign", paused_get)

        async def stale_currency_update() -> str:
            async with postgis_db_sessionmaker() as session:
                try:
                    await update_advertiser_campaign(
                        session,
                        user_id=owner.id,
                        campaign_id=campaign.id,
                        payload=CampaignUpdate(currency="USD"),
                    )
                    await session.commit()
                except AppError as exc:
                    await session.rollback()
                    return exc.code
                return "updated"

        stale_task = asyncio.create_task(
            stale_currency_update(),
            name="stale-review-currency-update",
        )
        await stale_read.wait()

        async with postgis_db_sessionmaker() as session:
            submitted = await submit_campaign_for_review(
                session,
                user_id=owner.id,
                campaign_id=campaign.id,
            )
            assert submitted.status == CampaignStatus.PENDING_REVIEW.value
            await session.commit()

        release_stale.set()
        outcome = await stale_task

        async with postgis_db_sessionmaker() as session:
            current = await session.get(type(campaign), campaign.id)
            submission = await session.scalar(
                select(CampaignReviewEvent).where(
                    CampaignReviewEvent.campaign_id == campaign.id,
                    CampaignReviewEvent.new_status == CampaignStatus.PENDING_REVIEW.value,
                )
            )
            assert current is not None and submission is not None
            return outcome, current.currency, str(submission.reviewed_snapshot["currency"])

    assert asyncio.run(race()) == (
        "CAMPAIGN_REVIEW_STATE_CONFLICT",
        "NGN",
        "NGN",
    )
