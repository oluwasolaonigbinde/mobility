import asyncio
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_payout_revision,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
    fetch_audit_events,
)
from sqlalchemy import select

from app.core.errors import AppError
from app.models.billing import AcceptanceMethod, PaymentClass, QuoteRequestSource
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_change import CampaignChangeRequest
from app.models.driver import DriverOnboardingStatus
from app.models.payout import AssignmentRuleBinding
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.schemas.campaign_changes import CampaignChangeCreate
from app.services.billing import (
    accept_quotation_revision,
    record_approved_credit_authorization,
    record_quotation_revision,
    request_custom_quote,
    reserved_campaign_liability_total,
)
from app.services.campaign_changes import (
    decide_campaign_change,
    request_campaign_change,
    resolve_campaign_change_snapshot,
)

PASSWORD = "long-secure-password"


def change_graph(db_sessionmaker, suffix: str):
    admin = create_test_user(
        db_sessionmaker,
        email=f"change-admin-{suffix}@example.com",
        password=PASSWORD,
    )
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"change-advertiser-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker, owner_user_id=advertiser.id
    )
    now = datetime.now(UTC)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=10),
        budget_amount="1000.00",
        daily_budget_amount="100.00",
    )
    return admin, advertiser, campaign


def test_safe_budget_expansion_applies_immediately_and_retry_converges(
    db_client,
    db_sessionmaker,
) -> None:
    _, advertiser, campaign = change_graph(db_sessionmaker, "safe")
    request_id = uuid4()
    payload = {
        "client_request_id": str(request_id),
        "budget_amount": "1200.00",
        "reason": "Add approved media spend without changing driver scope",
    }
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    created = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json=payload,
    )
    replay = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json=payload,
    )

    assert created.status_code == 201, created.text
    assert replay.status_code == 201
    assert created.json()["id"] == replay.json()["id"]
    assert created.json()["status"] == "applied"
    assert created.json()["classifications"] == ["expansion"]
    assert created.json()["requested_liability_amount"] == "0.00"

    async def current_budget():
        async with db_sessionmaker() as session:
            current = await session.get(Campaign, campaign.id)
            return str(current.budget_amount)

    assert asyncio.run(current_budget()) == "1200.00"
    assert [event.action for event in fetch_audit_events(db_sessionmaker)].count(
        "campaign.change.applied"
    ) == 1


def test_reduction_and_date_change_require_reasoned_admin_decision_and_stale_fails(
    db_client,
    db_sessionmaker,
) -> None:
    admin, advertiser, campaign = change_graph(db_sessionmaker, "review")
    proposed_end = datetime.now(UTC) + timedelta(days=5)
    created = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "budget_amount": "900.00",
            "end_at": proposed_end.isoformat(),
            "reason": "Reduce scope after advertiser request",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending_admin"
    assert created.json()["classifications"] == ["date_change", "reduction"]

    approved = db_client.post(
        f"/api/v1/admin/campaign-change-requests/{created.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Approved reduction with preserved accepted history"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "applied"
    assert approved.json()["review_reason"] == (
        "Approved reduction with preserved accepted history"
    )

    stale = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "daily_budget_amount": "80.00",
            "reason": "Second reduction",
        },
    )
    assert stale.status_code == 201

    async def concurrent_change():
        async with db_sessionmaker() as session:
            current = await session.get(Campaign, campaign.id)
            current.budget_amount = 850
            await session.commit()

    asyncio.run(concurrent_change())
    stale_decision = db_client.post(
        f"/api/v1/admin/campaign-change-requests/{stale.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Attempt stale approval"},
    )
    assert stale_decision.status_code == 409
    assert stale_decision.json()["error"]["code"] == "CAMPAIGN_CHANGE_STALE"


def test_campaign_change_retry_conflict_and_tenant_isolation(
    db_client,
    db_sessionmaker,
) -> None:
    _, advertiser, campaign = change_graph(db_sessionmaker, "tenant-a")
    _, other, _ = change_graph(db_sessionmaker, "tenant-b")
    request_id = uuid4()
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    first = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json={
            "client_request_id": str(request_id),
            "budget_amount": "1100.00",
            "reason": "First payload",
        },
    )
    conflict = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json={
            "client_request_id": str(request_id),
            "budget_amount": "1300.00",
            "reason": "Changed payload",
        },
    )
    isolated = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=auth_headers(db_client, other.email, PASSWORD),
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CAMPAIGN_CHANGE_RETRY_CONFLICT"
    assert isolated.status_code == 200
    assert isolated.json()["items"] == []


