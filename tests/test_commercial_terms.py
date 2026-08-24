import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from sqlalchemy import select

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.billing import AcceptanceMethod, CommercialTerms, PaymentClass, QuoteRequestSource
from app.models.organization import MembershipRole
from app.models.user import UserRole
from app.services.billing import (
    accept_quotation_revision,
    record_quotation_revision,
    request_custom_quote,
)


def _commercial_fixture(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="billing-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="advertiser-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=admin.id,
    )
    return admin, owner, organization, campaign


def test_custom_quote_acceptance_freezes_exact_commercial_snapshot(db_sessionmaker) -> None:
    admin, owner, organization, campaign = _commercial_fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={"brief": "Abuja launch"},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="CV-Q-0001",
                currency="ngn",
                line_items=[
                    {
                        "code": "MEDIA",
                        "description": "Campaign media",
                        "kind": "media",
                        "amount": "100000.00",
                    },
                    {
                        "code": "PRINT",
                        "description": "Print and install",
                        "kind": "production",
                        "amount": "25000.00",
                        "metadata": {"vendor_managed": True},
                    },
                ],
                production_scope={"vehicle_count": 10, "city": "Abuja"},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={"due": "before_production"},
                tax_rate="0.075",
            )
            terms = await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=owner.id,
                acceptance_method=AcceptanceMethod.IN_PLATFORM,
            )
            await session.commit()

            assert terms.organization_id == organization.id
            assert terms.quote_reference == "CV-Q-0001"
            assert terms.quotation_revision_number == 1
            assert terms.currency == "NGN"
            assert terms.production_cost_amount == Decimal("25000.00")
            assert terms.net_amount == Decimal("125000.00")
            assert terms.tax_amount == Decimal("9375.00")
            assert terms.gross_amount == Decimal("134375.00")
            assert terms.standard_production_wait_hours == 24
            assert terms.line_items[1]["metadata"] == {"vendor_managed": True}
            assert terms.accepted_by_user_id == owner.id

            actions = list(
                await session.scalars(
                    select(AuditEvent.action).where(AuditEvent.action.like("commercial.%"))
                )
            )
            assert set(actions) == {
                "commercial.quote_request.created",
                "commercial.quotation_revision.recorded",
                "commercial.terms.accepted",
            }

            with pytest.raises(AppError) as duplicate:
                await accept_quotation_revision(
                    session,
                    quotation_revision_id=revision.id,
                    actor_user_id=owner.id,
                    acceptance_method=AcceptanceMethod.IN_PLATFORM,
                )
            assert duplicate.value.code == "COMMERCIAL_TERMS_ALREADY_ACCEPTED"

    asyncio.run(scenario())


def test_external_acceptance_preserves_provenance_and_effective_time(db_sessionmaker) -> None:
    admin, _, _, campaign = _commercial_fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                source=QuoteRequestSource.EXTERNAL_RECORDED,
                request_details={"source": "signed quotation"},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="EXT-2026-17",
                currency="NGN",
                line_items=[
                    {
                        "code": "DEAL",
                        "description": "Accepted external deal",
                        "kind": "other",
                        "amount": "50000.00",
                    }
                ],
                production_scope={"recorded": True},
                payment_class=PaymentClass.APPROVED_CORPORATE_CREDIT,
                payment_terms={"due_days": 30},
                tax_rate="0.075",
            )
            accepted_at = datetime.now(UTC) - timedelta(days=1)
            terms = await accept_quotation_revision(
                session,
                quotation_revision_id=revision.id,
                actor_user_id=admin.id,
                acceptance_method=AcceptanceMethod.EXTERNAL_RECORDED,
                external_accepted_at=accepted_at,
                external_acceptance_reference="SIGNED-PDF-SHA256:abc",
            )
            await session.commit()
            assert terms.accepted_by_user_id is None
            assert terms.recorded_by_user_id == admin.id
            assert terms.external_acceptance_reference == "SIGNED-PDF-SHA256:abc"
            assert terms.accepted_at == accepted_at

    asyncio.run(scenario())


def test_quote_request_and_acceptance_are_tenant_safe(db_sessionmaker) -> None:
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)
    outsider = create_test_user(
        db_sessionmaker, email="outsider@example.com", role=UserRole.ADVERTISER
    )
    create_test_organization(db_sessionmaker, name="Other", owner_user_id=outsider.id)
    viewer = create_test_user(db_sessionmaker, email="viewer@example.com", role=UserRole.ADVERTISER)
    create_test_organization(
        db_sessionmaker,
        name="Viewer Org",
        owner_user_id=viewer.id,
        membership_role=MembershipRole.VIEWER,
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            for actor_id in (outsider.id, viewer.id):
                with pytest.raises(AppError):
                    await request_custom_quote(
                        session,
                        campaign_id=campaign.id,
                        actor_user_id=actor_id,
                        source=QuoteRequestSource.IN_PLATFORM,
                        request_details={},
                    )
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            revision = await record_quotation_revision(
                session,
                quote_request_id=request.id,
                actor_user_id=admin.id,
                quote_reference="TENANT-Q1",
                currency="NGN",
                line_items=[
                    {"code": "M", "description": "Media", "kind": "media", "amount": "1.00"}
                ],
                production_scope={"vehicle_count": 1},
                payment_class=PaymentClass.STANDARD_PREPAID,
                payment_terms={},
                tax_rate="0",
            )
            with pytest.raises(AppError) as hidden:
                await accept_quotation_revision(
                    session,
                    quotation_revision_id=revision.id,
                    actor_user_id=outsider.id,
                    acceptance_method=AcceptanceMethod.IN_PLATFORM,
                )
            assert hidden.value.code == "QUOTATION_NOT_FOUND"
            assert await session.scalar(select(CommercialTerms.id)) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("line_items", "tax_rate", "expected_code"),
    [
        ([], "0.075", "COMMERCIAL_LINE_ITEMS_REQUIRED"),
        (
            [{"code": "X", "description": "Bad", "kind": "media", "amount": "1.001"}],
            "0",
            "INVALID_COMMERCIAL_AMOUNT",
        ),
        (
            [{"code": "X", "description": "Bad", "kind": "media", "amount": "1.00"}],
            "1.1",
            "INVALID_TAX_RATE",
        ),
    ],
)
def test_invalid_quotation_arithmetic_fails_closed(
    db_sessionmaker, line_items, tax_rate, expected_code
) -> None:
    admin, owner, _, campaign = _commercial_fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            request = await request_custom_quote(
                session,
                campaign_id=campaign.id,
                actor_user_id=owner.id,
                source=QuoteRequestSource.IN_PLATFORM,
                request_details={},
            )
            with pytest.raises(AppError) as caught:
                await record_quotation_revision(
                    session,
                    quote_request_id=request.id,
                    actor_user_id=admin.id,
                    quote_reference="BAD",
                    currency="NGN",
                    line_items=line_items,
                    production_scope={"vehicle_count": 1},
                    payment_class=PaymentClass.STANDARD_PREPAID,
                    payment_terms={},
                    tax_rate=tax_rate,
                )
            assert caught.value.code == expected_code

    asyncio.run(scenario())
