"""S23/D118 derives Finished without reopening jobs or financial authority."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select
from test_campaign_changes import PASSWORD, _preview_and_confirm, change_graph

from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignActivationEvent, CampaignAssignment
from app.models.campaign_change import CampaignChangeRequest
from app.schemas.campaign_assignments import CampaignAssignmentCancel, CampaignAssignmentTransition
from app.services.campaign_assignments import (
    cancel_admin_assignment,
    deactivate_driver_assignment,
    ensure_not_expired,
)
from app.services.campaign_lifecycle import campaign_display_status
from app.services.reports import assignment_counts_for_campaign, assignment_counts_for_org


def test_ended_campaign_cannot_be_extended_and_pending_change_cannot_cross_end(
    db_client,
    db_sessionmaker,
    monkeypatch,
):
    admin, owner, campaign = change_graph(db_sessionmaker, "finished-change")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    _, pending = _preview_and_confirm(
        db_client,
        campaign_id=campaign.id,
        headers=headers,
        payload={
            "client_request_id": str(uuid4()),
            "daily_budget_amount": "80.00",
            "reason": "Review a proposed reduction",
        },
    )
    assert pending.status_code == 201 and pending.json()["status"] == "pending_admin"
    end = campaign.end_at

    async def after_end(_session):
        return end + timedelta(seconds=1)

    monkeypatch.setattr("app.services.campaign_changes.database_clock", after_end)
    preview = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-preview",
        headers=headers,
        json={
            "end_at": (end + timedelta(days=5)).isoformat(),
            "reason": "Try to extend a finished campaign",
        },
    )
    assert preview.status_code == 409 and preview.json()["error"]["code"] == "CAMPAIGN_FINISHED"
    decision = db_client.post(
        f"/api/v1/admin/campaign-change-requests/{pending.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Try to approve after the campaign end"},
    )
    assert decision.status_code == 409 and decision.json()["error"]["code"] == "CAMPAIGN_FINISHED"

    async def unchanged():
        async with db_sessionmaker() as session:
            row = await session.get(Campaign, campaign.id)
            request = await session.get(CampaignChangeRequest, UUID(pending.json()["id"]))
            assert row.end_at == end and request.status == "pending_admin"
            assert request.applied_at is None

    asyncio.run(unchanged())


def test_finished_assignment_counts_and_mutations_use_end_date(db_sessionmaker):
    admin, owner, campaign = change_graph(db_sessionmaker, "finished-assignment")
    driver = create_test_user(db_sessionmaker, email="finished-driver@example.com", role="driver")
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        assigned_by_user_id=admin.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assignment_status="active",
        activated_at=datetime.now(UTC) - timedelta(days=2),
    )
    # The same driver/car can now belong to a different current campaign.
    current = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=owner.id,
        campaign_status="active",
        start_at=datetime.now(UTC) - timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=10),
    )

    async def mark_ended():
        async with db_sessionmaker() as session:
            row = await session.get(Campaign, campaign.id)
            row.end_at = datetime.now(UTC) - timedelta(hours=1)
            row.start_at = row.end_at - timedelta(days=5)
            await session.commit()

    asyncio.run(mark_ended())
    create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=current.id,
        assigned_by_user_id=admin.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assignment_status="active",
        activated_at=datetime.now(UTC),
    )

    async def exercise():
        async with db_sessionmaker() as session:
            total = await assignment_counts_for_org(session, campaign.organization_id)
            own = await assignment_counts_for_campaign(session, campaign.id)
            assert total.total == 2 and total.finished == 1 and total.active == 1
            assert own.total == own.finished == 1 and own.active == 0
            events = await session.scalar(select(func.count()).select_from(CampaignActivationEvent))
        for action in ("cancel", "deactivate"):
            async with db_sessionmaker() as session:
                with pytest.raises(AppError) as denied:
                    if action == "cancel":
                        await cancel_admin_assignment(
                            session,
                            admin_user_id=admin.id,
                            assignment_id=assignment.id,
                            payload=CampaignAssignmentCancel(reason="Check finished protection"),
                        )
                    else:
                        await deactivate_driver_assignment(
                            session,
                            user_id=driver.id,
                            assignment_id=assignment.id,
                            payload=CampaignAssignmentTransition(),
                        )
                assert denied.value.code == "ASSIGNMENT_FINISHED"
                await session.rollback()
        async with db_sessionmaker() as session:
            saved = await session.get(CampaignAssignment, assignment.id)
            assert saved.status == "active" and saved.cancelled_at is saved.deactivated_at is None
            assert (
                await session.scalar(select(func.count()).select_from(CampaignActivationEvent))
                == events
            )
            row = await session.get(Campaign, campaign.id)
            assert campaign_display_status(row.status, row.end_at) == "finished"
            # Exactly at the end is closed, as the read projection says.
            with pytest.raises(AppError, match="already ended"):
                ensure_not_expired(row, row.end_at, code="CAMPAIGN_EXPIRED")

    asyncio.run(exercise())
