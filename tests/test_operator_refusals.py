import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_creative,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from test_campaign_changes import PASSWORD, change_graph

from app.core.errors import AppError
from app.models.campaign import CampaignCreative, CampaignStatus, CreativeStatus
from app.models.user import UserRole
from app.schemas.campaign_changes import CampaignChangePreviewCreate
from app.schemas.campaigns import CampaignCreate, CreativeUpdate
from app.services import billing
from app.services.campaign_assignments import list_admin_assignments
from app.services.campaign_changes import preview_campaign_change
from app.services.campaigns import (
    create_campaign,
    list_admin_campaigns,
    submit_creative_for_review,
    update_campaign_creative,
)
from app.services.disbursements import create_payout_batch_draft
from app.services.driver_applications import (
    list_driver_applications,
    renew_driver_application_access,
)
from app.services.drivers import list_driver_profiles
from app.services.vehicles import list_admin_vehicles


def _operator_graph(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="refusal-admin@example.com", password=PASSWORD)
    advertiser = create_test_user(
        db_sessionmaker, email="refusal-advertiser@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="Refusal Search Campaign",
    )
    rows = []
    for name, plate, city in (
        ("Chinedu Okafor", "OKA-101", "Abuja"),
        ("Ngozi Eze", "EZE-202", "Lagos"),
    ):
        driver = create_test_user(
            db_sessionmaker,
            email=f"{plate.lower()}@example.com",
            full_name=name,
            role=UserRole.DRIVER,
        )
        profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id, service_city=city)
        vehicle = create_test_vehicle(
            db_sessionmaker, driver_profile_id=profile.id, plate_number=plate
        )
        create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=admin.id,
        )
        rows.append((profile, vehicle))
    return admin, rows


def test_named_search_narrows_driver_vehicle_and_assignment_lists(db_sessionmaker) -> None:
    _, rows = _operator_graph(db_sessionmaker)
    okafor_profile, okafor_vehicle = rows[0]

    async def exercise():
        async with db_sessionmaker() as session:
            drivers, driver_total = await list_driver_profiles(
                session,
                limit=25,
                offset=0,
                onboarding_status=None,
                country_code=None,
                service_city=None,
                q="okafor",
            )
            vehicles, vehicle_total = await list_admin_vehicles(
                session,
                limit=25,
                offset=0,
                vehicle_status=None,
                vehicle_type=None,
                plate_country_code=None,
                driver_profile_id=None,
                q="OKA-1",
            )
            assignments, assignment_total = await list_admin_assignments(
                session,
                limit=25,
                offset=0,
                assignment_status=None,
                campaign_id=None,
                driver_profile_id=None,
                vehicle_id=None,
                q="Okafor",
            )
            blank, blank_total = await list_driver_profiles(
                session,
                limit=25,
                offset=0,
                onboarding_status=None,
                country_code=None,
                service_city=None,
                q="   ",
            )
            return (
                [profile.id for profile, _ in drivers],
                driver_total,
                [vehicle.id for vehicle, _, _ in vehicles],
                vehicle_total,
                [assignment.driver_profile_id for assignment in assignments],
                assignment_total,
                blank_total,
            )

    (
        driver_ids,
        driver_total,
        vehicle_ids,
        vehicle_total,
        assignment_drivers,
        assignment_total,
        blank_total,
    ) = asyncio.run(exercise())
    assert (driver_ids, driver_total) == ([okafor_profile.id], 1)
    assert (vehicle_ids, vehicle_total) == ([okafor_vehicle.id], 1)
    assert (assignment_drivers, assignment_total) == ([okafor_profile.id], 1)
    assert blank_total == 2


def test_admin_application_routes_hide_unknown_applications(db_client, db_sessionmaker) -> None:
    admin = create_test_user(
        db_sessionmaker, email="refusal-app-admin@example.com", password=PASSWORD
    )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    missing = uuid4()

    detail = db_client.get(f"/api/v1/admin/driver-applications/{missing}", headers=headers)
    setup = db_client.post(
        f"/api/v1/admin/driver-applications/{missing}/account-setup",
        headers=headers,
        json={"client_request_id": str(uuid4())},
    )

    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "DRIVER_APPLICATION_NOT_FOUND"
    assert setup.status_code == 404
    assert setup.json()["error"]["code"] == "DRIVER_APPLICATION_NOT_FOUND"


