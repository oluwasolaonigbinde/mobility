from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from starlette import status as http_status

from app.models.user import UserRole

PASSWORD = "long-secure-password"


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
