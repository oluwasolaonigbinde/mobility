import asyncio
from uuid import uuid4

from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette import status as http_status

from app.models.campaign import Campaign, CampaignStatus
from app.models.organization import MembershipRole, MembershipStatus, OrganizationMembership
from app.models.user import UserRole

PASSWORD = "long-secure-password"


def add_membership(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    *,
    organization_id,
    user_id,
    role: MembershipRole,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
) -> None:
    async def create() -> None:
        async with db_sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    organization_id=organization_id,
                    user_id=user_id,
                    role=role,
                    status=membership_status,
                )
            )
            await session.commit()

    asyncio.run(create())


def set_campaign_status(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    campaign_id,
    campaign_status: CampaignStatus,
) -> None:
    async def update() -> None:
        async with db_sessionmaker() as session:
            campaign = await session.get(Campaign, campaign_id)
            assert campaign is not None
            campaign.status = campaign_status
            await session.commit()

    asyncio.run(update())


def create_advertiser_campaign(
    db_sessionmaker,
    *,
    email: str,
    role: MembershipRole = MembershipRole.OWNER,
    campaign_status: CampaignStatus = CampaignStatus.DRAFT,
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
        campaign_status=campaign_status,
    )
    return advertiser, organization, campaign


def polygon_geometry(offset: float = 0.0):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [3.3900 + offset, 6.4500],
                [3.4100 + offset, 6.4500],
                [3.4100 + offset, 6.4700],
                [3.3900 + offset, 6.4700],
                [3.3900 + offset, 6.4500],
            ]
        ],
    }


def multipolygon_geometry():
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [3.3900, 6.4500],
                    [3.4100, 6.4500],
                    [3.4100, 6.4700],
                    [3.3900, 6.4700],
                    [3.3900, 6.4500],
                ]
            ]
        ],
    }


def zone_payload(**overrides):
    payload = {
        "name": " Lagos Island Target Zone ",
        "description": " Primary campaign exposure area. ",
        "zone_type": "target",
        "geometry": polygon_geometry(),
        "metadata": {"priority": "high"},
    }
    payload.update(overrides)
    return payload


def test_owner_and_manager_can_create_campaign_zones_with_geojson_and_audit(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, owner_campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="owner@example.com",
    )
    _, _, manager_campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="manager@example.com",
        role=MembershipRole.MANAGER,
    )

    owner_response = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{owner_campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "owner@example.com", PASSWORD),
        json=zone_payload(),
    )
    manager_response = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{manager_campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "manager@example.com", PASSWORD),
        json=zone_payload(
            name="Manager Bonus Zone",
            zone_type="bonus",
            geometry=multipolygon_geometry(),
        ),
    )

    assert owner_response.status_code == http_status.HTTP_201_CREATED
    owner_data = owner_response.json()
    assert owner_data["campaign_id"] == str(owner_campaign.id)
    assert owner_data["name"] == "Lagos Island Target Zone"
    assert owner_data["description"] == "Primary campaign exposure area."
    assert owner_data["zone_type"] == "target"
    assert owner_data["geometry"]["type"] == "MultiPolygon"
    assert float(owner_data["area_sq_m"]) > 0
    assert owner_data["metadata"] == {"priority": "high"}
    assert "created_by_user_id" not in owner_data
    assert "password_hash" not in owner_response.text
    assert "POLYGON" not in owner_response.text

    assert manager_response.status_code == http_status.HTTP_201_CREATED
    assert manager_response.json()["zone_type"] == "bonus"
    assert manager_response.json()["geometry"]["type"] == "MultiPolygon"

    audit_events = fetch_audit_events(postgis_db_sessionmaker)
    assert [event.action for event in audit_events] == [
        "advertiser.campaign_zone.created",
        "advertiser.campaign_zone.created",
    ]


