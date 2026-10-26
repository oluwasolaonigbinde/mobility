"""Quotation serialization, configured invoice issuing and safe portal reads."""

import asyncio

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_commercial_terms import _commercial_fixture
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import (
    AcceptanceMethod,
    CommercialQuotationRevision,
    InvoiceNumberSequence,
    IssuerVerificationStatus,
    PaymentClass,
    QuoteRequestSource,
)
from app.models.campaign import Campaign
from app.models.notification import Notification
from app.services.billing import quotes
from app.services.billing.invoices import create_invoice_draft
from app.services.payout_rule_serialization import acquire_campaign_terms_lock


def test_revision_waiting_on_acceptance_refuses_without_a_new_notice(db_sessionmaker, monkeypatch):
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)

    async def exercise():
        async with db_sessionmaker() as setup:
            request = await quotes.request_custom_quote(
                setup,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            values = dict(
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="SERIAL-1",
                currency="NGN",
                line_items=[
                    {"code": "M", "description": "Media", "kind": "media", "amount": "100.00"},
                    {
                        "code": "P",
                        "description": "Printing",
                        "kind": "production",
                        "amount": "25.00",
                    },
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0.075",
            )
            first = await quotes.record_quotation_revision(setup, **values)
            await setup.commit()
            notices_before = await setup.scalar(select(func.count()).select_from(Notification))
        async with db_sessionmaker() as accepting, db_sessionmaker() as revising:
            await acquire_campaign_terms_lock(accepting, campaign.id)
            reached_lock = asyncio.Event()

            async def observe_lock(session, identity):
                if session is revising:
                    reached_lock.set()
                await acquire_campaign_terms_lock(session, identity)

            monkeypatch.setattr(quotes, "acquire_campaign_terms_lock", observe_lock)

            async def revise():
                with pytest.raises(AppError) as blocked:
                    await quotes.record_quotation_revision(
                        revising, **{**values, "quote_reference": "SERIAL-2"}
                    )
                assert blocked.value.status_code == 409
                assert blocked.value.code == "QUOTATION_ALREADY_ACCEPTED"
                await revising.rollback()

            attempt = asyncio.create_task(revise())
            await asyncio.wait_for(reached_lock.wait(), timeout=5)
            await quotes.accept_quotation_revision(
                accepting,
                quotation_revision_id=first.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            await accepting.commit()
            await asyncio.wait_for(attempt, timeout=5)
        async with db_sessionmaker() as read:
            assert (
                await read.scalar(select(func.count()).select_from(CommercialQuotationRevision))
                == 1
            )
            assert (
                await read.scalar(select(func.count()).select_from(Notification)) == notices_before
            )

    asyncio.run(exercise())


def test_invoice_issue_uses_configured_authority_not_request_ids(
    db_client, db_sessionmaker, settings
):
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)
    reference = "SYNTHETIC-REQ231-ISSUER"

    async def setup():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="ISSUE-REQ231",
                amount="100.00",
                tax_rate="0.075",
            )
            invoice = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session, admin, IssuerVerificationStatus.SYNTHETIC, reference, settings
            )
            await session.commit()
            return invoice.id, issuer.id

    invoice_id, issuer_id = asyncio.run(setup())
    settings.invoice_issuer_external_input_reference = ""
    headers = auth_headers(db_client, admin.email)
    state_url = f"/api/v1/admin/campaigns/{campaign.id}/commercial"
    issue_url = f"/api/v1/admin/invoices/{invoice_id}/issue"
    assert db_client.get(state_url, headers=headers).json()["issuing_available"] is False
    assert (
        db_client.post(
            issue_url, headers=headers, json={"issuer_profile_id": str(issuer_id)}
        ).status_code
        == 409
    )
    settings.invoice_issuer_external_input_reference = reference
    settings.environment = "production"
    assert db_client.get(state_url, headers=headers).json()["issuing_available"] is False
    assert db_client.post(issue_url, headers=headers).status_code == 409
    settings.environment = "test"
    assert db_client.get(state_url, headers=headers).json()["issuing_available"] is True
    issued = db_client.post(issue_url, headers=headers)
    assert issued.status_code == 200, issued.text
    assert issued.json()["invoice_number"].startswith("TEST-CV-")
    assert issued.json()["net_amount"] == "100.00"
    assert issued.json()["tax_amount"] == "7.50"
    assert issued.json()["gross_amount"] == "107.50"

    async def issuance_counters():
        async with db_sessionmaker() as session:
            return (
                await session.scalar(select(func.sum(InvoiceNumberSequence.next_number))),
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "billing.invoice.issued"
                    )
                ),
            )

    before_retry = asyncio.run(issuance_counters())
    settings.invoice_issuer_external_input_reference = ""
    replay = db_client.post(issue_url, headers=headers)
    assert replay.status_code == 200, replay.text
    for field in ("invoice_number", "issued_at", "net_amount", "tax_amount", "gross_amount"):
        assert replay.json()[field] == issued.json()[field]
    assert asyncio.run(issuance_counters()) == before_retry
    advertiser = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/commercial",
        headers=auth_headers(db_client, owner.email),
    )
    assert "issuing_available" not in advertiser.json()


@pytest.mark.parametrize("kind", ["budget", "operational", "unknown"])
def test_advertiser_pause_read_exposes_only_a_kind(db_client, db_sessionmaker, kind):
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)
    private_reason = "Private staff note: driver Alice lives at 12 Example Street"

    async def pause():
        async with db_sessionmaker() as session:
            current = await session.get(Campaign, campaign.id)
            assert current is not None
            current.status = "paused"
            await session.flush()
            await session.refresh(current, ["updated_at"])
            if kind != "unknown":
                session.add(
                    AuditEvent(
                        actor_user_id=admin.id,
                        action="admin.campaign.paused",
                        entity_type="campaign",
                        entity_id=str(current.id),
                        event_metadata={
                            "pause_reason_kind": kind,
                            "reason": private_reason,
                            "status_after": "paused",
                            "pause_version": current.updated_at.isoformat(),
                        },
                    )
                )
            await session.commit()

    asyncio.run(pause())
    headers = auth_headers(db_client, owner.email)
    for path in [f"/api/v1/advertiser/campaigns/{campaign.id}", "/api/v1/advertiser/campaigns"]:
        response = db_client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        item = response.json() if "items" not in response.json() else response.json()["items"][0]
        assert item["pause_kind"] == kind
        assert private_reason not in response.text
        assert "pause_id" not in item
        assert "reason" not in item
