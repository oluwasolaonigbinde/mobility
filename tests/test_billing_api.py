import asyncio
import json
from datetime import UTC, datetime

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import func, select

from app.adapters.payments import FakePaymentGatewayAdapter
from app.api.v1.billing import get_payment_gateway_adapter
from app.api.v1.dependencies import get_payment_event_enqueuer
from app.jobs.payment_gateway import sweep_payment_gateway_events
from app.models.billing import PaymentGatewayProcessingAttempt, PaymentReceipt
from app.models.user import UserRole


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
    db_client, db_sessionmaker
) -> None:
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

    accepted = db_client.post(
        f"/api/v1/advertiser/quotations/{revision.json()['id']}/accept",
        headers=owner_headers,
        json={"acceptance_method": "in_platform"},
    )
    assert accepted.status_code == 200, accepted.text
    terms_id = accepted.json()["id"]

    premature = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=owner_headers,
        json={"status": "active"},
    )
    assert premature.status_code == 409
    assert premature.json()["error"]["code"] == "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED"

    transfer = db_client.post(
        "/api/v1/admin/billing/manual-transfers",
        headers=admin_headers,
        json={
            "organization_id": str(organization.id),
            "commercial_terms_id": terms_id,
            "external_transaction_id": "API-BANK-001",
            "observed_amount": "100.00",
            "expected_amount": "100.00",
            "currency": "NGN",
            "payer_name": "API Advertiser",
            "evidence_reference": "API-BANK-EVIDENCE-001",
            "observed_at": datetime.now(UTC).isoformat(),
        },
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

    blocked = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/budget-policy-evaluation",
        headers=admin_headers,
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["state"] == "blocked_external_policy"
    assert blocked.json()["billing_spend_amount"] is None


def test_payment_webhook_commits_then_enqueues_and_duplicate_reenqueues(
    db_client, db_sessionmaker
) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "webhook")
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