def test_campaign_change_preview_refuses_invalid_proposals(db_sessionmaker) -> None:
    _, advertiser, campaign = change_graph(db_sessionmaker, "refusals")
    _, _, other_campaign = change_graph(db_sessionmaker, "refusals-other")
    now = datetime.now(UTC)
    draft = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=advertiser.id,
        name="Draft change target",
        campaign_status=CampaignStatus.DRAFT,
    )
    cases = [
        (uuid4(), {"budget_amount": "1100.00", "reason": "Unknown"}, "CAMPAIGN_NOT_FOUND"),
        (
            other_campaign.id,
            {"budget_amount": "1100.00", "reason": "Other tenant"},
            "CAMPAIGN_NOT_FOUND",
        ),
        (
            draft.id,
            {"budget_amount": "1100.00", "reason": "Draft"},
            "CAMPAIGN_CHANGE_NOT_AVAILABLE",
        ),
        (
            campaign.id,
            {"budget_amount": "1000.00", "reason": "Same budget"},
            "CAMPAIGN_CHANGE_NOOP",
        ),
        (
            campaign.id,
            {"start_at": now - timedelta(hours=1), "reason": "Past start"},
            "CAMPAIGN_CHANGE_RETROACTIVE_DATE",
        ),
        (
            campaign.id,
            {"start_at": now + timedelta(days=20), "reason": "Start after end"},
            "INVALID_CAMPAIGN_WINDOW",
        ),
        (
            campaign.id,
            {"daily_budget_amount": "2000.00", "reason": "Daily above total"},
            "INVALID_CAMPAIGN_BUDGET",
        ),
    ]

    async def refusal(campaign_id, proposal):
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as refused:
                await preview_campaign_change(
                    session,
                    actor_user_id=advertiser.id,
                    campaign_id=campaign_id,
                    payload=CampaignChangePreviewCreate(**proposal),
                )
            return refused.value.code

    for campaign_id, proposal, expected in cases:
        assert asyncio.run(refusal(campaign_id, proposal)) == expected, proposal


def test_driver_application_queue_filters_and_generic_renewal(db_sessionmaker, settings) -> None:
    admin = create_test_user(db_sessionmaker, email="queue-filter-admin@example.com")

    async def exercise():
        async with db_sessionmaker() as session:
            pending = await list_driver_applications(
                session, admin_user_id=admin.id, limit=25, offset=0, q="Nobody Here"
            )
            history = await list_driver_applications(
                session, admin_user_id=admin.id, limit=25, offset=0, history=True
            )
            renewal = await renew_driver_application_access(
                session, email="unknown-applicant@example.com", settings=settings
            )
            return pending, history, renewal

    pending, history, renewal = asyncio.run(exercise())
    assert pending == ([], 0)
    assert history == ([], 0)
    assert renewal is None


def test_assignment_readiness_refuses_an_unknown_assignment(db_sessionmaker) -> None:
    async def exercise():
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as missing:
                await billing.assignment_liability_readiness(session, assignment_id=uuid4())
            return missing.value

    error = asyncio.run(exercise())
    assert error.code == "ASSIGNMENT_NOT_FOUND"
    assert error.status_code == 404


def test_payout_draft_reference_cannot_be_reused_by_another_maker_or_currency(
    db_sessionmaker,
) -> None:
    maker = create_test_user(db_sessionmaker, email="draft-maker@example.com")
    other = create_test_user(db_sessionmaker, email="draft-other@example.com")
    request_id = uuid4()

    async def exercise():
        async with db_sessionmaker() as session:
            first = await create_payout_batch_draft(
                session, currency="ngn", actor_user_id=maker.id, request_id=request_id
            )
            await session.commit()
            again = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=maker.id, request_id=request_id
            )
            codes = []
            for actor, currency in ((other.id, "NGN"), (maker.id, "USD")):
                with pytest.raises(AppError) as conflict:
                    await create_payout_batch_draft(
                        session, currency=currency, actor_user_id=actor, request_id=request_id
                    )
                codes.append(conflict.value.code)
            return first.id, again.id, codes

    first_id, again_id, codes = asyncio.run(exercise())
    assert first_id == again_id == request_id
    assert codes == ["PAYOUT_DRAFT_RETRY_CONFLICT", "PAYOUT_DRAFT_RETRY_CONFLICT"]


