import asyncio

import pytest
from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from starlette import status as http_status

from app.core.config import Settings
from app.core.errors import AppError
from app.db.integrity import integrity_constraint_name
from app.models.organization import (
    AdvertiserOrganization,
    MembershipStatus,
    OrganizationMembership,
)
from app.models.user import UserRole
from app.schemas.organizations import AdvertiserOrganizationCreate
from app.services.organizations import create_advertiser_organization

PASSWORD = "long-secure-password"


def _company_payload(owner_id, name="Acme Ads") -> dict:
    return {
        "name": name,
        "billing_email": "billing@acme.test",
        "country_code": "NG",
        "currency": "NGN",
        "status": "active",
        "owner_user_id": str(owner_id),
    }


def _count(sessionmaker, model, *criteria) -> int:
    async def read() -> int:
        async with sessionmaker() as session:
            statement = select(func.count()).select_from(model).where(*criteria)
            return int(await session.scalar(statement))

    return asyncio.run(read())


def test_advertiser_login_cannot_own_a_second_active_company(
    db_client,
    db_sessionmaker,
) -> None:
    """D29: one active advertiser company per login, and a refusal leaves no rows."""
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    owner = create_test_user(
        db_sessionmaker,
        email="owner@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)
    first = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=headers,
        json=_company_payload(owner.id, "First Co"),
    )
    assert first.status_code == http_status.HTTP_201_CREATED

    second = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=headers,
        json=_company_payload(owner.id, "Second Co"),
    )

    assert second.status_code == http_status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "ADVERTISER_COMPANY_EXISTS"
    assert _count(db_sessionmaker, AdvertiserOrganization) == 1
    owner_memberships = _count(
        db_sessionmaker, OrganizationMembership, OrganizationMembership.user_id == owner.id
    )
    assert owner_memberships == 1
    context = db_client.get(
        "/api/v1/advertiser/organization",
        headers=auth_headers(db_client, "owner@example.com", PASSWORD),
    )
    assert context.json()["organization"]["name"] == "First Co"


def test_company_service_refuses_a_second_active_company_for_one_login(db_sessionmaker) -> None:
    owner = create_test_user(
        db_sessionmaker, email="service-owner@example.com", role=UserRole.ADVERTISER
    )
    settings = Settings(environment="test")

    async def create_two() -> tuple[str, int]:
        async with db_sessionmaker() as session:
            await create_advertiser_organization(
                session, AdvertiserOrganizationCreate(**_company_payload(owner.id)), settings
            )
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as refused:
                await create_advertiser_organization(
                    session,
                    AdvertiserOrganizationCreate(**_company_payload(owner.id, "Second Co")),
                    settings,
                )
            await session.rollback()
            return refused.value.code, refused.value.status_code

    assert asyncio.run(create_two()) == ("ADVERTISER_COMPANY_EXISTS", 409)
    assert _count(db_sessionmaker, AdvertiserOrganization) == 1