def test_viewer_can_list_and_read_but_cannot_write_campaign_zones(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    owner, organization, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="owner@example.com",
    )
    viewer = create_test_user(
        postgis_db_sessionmaker,
        email="viewer@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    add_membership(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        user_id=viewer.id,
        role=MembershipRole.VIEWER,
    )
    create_response = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "owner@example.com", PASSWORD),
        json=zone_payload(),
    )
    assert create_response.status_code == http_status.HTTP_201_CREATED
    zone_id = create_response.json()["id"]
    del owner

    headers = auth_headers(postgis_db_client, "viewer@example.com", PASSWORD)
    list_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
    )
    read_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
    )
    viewer_create = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(name="Viewer Write"),
    )
    viewer_update = postgis_db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
        json={"name": "Viewer Update"},
    )
    viewer_delete = postgis_db_client.delete(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert read_response.status_code == http_status.HTTP_200_OK
    assert read_response.json()["id"] == zone_id
    assert viewer_create.status_code == http_status.HTTP_403_FORBIDDEN
    assert viewer_update.status_code == http_status.HTTP_403_FORBIDDEN
    assert viewer_delete.status_code == http_status.HTTP_403_FORBIDDEN
    assert viewer_create.json()["error"]["code"] == "ADVERTISER_MEMBERSHIP_WRITE_FORBIDDEN"


def test_non_advertisers_unauthenticated_and_missing_membership_are_rejected(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="advertiser@example.com",
    )
    create_test_user(postgis_db_sessionmaker, email="admin@example.com", password=PASSWORD)
    create_test_user(
        postgis_db_sessionmaker,
        email="driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    create_test_user(
        postgis_db_sessionmaker,
        email="no-org@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )

    admin_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "admin@example.com", PASSWORD),
    )
    driver_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "driver@example.com", PASSWORD),
    )
    unauthenticated_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones"
    )
    missing_membership_list = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "no-org@example.com", PASSWORD),
    )
    missing_membership_create = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "no-org@example.com", PASSWORD),
        json=zone_payload(),
    )

    assert admin_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert driver_response.status_code == http_status.HTTP_403_FORBIDDEN
    assert unauthenticated_response.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert missing_membership_list.status_code == http_status.HTTP_404_NOT_FOUND
    assert missing_membership_create.status_code == http_status.HTTP_404_NOT_FOUND
    assert admin_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert driver_response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert unauthenticated_response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert missing_membership_create.json()["error"]["code"] == "ADVERTISER_ORGANIZATION_NOT_FOUND"


def test_campaign_zones_are_tenant_and_campaign_scoped(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    advertiser, organization, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="advertiser@example.com",
    )
    _, _, other_campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="other@example.com",
    )
    wrong_campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        name="Second Own Campaign",
    )
    headers = auth_headers(postgis_db_client, "advertiser@example.com", PASSWORD)
    own_zone = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(),
    )
    other_zone = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/zones",
        headers=auth_headers(postgis_db_client, "other@example.com", PASSWORD),
        json=zone_payload(name="Other Zone", geometry=polygon_geometry(0.1)),
    )
    assert own_zone.status_code == http_status.HTTP_201_CREATED
    assert other_zone.status_code == http_status.HTTP_201_CREATED

    list_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones?zone_type=target",
        headers=headers,
    )
    other_campaign_list = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/zones",
        headers=headers,
    )
    read_own = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{own_zone.json()['id']}",
        headers=headers,
    )
    read_other = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/zones/{other_zone.json()['id']}",
        headers=headers,
    )
    read_wrong_campaign = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{wrong_campaign.id}/zones/{own_zone.json()['id']}",
        headers=headers,
    )
    update_other = postgis_db_client.patch(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/zones/{other_zone.json()['id']}",
        headers=headers,
        json={"name": "Nope"},
    )
    delete_other = postgis_db_client.delete(
        f"/api/v1/advertiser/campaigns/{other_campaign.id}/zones/{other_zone.json()['id']}",
        headers=headers,
    )

    assert list_response.status_code == http_status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == own_zone.json()["id"]
    assert other_campaign_list.status_code == http_status.HTTP_404_NOT_FOUND
    assert read_own.status_code == http_status.HTTP_200_OK
    assert read_other.status_code == http_status.HTTP_404_NOT_FOUND
    assert read_wrong_campaign.status_code == http_status.HTTP_404_NOT_FOUND
    assert update_other.status_code == http_status.HTTP_404_NOT_FOUND
    assert delete_other.status_code == http_status.HTTP_404_NOT_FOUND


