import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import select
from test_payouts_v2 import create_v2_rule
from test_payouts_v3 import create_revision_row, insert_binding
from test_receipt_allocations import _accepted_terms
from test_trips import create_trip_ready_graph, start_trip

from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    PaymentClass,
    ProductionAuthorityBasis,
    QuoteRequestSource,
    ReceiptMethod,
)
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.driver import DriverOnboardingStatus
from app.models.user import User, UserRole
from app.models.vehicle import VehicleStatus
from app.services import billing
from app.services.billing import (
    accept_quotation_revision,
    allocate_payment_receipt,
    confirm_payment_receipt,
    reconcile_payment_receipt,
    record_approved_credit_authorization,
    record_expedited_production_waiver,
    record_payment_receipt,
    record_prepaid_cash_authorization,
    record_production_start,
    record_quotation_revision,
    request_custom_quote,
    reserve_assignment_liability,
)


def _fixture(db_sessionmaker, suffix: str):
    admin = create_test_user(db_sessionmaker, email=f"authority-admin-{suffix}@example.com")
    owner = create_test_user(
        db_sessionmaker,
        email=f"authority-owner-{suffix}@example.com",
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    return admin, owner, organization, campaign


async def _funded_terms(session, *, admin, owner, organization, campaign, reference: str):
    terms = await _accepted_terms(
        session,
        campaign=campaign,
        admin=admin,
        owner=owner,
        reference=reference,
        amount="100.00",
    )
    receipt = await record_payment_receipt(
        session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        method=ReceiptMethod.MANUAL_TRANSFER,
        provider="bank-transfer",
        external_transaction_id=f"{reference}-PAYMENT",
        amount="100.00",
        currency="NGN",
        payer_name="Advertiser",
        evidence_reference=f"{reference}-EVIDENCE",
        observed_at=datetime.now(UTC),
    )
    await reconcile_payment_receipt(
        session,
        receipt_id=receipt.id,
        actor_user_id=admin.id,
        expected_amount="100.00",
        expected_currency="NGN",
    )
    await confirm_payment_receipt(session, receipt_id=receipt.id, actor_user_id=admin.id)
    allocation = await allocate_payment_receipt(
        session,
        receipt_id=receipt.id,
        commercial_terms_id=terms.id,
        actor_user_id=admin.id,
        amount="100.00",
    )
    authorization = await record_prepaid_cash_authorization(
        session,
        campaign_id=campaign.id,
        actor_user_id=admin.id,
        max_driver_liability="80.00",
        reason="fund bounded driver work",
    )
    return terms, allocation, authorization


def test_cash_authority_uses_confirmed_allocations_and_standard_boundary(
    db_sessionmaker, monkeypatch
) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "standard")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            _, allocation, authorization = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="AUTH-STANDARD",
            )
            assert str(authorization.authorized_amount) == "100.00"
            assert str(authorization.max_driver_liability) == "80.00"

            async def before_boundary(_session):
                return allocation.allocated_at + timedelta(hours=24) - timedelta(microseconds=1)

            monkeypatch.setattr(billing, "database_clock", before_boundary)
            with pytest.raises(AppError) as error:
                await record_production_start(
                    session, campaign_id=campaign.id, actor_user_id=admin.id
                )
            assert error.value.code == "PRODUCTION_WAIT_ACTIVE"

            async def at_boundary(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(billing, "database_clock", at_boundary)
            production = await record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id
            )
            assert production.authority_basis == ProductionAuthorityBasis.STANDARD_WINDOW_ELAPSED
            assert production.started_at == allocation.allocated_at + timedelta(hours=24)
            await session.commit()

    asyncio.run(scenario())


