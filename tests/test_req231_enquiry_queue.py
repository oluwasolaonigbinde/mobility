import asyncio

from conftest import auth_headers, create_test_user

from app.models.campaign_enquiry import CampaignEnquiry


def test_enquiry_badge_matches_new_list_and_disappears_after_conversion(db_client, db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="queue-admin@example.invalid")

    async def seed():
        async with db_sessionmaker() as session:
            enquiry = CampaignEnquiry(
                company="Queue company",
                contact_name="Enquiry contact",
                email="contact@example.invalid",
                phone="",
                brief="Advertise in Abuja",
            )
            session.add(enquiry)
            await session.commit()
            return enquiry.id

    enquiry_id = asyncio.run(seed())
    headers = auth_headers(db_client, admin.email)
    listed = db_client.get("/api/v1/admin/campaign-enquiries?status=new", headers=headers)
    badges = db_client.get("/api/v1/admin/badge-summary", headers=headers)
    assert listed.status_code == badges.status_code == 200
    assert listed.json()["total"] == badges.json()["source_counts"]["enquiries"] == 1
    assert badges.json()["support"] == badges.json()["total"] == 1
    converted = db_client.post(
        f"/api/v1/admin/campaign-enquiries/{enquiry_id}/create-advertiser", headers=headers, json={}
    )
    assert converted.status_code == 200, converted.text
    assert (
        db_client.get("/api/v1/admin/campaign-enquiries?status=new", headers=headers).json()[
            "total"
        ]
        == 0
    )
    badges = db_client.get("/api/v1/admin/badge-summary", headers=headers).json()
    assert badges["source_counts"]["enquiries"] == badges["support"] == badges["total"] == 0