def test_owner_can_update_and_delete_campaign_zone_with_audit(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="owner@example.com",
    )
    headers = auth_headers(postgis_db_client, "owner@example.com", PASSWORD)
    create_response = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(),
    )
    assert create_response.status_code == http_status.HTTP_201_CREATED
    zone_id = create_response.json()["id"]
    original_area = create_response.json()["area_sq_m"]

    update_response = postgis_db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
        json={
            "name": " Updated Bonus Zone ",
            "description": None,
            "zone_type": "bonus",
            "geometry": polygon_geometry(0.02),
            "metadata": {"updated": True},
        },
    )
    delete_response = postgis_db_client.delete(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
    )
    read_deleted = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
    )
    list_deleted = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
    )

    assert update_response.status_code == http_status.HTTP_200_OK
    assert update_response.json()["name"] == "Updated Bonus Zone"
    assert update_response.json()["description"] is None
    assert update_response.json()["zone_type"] == "bonus"
    assert update_response.json()["metadata"] == {"updated": True}
    assert update_response.json()["area_sq_m"] == original_area
    assert delete_response.status_code == http_status.HTTP_204_NO_CONTENT
    assert read_deleted.status_code == http_status.HTTP_404_NOT_FOUND
    assert list_deleted.status_code == http_status.HTTP_200_OK
    assert list_deleted.json()["total"] == 0

    audit_events = fetch_audit_events(postgis_db_sessionmaker)
    assert [event.action for event in audit_events] == [
        "advertiser.campaign_zone.created",
        "advertiser.campaign_zone.updated",
        "advertiser.campaign_zone.deleted",
    ]


def test_campaign_lifecycle_blocks_mutation_but_allows_reads(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    for blocked_status in [CampaignStatus.COMPLETED, CampaignStatus.CANCELLED]:
        _, _, campaign = create_advertiser_campaign(
            postgis_db_sessionmaker,
            email=f"{blocked_status}@example.com",
        )
        headers = auth_headers(postgis_db_client, f"{blocked_status}@example.com", PASSWORD)
        create_response = postgis_db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
            headers=headers,
            json=zone_payload(name=f"{blocked_status} zone"),
        )
        assert create_response.status_code == http_status.HTTP_201_CREATED
        zone_id = create_response.json()["id"]
        set_campaign_status(postgis_db_sessionmaker, campaign.id, blocked_status)

        list_response = postgis_db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
            headers=headers,
        )
        read_response = postgis_db_client.get(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
            headers=headers,
        )
        create_blocked = postgis_db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
            headers=headers,
            json=zone_payload(name="blocked create"),
        )
        update_blocked = postgis_db_client.patch(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
            headers=headers,
            json={"name": "blocked update"},
        )
        delete_blocked = postgis_db_client.delete(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
            headers=headers,
        )

        assert list_response.status_code == http_status.HTTP_200_OK
        assert read_response.status_code == http_status.HTTP_200_OK
        assert create_blocked.status_code == http_status.HTTP_400_BAD_REQUEST
        assert update_blocked.status_code == http_status.HTTP_400_BAD_REQUEST
        assert delete_blocked.status_code == http_status.HTTP_400_BAD_REQUEST
        assert (
            create_blocked.json()["error"]["code"]
            == "CAMPAIGN_STATUS_FORBIDS_ZONE_MUTATION"
        )


