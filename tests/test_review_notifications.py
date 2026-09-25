# ruff: noqa: F401, F811
"""Advertisers are told about every review decision and each new quotation (W2-04C)."""

import asyncio
from uuid import UUID, uuid4

from conftest import auth_headers, create_test_campaign, create_test_user
from sqlalchemy import select
from test_campaigns import PASSWORD, create_advertiser_with_org
from test_commercial_terms import _commercial_fixture
from test_creative_reviews import _managed_draft
from test_file_scanning import confirm_png, file_boundaries, scan_file

from app.models.billing import PaymentClass, QuoteRequestSource
from app.models.campaign import CreativeStatus
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.models.organization import MembershipRole
from app.services.billing import record_quotation_revision, request_custom_quote
from app.services.campaigns import decide_creative_review
from app.services.email_templates import render_email_template


def _notifications(db_sessionmaker, type_key: NotificationType) -> list[Notification]:
    async def read() -> list[Notification]:
        async with db_sessionmaker() as session:
            return list(
                await session.scalars(
                    select(Notification)
                    .where(Notification.type_key == type_key.value)
                    .order_by(Notification.channel)
                )
            )

    return asyncio.run(read())


def test_campaign_rejection_notifies_without_copying_the_reason(db_client, db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="notify-admin@example.com", password=PASSWORD)
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker, email="notify-manager@example.com", role=MembershipRole.MANAGER
    )
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=advertiser.id
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    reason = "Private reviewer note: replace the fleet count"

    db_client.post(f"/api/v1/advertiser/campaigns/{campaign.id}/submit", headers=advertiser_headers)
    rejected = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/reject",
        headers=admin_headers,
        json={"reason": reason},
    )
    assert rejected.status_code == 200, rejected.text

    notices = _notifications(db_sessionmaker, NotificationType.CAMPAIGN_REJECTED)
    assert [(notice.recipient_user_id, notice.channel) for notice in notices] == [
        (advertiser.id, NotificationChannel.IN_APP.value),
        (advertiser.id, NotificationChannel.TRANSACTIONAL_EMAIL.value),
    ]
    assert all(reason not in repr(notice.payload) for notice in notices)
    assert notices[0].payload["campaign_id"] == str(campaign.id)
    email = render_email_template(
        notices[1].type_key, notices[1].template_version, notices[1].payload
    )
    assert reason not in email.text_body
    feed = db_client.get("/api/v1/notifications", headers=advertiser_headers).json()["items"]
    assert [(item["title"], reason in item["body"]) for item in feed] == [
        ("Campaign needs changes", False)
    ]

    db_client.post(f"/api/v1/advertiser/campaigns/{campaign.id}/submit", headers=advertiser_headers)
    approved = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/approve", headers=admin_headers
    )
    assert approved.status_code == 200, approved.text
    assert len(_notifications(db_sessionmaker, NotificationType.CAMPAIGN_APPROVED)) == 2


