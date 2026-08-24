from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from starlette import status as http_status

from app.models.campaign import CampaignStatus
from app.models.organization import MembershipRole, MembershipStatus
from app.models.user import UserRole

PASSWORD = "long-secure-password"


def create_advertiser_with_org(
    db_sessionmaker,
    *,
    email: str,
    role: MembershipRole = MembershipRole.OWNER,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
    currency: str = "NGN",
):
    advertiser = create_test_user(
        db_sessionmaker,
        email=email,
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(
        db_sessionmaker,
        owner_user_id=advertiser.id,
        membership_role=role,
        membership_status=membership_status,
        currency=currency,
    )
    return advertiser, organization


def campaign_payload(**overrides):
    payload = {
        "name": " Lagos Launch Campaign ",
        "description": " Brand campaign across shared ride vehicles. ",
        "status": "draft",
        "start_at": "2026-06-01T00:00:00Z",
        "end_at": "2026-06-30T23:59:59Z",
        "budget_amount": "500000.00",
        "daily_budget_amount": "25000.00",
        "metadata": {"channel": "vehicle"},
    }
    payload.update(overrides)
    return payload


def test_advertiser_owner_can_create_campaign_with_inferred_org_and_audit(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="owner@example.com",
        currency="usd",
    )

    response = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "owner@example.com", PASSWORD),
        json=campaign_payload(currency=None),
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["organization_id"] == str(organization.id)
    assert data["name"] == "Lagos Launch Campaign"
    assert data["description"] == "Brand campaign across shared ride vehicles."
    assert data["currency"] == "USD"
    assert data["budget_amount"] == "500000.00"
    assert data["daily_budget_amount"] == "25000.00"
    assert data["metadata"] == {"channel": "vehicle"}
    assert "created_by_user_id" not in data
    assert "password_hash" not in response.text
    del advertiser

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["advertiser.campaign.created"]


def test_advertiser_manager_can_create_campaign(db_client, db_sessionmaker) -> None:
    _, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="manager@example.com",
        role=MembershipRole.MANAGER,
    )

    response = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "manager@example.com", PASSWORD),
        json=campaign_payload(currency="ngn"),
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    assert response.json()["organization_id"] == str(organization.id)
    assert response.json()["currency"] == "NGN"


def test_active_campaign_creation_and_unfunded_activation_are_rejected(
    db_client, db_sessionmaker
) -> None:
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="commercial-activation@example.com",
    )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    active_create = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=headers,
        json=campaign_payload(status="active"),
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    activate_without_terms = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=headers,
        json={"status": "active"},
    )

    assert active_create.status_code == http_status.HTTP_409_CONFLICT
    assert active_create.json()["error"]["code"] == "CAMPAIGN_ACTIVE_CREATE_FORBIDDEN"
    assert activate_without_terms.status_code == http_status.HTTP_409_CONFLICT
    assert (
        activate_without_terms.json()["error"]["code"]
        == "PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED"
    )


def test_advertiser_viewer_and_missing_membership_cannot_write_campaigns(
    db_client,
    db_sessionmaker,
) -> None:
    viewer, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="viewer@example.com",
        role=MembershipRole.VIEWER,
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=viewer.id,
    )
    create_test_user(
        db_sessionmaker,
        email="no-org@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_advertiser_with_org(
        db_sessionmaker,
        email="invited-manager@example.com",
        role=MembershipRole.MANAGER,
        membership_status=MembershipStatus.INVITED,
    )

    viewer_create = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "viewer@example.com", PASSWORD),
        json=campaign_payload(),
    )
    viewer_update = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=auth_headers(db_client, "viewer@example.com", PASSWORD),
        json={"name": "Updated"},
    )
    missing_org_create = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "no-org@example.com", PASSWORD),
        json=campaign_payload(),
    )
    invited_manager_create = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "invited-manager@example.com", PASSWORD),
        json=campaign_payload(),
    )

    assert viewer_create.status_code == http_status.HTTP_403_FORBIDDEN
    assert viewer_update.status_code == http_status.HTTP_403_FORBIDDEN
    assert viewer_create.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"
    assert viewer_update.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"
    assert missing_org_create.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_org_create.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"
    assert invited_manager_create.status_code == http_status.HTTP_403_FORBIDDEN
    assert (
        invited_manager_create.json()["error"]["code"]
        == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"
    )


def test_non_advertisers_and_unauthenticated_are_rejected_from_advertiser_campaigns(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    create_test_user(
        db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    admin_response = db_client.get(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
    )
    driver_response = db_client.get(
        "/api/v1/advertiser/campaigns",
        headers=auth_headers(db_client, "driver@example.com", PASSWORD),
    )
    unauthenticated_response = db_client.get("/api/v1/advertiser/campaigns")

    assert admin_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert driver_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert admin_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert driver_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert unauthenticated_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_advertiser_campaign_list_read_and_update_are_tenant_scoped(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    other_advertiser, other_organization = create_advertiser_with_org(
        db_sessionmaker,
        email="other@example.com",
    )
    own_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        campaign_status=CampaignStatus.ACTIVE,
    )
    other_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=other_organization.id,
        created_by_user_id=other_advertiser.id,
        name="Other Org Campaign",
    )
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)

    list_response = db_client.get("/api/v1/advertiser/campaigns", headers=headers)
    filtered_response = db_client.get(
        "/api/v1/advertiser/campaigns?status=active&limit=1&offset=0",
        headers=headers,
    )
    own_response = db_client.get(f"/api/v1/advertiser/campaigns/{own_campaign.id}", headers=headers)
    other_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}",
        headers=headers,
    )
    update_response = db_client.patch(
        f"/api/v1/advertiser/campaigns/{own_campaign.id}",
        headers=headers,
        json={"name": " Updated Campaign ", "status": "paused", "metadata": {"phase": "hold"}},
    )
    other_update = db_client.patch(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}",
        headers=headers,
        json={"name": "Nope"},
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == str(own_campaign.id)
    assert filtered_response.status_code == http_status.HTTP_200_OK
    assert filtered_response.json()["total"] == 1
    assert filtered_response.json()["limit"] == 1
    assert own_response.status_code == http_status.HTTP_200_OK
    assert own_response.json()["id"] == str(own_campaign.id)
    assert other_response.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_update.status_code == http_status.HTTP_404_NOT_FOUND
    assert update_response.status_code == http_status.HTTP_200_OK
    assert update_response.json()["name"] == "Updated Campaign"
    assert update_response.json()["status"] == "paused"
    assert update_response.json()["metadata"] == {"phase": "hold"}

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["advertiser.campaign.updated"]