def test_geojson_and_schema_validation_reject_invalid_zone_payloads(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="advertiser@example.com",
    )
    headers = auth_headers(postgis_db_client, "advertiser@example.com", PASSWORD)
    invalid_geojson_payloads = [
        zone_payload(geometry={"type": "Point", "coordinates": [3.39, 6.45]}),
        zone_payload(geometry={"type": "FeatureCollection", "features": []}),
        zone_payload(geometry={"type": "Polygon", "coordinates": []}),
        zone_payload(
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [[181.0, 6.45], [3.41, 6.45], [3.41, 6.47], [181.0, 6.45]]
                ],
            },
        ),
        zone_payload(
            geometry={
                "type": "Polygon",
                "coordinates": [[[3.39, 6.45], [3.41, 6.45], [3.41, 6.47], [3.39, 6.47]]],
            },
        ),
        zone_payload(
            geometry={
                "type": "Polygon",
                "coordinates": [[[3.39, 6.45], [3.41, 6.45], [3.39, 6.45]]],
            },
        ),
    ]
    schema_invalid_payloads = [
        zone_payload(name="   "),
        zone_payload(zone_type="premium"),
        zone_payload(metadata=["not", "object"]),
        zone_payload(campaign_id=str(campaign.id)),
        zone_payload(created_by_user_id=str(uuid4())),
    ]

    geojson_responses = [
        postgis_db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
            headers=headers,
            json=payload,
        )
        for payload in invalid_geojson_payloads
    ]
    schema_responses = [
        postgis_db_client.post(
            f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
            headers=headers,
            json=payload,
        )
        for payload in schema_invalid_payloads
    ]

    assert all(
        response.status_code == http_status.HTTP_400_BAD_REQUEST
        for response in geojson_responses
    )
    assert {response.json()["error"]["code"] for response in geojson_responses} == {
        "INVALID_GEOJSON"
    }
    assert all(
        response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
        for response in schema_responses
    )
    assert {response.json()["error"]["code"] for response in schema_responses} == {
        "VALIDATION_ERROR"
    }


def test_postgis_invalidity_area_cap_and_patch_integrity(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    _, _, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="advertiser@example.com",
    )
    headers = auth_headers(postgis_db_client, "advertiser@example.com", PASSWORD)
    create_response = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(),
    )
    assert create_response.status_code == http_status.HTTP_201_CREATED
    zone_id = create_response.json()["id"]
    original_name = create_response.json()["name"]

    self_intersecting = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.39, 6.45],
                        [3.43, 6.49],
                        [3.39, 6.49],
                        [3.43, 6.45],
                        [3.39, 6.45],
                    ]
                ],
            },
        ),
    )
    too_large = postgis_db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones",
        headers=headers,
        json=zone_payload(
            geometry={
                "type": "Polygon",
                "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
            },
        ),
    )
    invalid_patch = postgis_db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
        json={"name": "Should Not Persist", "geometry": {"type": "Point", "coordinates": [0, 0]}},
    )
    read_after_invalid_patch = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
    )
    area_update = postgis_db_client.patch(
        f"/api/v1/advertiser/campaigns/{campaign.id}/zones/{zone_id}",
        headers=headers,
        json={
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3.3900, 6.4500],
                        [3.4200, 6.4500],
                        [3.4200, 6.4800],
                        [3.3900, 6.4800],
                        [3.3900, 6.4500],
                    ]
                ],
            }
        },
    )

    assert self_intersecting.status_code == http_status.HTTP_400_BAD_REQUEST
    assert self_intersecting.json()["error"]["code"] == "INVALID_POLYGON"
    assert too_large.status_code == http_status.HTTP_400_BAD_REQUEST
    assert too_large.json()["error"]["code"] == "CAMPAIGN_ZONE_AREA_EXCEEDED"
    assert invalid_patch.status_code == http_status.HTTP_400_BAD_REQUEST
    assert read_after_invalid_patch.status_code == http_status.HTTP_200_OK
    assert read_after_invalid_patch.json()["name"] == original_name
    assert area_update.status_code == http_status.HTTP_200_OK
    assert area_update.json()["area_sq_m"] != create_response.json()["area_sq_m"]
