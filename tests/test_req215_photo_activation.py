"""Photo approval reuses funded activation and preserves approval on blocked work."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from conftest import auth_headers, create_test_user, fetch_user_by_email
from sqlalchemy import func, select
from test_campaign_assignments import PASSWORD, create_assignment_ready_graph, post_assignment
from test_installation_evidence import evidence_payload
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import CampaignLiabilityReservation, PaymentClass
from app.models.campaign import Campaign, CampaignCreative, CampaignStatus
from app.models.campaign_assignment import CampaignActivationEvent, CampaignAssignment
from app.models.driver import DriverProfile
from app.models.installation_evidence import InstallationEvidenceSubmission
from app.models.vehicle import Vehicle
from app.services import installation_evidence
from app.services.billing.authority import (
    record_approved_credit_authorization,
    record_production_start,
)


@pytest.mark.parametrize(
    "authority",
    [
        "ready",
        "concurrent",
        "missing_production",
        "missing_funding",
        "future_window",
        "ended_window",
        "driver_suspended",
        "car_inactive",
        "artwork_archived",
        "changed_terms",
    ],
)
def test_photo_approval_starts_only_fully_authorized_work(
    db_client, db_sessionmaker, settings, monkeypatch, authority
):
    now = datetime.now(UTC)
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(
        db_sessionmaker,
        campaign_status=CampaignStatus.DRAFT,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(days=2),
    )
    owner = fetch_user_by_email(db_sessionmaker, "advertiser@example.com")

    async def prepare_review():
        async with db_sessionmaker() as session:
            current = await session.get(Campaign, campaign.id)
            current.budget_amount = 1000000
            await session.commit()

    asyncio.run(prepare_review())
    submitted_campaign = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/submit",
        headers=auth_headers(db_client, owner.email, PASSWORD),
    )
    assert submitted_campaign.status_code == 200, submitted_campaign.text
    approved_campaign = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert approved_campaign.status_code == 200, approved_campaign.text
    offered = post_assignment(db_client, campaign, profile, vehicle)
    assert offered.status_code == 201, offered.text
    assignment_id = UUID(offered.json()["id"])
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/accept",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json={"metadata": {}},
    )
    assert accepted.status_code == 200, accepted.text

    async def fund():
        async with db_sessionmaker() as session:
            await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="PHOTO-AUTO",
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
                reason="Photo activation regression",
            )
            if authority != "missing_production":
                await record_production_start(
                    session, campaign_id=campaign.id, actor_user_id=admin.id
                )
            await session.commit()

    if authority != "missing_funding":
        asyncio.run(fund())
    submitted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence",
        headers=auth_headers(db_client, driver.email, PASSWORD),
        json=evidence_payload(db_sessionmaker, driver_id=driver.id),
    )
    assert submitted.status_code == 201, submitted.text

    async def revoke():
        async with db_sessionmaker() as session:
            if authority == "future_window":
                current = await session.get(Campaign, campaign.id)
                current.start_at = now + timedelta(days=1)
            elif authority == "ended_window":
                current = await session.get(Campaign, campaign.id)
                current.end_at = now - timedelta(minutes=1)
            elif authority == "driver_suspended":
                current = await session.get(DriverProfile, profile.id)
                current.onboarding_status = "suspended"
            elif authority == "car_inactive":
                current = await session.get(Vehicle, vehicle.id)
                current.status = "inactive"
            elif authority == "artwork_archived":
                current = await session.get(
                    CampaignCreative, UUID(campaign.campaign_metadata["_test_creative_id"])
                )
                current.status = "archived"
            elif authority == "changed_terms":
                current = await session.get(CampaignAssignment, assignment_id)
                current.offer_terms_sha256 = "0" * 64
            await session.commit()

    asyncio.run(revoke())
    if authority == "concurrent":
        other_admin = create_test_user(db_sessionmaker, email="second-photo-reviewer@example.com")
        original_lock = installation_evidence.acquire_campaign_terms_lock
        held, attempted, acquired, release = (asyncio.Event() for _ in range(4))
        calls = 0

        async def controlled_lock(session, campaign_id):
            nonlocal calls
            calls += 1
            leading = calls == 1
            if not leading:
                attempted.set()
            await original_lock(session, campaign_id)
            if leading:
                held.set()
                await release.wait()
            else:
                acquired.set()

        monkeypatch.setattr(installation_evidence, "acquire_campaign_terms_lock", controlled_lock)

        async def race():
            async def review(actor):
                async with db_sessionmaker() as session:
                    try:
                        photo, readiness = await installation_evidence.review_installation_evidence(
                            session,
                            actor_user_id=actor,
                            submission_id=UUID(submitted.json()["id"]),
                            approve=True,
                            reason=None,
                            settings=settings,
                        )
                        result = {
                            "id": str(photo.id),
                            "status": photo.status,
                            "activation": readiness.model_dump(),
                        }
                        await session.commit()
                        return result
                    except AppError as exc:
                        await session.rollback()
                        return exc.code

            first = asyncio.create_task(review(admin.id))
            await asyncio.wait_for(held.wait(), 5)
            second = asyncio.create_task(review(other_admin.id))
            await asyncio.wait_for(attempted.wait(), 5)
            try:
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(acquired.wait(), 0.15)
            finally:
                release.set()
            winner, loser = await asyncio.wait_for(asyncio.gather(first, second), 15)
            assert loser == "INSTALLATION_EVIDENCE_ALREADY_REVIEWED"
            return winner

        result = asyncio.run(race())
    else:
        approval = db_client.post(
            f"/api/v1/admin/installation-evidence/{submitted.json()['id']}/approve",
            headers=auth_headers(db_client, admin.email, PASSWORD),
            json={},
        )
        assert approval.status_code == 200, approval.text
        result = approval.json()
    ready = authority in {"ready", "concurrent"}
    assert result["status"] == "approved"
    assert result["activation"]["ready"] is ready, result["activation"]
    if not ready:
        assert result["activation"]["blocker_code"]
    else:
        duplicate = db_client.post(
            f"/api/v1/admin/installation-evidence/{submitted.json()['id']}/approve",
            headers=auth_headers(db_client, admin.email, PASSWORD),
            json={},
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["error"]["code"] == "INSTALLATION_EVIDENCE_ALREADY_REVIEWED"

    async def inspect():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, assignment_id)
            campaign_row = await session.get(Campaign, campaign.id)
            photo = await session.get(InstallationEvidenceSubmission, UUID(result["id"]))
            reserves = await session.scalar(
                select(func.count()).select_from(CampaignLiabilityReservation)
            )
            actions = list(await session.scalars(select(AuditEvent.action)))
            assert photo.status == "approved"
            assert "installation_evidence.approved" in actions
            if ready:
                assert assignment.status == campaign_row.status == "active"
                assert reserves == 1
                assert actions.count("admin.campaign_assignment.activated") == 1
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(CampaignActivationEvent)
                        .where(
                            CampaignActivationEvent.assignment_id == assignment_id,
                            CampaignActivationEvent.event_type == "activated",
                        )
                    )
                    == 1
                )
            else:
                assert assignment.status == "accepted"
                assert reserves == 0
                assert "billing.liability_reservation.recorded" not in actions
                assert "admin.campaign_assignment.activated" not in actions

    asyncio.run(inspect())
