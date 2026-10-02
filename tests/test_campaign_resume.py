"""Recorded pause authority, guarded mutation and concurrent exact replay."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_user, fetch_audit_events
from test_admin_hub_reads import bearer
from test_campaign_assignments import create_assignment_ready_graph

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign import Campaign, CampaignReviewEvent, CampaignStatus
from app.models.user import UserRole, UserStatus
from app.services import campaign_resume

PASSWORD = "long-secure-password"


@pytest.fixture
def db_sessionmaker(postgis_db_sessionmaker):
    return postgis_db_sessionmaker


def setup_pause(maker, *, kind="operational", reason="Artwork inspection complete", recorded=True):
    now = datetime.now(UTC)
    admin, campaign, driver, _, _ = create_assignment_ready_graph(
        maker,
        campaign_status=CampaignStatus.PAUSED,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(days=1),
    )

    async def add():
        async with maker() as session:
            current = await session.get(Campaign, campaign.id)
            pause = AuditEvent(
                actor_user_id=admin.id,
                action="admin.campaign.paused",
                entity_type="campaign",
                entity_id=str(campaign.id),
                event_metadata={
                    "pause_reason_kind": kind,
                    "reason": reason,
                    "status_after": "paused",
                    "pause_version": current.updated_at.isoformat(),
                },
            )
            if recorded:
                session.add(pause)
            submitted = CampaignReviewEvent(
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                prior_status="draft",
                new_status="pending_review",
                reviewed_snapshot={},
                reviewed_snapshot_sha256="0" * 64,
            )
            session.add(submitted)
            await session.flush()
            session.add(
                CampaignReviewEvent(
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    prior_status="pending_review",
                    new_status="approved",
                    submission_event_id=submitted.id,
                )
            )
            await session.commit()
            return pause.id if recorded else uuid4()

    return admin, campaign, driver, asyncio.run(add())


def test_resume_denial_matrix_and_unknown_cause(db_client, db_sessionmaker, settings):
    admin, campaign, driver, pause_id = setup_pause(db_sessionmaker, recorded=False)
    other = create_test_user(
        db_sessionmaker, email="resume-advertiser@example.com", role=UserRole.ADVERTISER
    )
    inactive = create_test_user(
        db_sessionmaker, email="resume-inactive@example.com", user_status=UserStatus.SUSPENDED
    )
    path = f"/api/v1/admin/campaigns/{campaign.id}/resume"
    body = {"pause_id": str(pause_id), "reason": "Resume after review"}
    before = len(fetch_audit_events(db_sessionmaker))
    for headers in [
        {},
        bearer(driver, settings),
        bearer(other, settings),
        bearer(inactive, settings),
    ]:
        assert db_client.post(path, headers=headers, json=body).status_code in {401, 403}
    response = db_client.post(path, headers=bearer(admin, settings), json=body)
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "PAUSE_REASON_UNKNOWN"
    )
    assert "reason" in response.json()["error"]["message"]
    assert len(fetch_audit_events(db_sessionmaker)) == before


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("budget", "Reached campaign budget"),
        ("operational", "Funding exhausted"),
        ("unknown", "Check campaign"),
    ],
)
def test_budget_or_unknown_recorded_reason_cannot_be_overridden(
    db_client, db_sessionmaker, kind, reason
):
    admin, campaign, _, pause_id = setup_pause(db_sessionmaker, kind=kind, reason=reason)
    response = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/resume",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"pause_id": str(pause_id), "reason": "This is operational"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] in {
        "BUDGET_PAUSE_REQUIRES_FINANCE",
        "PAUSE_REASON_UNKNOWN",
    }
    assert not any(
        e.action == "admin.campaign.resumed" for e in fetch_audit_events(db_sessionmaker)
    )


def test_operational_pause_requires_same_current_pause_and_real_funding(db_client, db_sessionmaker):
    admin, campaign, _, pause_id = setup_pause(db_sessionmaker)
    headers = auth_headers(db_client, admin.email, PASSWORD)
    path = f"/api/v1/admin/campaigns/{campaign.id}/resume"
    stale = db_client.post(
        path, headers=headers, json={"pause_id": str(uuid4()), "reason": "Inspected"}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "CAMPAIGN_PAUSE_CHANGED"
    unfunded = db_client.post(
        path, headers=headers, json={"pause_id": str(pause_id), "reason": "Inspected"}
    )
    assert (
        unfunded.status_code == 409
        and unfunded.json()["error"]["code"] == "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED"
    )

    async def state():
        async with db_sessionmaker() as session:
            return (await session.get(Campaign, campaign.id)).status

    assert asyncio.run(state()) == "paused"
    assert not any(
        e.action == "admin.campaign.resumed" for e in fetch_audit_events(db_sessionmaker)
    )


def test_start_guard_failures_roll_back_and_exact_concurrent_retry_is_one_audit(
    db_sessionmaker, monkeypatch
):
    admin, campaign, _, pause_id = setup_pause(db_sessionmaker)

    async def pass_funding(*args, **kwargs):
        return None

    monkeypatch.setattr(campaign_resume, "assert_campaign_production_authorized", pass_funding)

    async def run():
        async def resume(reason="Inspected"):
            async with db_sessionmaker() as session:
                result = await campaign_resume.resume_campaign(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    pause_id=pause_id,
                    reason=reason,
                )
                await session.commit()
                return result.status

        results = await asyncio.gather(resume(), resume())
        return results

    assert asyncio.run(run()) == ["active", "active"]
    audits = [
        e for e in fetch_audit_events(db_sessionmaker) if e.action == "admin.campaign.resumed"
    ]
    assert len(audits) == 1 and audits[0].actor_user_id == admin.id
    assert audits[0].event_metadata["pause_id"] == str(pause_id)

    async def changed():
        async with db_sessionmaker() as session:
            await campaign_resume.resume_campaign(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                pause_id=pause_id,
                reason="Different reason",
            )

    with pytest.raises(AppError):
        asyncio.run(changed())


@pytest.mark.parametrize(
    "gate",
    [
        "ensure_campaign_review_approved",
        "assert_campaign_production_authorized",
        "_check_active_jobs",
    ],
)
def test_each_start_gate_refusal_has_no_resume_write(db_sessionmaker, monkeypatch, gate):
    admin, campaign, _, pause_id = setup_pause(db_sessionmaker)

    async def pass_gate(*args, **kwargs):
        return None

    async def refuse(*args, **kwargs):
        raise AppError("START_BLOCKED", "Check the campaign before resuming.", status_code=409)

    for name in [
        "ensure_campaign_review_approved",
        "assert_campaign_production_authorized",
        "_check_active_jobs",
    ]:
        monkeypatch.setattr(campaign_resume, name, pass_gate)
    monkeypatch.setattr(campaign_resume, gate, refuse)

    async def run():
        async with db_sessionmaker() as session:
            await campaign_resume.resume_campaign(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                pause_id=pause_id,
                reason="Inspected",
            )

    with pytest.raises(AppError):
        asyncio.run(run())
    assert not any(
        e.action == "admin.campaign.resumed" for e in fetch_audit_events(db_sessionmaker)
    )


def test_real_funded_active_job_guards_and_atomic_resume(
    db_client, db_sessionmaker, settings, monkeypatch
):
    from uuid import UUID

    from conftest import create_test_display_proof, fetch_user_by_email
    from sqlalchemy import select
    from test_campaign_assignments import assignment_payload

    from app.models.billing import (
        AcceptanceMethod,
        CampaignLiabilityReservation,
        PaymentClass,
        QuoteRequestSource,
    )
    from app.models.campaign import CampaignCreative
    from app.models.campaign_assignment import CampaignActivationEvent
    from app.models.driver import DriverProfile
    from app.models.installation_evidence import InstallationEvidenceSubmission
    from app.models.payout import CampaignPayoutRule, CampaignPayoutRuleRevision
    from app.models.vehicle import Vehicle
    from app.services.billing import (
        accept_quotation_revision,
        record_approved_credit_authorization,
        record_production_start,
        record_quotation_revision,
        request_custom_quote,
        reserve_assignment_liability,
    )

    monkeypatch.setattr(campaign_resume, "get_settings", lambda: settings)
    admin, campaign, driver, _ = setup_pause(db_sessionmaker)
    advertiser = fetch_user_by_email(db_sessionmaker, "advertiser@example.com")
    assert advertiser is not None

    async def prepare():
        async with db_sessionmaker() as session:
            c = await session.get(Campaign, campaign.id)
            c.status = "approved"
            profile = await session.scalar(
                select(DriverProfile).where(DriverProfile.user_id == driver.id)
            )
            car = await session.scalar(
                select(Vehicle).where(Vehicle.driver_profile_id == profile.id)
            )
            await session.commit()
            return profile, car

    profile, car = asyncio.run(prepare())
    staff = bearer(admin, settings)
    created = db_client.post(
        "/api/v1/admin/campaign-assignments",
        headers=staff,
        json=assignment_payload(
            campaign,
            profile,
            car,
            expires_at=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        ),
    )
    assert created.status_code == 201, created.text
    job_id = UUID(created.json()["id"])
    accepted = db_client.post(
        f"/api/v1/driver/campaign-assignments/{job_id}/accept",
        headers=bearer(driver, settings),
        json={"metadata": {}},
    )
    assert accepted.status_code == 200, accepted.text
    create_test_display_proof(db_sessionmaker, assignment_id=job_id, reviewed_by_user_id=admin.id)

    async def fund():
        async with db_sessionmaker() as session:
            quote = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=advertiser.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={"synthetic_test": True},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=quote.id,
                actor_user_id=admin.id,
                quote_reference="RESUME-TEST",
                currency="NGN",
                line_items=[
                    {
                        "code": "TEST",
                        "description": "Synthetic Resume authority",
                        "kind": "media",
                        "amount": "1000000.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                payment_terms={"synthetic_test": True},
                tax_rate="0",
            )
            await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=advertiser.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            await record_approved_credit_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                credit_limit="1000000.00",
                max_driver_liability="1000000.00",
                due_at=datetime(2100, 1, 1, tzinfo=UTC),
                approved_by_user_id=admin.id,
                credit_terms={"synthetic_test": True},
                reason="Synthetic Resume test",
            )
            await record_production_start(session, campaign_id=campaign.id, actor_user_id=admin.id)
            await reserve_assignment_liability(
                session, assignment_id=job_id, actor_user_id=admin.id
            )
            await session.commit()

    asyncio.run(fund())
    activated = db_client.post(
        f"/api/v1/admin/campaign-assignments/{job_id}/activate",
        headers=staff,
        json={"metadata": {}},
    )
    assert activated.status_code == 200, activated.text

    async def pause():
        async with db_sessionmaker() as session:
            c = await session.get(Campaign, campaign.id)
            c.status = "paused"
            await session.flush()
            await session.refresh(c)
            event = AuditEvent(
                actor_user_id=admin.id,
                action="admin.campaign.paused",
                entity_type="campaign",
                entity_id=str(c.id),
                event_metadata={
                    "pause_reason_kind": "operational",
                    "reason": "Artwork inspection",
                    "status_after": "paused",
                    "pause_version": c.updated_at.isoformat(),
                },
            )
            session.add(event)
            await session.commit()
            return event.id

    pause_id = asyncio.run(pause())

    async def refused(case, expected):
        async with db_sessionmaker() as session:
            c = await session.get(Campaign, campaign.id)
            if case == "driver":
                (await session.get(DriverProfile, profile.id)).onboarding_status = "suspended"
            if case == "car":
                (await session.get(Vehicle, car.id)).status = "suspended"
            if case == "snapshot":
                row = await session.scalar(
                    select(CampaignActivationEvent).where(
                        CampaignActivationEvent.assignment_id == job_id,
                        CampaignActivationEvent.event_type == "activated",
                    )
                )
                row.event_metadata = {}
            if case == "installation":
                row = await session.scalar(
                    select(InstallationEvidenceSubmission).where(
                        InstallationEvidenceSubmission.assignment_id == job_id
                    )
                )
                row.approved_until = datetime(2020, 1, 1, tzinfo=UTC)
            if case == "reservation":
                row = await session.scalar(
                    select(CampaignLiabilityReservation).where(
                        CampaignLiabilityReservation.assignment_id == job_id
                    )
                )
                row.status = "pending_funding"
                row.authorization_id = None
                row.reserved_amount = None
                row.reserved_at = None
            if case == "artwork":
                row = await session.scalar(
                    select(CampaignCreative).where(CampaignCreative.campaign_id == c.id)
                )
                row.name = "Changed artwork"
            if case == "expiry":
                c.start_at = datetime(2019, 1, 1, tzinfo=UTC)
                c.end_at = datetime(2020, 1, 1, tzinfo=UTC)
            if case == "pay":
                row = await session.scalar(
                    select(CampaignPayoutRule).where(CampaignPayoutRule.campaign_id == c.id)
                )
                row.status = "inactive"
            if case == "future_pay":
                current_rule = await session.scalar(
                    select(CampaignPayoutRule).where(CampaignPayoutRule.campaign_id == c.id)
                )
                current_rule.formula_version = "payout_v3"
                rows = await session.scalars(
                    select(CampaignPayoutRuleRevision).where(
                        CampaignPayoutRuleRevision.campaign_id == c.id
                    )
                )
                for row in rows:
                    row.effective_from = datetime(2099, 1, 1, tzinfo=UTC)
            await session.flush()
            # Dates are campaign facts, so preserve the current recorded pause identity.
            if case == "expiry":
                await session.refresh(c)
                event = await session.get(AuditEvent, pause_id)
                event.event_metadata = {
                    **event.event_metadata,
                    "pause_version": c.updated_at.isoformat(),
                }
                await session.flush()
            with pytest.raises(AppError) as exc:
                await campaign_resume.resume_campaign(
                    session,
                    campaign_id=c.id,
                    actor_user_id=admin.id,
                    pause_id=pause_id,
                    reason="Inspected",
                )
            assert exc.value.code == expected, (case, exc.value.code)
            await session.rollback()
        async with db_sessionmaker() as session:
            assert (await session.get(Campaign, campaign.id)).status == "paused"
            assert not await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.action == "admin.campaign.resumed",
                    AuditEvent.entity_id == str(campaign.id),
                )
            )

    for case, expected in [
        ("driver", "DRIVER_PROFILE_NOT_ACTIVE"),
        ("car", "VEHICLE_NOT_ACTIVE"),
        ("snapshot", "VALID_ACTIVATION_SNAPSHOT_REQUIRED"),
        ("installation", "INSTALLATION_EVIDENCE_EXPIRED"),
        ("reservation", "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED"),
        ("artwork", "RESUME_ARTWORK_CHANGED"),
        ("expiry", "CAMPAIGN_EXPIRED"),
        ("pay", "CURRENT_PAY_TERMS_REQUIRED"),
        ("future_pay", "CURRENT_PAY_TERMS_REQUIRED"),
    ]:
        asyncio.run(refused(case, expected))

    async def success():
        async def once():
            async with db_sessionmaker() as session:
                result = await campaign_resume.resume_campaign(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=admin.id,
                    pause_id=pause_id,
                    reason="Inspected",
                )
                await session.commit()
                return result.status

        return await asyncio.gather(once(), once())

    assert asyncio.run(success()) == ["active", "active"]
    assert (
        len(
            [e for e in fetch_audit_events(db_sessionmaker) if e.action == "admin.campaign.resumed"]
        )
        == 1
    )


def test_budget_pause_chronology_and_unknown_current_record(db_sessionmaker):
    from sqlalchemy import select

    from app.models.billing import BudgetCampaignTransition, BudgetPolicyEvaluation

    admin, campaign, _, pause_id = setup_pause(db_sessionmaker)

    async def run():
        async with db_sessionmaker() as session:
            c = await session.get(Campaign, campaign.id)
            pause = await session.get(AuditEvent, pause_id)
            earlier = pause.created_at - timedelta(minutes=10)
            evaluation = BudgetPolicyEvaluation(
                campaign_id=c.id,
                evaluation_key="a" * 64,
                state="blocked_external_policy",
                external_gate="EXT-BUDGET-POLICY",
                campaign_budget_amount="10000",
                currency="NGN",
                pause_applied=False,
                evaluated_at=earlier,
            )
            session.add(evaluation)
            await session.flush()
            session.add(
                BudgetCampaignTransition(
                    campaign_id=c.id,
                    evaluation_id=evaluation.id,
                    action="pause",
                    prior_status="active",
                    new_status="paused",
                    reason="Budget limit",
                    created_at=earlier,
                )
            )
            session.add(
                BudgetCampaignTransition(
                    campaign_id=c.id,
                    evaluation_id=evaluation.id,
                    action="resume",
                    prior_status="paused",
                    new_status="active",
                    actor_user_id=admin.id,
                    reason="Funding corrected",
                    created_at=earlier + timedelta(minutes=1),
                )
            )
            await session.flush()
            assert (await campaign_resume.pause_info(session, c))["kind"] == "operational"
            later = BudgetPolicyEvaluation(
                campaign_id=c.id,
                evaluation_key="b" * 64,
                state="blocked_external_policy",
                external_gate="EXT-BUDGET-POLICY",
                campaign_budget_amount="10000",
                currency="NGN",
                pause_applied=False,
                evaluated_at=pause.created_at + timedelta(minutes=1),
            )
            session.add(later)
            await session.flush()
            transition = BudgetCampaignTransition(
                campaign_id=c.id,
                evaluation_id=later.id,
                action="pause",
                prior_status="active",
                new_status="paused",
                reason="Budget limit",
                created_at=later.evaluated_at,
            )
            session.add(transition)
            await session.flush()
            with pytest.raises(AppError) as blocked:
                await campaign_resume._require_operational_pause(session, c, pause_id)
            assert blocked.value.code == "BUDGET_PAUSE_REQUIRES_FINANCE"
            await session.delete(transition)
            await session.flush()
            pause.event_metadata = {**pause.event_metadata, "pause_version": "bad-date"}
            await session.flush()
            assert (await campaign_resume.pause_info(session, c))["kind"] == "unknown"
            pause.event_metadata = {
                **pause.event_metadata,
                "pause_version": c.updated_at.isoformat(),
            }
            await session.flush()
            newer = AuditEvent(
                actor_user_id=admin.id,
                action="admin.campaign.paused",
                entity_type="campaign",
                entity_id=str(c.id),
                created_at=pause.created_at + timedelta(minutes=2),
                event_metadata={"reason": "Unclassified"},
            )
            session.add(newer)
            await session.flush()
            assert (await campaign_resume.pause_info(session, c))["kind"] == "unknown"
            assert not await session.scalar(
                select(AuditEvent.id).where(AuditEvent.action == "admin.campaign.resumed")
            )
            await session.rollback()

    asyncio.run(run())
