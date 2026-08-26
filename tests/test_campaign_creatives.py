# ruff: noqa: F401, F811

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_creative,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from starlette import status as http_status
from test_file_scanning import confirm_png, file_boundaries, scan_file

from app.models.organization import MembershipRole
from app.models.user import UserRole

PASSWORD = "long-secure-password"


def create_advertiser_campaign(
    db_sessionmaker,
    *,
    email: str,
    role: MembershipRole = MembershipRole.OWNER,
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
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
    )
    return advertiser, organization, campaign


def creative_payload(stored_file_id: str, **overrides):
    payload = {
        "name": " Exterior Wrap Artwork ",
        "creative_type": "image",
        "placement": "vehicle_exterior",
        "stored_file_id": stored_file_id,
        "width_px": 1200,
        "height_px": 800,
        "duration_seconds": None,
        "status": "draft",
        "metadata": {"asset": "managed-file"},
    }
    payload.update(overrides)
    return payload


def test_advertiser_owner_can_create_creative_metadata_with_audit(
    db_client,
    db_sessionmaker,
    file_boundaries,
) -> None:
    storage, scanner = file_boundaries
    advertiser, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="owner@example.com",
    )

    stored = confirm_png(db_client, storage, advertiser.email)
    scan_file(db_sessionmaker, stored["id"], storage, scanner)
    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, "owner@example.com", PASSWORD),
        json=creative_payload(stored["id"]),
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    data = response.json()
    assert data["campaign_id"] == str(campaign.id)
    assert data["name"] == "Exterior Wrap Artwork"
    assert data["stored_file_id"] == stored["id"]
    assert data["asset_source"] == "managed_file"
    assert data["asset_url"] is None
    assert data["mime_type"] == "image/png"
    assert data["checksum"] == stored["checksum_sha256"]
    assert data["metadata"] == {"asset": "managed-file"}
    assert "password_hash" not in response.text

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [
        event.action
        for event in audit_events
        if event.action == "advertiser.campaign_creative.created"
    ] == ["advertiser.campaign_creative.created"]


def test_advertiser_manager_can_create_creative_metadata(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    storage, scanner = file_boundaries
    manager, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="manager@example.com",
        role=MembershipRole.MANAGER,
    )

    stored = confirm_png(db_client, storage, manager.email)
    scan_file(db_sessionmaker, stored["id"], storage, scanner)
    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, "manager@example.com", PASSWORD),
        json=creative_payload(stored["id"]),
    )

    assert response.status_code == http_status.HTTP_201_CREATED
    assert response.json()["campaign_id"] == str(campaign.id)


def test_viewer_cannot_create_or_update_creative_metadata(db_client, db_sessionmaker) -> None:
    _, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="viewer@example.com",
        role=MembershipRole.VIEWER,
    )
    creative = create_test_campaign_creative(db_sessionmaker, campaign_id=campaign.id)

    create_response = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, "viewer@example.com", PASSWORD),
        json=creative_payload(str(campaign.id)),
    )
    update_response = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=auth_headers(db_client, "viewer@example.com", PASSWORD),
        json={"name": "Updated"},
    )

    assert create_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert update_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert create_response.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"
    assert update_response.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"


def test_creative_list_read_and_update_are_campaign_and_tenant_scoped(
    db_client,
    db_sessionmaker,
) -> None:
    advertiser, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    other_advertiser, _, other_campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="other@example.com",
    )
    own_creative = create_test_campaign_creative(db_sessionmaker, campaign_id=campaign.id)
    other_campaign_creative = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=other_campaign.id,
        name="Other Creative",
    )
    wrong_campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=campaign.organization_id,
        created_by_user_id=advertiser.id,
        name="Second Own Campaign",
    )
    del other_advertiser
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)

    list_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives?creative_type=image",
        headers=headers,
    )
    other_list_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/creatives",
        headers=headers,
    )
    own_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{own_creative.id}",
        headers=headers,
    )
    wrong_campaign_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{wrong_campaign.id}/creatives/{own_creative.id}",
        headers=headers,
    )
    other_creative_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/creatives/"
        f"{other_campaign_creative.id}",
        headers=headers,
    )
    update_response = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{own_creative.id}",
        headers=headers,
        json={"name": " Updated Creative ", "metadata": {"ready": False}},
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == str(own_creative.id)
    assert other_list_response.status_code == http_status.HTTP_404_NOT_FOUND
    assert own_response.status_code == http_status.HTTP_200_OK
    assert own_response.json()["id"] == str(own_creative.id)
    assert wrong_campaign_response.status_code == http_status.HTTP_404_NOT_FOUND
    assert other_creative_response.status_code == http_status.HTTP_404_NOT_FOUND
    assert update_response.status_code == http_status.HTTP_200_OK
    assert update_response.json()["name"] == "Updated Creative"
    assert update_response.json()["status"] == "draft"
    assert update_response.json()["metadata"] == {"ready": False}

    audit_events = fetch_audit_events(db_sessionmaker)
    assert [event.action for event in audit_events] == ["advertiser.campaign_creative.updated"]


