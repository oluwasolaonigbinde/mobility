import asyncio

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_zone,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import event

from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.user import UserRole
from app.services.list_counts import campaign_list_counts


def test_navigation_counts_match_filtered_lists_and_group_pages_without_fanout(
    db_client, db_sessionmaker
):
    password = "navigation-test-password"
    admin = create_test_user(db_sessionmaker, email="counts-admin@example.test", password=password)
    advertiser = create_test_user(
        db_sessionmaker,
        email="counts-adv@example.test",
        password=password,
        role=UserRole.ADVERTISER,
    )
    driver = create_test_user(
        db_sessionmaker, email="counts-driver@example.test", password=password, role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    car = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    org, _ = create_test_organization(
        db_sessionmaker, name="Own company", owner_user_id=advertiser.id
    )
    other, _ = create_test_organization(db_sessionmaker, name="Other company")
    foreign = create_test_campaign(
        db_sessionmaker, organization_id=other.id, created_by_user_id=admin.id
    )
    campaigns = []
    active_id = None
    for index, assignment_status in enumerate(CampaignAssignmentStatus):
        status = (
            CampaignStatus.PENDING_REVIEW
            if index == 0
            else CampaignStatus.PAUSED
            if index == 1
            else CampaignStatus.ACTIVE
        )
        campaign = create_test_campaign(
            db_sessionmaker,
            organization_id=org.id,
            created_by_user_id=admin.id,
            name=f"Own job {index}",
            campaign_status=status,
        )
        if assignment_status in {
            CampaignAssignmentStatus.DECLINED,
            CampaignAssignmentStatus.EXPIRED,
        }:

            async def terminal_assignment(
                campaign_id=campaign.id, terminal_status=assignment_status
            ):
                from datetime import UTC, datetime

                now = datetime.now(UTC)
                async with db_sessionmaker() as session:
                    row = CampaignAssignment(
                        campaign_id=campaign_id,
                        driver_profile_id=profile.id,
                        vehicle_id=car.id,
                        assigned_by_user_id=admin.id,
                        status=terminal_status,
                        offered_at=now,
                        **{f"{terminal_status.value}_at": now},
                    )
                    session.add(row)
                    await session.commit()
                    return row

            assignment = asyncio.run(terminal_assignment())
        else:
            assignment = create_test_campaign_assignment(
                db_sessionmaker,
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=car.id,
                assigned_by_user_id=admin.id,
                assignment_status=assignment_status,
            )
        if assignment_status == CampaignAssignmentStatus.ACTIVE:
            active_id = str(assignment.id)
        campaigns.append(campaign)
    create_test_campaign_zone(
        db_sessionmaker, campaign_id=campaigns[0].id, created_by_user_id=admin.id
    )
    ah = auth_headers(db_client, admin.email, password)
    dh = auth_headers(db_client, driver.email, password)
    vh = auth_headers(db_client, advertiser.email, password)
    summary = db_client.get("/api/v1/driver/current-job", headers=dh)
    assert summary.status_code == 200, summary.text
    assert summary.json()["counts"] == {status.value: 1 for status in CampaignAssignmentStatus}
    assert summary.json()["assignment"]["id"] == active_id
    for status in CampaignAssignmentStatus:
        listed = db_client.get(
            "/api/v1/driver/campaign-assignments",
            headers=dh,
            params={"status": status.value, "limit": 1},
        )
        assert listed.json()["total"] == summary.json()["counts"][status.value]
    badges = db_client.get("/api/v1/admin/badge-summary", headers=ah).json()
    assert badges["source_counts"]["cars"] == 1
    assert badges["source_counts"]["jobs"] == 1
    assert badges["source_counts"]["campaigns"] == 1
    assert badges["source_counts"]["paused"] == 1
    assert badges["total"] == 4
    listed = db_client.get("/api/v1/advertiser/campaigns", headers=vh).json()
    assert listed["total"] == 8
    assert all(
        row["id"] != str(foreign.id) and row["assignment_count"] == 1 for row in listed["items"]
    )
    assert (
        next(row for row in listed["items"] if row["id"] == str(campaigns[0].id))[
            "target_zone_count"
        ]
        == 1
    )
    companies = db_client.get(
        "/api/v1/admin/advertiser-organizations", headers=ah, params={"limit": 1, "q": "Own"}
    ).json()
    assert companies["total"] == 1
    assert companies["items"][0]["member_count"] == 1
    assert companies["items"][0]["live_campaign_count"] == 7

    async def query_bound():
        engine = db_sessionmaker.kw["bind"]
        reads = []

        def record(_conn, _cursor, statement, *_args):
            if statement.lstrip().upper().startswith("SELECT"):
                reads.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            async with db_sessionmaker() as session:
                await campaign_list_counts(session, [campaigns[0].id])
                assert len(reads) == 2
                reads.clear()
                counts = await campaign_list_counts(session, [row.id for row in campaigns])
                assert len(reads) == 2
                assert counts[campaigns[0].id] == {"assignment_count": 1, "target_zone_count": 1}
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)

    asyncio.run(query_bound())
