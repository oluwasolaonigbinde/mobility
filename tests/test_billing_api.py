import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
    make_test_campaign_reviewable,
)
from sqlalchemy import func, select
from test_invoices import _issuer
from test_receipt_allocations import _accepted_terms

from app.adapters.payments import FakePaymentGatewayAdapter
from app.api.v1.billing import get_payment_gateway_adapter
from app.api.v1.dependencies import get_payment_event_enqueuer
from app.jobs.payment_gateway import sweep_payment_gateway_events
from app.models.audit import AuditEvent
from app.models.billing import (
    InvoiceCorrectionType,
    IssuerVerificationStatus,
    PaymentGatewayProcessingAttempt,
    PaymentReceipt,
)
from app.models.user import UserRole
from app.services.billing.invoices import create_invoice_draft, issue_invoice
from app.services.billing.settlements import record_invoice_correction


@pytest.mark.parametrize(
    "connected,return_url,available",
    [
        (False, "https://example.test/return", False),
        (True, "", False),
        (True, "https://example.test/return", True),
    ],
)
def test_invoice_read_reports_gateway_and_return_url_readiness(
    settings, connected, return_url, available, monkeypatch
):
    from decimal import Decimal
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from pydantic import SecretStr

    from app.api.v1 import billing
    from app.schemas.billing import InvoiceRead

    settings.paystack_secret_key = SecretStr("sk_test_synthetic") if connected else None
    settings.paystack_checkout_return_url = return_url
    monkeypatch.setattr(
        billing, "invoice_payment_status", AsyncMock(return_value=("unpaid", Decimal(0)))
    )
    monkeypatch.setattr(
        billing, "adjusted_invoice_obligation", AsyncMock(return_value=Decimal(100))
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[]))
    invoice = InvoiceRead.model_construct(id=uuid4())
    result = asyncio.run(billing._invoice_read(session, invoice, settings))
    assert result.online_payment_available is available


def _fixture(db_sessionmaker, suffix: str):
    admin = create_test_user(db_sessionmaker, email=f"billing-api-admin-{suffix}@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email=f"billing-api-owner-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        budget_amount="1000.00",
    )
    return admin, owner, organization, campaign


