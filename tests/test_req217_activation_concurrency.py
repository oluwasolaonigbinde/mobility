"""S23/D118 keeps driver/car exclusivity when Finished becomes a date projection."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_installation_evidence, fetch_user_by_email
from sqlalchemy import func, select
from test_campaign_assignments import (
    PASSWORD,
    assignment_payload,
    create_assignment_ready_graph,
)
from test_campaign_changes import _service_confirmation_payload
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import PaymentClass
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment
from app.schemas.campaign_assignments import CampaignAssignmentTransition
from app.services import campaign_assignments as assignments
from app.services.billing.authority import (
    record_approved_credit_authorization,
    record_production_start,
)
from app.services.campaign_changes import request_campaign_change
from app.services.campaign_lifecycle import assignment_window_open


@pytest.mark.parametrize("leading", [0, 1])
def test_cross_campaign_activation_serializes_and_finished_job_cannot_revive(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    leading,
):
    now = datetime.now(UTC)
    graphs = [
        create_assignment_ready_graph(
            db_sessionmaker,
            campaign_status=CampaignStatus.DRAFT,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=2),
            admin_email=f"exclusive-staff-{i}@example.com",
            advertiser_email=f"exclusive-owner-{i}@example.com",
            driver_email=f"exclusive-driver-{i}@example.com",
            plate_number=f"XCL-{i}",
        )
        for i in range(2)
    ]
    admin, _, driver, profile, vehicle = graphs[0]
    campaigns = [graph[1] for graph in graphs]
    owners = [
        fetch_user_by_email(db_sessionmaker, f"exclusive-owner-{i}@example.com") for i in range(2)
    ]
    staff_headers = auth_headers(db_client, admin.email, PASSWORD)
    identities = []
    for index, campaign in enumerate(campaigns):

        async def set_budget(campaign=campaign):
            async with db_sessionmaker() as session:
                row = await session.get(Campaign, campaign.id)
                row.budget_amount = 1000000
                await session.commit()

        asyncio.run(set_budget())
        assert (
            db_client.post(
                f"/api/v1/advertiser/campaigns/{campaign.id}/submit",
                headers=auth_headers(db_client, owners[index].email, PASSWORD),
            ).status_code
            == 200
        )
        assert (
            db_client.post(
                f"/api/v1/admin/campaigns/{campaign.id}/approve", headers=staff_headers
            ).status_code
            == 200
        )
        offered = db_client.post(
            "/api/v1/admin/campaign-assignments",
            headers=staff_headers,
            json=assignment_payload(campaign, profile, vehicle),
        )
        assert offered.status_code == 201, offered.text
        identity = UUID(offered.json()["id"])
        accepted = db_client.post(
            f"/api/v1/driver/campaign-assignments/{identity}/accept",
            headers=auth_headers(db_client, driver.email, PASSWORD),
            json={"metadata": {}},
        )
        assert accepted.status_code == 200, accepted.text
        create_test_installation_evidence(
            db_sessionmaker, assignment_id=identity, reviewed_by_user_id=admin.id
        )

        async def fund(campaign=campaign, index=index):
            async with db_sessionmaker() as session:
                await _accepted_terms(
                    session,
                    campaign=campaign,
                    admin=admin,
                    owner=owners[index],
                    reference=f"S23-EXCLUSIVITY-{index}",
                    amount="1000000.00",
                    payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                )
                await record_approved_credit_authorization(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    credit_limit="1000000.00",
                    max_driver_liability="1000000.00",
                    due_at=now + timedelta(days=3),
                    approved_by_user_id=admin.id,
                    credit_terms={"synthetic": True},
                    reason="Verify retained activation authority",
                )
                await record_production_start(
                    session, campaign_id=campaign.id, actor_user_id=admin.id
                )
                await session.commit()

        asyncio.run(fund())
        identities.append(identity)

    original_lock = assignments.acquire_work_eligibility_lock

    async def exercise():
        held, release = asyncio.Event(), asyncio.Event()
        first = True

        async def controlled_lock(*args, **kwargs):
            nonlocal first
            await original_lock(*args, **kwargs)
            if first:
                first = False
                held.set()
                await release.wait()

        monkeypatch.setattr(assignments, "acquire_work_eligibility_lock", controlled_lock)

        async def activate(index):
            async with db_sessionmaker() as session:
                try:
                    row = await assignments.activate_admin_assignment(
                        session,
                        admin_user_id=admin.id,
                        assignment_id=identities[index],
                        payload=CampaignAssignmentTransition(),
                        settings=settings,
                    )
                    await session.commit()
                    return row.status
                except AppError as error:
                    await session.rollback()
                    return error.code

        winner = asyncio.create_task(activate(leading))
        await asyncio.wait_for(held.wait(), 10)
        other = asyncio.create_task(activate(1 - leading))
        await asyncio.sleep(0.2)
        assert not other.done()
        release.set()
        assert await asyncio.wait_for(winner, 20) == "active"
        assert await asyncio.wait_for(other, 20) != "active"

        async with db_sessionmaker() as session:
            proposal = await _service_confirmation_payload(
                session,
                advertiser_id=owners[leading].id,
                campaign_id=campaigns[leading].id,
                client_request_id=uuid4(),
                end_at=now + timedelta(days=3),
                reason="Attempt an extension after this job has finished",
            )
            row = await session.get(Campaign, campaigns[leading].id)
            row.end_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

        async def extend_finished():
            async with db_sessionmaker() as session:
                with pytest.raises(AppError) as denied:
                    await request_campaign_change(
                        session,
                        actor_user_id=owners[leading].id,
                        campaign_id=campaigns[leading].id,
                        payload=proposal,
                    )
                assert denied.value.code == "CAMPAIGN_FINISHED"
                await session.rollback()

        restarted, _ = await asyncio.wait_for(
            asyncio.gather(activate(1 - leading), extend_finished()), 25
        )
        assert restarted == "active"
        async with db_sessionmaker() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CampaignAssignment)
                    .where(
                        CampaignAssignment.driver_profile_id == profile.id,
                        CampaignAssignment.status == "active",
                        assignment_window_open(),
                    )
                )
                == 1
            )

    asyncio.run(exercise())