def test_advertiser_can_move_to_a_new_company_after_the_old_membership_is_disabled(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    owner = create_test_user(
        db_sessionmaker,
        email="owner@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(
        db_sessionmaker,
        name="Former Co",
        owner_user_id=owner.id,
        membership_status=MembershipStatus.DISABLED,
    )

    response = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json=_company_payload(owner.id, "New Co"),
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    context = db_client.get(
        "/api/v1/advertiser/organization",
        headers=auth_headers(db_client, "owner@example.com", PASSWORD),
    )
    assert context.json()["organization"]["name"] == "New Co"


def test_concurrent_company_creation_for_one_login_has_one_winner(
    postgis_db_sessionmaker,
) -> None:
    owner = create_test_user(
        postgis_db_sessionmaker,
        email="race-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    settings = Settings(environment="test")

    async def race():
        # Both transactions start before either commits, so neither can see the
        # other's membership; only the partial unique index can decide the race.
        started = asyncio.Barrier(2)

        async def create(name: str) -> str:
            async with postgis_db_sessionmaker() as session:
                await session.execute(select(func.now()))
                await started.wait()
                payload = AdvertiserOrganizationCreate(**_company_payload(owner.id, name))
                try:
                    organization, _ = await create_advertiser_organization(
                        session, payload, settings
                    )
                except AppError as exc:
                    await session.rollback()
                    return exc.code
                await session.commit()
                return organization.name

        return await asyncio.gather(create("Race One"), create("Race Two"))

    outcomes = asyncio.run(race())
    assert sorted(outcomes)[0] == "ADVERTISER_COMPANY_EXISTS"
    assert sorted(outcomes)[1] in {"Race One", "Race Two"}
    assert _count(postgis_db_sessionmaker, AdvertiserOrganization) == 1
    assert (
        _count(
            postgis_db_sessionmaker,
            OrganizationMembership,
            OrganizationMembership.user_id == owner.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
        == 1
    )


def test_a_second_active_membership_cannot_be_written_directly(db_sessionmaker) -> None:
    owner = create_test_user(
        db_sessionmaker,
        email="direct-owner@example.com",
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, name="Kept Co", owner_user_id=owner.id)
    _, invited = create_test_organization(
        db_sessionmaker,
        name="Invited Co",
        owner_user_id=owner.id,
        membership_status=MembershipStatus.INVITED,
    )
    assert invited is not None

    async def activate() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                update(OrganizationMembership)
                .where(OrganizationMembership.id == invited.id)
                .values(status=MembershipStatus.ACTIVE)
            )
            await session.commit()

    with pytest.raises(IntegrityError) as conflict:
        asyncio.run(activate())
    assert integrity_constraint_name(conflict.value) == "uq_organization_memberships_user_active"


def test_admin_can_create_advertiser_organization_with_owner(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    owner = create_test_user(
        db_sessionmaker,
        email="owner@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "name": "Acme Ads",
            "billing_email": "billing@acme.test",
            "country_code": "ng",
            "currency": "ngn",
            "status": "active",
            "owner_user_id": str(owner.id),
        },
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["organization"]["name"] == "Acme Ads"
    assert data["organization"]["country_code"] == "NG"
    assert data["organization"]["currency"] == "NGN"
    assert data["owner_membership"] == {"role": "owner", "status": "active"}

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == [
        "admin.advertiser_organization.created"
    ]


def test_organization_owner_attachment_rejects_non_advertiser_user(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    driver = create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.post(
        "/api/v1/admin/advertiser-organizations",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
        json={
            "name": "Acme Ads",
            "billing_email": "billing@acme.test",
            "country_code": "NG",
            "currency": "NGN",
            "status": "active",
            "owner_user_id": str(driver.id),
        },
    )

    assert response.status_code == http_status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "INVALID_OWNER_USER"


def test_advertiser_can_retrieve_only_own_organization_context(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other_advertiser = create_test_user(
        db_sessionmaker,
        email="other@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    own_organization, _ = create_test_organization(
        db_sessionmaker,
        name="Own Org",
        owner_user_id=advertiser.id,
    )
    create_test_organization(
        db_sessionmaker,
        name="Other Org",
        owner_user_id=other_advertiser.id,
    )

    response = db_client.get(
        "/api/v1/advertiser/organization",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_200_OK
    data = response.json()
    assert data["organization"]["id"] == str(own_organization.id)
    assert data["organization"]["name"] == "Own Org"
    assert data["membership"] == {"role": "owner", "status": "active"}


def test_driver_is_rejected_from_advertiser_organization_endpoint(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    response = db_client.get(
        "/api/v1/advertiser/organization",
        headers=auth_headers(db_client, "driver@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_advertiser_organization_endpoint_returns_clear_missing_org_error(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(
        db_sessionmaker,
        email="advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    response = db_client.get(
        "/api/v1/advertiser/organization",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"