def test_campaign_change_rejects_retroactive_date_and_resolves_effective_revision(
    db_client,
    db_sessionmaker,
) -> None:
    admin, advertiser, campaign = change_graph(db_sessionmaker, "effective")
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    retroactive = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "end_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "reason": "Attempt retroactive end date",
        },
    )
    assert retroactive.status_code == 400
    assert retroactive.json()["error"]["code"] == "CAMPAIGN_CHANGE_RETROACTIVE_DATE"

    original_budget = str(campaign.budget_amount)
    requested = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "budget_amount": "800.00",
            "reason": "Effective revision test",
        },
    )
    assert requested.status_code == 201
    approved = db_client.post(
        f"/api/v1/admin/campaign-change-requests/{requested.json()['id']}/approve",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"reason": "Approve effective revision test"},
    )
    assert approved.status_code == 200

    async def resolve():
        async with db_sessionmaker() as session:
            before = await resolve_campaign_change_snapshot(
                session,
                campaign_id=campaign.id,
                effective_at=campaign.created_at,
            )
            after = await resolve_campaign_change_snapshot(
                session,
                campaign_id=campaign.id,
                effective_at=datetime.now(UTC) + timedelta(minutes=1),
            )
            return before, after

    before, after = asyncio.run(resolve())
    assert before["budget_amount"] == original_budget
    assert after["budget_amount"] == "800.00"


def test_earlier_future_start_is_classified_as_an_expansion(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="change-advertiser-start-expansion@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker, owner_user_id=advertiser.id
    )
    now = datetime.now(UTC)
    current_start = now + timedelta(days=5)
    proposed_start = (current_start - timedelta(minutes=30)).astimezone(
        timezone(timedelta(hours=1))
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.SCHEDULED,
        start_at=current_start,
        end_at=now + timedelta(days=10),
        budget_amount="1000.00",
        daily_budget_amount="100.00",
    )
    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/change-requests",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            # The local clock text is later, but the represented instant is
            # thirty minutes earlier. Classification must compare instants.
            "start_at": proposed_start.isoformat(),
            "reason": "Open one additional future campaign day",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["classifications"] == ["date_change", "expansion"]
    assert response.json()["status"] == "pending_admin"