def test_rejected_campaign_edit_and_resubmission_journey_on_postgresql(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    """The edit form's PATCH (changed fields only) repairs a rejection end to end."""
    admin = create_test_user(
        postgis_db_sessionmaker, email="journey-admin@example.com", password=PASSWORD
    )
    advertiser, organization = create_advertiser_with_org(
        postgis_db_sessionmaker, email="journey-owner@example.com"
    )
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="Journey campaign",
    )
    advertiser_headers = auth_headers(postgis_db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(postgis_db_client, admin.email, PASSWORD)
    base = f"/api/v1/advertiser/campaigns/{campaign.id}"

    assert postgis_db_client.post(f"{base}/submit", headers=advertiser_headers).status_code == 200
    rejected = postgis_db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/reject",
        headers=admin_headers,
        json={"reason": "Start a day later"},
    )
    assert rejected.json()["status"] == "rejected"

    edited = postgis_db_client.patch(
        base,
        headers=advertiser_headers,
        json={"name": "Journey campaign v2", "start_at": "2026-10-02T08:00:00.000Z"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "rejected"
    assert edited.json()["name"] == "Journey campaign v2"
    assert edited.json()["start_at"].startswith("2026-10-02T08:00:00")

    resubmitted = postgis_db_client.post(f"{base}/submit", headers=advertiser_headers)
    assert resubmitted.json()["status"] == "pending_review"
    frozen = postgis_db_client.patch(base, headers=advertiser_headers, json={"name": "Late edit"})
    assert frozen.status_code == 409
    approved = postgis_db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/approve", headers=admin_headers
    )
    assert approved.json()["status"] == "approved"
    history = postgis_db_client.get(f"{base}/review-history", headers=advertiser_headers).json()
    snapshot = next(
        item["reviewed_snapshot"]
        for item in history["items"]
        if item["new_status"] == "pending_review" and item["prior_status"] == "rejected"
    )
    assert snapshot["name"] == "Journey campaign v2"


def test_creative_decisions_notify_the_owning_company(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    admin = create_test_user(
        db_sessionmaker, email="notify-creative-admin@example.com", password=PASSWORD
    )
    advertiser, campaign, creative, _ = _managed_draft(
        db_client, db_sessionmaker, file_boundaries, email="notify-creative@example.com"
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    base = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative['id']}"

    db_client.post(f"{base}/submit", headers=advertiser_headers)
    rejected = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/reject",
        headers=admin_headers,
        json={"reason": "Logo is cropped"},
    )
    assert rejected.status_code == 200, rejected.text
    rejection_notices = _notifications(db_sessionmaker, NotificationType.CREATIVE_REJECTED)
    assert {notice.recipient_user_id for notice in rejection_notices} == {advertiser.id}
    assert rejection_notices[0].payload["creative_id"] == creative["id"]
    assert "Logo is cropped" not in repr(rejection_notices[0].payload)

    replacement = confirm_png(db_client, storage, advertiser.email, client_request_id=str(uuid4()))
    scan_file(db_sessionmaker, replacement["id"], storage, scanner)
    db_client.patch(
        base,
        headers=advertiser_headers,
        json={"stored_file_id": replacement["id"], "creative_type": "image"},
    )
    db_client.post(f"{base}/submit", headers=advertiser_headers)
    approved = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/approve", headers=admin_headers
    )
    assert approved.status_code == 200, approved.text
    feed_titles = [
        item["title"]
        for item in db_client.get("/api/v1/notifications", headers=advertiser_headers).json()[
            "items"
        ]
    ]
    assert "Artwork approved" in feed_titles
    assert "Artwork needs changes" in feed_titles


def test_creative_decision_service_notifies_with_identifiers_only(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="notify-creative-service-admin@example.com", password=PASSWORD
    )
    advertiser, campaign, creative, _ = _managed_draft(
        db_client, db_sessionmaker, file_boundaries, email="notify-creative-service@example.com"
    )
    base = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative['id']}"
    submitted = db_client.post(
        f"{base}/submit", headers=auth_headers(db_client, advertiser.email, PASSWORD)
    )
    assert submitted.status_code == 200, submitted.text

    async def decide() -> None:
        async with db_sessionmaker() as session:
            await decide_creative_review(
                session,
                admin_user_id=admin.id,
                creative_id=UUID(creative["id"]),
                target_status=CreativeStatus.REJECTED,
                rejection_reason="Colours are off-brand",
            )
            await session.commit()

    asyncio.run(decide())

    notices = _notifications(db_sessionmaker, NotificationType.CREATIVE_REJECTED)
    assert {notice.recipient_user_id for notice in notices} == {advertiser.id}
    assert {notice.channel for notice in notices} == {
        NotificationChannel.IN_APP.value,
        NotificationChannel.TRANSACTIONAL_EMAIL.value,
    }
    identifiers = {"campaign_id", "creative_id", "creative_review_event_id"}
    # The email row also carries the organization scope added by the email helper.
    assert {notice.channel: set(notice.payload) for notice in notices} == {
        NotificationChannel.IN_APP.value: identifiers,
        NotificationChannel.TRANSACTIONAL_EMAIL.value: identifiers | {"advertiser_organization_id"},
    }


def test_only_in_platform_quotations_ask_the_advertiser_to_review(db_sessionmaker) -> None:
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)
    external_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=admin.id,
        name="Externally agreed campaign",
    )

    async def record(campaign_id, source, actor_id) -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign_id,
                actor_user_id=actor_id,
                source=source,
                request_details={"brief": "Abuja launch"},
            )
            await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference=f"CV-Q-{source.value}",
                currency="NGN",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Campaign media",
                        "kind": "media",
                        "amount": "100000.00",
                    }
                ],
                production_scope={"vehicle_count": 10},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0.075",
            )
            await session.commit()

    asyncio.run(record(campaign.id, QuoteRequestSource.IN_PLATFORM, owner.id))
    asyncio.run(record(external_campaign.id, QuoteRequestSource.EXTERNAL_RECORDED, admin.id))

    notices = _notifications(db_sessionmaker, NotificationType.QUOTATION_READY)
    assert {(notice.recipient_user_id, notice.payload["campaign_id"]) for notice in notices} == {
        (owner.id, str(campaign.id))
    }
