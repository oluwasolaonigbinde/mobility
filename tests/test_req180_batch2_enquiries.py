import asyncio
from unittest.mock import AsyncMock

from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import func, select

from app.api.v1.campaign_enquiries import get_enquiry_limiter
from app.core.config import get_settings
from app.core.rate_limit import RateLimitDecision
from app.models.audit import AuditEvent
from app.models.campaign_enquiry import CampaignEnquiry
from app.models.organization import AdvertiserOrganization
from app.models.user import UserRole
from app.services.campaign_enquiries import convert_enquiry

PAYLOAD = {
    "company": "Saved brand",
    "contact_name": "Named contact",
    "email": "saved@example.test",
    "phone": "",
    "brief": "A quote for Abuja.",
}


def test_enquiries_persist_without_email_and_conversion_is_exact(
    db_client, db_sessionmaker, settings, caplog
):
    enabled = settings.model_copy(update={"campaign_enquiry_enabled": True, "email_provider": ""})
    db_client.app.dependency_overrides[get_settings] = lambda: enabled
    limiter = AsyncMock()
    limiter.reserve.return_value = RateLimitDecision(allowed=True)
    db_client.app.dependency_overrides[get_enquiry_limiter] = lambda: limiter
    admin = create_test_user(db_sessionmaker, email="enquiry-admin@example.test")
    owner = create_test_user(
        db_sessionmaker, email="enquiry-owner@example.test", role=UserRole.ADVERTISER
    )
    other = create_test_user(
        db_sessionmaker, email="enquiry-other@example.test", role=UserRole.ADVERTISER
    )
    create_test_organization(db_sessionmaker, owner_user_id=other.id)
    headers = auth_headers(db_client, admin.email)
    own_headers = auth_headers(db_client, owner.email)
    for company in ("Saved brand", "Second brand"):
        sent = db_client.post("/api/v1/campaign-enquiries", json={**PAYLOAD, "company": company})
        assert sent.status_code == 200 and sent.json() == {"status": "submitted"}
        assert PAYLOAD["email"] not in sent.text + caplog.text
    page = db_client.get(
        "/api/v1/admin/campaign-enquiries", headers=headers, params={"q": "brand", "limit": 1}
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert db_client.get("/api/v1/admin/campaign-enquiries", headers=own_headers).status_code == 403
    identity = page["items"][0]["id"]
    assert (
        db_client.get(f"/api/v1/admin/campaign-enquiries/{identity}", headers=headers).json()[
            "brief"
        ]
        == PAYLOAD["brief"]
    )
    assert (
        db_client.post(
            f"/api/v1/admin/campaign-enquiries/{identity}/create-advertiser",
            headers=headers,
            json={"owner_user_id": str(other.id)},
        ).status_code
        == 409
    )
    assert db_client.get("/api/v1/admin/campaign-enquiries", headers=headers).json()["total"] == 2

    async def concurrent_conversion():
        async def one():
            async with db_sessionmaker() as session:
                from uuid import UUID

                result = await convert_enquiry(
                    session,
                    actor_user_id=admin.id,
                    enquiry_id=UUID(identity),
                    owner_user_id=owner.id,
                    settings=enabled,
                )
                await session.commit()
                return result

        return await asyncio.gather(one(), one())

    organizations = asyncio.run(concurrent_conversion())
    assert organizations[0] == organizations[1]
    repeat = db_client.post(
        f"/api/v1/admin/campaign-enquiries/{identity}/create-advertiser",
        headers=headers,
        json={"owner_user_id": str(owner.id)},
    )
    assert repeat.json() == {"organization_id": str(organizations[0]), "status": "converted"}
    assert (
        db_client.post(
            f"/api/v1/admin/campaign-enquiries/{identity}/create-advertiser",
            headers=headers,
            json={"owner_user_id": None},
        ).status_code
        == 409
    )
    assert db_client.get("/api/v1/admin/campaign-enquiries", headers=headers).json()["total"] == 1
    converted = db_client.get(
        "/api/v1/admin/campaign-enquiries", headers=headers, params={"status": "converted"}
    ).json()
    assert converted["total"] == 1 and converted["items"][0]["organization_id"] == str(
        organizations[0]
    )
    limiter.reserve.return_value = RateLimitDecision(allowed=False, retry_after_seconds=5)
    assert db_client.post("/api/v1/campaign-enquiries", json=PAYLOAD).status_code == 429
    assert (
        db_client.post(
            "/api/v1/campaign-enquiries", json={**PAYLOAD, "email": "invalid"}
        ).status_code
        == 422
    )

    async def verify():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(CampaignEnquiry)) == 2
            org = await session.get(AdvertiserOrganization, organizations[0])
            assert org.billing_email == PAYLOAD["email"]
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "campaign_enquiry.converted")
                )
                == 1
            )

    asyncio.run(verify())