def test_funding_and_change_approval_serialize_without_overauthorization_pg(
    postgis_db_sessionmaker,
) -> None:
    admin, advertiser, campaign = change_graph(postgis_db_sessionmaker, "funding-race")
    driver = create_test_user(
        postgis_db_sessionmaker,
        email="change-driver-funding-race@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(
        postgis_db_sessionmaker,
        user_id=driver.id,
        onboarding_status=DriverOnboardingStatus.ACTIVE,
    )
    vehicle = create_test_vehicle(
        postgis_db_sessionmaker,
        driver_profile_id=profile.id,
        plate_number="CHG-001",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    payout_revision = create_test_campaign_payout_revision(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
    )
    assignment = create_test_campaign_assignment(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACCEPTED,
        accepted_at=datetime.now(UTC),
    )

    async def seed_authority() -> None:
        async with postgis_db_sessionmaker() as session:
            session.add(
                AssignmentRuleBinding(
                    assignment_id=assignment.id,
                    revision_id=payout_revision.id,
                    hourly_rate_naira="1000.00",
                    premium_hourly_rate_naira="1500.00",
                    daily_payable_hours_cap="8.00",
                    eligibility_params={},
                    resolved_eligibility_params={},
                    formula_version="payout_v3",
                    premium_zone_ids=[],
                    premium_zone_geometry_hash="0" * 64,
                    premium_zone_geometry_wkts=[],
                    exclusion_zone_ids=[],
                    exclusion_zone_geometry_hash="0" * 64,
                    exclusion_zone_geometry_wkts=[],
                    stationary_policy_marker="ext-rm2-fail-closed",
                    campaign_window_start_at=campaign.start_at,
                    campaign_window_end_at=campaign.end_at,
                    campaign_window_frozen=True,
                )
            )
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
                quote_reference="CHANGE-RACE",
                currency="NGN",
                line_items=[
                    {
                        "code": "TEST",
                        "description": "Synthetic change authority",
                        "kind": "media",
                        "amount": "100000.00",
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
                credit_limit="10000.00",
                max_driver_liability="10000.00",
                due_at=datetime.now(UTC) + timedelta(days=30),
                approved_by_user_id=admin.id,
                credit_terms={"synthetic_test": True, "revision": 1},
                reason="Initial synthetic authority",
            )
            await session.commit()

    asyncio.run(seed_authority())
    requested_end = campaign.end_at + timedelta(days=1)

    async def create_change() -> CampaignChangeRequest:
        async with postgis_db_sessionmaker() as session:
            request = await request_campaign_change(
                session,
                actor_user_id=advertiser.id,
                campaign_id=campaign.id,
                payload=CampaignChangeCreate(
                    client_request_id=uuid4(),
                    end_at=requested_end,
                    reason="One funded additional service day",
                ),
            )
            await session.commit()
            return request

    created = asyncio.run(create_change())
    assert created.requested_liability_amount == 12000
    change_request_id = UUID(str(created.id))

    async def record_pending_and_replays() -> None:
        async with postgis_db_sessionmaker() as session:
            pending = await decide_campaign_change(
                session,
                actor_user_id=admin.id,
                request_id=change_request_id,
                approve=True,
                reason="Approve funded additional day",
            )
            assert pending.status == "pending_funding"
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            replay = await decide_campaign_change(
                session,
                actor_user_id=admin.id,
                request_id=change_request_id,
                approve=True,
                reason="Approve funded additional day",
            )
            assert replay.status == "pending_funding"
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            try:
                await decide_campaign_change(
                    session,
                    actor_user_id=admin.id,
                    request_id=change_request_id,
                    approve=True,
                    reason="Changed retry reason",
                )
            except AppError as exc:
                assert exc.code == "CAMPAIGN_CHANGE_DECISION_CONFLICT"
                await session.rollback()
            else:
                raise AssertionError("changed decision retry should fail closed")

    asyncio.run(record_pending_and_replays())
    assert [
        event.action for event in fetch_audit_events(postgis_db_sessionmaker)
    ].count("admin.campaign_change.pending_funding") == 1

    start = asyncio.Event()

    async def fund() -> None:
        await start.wait()
        async with postgis_db_sessionmaker() as session:
            await record_approved_credit_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                credit_limit="20000.00",
                max_driver_liability="20000.00",
                due_at=datetime.now(UTC) + timedelta(days=30),
                approved_by_user_id=admin.id,
                credit_terms={"synthetic_test": True, "revision": 2},
                reason="Fund the additional day",
            )
            await session.commit()

    async def approve() -> None:
        await start.wait()
        async with postgis_db_sessionmaker() as session:
            await decide_campaign_change(
                session,
                actor_user_id=admin.id,
                request_id=change_request_id,
                approve=True,
                reason="Approve funded additional day",
            )
            await session.commit()

    async def race_and_converge():
        tasks = [asyncio.create_task(fund()), asyncio.create_task(approve())]
        start.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        async with postgis_db_sessionmaker() as session:
            request = await session.get(CampaignChangeRequest, change_request_id)
            assert request is not None
            if request.status == "pending_funding":
                await decide_campaign_change(
                    session,
                    actor_user_id=admin.id,
                    request_id=request.id,
                    approve=True,
                    reason="Approve funded additional day",
                )
                await session.commit()
            request = await session.get(CampaignChangeRequest, change_request_id)
            reserved = await reserved_campaign_liability_total(
                session, campaign_id=campaign.id
            )
            binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == assignment.id
                )
            )
            return request, reserved, binding

    request, reserved, binding = asyncio.run(race_and_converge())
    assert request.status == "applied"
    assert request.authorization_id is not None
    assert reserved == 12000
    assert binding is not None
    assert binding.campaign_window_end_at == campaign.end_at
