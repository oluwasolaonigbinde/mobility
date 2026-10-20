"""REQ-193/194 and D103/D104 edge cases: booked amount, cancellation requests, staff cancel."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import auth_headers, create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import func, select, update
from test_budget_enforcement_w2_01e import (
    HALF_QUOTE,
    accepted_terms,
    correct,
    fund,
    in_production,
    raised_budget_in_production,
)

from app.models.billing import BudgetCampaignTransition, PaymentReceipt, ReceiptAllocation
from app.models.complaint import Complaint, ComplaintReferenceType
from app.models.notification import Notification
from app.models.organization import OrganizationMembership
from app.models.user import User, UserRole
from app.schemas.campaign_cancellations import CampaignCancellationCreate
from app.schemas.complaints import ComplaintCategory
from app.services import complaints
from app.services.billing import budget
from app.services.billing.receipts import reverse_payment_receipt
from app.services.campaign_cancellations import request_campaign_cancellation

BUDGET_NOTICE_TYPES = ("budget_alert", "budget_urgent_alert", "campaign_budget_paused")


def _actors(maker, tag, *, status="active", budget_amount="1000.00", currency="NGN"):
    admin = create_test_user(maker, email=f"{tag}-admin@example.com")
    owner = create_test_user(maker, email=f"{tag}-owner@example.com", role=UserRole.ADVERTISER)
    organization, _ = create_test_organization(maker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        maker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        campaign_status=status,
        budget_amount=budget_amount,
        currency=currency,
    )
    return admin, owner, organization, campaign


def _detail(client, headers, campaign):
    response = client.get(f"/api/v1/advertiser/campaigns/{campaign.id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["budget_used"]


async def _staff_cancel(session, *, admin, campaign, reason="Advertiser asked Terrax to stop"):
    return await request_campaign_cancellation(
        session,
        actor_user_id=admin.id,
        actor_session_version=admin.session_version,
        campaign_id=campaign.id,
        payload=CampaignCancellationCreate(client_request_id=uuid4(), reason=reason),
    )


def test_budget_used_is_the_booked_total_on_every_advertiser_response(
    db_client, db_sessionmaker, settings
):
    admin, owner, organization, funded = _actors(db_sessionmaker, "used-read")
    usd = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        budget_amount="500.00",
        currency="USD",
        name="Dollar draft",
    )
    produced = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        campaign_status="active",
        budget_amount="1000.00",
        daily_budget_amount="50.00",
        name="In production",
    )
    stranger = create_test_user(
        db_sessionmaker, email="used-read-stranger@example.com", role=UserRole.ADVERTISER
    )
    create_test_organization(db_sessionmaker, owner_user_id=stranger.id)
    headers = auth_headers(db_client, owner.email)

    empty = _detail(db_client, headers, funded)
    assert {key: empty[key] for key in ("amount", "budget_amount", "currency", "basis")} == {
        "amount": "0.00",
        "budget_amount": "1000.00",
        "currency": "NGN",
        "basis": "funding",
    }
    assert datetime.fromisoformat(empty["as_of"].replace("Z", "+00:00")).tzinfo is not None

    async def book():
        async with db_sessionmaker() as session:
            terms = await accepted_terms(
                session, campaign=funded, admin=admin, owner=owner, line_items=HALF_QUOTE
            )
            await fund(
                session,
                terms=terms,
                organization=organization,
                admin=admin,
                reference="USED-DEPOSIT",
                amount="250.00",
            )
            produced_terms = await accepted_terms(
                session,
                campaign=produced,
                admin=admin,
                owner=owner,
                line_items=HALF_QUOTE,
                quote_reference="USED-Q2",
            )
            invoice = await in_production(
                session,
                campaign=produced,
                terms=produced_terms,
                organization=organization,
                admin=admin,
                owner=owner,
                settings=settings,
            )
            # An extra charge takes the booked amount above the budget.
            await correct(
                session, invoice=invoice, admin=admin, reference="USED-X", amount="600.00"
            )
            evaluation = await budget.evaluate_campaign_budget_policy(
                session, campaign_id=produced.id
            )
            locked = [
                await budget._campaign_billing_spend(session, campaign_id=row.id)
                for row in (funded, produced)
            ]
            await session.commit()
            return evaluation, locked

    evaluation, locked = asyncio.run(book())
    deposit = _detail(db_client, headers, funded)
    assert (deposit["amount"], deposit["basis"]) == ("250.00", "funding")
    assert Decimal(deposit["amount"]) == locked[0][0]
    over = _detail(db_client, headers, produced)
    # A daily budget never changes the figure: it is always the booked total.
    assert over == {**over, "amount": "1100.00", "budget_amount": "1000.00", "basis": "invoice"}
    assert Decimal(over["amount"]) == locked[1][0] == evaluation.billing_spend_amount
    assert evaluation.budget_basis == "total"

    listing = db_client.get("/api/v1/advertiser/campaigns", headers=headers).json()["items"]
    by_id = {item["id"]: item["budget_used"] for item in listing}
    assert by_id[str(usd.id)]["currency"] == "USD" and by_id[str(usd.id)]["amount"] == "0.00"
    assert by_id[str(produced.id)]["amount"] == "1100.00"
    patched = db_client.patch(
        f"/api/v1/advertiser/campaigns/{usd.id}", headers=headers, json={"name": "Dollar plan"}
    )
    assert patched.status_code == 200 and patched.json()["budget_used"]["currency"] == "USD"
    created = db_client.post(
        "/api/v1/advertiser/campaigns", headers=headers, json={"name": "No budget yet"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["budget_used"]["amount"] == "0.00"
    assert created.json()["budget_used"]["budget_amount"] is None
    foreign = db_client.get(
        f"/api/v1/advertiser/campaigns/{funded.id}", headers=auth_headers(db_client, stranger.email)
    )
    assert foreign.status_code == 404


def test_cancelled_campaigns_keep_a_truthful_booked_amount_and_no_repeat_notices(
    db_client, db_sessionmaker, settings
):
    admin, owner, organization, running = _actors(db_sessionmaker, "used-cancel")
    early = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        campaign_status="active",
        budget_amount="500.00",
        name="Cancelled before production",
    )
    headers = auth_headers(db_client, owner.email)

    async def exercise():
        async with db_sessionmaker() as session:
            _terms, invoice = await raised_budget_in_production(
                session,
                campaign=running,
                admin=admin,
                owner=owner,
                organization=organization,
                settings=settings,
            )
            await correct(session, invoice=invoice, admin=admin, reference="CXL-X", amount="350.00")
            alert = await budget.evaluate_campaign_budget_policy(session, campaign_id=running.id)
            assert alert.state == "alert_threshold"
            notices = await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.type_key.in_(BUDGET_NOTICE_TYPES))
            )
            await _staff_cancel(session, admin=admin, campaign=running)
            for _ in range(2):
                await budget.sweep_budget_policy_evaluations(session)
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key.in_(BUDGET_NOTICE_TYPES))
                )
                == notices
            )
            assert (
                await session.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                == 0
            )
            settled = (await budget._campaign_billing_spend(session, campaign_id=running.id))[0]

            early_terms = await accepted_terms(
                session,
                campaign=early,
                admin=admin,
                owner=owner,
                line_items=HALF_QUOTE,
                quote_reference="CXL-Q2",
            )
            await fund(
                session,
                terms=early_terms,
                organization=organization,
                admin=admin,
                reference="CXL-EARLY",
                amount="500.00",
            )
            cancellation = await _staff_cancel(session, admin=admin, campaign=early)
            assert cancellation.disposition == "cash_refund_due"
            receipt = await session.scalar(
                select(PaymentReceipt)
                .join(ReceiptAllocation, ReceiptAllocation.receipt_id == PaymentReceipt.id)
                .where(ReceiptAllocation.commercial_terms_id == early_terms.id)
            )
            await reverse_payment_receipt(
                session, receipt_id=receipt.id, actor_user_id=admin.id, reason="refund"
            )
            await session.commit()
            return settled

    settled = asyncio.run(exercise())
    after = _detail(db_client, headers, running)
    assert (after["amount"], after["basis"]) == (f"{settled:.2f}", "invoice")
    assert Decimal(after["amount"]) == Decimal("850.00")
    assert _detail(db_client, headers, early)["amount"] == "0.00"
    # Staff cannot cancel a campaign that already ended.
    completed = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        campaign_status="completed",
        budget_amount="100.00",
        name="Already finished",
    )
    refused = db_client.post(
        f"/api/v1/admin/campaigns/{completed.id}/cancel",
        headers=auth_headers(db_client, admin.email),
        json={"client_request_id": str(uuid4()), "reason": "Too late"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "CAMPAIGN_CANCELLATION_NOT_AVAILABLE"


def test_pending_cancellation_read_is_tenant_scoped_and_survives_the_list_limit(
    db_client, db_sessionmaker
):
    _, owner, _, campaign = _actors(db_sessionmaker, "pending-read")
    _, stranger, _, other_campaign = _actors(db_sessionmaker, "pending-other")

    async def raise_many():
        async with db_sessionmaker() as session:
            user = await session.get(User, owner.id)
            complaint_owner = await complaints.advertiser_owner(session, user)
            request = await complaints.raise_complaint(
                session,
                owner=complaint_owner,
                category=ComplaintCategory.CAMPAIGN_CANCELLATION,
                message="Please cancel this campaign.",
                reference_type=ComplaintReferenceType.CAMPAIGN,
                reference_id=campaign.id,
                client_request_id=uuid4(),
            )
            for index in range(complaints.COMPLAINANT_LIST_LIMIT):
                await complaints.raise_complaint(
                    session,
                    owner=complaint_owner,
                    category=ComplaintCategory.OTHER,
                    message=f"Question {index}",
                    reference_type=None,
                    reference_id=None,
                    client_request_id=uuid4(),
                )
            # The request is older than the 100 most recent threads.
            await session.execute(
                update(Complaint)
                .where(Complaint.id == request.complaint.id)
                .values(last_message_at=datetime.now(UTC) - timedelta(days=30))
            )
            await session.commit()
            return request.complaint.id

    request_id = asyncio.run(raise_many())
    headers = auth_headers(db_client, owner.email)
    unfiltered = db_client.get("/api/v1/advertiser/complaints", headers=headers).json()["items"]
    assert len(unfiltered) == 100 and all(
        item["category"] != "campaign_cancellation" for item in unfiltered
    )
    filtered = db_client.get(
        "/api/v1/advertiser/complaints", headers=headers, params={"campaign_id": str(campaign.id)}
    ).json()["items"]
    assert [(item["id"], item["category"], item["status"]) for item in filtered] == [
        (str(request_id), "campaign_cancellation", "open")
    ]
    stranger_headers = auth_headers(db_client, stranger.email)
    for target in (campaign.id, uuid4()):
        assert (
            db_client.get(
                "/api/v1/advertiser/complaints",
                headers=stranger_headers,
                params={"campaign_id": str(target)},
            ).json()["items"]
            == []
        )
    assert (
        db_client.get(
            "/api/v1/advertiser/complaints",
            headers=headers,
            params={"campaign_id": str(other_campaign.id)},
        ).json()["items"]
        == []
    )


def test_converting_an_enquiry_never_links_an_existing_user_by_email(
    db_client, db_sessionmaker, settings
):
    from unittest.mock import AsyncMock

    from app.api.v1.campaign_enquiries import get_enquiry_limiter
    from app.core.config import get_settings
    from app.core.rate_limit import RateLimitDecision

    enabled = settings.model_copy(update={"campaign_enquiry_enabled": True, "email_provider": ""})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    limiter = AsyncMock()
    limiter.reserve.return_value = RateLimitDecision(allowed=True)
    db_client.app.dependency_overrides[get_enquiry_limiter] = lambda: limiter
    admin = create_test_user(db_sessionmaker, email="enquiry-existing-admin@example.test")
    existing = create_test_user(
        db_sessionmaker, email="already-here@example.test", role=UserRole.ADVERTISER
    )
    sent = db_client.post(
        "/api/v1/campaign-enquiries",
        json={
            "company": "Existing person brand",
            "contact_name": "Someone",
            "email": "  Already-Here@Example.test ",
            "phone": "",
            "brief": "A quote please.",
        },
    )
    assert sent.status_code == 200, sent.text
    headers = auth_headers(db_client, admin.email)
    identity = db_client.get("/api/v1/admin/campaign-enquiries", headers=headers).json()["items"][
        0
    ]["id"]
    converted = db_client.post(
        f"/api/v1/admin/campaign-enquiries/{identity}/create-advertiser",
        headers=headers,
        json={"owner_user_id": None},
    )
    assert converted.status_code == 200, converted.text

    async def verify():
        async with db_sessionmaker() as session:
            user = await session.get(User, existing.id)
            memberships = await session.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(OrganizationMembership.user_id == existing.id)
            )
            return user, memberships

    user, memberships = asyncio.run(verify())
    assert memberships == 0
    assert (user.role, user.status, user.email) == (
        existing.role,
        existing.status,
        existing.email,
    )