def test_creative_create_rejects_cross_org_campaign(db_client, db_sessionmaker) -> None:
    create_advertiser_campaign(db_sessionmaker, email="advertiser@example.com")
    _, _, other_campaign = create_advertiser_campaign(db_sessionmaker, email="other@example.com")

    response = db_client.post(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/creatives",
        headers=auth_headers(db_client, "advertiser@example.com", PASSWORD),
        json=creative_payload(str(other_campaign.id)),
    )

    assert response.status_code == http_status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "CAMPAIGN_NOT_FOUND"


def test_creative_create_validation_rejects_invalid_inputs(db_client, db_sessionmaker) -> None:
    _, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)
    invalid_payloads = [
        creative_payload(str(campaign.id), creative_type="audio"),
        creative_payload(str(campaign.id), placement="roof"),
        creative_payload(str(campaign.id), status="published"),
        creative_payload(str(campaign.id), name="   "),
        creative_payload("not-a-uuid"),
        creative_payload(str(campaign.id), asset_url="https://example.com/wrap.png"),
        creative_payload(str(campaign.id), mime_type="image/png"),
        creative_payload(str(campaign.id), width_px=0),
        creative_payload(str(campaign.id), height_px=-1),
        creative_payload(str(campaign.id), duration_seconds=0),
        creative_payload(str(campaign.id), metadata=["not", "object"]),
        creative_payload(str(campaign.id), binary_data="not-allowed"),
    ]

    responses = [
        db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
            headers=headers,
            json=payload,
        )
        for payload in invalid_payloads
    ]

    assert all(
        response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        for response in responses
    )
    assert {response.json()["error"]["code"] for response in responses} == {"VALIDATION_ERROR"}


def test_creative_patch_rejects_null_required_fields_and_metadata(
    db_client,
    db_sessionmaker,
) -> None:
    _, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="advertiser@example.com",
    )
    creative = create_test_campaign_creative(db_sessionmaker, campaign_id=campaign.id)
    headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)

    null_name = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"name": None},
    )
    null_type = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"creative_type": None},
    )
    null_placement = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"placement": None},
    )
    null_status = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"status": None},
    )
    null_metadata = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"metadata": None},
    )
    campaign_id_update = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"campaign_id": str(campaign.id)},
    )
    binary_update = db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative.id}",
        headers=headers,
        json={"binary_data": "not-allowed"},
    )

    assert null_name.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_type.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_placement.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_status.status_code == http_status.HTTP_400_BAD_REQUEST
    assert null_metadata.status_code == http_status.HTTP_400_BAD_REQUEST
    assert campaign_id_update.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert binary_update.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert null_name.json()["error"]["code"] == "INVALID_CAMPAIGN_CREATIVE_UPDATE"
    assert null_type.json()["error"]["code"] == "INVALID_CAMPAIGN_CREATIVE_UPDATE"
    assert null_placement.json()["error"]["code"] == "INVALID_CAMPAIGN_CREATIVE_UPDATE"
    assert null_status.json()["error"]["code"] == "INVALID_CAMPAIGN_CREATIVE_UPDATE"
    assert null_metadata.json()["error"]["code"] == "INVALID_METADATA"
    assert campaign_id_update.json()["error"]["code"] == "VALIDATION_ERROR"
    assert binary_update.json()["error"]["code"] == "VALIDATION_ERROR"


def test_non_advertisers_and_unauthenticated_are_rejected_from_creative_endpoints(
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
    _, _, campaign = create_advertiser_campaign(
        db_sessionmaker,
        email="advertiser@example.com",
    )

    admin_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
    )
    driver_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, "driver@example.com", PASSWORD),
    )
    unauthenticated_response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives"
    )

    assert admin_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert driver_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert admin_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert driver_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert unauthenticated_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