def test_concurrent_liability_reservations_never_overbook(
    postgis_db_sessionmaker, settings
) -> None:
    admin, owner, organization, _ = _fixture(postgis_db_sessionmaker, "reserve-seed")
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
        name="Reservation campaign",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assignments = []
    for index in (1, 2):
        driver = create_test_user(
            postgis_db_sessionmaker,
            email=f"reserve-driver-{index}@example.com",
            role=UserRole.DRIVER,
        )
        profile = create_test_driver_profile(
            postgis_db_sessionmaker,
            user_id=driver.id,
            onboarding_status=DriverOnboardingStatus.ACTIVE,
            license_number=f"RESERVE-{index}",
        )
        vehicle = create_test_vehicle(
            postgis_db_sessionmaker,
            driver_profile_id=profile.id,
            plate_number=f"RSV-{index}",
            vehicle_status=VehicleStatus.ACTIVE,
        )
        assignments.append(
            create_test_campaign_assignment(
                postgis_db_sessionmaker,
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                assigned_by_user_id=admin.id,
                assignment_status=CampaignAssignmentStatus.ACCEPTED,
                accepted_at=datetime.now(UTC),
            )
        )
    rule = create_v2_rule(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        created_by_user_id=admin.id,
        hourly_rate="60.00",
        daily_cap_hours="1.00",
    )
    revision = create_revision_row(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        rule_id=rule.id,
        created_by_user_id=admin.id,
        base="60.00",
        premium=None,
        cap="1.00",
    )
    for assignment in assignments:
        insert_binding(
            postgis_db_sessionmaker,
            settings,
            assignment_id=assignment.id,
            revision=revision,
        )

    async def setup_funding() -> None:
        async with postgis_db_sessionmaker() as session:
            await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="AUTH-RESERVE",
            )
            await session.commit()

    asyncio.run(setup_funding())

    async def reserve(assignment_id):
        async with postgis_db_sessionmaker() as session:
            reservation = await reserve_assignment_liability(
                session,
                assignment_id=assignment_id,
                actor_user_id=admin.id,
            )
            await session.commit()
            return reservation.status

    async def overlap():
        return await asyncio.gather(*(reserve(row.id) for row in assignments))

    assert sorted(asyncio.run(overlap())) == ["pending_funding", "reserved"]


def test_expedited_waiver_is_immutable_and_start_is_separate(db_sessionmaker) -> None:
    admin, owner, organization, campaign = _fixture(db_sessionmaker, "waiver")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference="AUTH-WAIVER",
            )
            waiver = await record_expedited_production_waiver(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                wording_version="refund-waiver-v1",
                accepted_wording="I request expedited production and accept the refund effect.",
            )
            assert len(waiver.accepted_wording_hash) == 64
            with pytest.raises(AppError) as error:
                await record_expedited_production_waiver(
                    session,
                    campaign_id=campaign.id,
                    actor_user_id=owner.id,
                    wording_version="refund-waiver-v2",
                    accepted_wording="Different wording",
                )
            assert error.value.code == "EXPEDITED_WAIVER_IMMUTABLE"
            production = await record_production_start(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                waiver_id=waiver.id,
            )
            assert (
                production.authority_basis
                == ProductionAuthorityBasis.ADVERTISER_EXPEDITED_WAIVER
            )
            assert production.started_at >= waiver.accepted_at
            await session.commit()

    asyncio.run(scenario())


def test_approved_credit_snapshots_limit_due_date_approver_and_terms(db_sessionmaker) -> None:
    admin, owner, _, campaign = _fixture(db_sessionmaker, "credit")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={"credit_requested": True},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="AUTH-CREDIT",
                currency="NGN",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Media",
                        "kind": "media",
                        "amount": "500.00",
                    }
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                payment_terms={"net_days": 30},
                tax_rate="0",
            )
            await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            due_at = datetime.now(UTC) + timedelta(days=30)
            authorization = await record_approved_credit_authorization(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                credit_limit="500.00",
                max_driver_liability="300.00",
                due_at=due_at,
                approved_by_user_id=admin.id,
                credit_terms={"net_days": 30, "approval_reference": "SYNTHETIC-CREDIT"},
                reason="record approved corporate credit",
            )
            assert str(authorization.credit_limit) == "500.00"
            assert authorization.credit_due_at == due_at
            assert authorization.credit_approved_by_user_id == admin.id
            assert authorization.credit_terms["net_days"] == 30
            production = await record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id
            )
            assert production.authority_basis == ProductionAuthorityBasis.APPROVED_CREDIT
            assert production.fully_funded_at is None
            await session.commit()

    asyncio.run(scenario())


def test_trip_start_fails_closed_for_commercial_campaign_without_authority(
    db_client, db_sessionmaker
) -> None:
    admin, campaign, _, _, _, assignment = create_trip_ready_graph(
        db_sessionmaker,
        admin_email="commercial-guard-admin@example.com",
        advertiser_email="commercial-guard-owner@example.com",
        driver_email="commercial-guard-driver@example.com",
        plate_number="CG-001",
    )

    async def add_terms() -> None:
        async with db_sessionmaker() as session:
            owner = await session.scalar(
                select(User).where(User.email == "commercial-guard-owner@example.com")
            )
            assert owner is not None
            await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="COMMERCIAL-GUARD",
            )
            await session.commit()

    asyncio.run(add_terms())
    response = start_trip(db_client, assignment.id, email="commercial-guard-driver@example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NEW_WORK_NOT_FINANCIALLY_AUTHORIZED"