def test_commercial_api_journey_is_tenant_scoped_and_uses_canonical_cash(
    db_client, db_sessionmaker, settings
) -> None:
    test_settings = settings
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "journey")
    admin_headers = auth_headers(db_client, admin.email)
    owner_headers = auth_headers(db_client, owner.email)

    company = db_client.patch(
        "/api/v1/advertiser/company",
        headers=owner_headers,
        json={"billing_contact_name": "Finance Lead", "address_city": "Abuja"},
    )
    assert company.status_code == 200
    assert company.json()["billing_contact_name"] == "Finance Lead"

    request = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/quote-request",
        headers=owner_headers,
        json={"request_details": {"vehicle_count": 1}},
    )
    assert request.status_code == 201, request.text
    quote_request_id = request.json()["id"]

    revision = db_client.post(
        f"/api/v1/admin/quote-requests/{quote_request_id}/revisions",
        headers=admin_headers,
        json={
            "quote_reference": "API-Q-001",
            "currency": "NGN",
            "line_items": [
                {
                    "code": "MEDIA",
                    "description": "Media campaign",
                    "kind": "media",
                    "amount": "100.00",
                }
            ],
            "production_scope": {"vehicle_count": 1},
            "payment_class": "standard_prepaid",
            "payment_terms": {},
            "tax_rate": "0.00",
        },
    )
    assert revision.status_code == 201, revision.text

    latest_revision = db_client.post(
        f"/api/v1/admin/quote-requests/{quote_request_id}/revisions",
        headers=admin_headers,
        json={
            "quote_reference": "API-Q-002",
            "currency": "NGN",
            "line_items": [
                {
                    "code": "MEDIA",
                    "description": "Media campaign",
                    "kind": "media",
                    "amount": "100.00",
                }
            ],
            "production_scope": {"vehicle_count": 1},
            "payment_class": "standard_prepaid",
            "payment_terms": {},
            "tax_rate": "0.00",
        },
    )
    assert latest_revision.status_code == 201, latest_revision.text

    superseded = db_client.post(
        f"/api/v1/advertiser/quotations/{revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    )
    assert superseded.status_code == 409, superseded.text
    assert superseded.json()["error"]["code"] == "QUOTATION_REVISION_SUPERSEDED"

    accepted = db_client.post(
        f"/api/v1/advertiser/quotations/{latest_revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    )
    assert accepted.status_code == 200, accepted.text
    terms_id = accepted.json()["id"]
    retried_acceptance = db_client.post(
        f"/api/v1/advertiser/quotations/{latest_revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    )
    assert retried_acceptance.status_code == 200, retried_acceptance.text
    assert retried_acceptance.json()["id"] == terms_id
    make_test_campaign_reviewable(
        db_sessionmaker, campaign_id=campaign.id, created_by_user_id=admin.id
    )

    submitted = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/submit",
        headers=owner_headers,
    )
    assert submitted.status_code == 200, submitted.text
    approved = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    premature = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/production-start",
        headers=admin_headers,
        json={},
    )
    assert premature.status_code == 409
    assert premature.json()["error"]["code"] == "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED"

    transfer_body = {
        "organization_id": str(organization.id),
        "commercial_terms_id": terms_id,
        "external_transaction_id": "API-BANK-001",
        "observed_amount": "100.00",
        "expected_amount": "100.00",
        "currency": "NGN",
        "payer_name": "API Advertiser",
        "evidence_reference": "API-BANK-EVIDENCE-001",
        "observed_at": datetime.now(UTC).isoformat(),
    }

    def receipt_count() -> int:
        async def count() -> int:
            async with db_sessionmaker() as session:
                return await session.scalar(select(func.count()).select_from(PaymentReceipt))

        return asyncio.run(count())

    # REQ-255: no invoice, then a draft invoice — both refused before any receipt is written.
    for step in ("no invoice", "draft invoice"):
        if step == "draft invoice":
            draft = db_client.post(
                "/api/v1/admin/invoices",
                headers=admin_headers,
                json={"commercial_terms_id": terms_id},
            )
            assert draft.status_code == 200, draft.text
            assert draft.json()["status"] == "draft"
        refused = db_client.post(
            "/api/v1/admin/billing/manual-transfers", headers=admin_headers, json=transfer_body
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "INVOICE_NOT_ISSUED"
        assert receipt_count() == 0

    async def issue() -> None:
        async with db_sessionmaker() as session:
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-API-JOURNEY",
                test_settings,
            )
            await issue_invoice(
                session,
                invoice_id=draft.json()["id"],
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=test_settings,
            )
            await session.commit()

    asyncio.run(issue())
    transfer = db_client.post(
        "/api/v1/admin/billing/manual-transfers", headers=admin_headers, json=transfer_body
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["matched"] is True
    assert transfer.json()["allocation"]["commercial_terms_id"] == terms_id

    advertiser_history = db_client.get("/api/v1/advertiser/billing", headers=owner_headers)
    assert advertiser_history.status_code == 200
    assert advertiser_history.json()[0]["current_status"] == "confirmed"

    snapshot = db_client.get(
        f"/api/v1/admin/campaigns/{campaign.id}/commercial", headers=admin_headers
    )
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["terms"]["id"] == terms_id
    canonical_wording = (
        "I want production to start early. I understand I can't get a refund once it starts."
    )
    canonical_copy = snapshot.json()["expedited_waiver_copy"]
    assert canonical_copy == {
        "wording_version": "advertiser-expedited-v2",
        "accepted_wording": canonical_wording,
        "accepted_wording_hash": hashlib.sha256(canonical_wording.encode()).hexdigest(),
    }

    altered_waiver = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/expedited-waiver",
        headers=owner_headers,
        json={**canonical_copy, "accepted_wording": f"{canonical_wording} altered"},
    )
    assert altered_waiver.status_code == 409, altered_waiver.text
    assert altered_waiver.json()["error"]["code"] == "EXPEDITED_WAIVER_COPY_MISMATCH"

    waiver = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/expedited-waiver",
        headers=owner_headers,
        json=canonical_copy,
    )
    assert waiver.status_code == 200, waiver.text
    retried_waiver = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/expedited-waiver",
        headers=owner_headers,
        json=canonical_copy,
    )
    assert retried_waiver.status_code == 200, retried_waiver.text
    assert retried_waiver.json()["id"] == waiver.json()["id"]

    async def accepted_effect_counts() -> tuple[int, int]:
        async with db_sessionmaker() as session:
            terms_events = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "commercial.terms.accepted")
            )
            waiver_events = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "billing.expedited_waiver.accepted")
            )
            return int(terms_events or 0), int(waiver_events or 0)

    assert asyncio.run(accepted_effect_counts()) == (1, 1)

    blocked = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/budget-policy-evaluation",
        headers=admin_headers,
    )
    assert blocked.status_code == 404