def _advertiser_campaign(db_sessionmaker, suffix):
    advertiser = create_test_user(
        db_sessionmaker,
        email=f"campaign-service-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name=f"Service Campaign {suffix}",
    )
    return advertiser, organization, campaign


def test_campaign_create_retry_converges_and_changed_retry_conflicts(db_sessionmaker) -> None:
    advertiser, organization, _ = _advertiser_campaign(db_sessionmaker, "create-retry")
    request_id = uuid4()
    start = datetime(2027, 1, 1, tzinfo=UTC)

    def payload(**changes):
        values = {
            "client_request_id": request_id,
            "name": "Retry Safe Campaign",
            "description": "Created once",
            "start_at": start,
            "end_at": start + timedelta(days=30),
            "budget_amount": "5000.00",
            "daily_budget_amount": "500.00",
        }
        return CampaignCreate(**(values | changes))

    async def exercise():
        async with db_sessionmaker() as session:
            first, created = await create_campaign(
                session, user_id=advertiser.id, payload=payload()
            )
            await session.commit()
            replay, replay_created = await create_campaign(
                session, user_id=advertiser.id, payload=payload()
            )
            codes = []
            for changed in (
                {"name": "Different name"},
                {"start_at": None},
                {"end_at": start + timedelta(days=31)},
            ):
                with pytest.raises(AppError) as conflict:
                    await create_campaign(
                        session, user_id=advertiser.id, payload=payload(**changed)
                    )
                codes.append(conflict.value.code)
            campaigns, total = await list_admin_campaigns(
                session,
                limit=25,
                offset=0,
                organization_id=None,
                campaign_status=None,
                q="retry safe",
            )
            return first, created, replay, replay_created, codes, campaigns, total

    first, created, replay, replay_created, codes, campaigns, total = asyncio.run(exercise())
    assert created is True and replay_created is False
    assert first.id == replay.id == request_id
    assert first.organization_id == organization.id
    assert codes == ["CAMPAIGN_CREATE_IDEMPOTENCY_CONFLICT"] * 3
    assert total == 1 and campaigns[0][0].id == request_id


def test_creative_update_metadata_and_pending_resubmission(db_sessionmaker) -> None:
    advertiser, _, campaign = _advertiser_campaign(db_sessionmaker, "creative")
    creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        metadata={"panel": "left"},
        creative_status=CreativeStatus.APPROVED,
    )

    async def exercise():
        async with db_sessionmaker() as session:
            row = await session.get(CampaignCreative, creative.id)
            row.status = CreativeStatus.DRAFT.value
            await session.commit()
            with pytest.raises(AppError) as null_metadata:
                await update_campaign_creative(
                    session,
                    user_id=advertiser.id,
                    campaign_id=campaign.id,
                    creative_id=creative.id,
                    payload=CreativeUpdate(metadata=None),
                )
            await session.rollback()
            _, unchanged = await update_campaign_creative(
                session,
                user_id=advertiser.id,
                campaign_id=campaign.id,
                creative_id=creative.id,
                payload=CreativeUpdate(metadata={"panel": "left"}),
            )
            await session.commit()
            submitted = await submit_creative_for_review(
                session, user_id=advertiser.id, campaign_id=campaign.id, creative_id=creative.id
            )
            await session.commit()
            replay = await submit_creative_for_review(
                session, user_id=advertiser.id, campaign_id=campaign.id, creative_id=creative.id
            )
            return null_metadata.value.code, unchanged, submitted.status, replay.status

    null_code, unchanged, submitted_status, replay_status = asyncio.run(exercise())
    assert null_code == "INVALID_METADATA"
    assert "metadata" not in unchanged
    assert submitted_status == replay_status == "pending_review"