def test_campaign_create_validation_rejects_invalid_inputs(db_client, db_sessionmaker) -> None:
    create_advertiser_with_org(db_sessionmaker, email="advertiser@example.com")
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)
    invalid_payloads = [
        campaign_payload(status="queued"),
        campaign_payload(name="   "),
        campaign_payload(budget_amount="-1.00"),
        campaign_payload(daily_budget_amount="600000.00"),
        campaign_payload(start_at="2026-07-01T00:00:00Z", end_at="2026-06-01T00:00:00Z"),
        campaign_payload(currency="NG"),
        campaign_payload(currency="N1N"),
        campaign_payload(metadata=["not", "object"]),
        campaign_payload(organization_id="00000000-0000-0000-0000-000000000000"),
        campaign_payload(zone_ids=[]),
    ]

    responses = [
        db_client.post("/api/v1/advertiser/campaigns", headers=headers, json=payload)
        for payload in invalid_payloads
    ]

    assert all(
        response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        for response in responses
    )
    assert {response.json()["error"]["code"] for response in responses} == {"VALIDATION_ERROR"}


def test_campaign_patch_validation_rejects_invalid_combined_state(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        budget_amount="100.00",
        daily_budget_amount="50.00",
    )
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)

    null_name = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=headers,
        json={"name": None},
    )
    invalid_budget = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=headers,
        json={"daily_budget_amount": "150.00"},
    )
    invalid_total_budget = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=headers,
        json={"budget_amount": "40.00"},
    )
    date_campaign = db_client.post(
        "/api/v1/advertiser/campaigns",
        headers=headers,
        json=campaign_payload(
            name="Date Campaign",
            start_at="2026-06-01T00:00:00Z",
            end_at="2026-06-30T00:00:00Z",
        ),
    )
    assert date_campaign.status_code == http_status.HTTP_201_CREATED
    invalid_date = db_client.patch(
        f"/api/v1/advertiser/campaigns/{date_campaign.json()['id']}",
        headers=headers,
        json={"start_at": "2026-07-01T00:00:00Z"},
    )
    null_metadata = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}",
        headers=headers,
        json={"metadata": None},
    )

    assert null_name.status_code == http_status.HTTP_400_BAD_REQUEST
    assert invalid_budget.status_code == http_status.HTTP_400_BAD_REQUEST
    assert invalid_total_budget.status_code == http_status.HTTP_400_BAD_REQUEST
    assert invalid_date.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_metadata.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_name.json()["error"]["code"] == "INVALID_CAMPAIGN_UPDATE"
    assert invalid_budget.json()["error"]["code"] == "INVALID_CAMPAIGN_BUDGET"
    assert invalid_total_budget.json()["error"]["code"] == "INVALID_CAMPAIGN_BUDGET"
    assert invalid_date.json()["error"]["code"] == "INVALID_CAMPAIGN_DATES"
    assert null_metadata.json()["error"]["code"] == "INVALID_METADATA"


def test_admin_can_list_and_read_campaigns_across_organizations(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="admin@example.com", password=PASSWORD)
    advertiser, organization = create_advertiser_with_org(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    other_advertiser, other_organization = create_advertiser_with_org(
        db_sessionmaker,
        email="other@example.com",
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="First Campaign",
    )
    create_test_campaign(
        db_sessionmaker,
        organization_id=other_organization.id,
        created_by_user_id=other_advertiser.id,
        name="Second Campaign",
    )
    headers = auth_headers(db_client, "admin@example.com", PASSWORD)

    list_response = db_client.get("/api/v1/admin/campaigns", headers=headers)
    filtered_response = db_client.get(
        f"/api/v1/admin/campaigns?organization_id={organization.id}",
        headers=headers,
    )
    get_response = db_client.get(f"/api/v1/admin/campaigns/{campaign.id}", headers=headers)
    advertiser_response = db_client.get(
        "/api/v1/admin/campaigns",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 2
    assert filtered_response.status_code == http_status.HTTP_200_OK
    assert filtered_response.json()["total"] == 1
    assert filtered_response.json()["items"][0]["organization"]["id"] == str(organization.id)
    assert get_response.status_code == http_status.HTTP_200_OK
    assert get_response.json()["organization"]["name"] == organization.name
    assert "password_hash" not in list_response.text
    assert "password_hash" not in get_response.text
    assert advertiser_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert advertiser_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