def test_payment_webhook_commits_then_enqueues_and_duplicate_reenqueues(
    db_client, db_sessionmaker
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "webhook")
    admin_headers = auth_headers(db_client, admin.email)
    owner_headers = auth_headers(db_client, owner.email)
    request = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/quote-request",
        headers=owner_headers,
        json={"request_details": {}},
    )
    revision = db_client.post(
        f"/api/v1/admin/quote-requests/{request.json()['id']}/revisions",
        headers=admin_headers,
        json={
            "quote_reference": "API-WEBHOOK-Q",
            "currency": "NGN",
            "line_items": [
                {"code": "MEDIA", "description": "Media", "kind": "media", "amount": "100.00"}
            ],
            "production_scope": {"vehicle_count": 1},
            "payment_class": "standard_prepaid",
            "payment_terms": {},
            "tax_rate": "0.00",
        },
    )
    terms = db_client.post(
        f"/api/v1/advertiser/quotations/{revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    ).json()

    async def issue() -> None:
        from invoice_helpers import issue_test_invoice

        from app.models.billing import CommercialTerms

        async with db_sessionmaker() as session:
            accepted = await session.get(CommercialTerms, UUID(terms["id"]))
            await issue_test_invoice(session, terms=accepted, admin=admin)
            await session.commit()

    asyncio.run(issue())
    fake = FakePaymentGatewayAdapter()

    class RecordingEnqueuer:
        def __init__(self) -> None:
            self.ids = []

        async def enqueue_payment_event(self, event_id) -> None:
            self.ids.append(event_id)

    enqueuer = RecordingEnqueuer()
    db_client.app.dependency_overrides[get_payment_gateway_adapter] = lambda: fake
    db_client.app.dependency_overrides[get_payment_event_enqueuer] = lambda: enqueuer
    payload = json.dumps(
        {
            "provider_event_id": "api-event-1",
            "external_transaction_id": "api-transaction-1",
            "event_type": "payment_confirmed",
            "commercial_terms_id": terms["id"],
            "organization_id": str(organization.id),
            "amount": "100.00",
            "currency": "NGN",
            "payer_name": "Gateway Advertiser",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    ).encode()
    headers = {"X-Payment-Signature": fake.sign_webhook(payload)}
    first = db_client.post("/api/v1/webhooks/payments", content=payload, headers=headers)
    second = db_client.post("/api/v1/webhooks/payments", content=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert len(enqueuer.ids) == 2
    assert str(enqueuer.ids[0]) == first.json()["event_id"]

    result = asyncio.run(sweep_payment_gateway_events({"sessionmaker": db_sessionmaker}))

    async def attempt_codes() -> list[str | None]:
        async with db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(PaymentGatewayProcessingAttempt.error_code).order_by(
                        PaymentGatewayProcessingAttempt.attempt_number
                    )
                )
            )

    assert result == {"selected": 1, "processed": 1, "failed": 0}, asyncio.run(attempt_codes())

    async def receipt_count() -> int:
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count()).select_from(PaymentReceipt)) or 0)

    assert asyncio.run(receipt_count()) == 1


def test_payment_webhook_missing_or_blank_signature_is_explicitly_unauthorized(db_client) -> None:
    payload = b"{}"

    missing = db_client.post("/api/v1/webhooks/payments", content=payload)
    blank = db_client.post(
        "/api/v1/webhooks/payments",
        content=payload,
        headers={"X-Payment-Signature": ""},
    )

    assert missing.status_code == blank.status_code == 401
    assert missing.json()["error"]["code"] == "PAYMENT_WEBHOOK_UNAUTHORIZED"
    assert blank.json()["error"]["code"] == "PAYMENT_WEBHOOK_UNAUTHORIZED"


