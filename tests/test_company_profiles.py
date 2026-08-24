import asyncio

import pytest
from conftest import create_test_organization, create_test_user
from sqlalchemy import select

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.organization import (
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
)
from app.models.user import UserRole
from app.services.organizations import get_company_profile, update_company_profile


def test_advertiser_owner_updates_canonical_company_profile_with_audit(db_sessionmaker) -> None:
    owner = create_test_user(
        db_sessionmaker, email="profile-owner@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            profile = await update_company_profile(
                session,
                actor_user_id=owner.id,
                organization_id=organization.id,
                changes={
                    "name": "Terrax Advertiser Ltd",
                    "billing_email": "Accounts@Advertiser.Test",
                    "address_line_1": "10 Example Way",
                    "address_city": "Abuja",
                    "address_region": "FCT",
                    "address_country_code": "ng",
                    "industry": "Consumer goods",
                    "operational_contact_name": "Operations Lead",
                    "operational_contact_email": "OPS@ADVERTISER.TEST",
                    "operational_contact_phone": "+2348000000000",
                    "billing_contact_name": "Finance Lead",
                    "billing_contact_phone": "+2348111111111",
                },
            )
            await session.commit()
            assert profile.name == "Terrax Advertiser Ltd"
            assert profile.billing_email == "accounts@advertiser.test"
            assert profile.address_country_code == "NG"
            assert profile.operational_contact_email == "ops@advertiser.test"

            event = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "advertiser_company_profile.updated")
            )
            assert event is not None
            assert event.event_metadata["before"]["name"] == "Acme Ads"
            assert event.event_metadata["after"]["address_city"] == "Abuja"
            assert event.event_metadata["actor_scope"] == "advertiser"

            canonical = await get_company_profile(
                session, actor_user_id=owner.id, organization_id=organization.id
            )
            assert canonical.id == organization.id
            assert canonical.industry == "Consumer goods"

    asyncio.run(scenario())


def test_company_profile_enforces_tenant_roles_and_admin_only_fields(db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="profile-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="profile-owner2@example.com", role=UserRole.ADVERTISER
    )
    viewer = create_test_user(
        db_sessionmaker, email="profile-viewer@example.com", role=UserRole.ADVERTISER
    )
    outsider = create_test_user(
        db_sessionmaker, email="profile-outsider@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    other_organization, _ = create_test_organization(
        db_sessionmaker, name="Other Co", owner_user_id=outsider.id
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=viewer.id,
                    role=MembershipRole.VIEWER,
                    status=MembershipStatus.ACTIVE,
                )
            )
            await session.commit()

            assert (
                await get_company_profile(
                    session, actor_user_id=viewer.id, organization_id=organization.id
                )
            ).id == organization.id
            with pytest.raises(AppError) as read_hidden:
                await get_company_profile(
                    session, actor_user_id=outsider.id, organization_id=organization.id
                )
            assert read_hidden.value.code == "COMPANY_PROFILE_NOT_FOUND"
            with pytest.raises(AppError) as viewer_write:
                await update_company_profile(
                    session,
                    actor_user_id=viewer.id,
                    organization_id=organization.id,
                    changes={"industry": "Transport"},
                )
            assert viewer_write.value.code == "ORGANIZATION_WRITE_FORBIDDEN"
            with pytest.raises(AppError) as advertiser_admin_field:
                await update_company_profile(
                    session,
                    actor_user_id=owner.id,
                    organization_id=organization.id,
                    changes={"profile_notes": "internal"},
                )
            assert advertiser_admin_field.value.code == "COMPANY_PROFILE_FIELD_FORBIDDEN"

            updated = await update_company_profile(
                session,
                actor_user_id=admin.id,
                organization_id=other_organization.id,
                changes={"profile_notes": "Account team only", "status": "suspended"},
            )
            await session.commit()
            assert updated.profile_notes == "Account team only"
            assert updated.status == "suspended"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"billing_email": "not-an-email"}, "INVALID_COMPANY_PROFILE"),
        ({"address_country_code": "Nigeria"}, "INVALID_COMPANY_PROFILE"),
        ({}, "COMPANY_PROFILE_CHANGES_REQUIRED"),
    ],
)
def test_company_profile_validation_fails_closed(db_sessionmaker, changes, expected_code) -> None:
    owner = create_test_user(
        db_sessionmaker, email="profile-validation@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as caught:
                await update_company_profile(
                    session,
                    actor_user_id=owner.id,
                    organization_id=organization.id,
                    changes=changes,
                )
            assert caught.value.code == expected_code

    asyncio.run(scenario())
