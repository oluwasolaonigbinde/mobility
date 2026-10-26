"""REQ-208: list reads carry what the list pages used to fetch one item at a time."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_creative,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import update
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

from app.models.billing import IssuerVerificationStatus, ReceiptMethod
from app.models.campaign import Campaign, CampaignCreative, CampaignStatus, CreativeStatus
from app.models.stored_file import FileScanStatus, StoredFile
from app.models.user import UserRole
from app.services.billing.invoices import create_invoice_draft, issue_invoice
from app.services.billing.receipts import (
    allocate_payment_receipt,
    confirm_payment_receipt,
    record_payment_receipt,
)

PASSWORD = "long-secure-password"


def _per_campaign_outstanding(db_client, headers, campaign_ids) -> list[dict]:
    """The former staff Advertisers algorithm: each campaign's commercial read, summed."""
    totals: dict[str, Decimal] = {}
    for campaign_id in campaign_ids:
        commercial = db_client.get(
            f"/api/v1/admin/campaigns/{campaign_id}/commercial", headers=headers
        )
        assert commercial.status_code == 200, commercial.text
        for invoice in commercial.json()["invoices"]:
            if invoice["status"] != "issued":
                continue
            due = Decimal(invoice["effective_obligation_amount"]) - Decimal(
                invoice["funded_amount"]
            )
            totals[invoice["currency"]] = totals.get(invoice["currency"], Decimal(0)) + max(
                due, Decimal(0)
            )
    return [
        {"currency": currency, "amount": f"{amount:.2f}"}
        for currency, amount in sorted(totals.items())
    ]


def test_company_list_outstanding_matches_the_per_campaign_reads(
    db_client, db_sessionmaker, settings
) -> None:
    admin = create_test_user(db_sessionmaker, email="req208-outstanding-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="req208-outstanding-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaigns = [
        create_test_campaign(
            db_sessionmaker,
            organization_id=organization.id,
            created_by_user_id=admin.id,
            name=f"Outstanding {index}",
        )
        for index in range(4)
    ]

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            issuer = await _issuer(
                session, admin, IssuerVerificationStatus.SYNTHETIC, "SYNTHETIC-REQ208", settings
            )
            terms = []
            for index, (campaign, amount) in enumerate(
                zip(campaigns, ("100.00", "250.50", "40.00", "75.00"), strict=True)
            ):
                terms.append(
                    await _accepted_terms(
                        session,
                        campaign=campaign,
                        admin=admin,
                        owner=owner,
                        reference=f"REQ208-{index}",
                        amount=amount,
                    )
                )
            # Campaigns 0-2 have issued invoices; campaign 3 only a draft, which never counts.
            for term in terms[:3]:
                await issue_invoice(
                    session,
                    invoice_id=(
                        await create_invoice_draft(
                            session, commercial_terms_id=term.id, actor_user_id=admin.id
                        )
                    ).id,
                    issuer_profile_id=issuer.id,
                    actor_user_id=admin.id,
                    settings=settings,
                )
            await create_invoice_draft(
                session, commercial_terms_id=terms[3].id, actor_user_id=admin.id
            )
            # Campaign 0 is part-paid; campaign 2 is overpaid and never shows negative money.
            for term, paid, reference in ((terms[0], "50.00", "A"), (terms[2], "40.00", "B")):
                receipt = await record_payment_receipt(
                    session,
                    organization_id=organization.id,
                    actor_user_id=admin.id,
                    method=ReceiptMethod.MANUAL_TRANSFER,
                    provider="bank-transfer",
                    external_transaction_id=f"REQ208-PAY-{reference}",
                    amount=paid,
                    currency="NGN",
                    payer_name="Acme",
                    evidence_reference=f"line-{reference}",
                    observed_at=datetime.now(UTC),
                )
                await confirm_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    actor_user_id=admin.id,
                    expected_amount=paid,
                    expected_currency="NGN",
                )
                await allocate_payment_receipt(
                    session,
                    receipt_id=receipt.id,
                    commercial_terms_id=term.id,
                    actor_user_id=admin.id,
                    amount=paid,
                )
            # Draft and cancelled campaigns still owe their issued invoices.
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaigns[1].id)
                .values(status=CampaignStatus.CANCELLED)
            )
            await session.commit()

    asyncio.run(scenario())
    headers = auth_headers(db_client, admin.email, PASSWORD)
    listing = db_client.get("/api/v1/admin/advertiser-organizations", headers=headers)
    assert listing.status_code == 200, listing.text
    [company] = [item for item in listing.json()["items"] if item["id"] == str(organization.id)]
    expected = _per_campaign_outstanding(db_client, headers, [c.id for c in campaigns])
    assert company["outstanding"] == expected == [{"currency": "NGN", "amount": "300.50"}]


def test_campaign_list_carries_the_card_picture(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="req208-preview-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="req208-preview-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=admin.id
    )
    bare = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="No artwork",
    )
    approved_old = create_test_campaign_creative(
        db_sessionmaker, campaign_id=campaign.id, creative_status=CreativeStatus.APPROVED
    )
    ready_new = create_test_campaign_creative(
        db_sessionmaker, campaign_id=campaign.id, creative_status=CreativeStatus.DRAFT
    )
    infected_newest = create_test_campaign_creative(
        db_sessionmaker, campaign_id=campaign.id, creative_status=CreativeStatus.APPROVED
    )
    # A legacy link creative has no managed file, so it can never be a card picture.
    create_test_campaign_creative(db_sessionmaker, campaign_id=bare.id)
    now = datetime.now(UTC)

    async def age() -> None:
        async with db_sessionmaker() as session:
            for creative, days in ((approved_old, 3), (ready_new, 1), (infected_newest, 0)):
                await session.execute(
                    update(CampaignCreative)
                    .where(CampaignCreative.id == creative.id)
                    .values(created_at=now - timedelta(days=days))
                )
            await session.execute(
                update(StoredFile)
                .where(StoredFile.id == infected_newest.stored_file_id)
                .values(scan_status=FileScanStatus.INFECTED.value)
            )
            await session.commit()

    asyncio.run(age())
    response = db_client.get(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, owner.email, PASSWORD),
    )
    assert response.status_code == 200, response.text
    previews = {item["id"]: item["preview_file_id"] for item in response.json()["items"]}
    # Approved clean artwork wins over newer drafts; unclean files never show.
    assert previews == {str(campaign.id): str(approved_old.stored_file_id), str(bare.id): None}