def test_campaign_commercial_api_exposes_derived_invoice_status(
    db_client, db_sessionmaker, settings
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "invoice-projection")

    async def setup() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="API-INVOICE-PROJECTION",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-API-INVOICE-PROJECTION",
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
                correction_reference="billing-api-correction",
                correction_type=InvoiceCorrectionType.CREDIT_NOTE,
                net_amount="20.00",
                tax_amount="0.00",
                reason="approved scope reduction",
            )
            await session.commit()

    asyncio.run(setup())
    response = db_client.get(
        f"/api/v1/admin/campaigns/{campaign.id}/commercial",
        headers=auth_headers(db_client, admin.email),
    )

    assert response.status_code == 200, response.text
    invoice = response.json()["invoices"][0]
    assert invoice["effective_obligation_amount"] == "80.00"
    assert invoice["funded_amount"] == "0.00"
    assert invoice["payment_status"] == "unpaid"
    assert len(invoice["corrections"]) == 1
    assert invoice["corrections"][0]["correction_type"] == "credit_note"
    assert invoice["corrections"][0]["gross_amount"] == "20.00"


def test_invoice_correction_http_retry_is_stable_and_conflicts_on_changed_payload(
    db_client, db_sessionmaker, settings
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "correction-retry")

    async def setup():
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="API-CORRECTION-RETRY",
                amount="100.00",
            )
            draft = await create_invoice_draft(
                session, commercial_terms_id=terms.id, actor_user_id=admin.id
            )
            issuer = await _issuer(
                session,
                admin,
                IssuerVerificationStatus.SYNTHETIC,
                "SYNTHETIC-API-CORRECTION-RETRY",
                settings,
            )
            invoice = await issue_invoice(
                session,
                invoice_id=draft.id,
                issuer_profile_id=issuer.id,
                actor_user_id=admin.id,
                settings=settings,
            )
            await session.commit()
            return invoice.id

    invoice_id = asyncio.run(setup())
    headers = auth_headers(db_client, admin.email)
    payload = {
        "correction_reference": "http-retry-reference-001",
        "correction_type": "credit_note",
        "net_amount": "10.00",
        "tax_amount": "0.00",
        "reason": "approved correction",
    }
    first = db_client.post(
        f"/api/v1/admin/invoices/{invoice_id}/corrections", json=payload, headers=headers
    )
    replay = db_client.post(
        f"/api/v1/admin/invoices/{invoice_id}/corrections", json=payload, headers=headers
    )
    assert first.status_code == replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    conflict = db_client.post(
        f"/api/v1/admin/invoices/{invoice_id}/corrections",
        json=payload | {"reason": "changed correction"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "INVOICE_CORRECTION_REFERENCE_CONFLICT"


def test_duplicate_quote_reference_returns_conflict_without_losing_saved_revision(
    db_client, db_sessionmaker
):
    admin, owner, organization, first_campaign = _fixture(db_sessionmaker, "duplicate-reference")
    second_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        budget_amount="1000.00",
    )
    admin_headers = auth_headers(db_client, admin.email)
    owner_headers = auth_headers(db_client, owner.email)
    body = {
        "quote_reference": "DUPLICATE-Q",
        "currency": "NGN",
        "line_items": [
            {"code": "MEDIA", "description": "Media campaign", "kind": "media", "amount": "100.00"}
        ],
        "production_scope": {"vehicle_count": 1},
        "payment_class": "standard_prepaid",
        "payment_terms": {},
        "tax_rate": "0.075",
    }
    paths = []
    for campaign in (first_campaign, second_campaign):
        requested = db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/quote-request",
            headers=owner_headers,
            json={"request_details": {"vehicle_count": 1}},
        )
        assert requested.status_code == 201, requested.text
        paths.append(f"/api/v1/admin/quote-requests/{requested.json()['id']}/revisions")
    assert db_client.post(paths[0], headers=admin_headers, json=body).status_code == 201
    duplicate = db_client.post(paths[1], headers=admin_headers, json=body)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "QUOTE_REFERENCE_CONFLICT"
    retry = db_client.post(
        paths[1], headers=admin_headers, json=body | {"quote_reference": "UNIQUE-Q"}
    )
    assert retry.status_code == 201, retry.text
