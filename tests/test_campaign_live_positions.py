import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_campaign_zone,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.disclosure import DisclosureQueryDecision
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.models.user import UserRole
from app.services import campaign_live_positions
from app.services.campaign_zones import geometry_expression
from app.services.trips import point_value

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
PASSWORD = "long-secure-password"


@pytest.fixture
def driving_graph(db_sessionmaker, monkeypatch):
    async def clock(_session):
        return NOW

    monkeypatch.setattr(campaign_live_positions, "database_clock", clock)
    owner = create_test_user(
        db_sessionmaker, email="map-owner@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    org, membership = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=org.id,
        created_by_user_id=owner.id,
        campaign_status=CampaignStatus.ACTIVE,
        start_at=NOW - timedelta(days=2),
        end_at=NOW + timedelta(days=5),
    )
    driver = create_test_user(
        db_sessionmaker, email="private-driver@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(
        db_sessionmaker, driver_profile_id=profile.id, plate_number="PRIVATE-CAR"
    )
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=owner.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        started_at=NOW - timedelta(hours=1),
    )
    create_test_campaign_zone(db_sessionmaker, campaign_id=campaign.id, created_by_user_id=owner.id)
    return {
        "owner": owner,
        "org": org,
        "membership": membership,
        "campaign": campaign,
        "driver": driver,
        "vehicle": vehicle,
        "assignment": assignment,
        "trip": trip,
    }


def add_point(maker, graph, *, age=20, received_age=20, speed=4, lon=3.4, lat=6.5, ping_id=None):
    async def add():
        async with maker() as session:
            batch = LocationPingBatch(
                trip_session_id=graph["trip"].id,
                idempotency_key=str(uuid4()),
                payload_hash="test",
                pings_accepted=1,
                pings_submitted=1,
                pings_rejected=0,
                received_at=NOW - timedelta(minutes=received_age),
                batch_metadata={},
            )
            session.add(batch)
            await session.flush()
            session.add(
                LocationPing(
                    id=ping_id or uuid4(),
                    trip_session_id=graph["trip"].id,
                    batch_id=batch.id,
                    recorded_at=NOW - timedelta(minutes=age),
                    received_at=NOW - timedelta(minutes=received_age),
                    latitude=lat,
                    longitude=lon,
                    speed_mps=speed,
                    geom=point_value(session, lon=lon, lat=lat),
                    ping_metadata={},
                )
            )
            await session.commit()

    asyncio.run(add())


def read(client, graph, suffix=""):
    return client.get(
        f"/api/v1/advertiser/campaigns/{graph['campaign'].id}/live-positions{suffix}",
        headers=auth_headers(client, "map-owner@example.com", PASSWORD),
    )


def test_single_car_is_delayed_in_area_and_identity_free(db_client, db_sessionmaker, driving_graph):
    add_point(db_sessionmaker, driving_graph)
    response = read(db_client, driving_graph)
    assert response.status_code == 200
    assert response.json() == {
        "campaign_id": str(driving_graph["campaign"].id),
        "delay_minutes": 15,
        "positions": [{"longitude": 3.4, "latitude": 6.5}],
    }
    assert "no-store" in response.headers["cache-control"]
    for key in ("driver", "vehicle", "trip", "assignment"):
        assert str(driving_graph[key].id) not in response.text
    assert "PRIVATE" not in response.text
    assert read(db_client, driving_graph).json() == response.json()

    async def history():
        async with db_sessionmaker() as session:
            rows = (
                await session.scalars(
                    select(DisclosureQueryDecision).where(
                        DisclosureQueryDecision.output_class == campaign_live_positions.ROUTE
                    )
                )
            ).all()
            assert len(rows) == 2
            assert len({row.result_hash for row in rows}) == 2
            for row in rows:
                assert row.decision == "served" and len(row.result_hash) == 64
                assert row.window_start == NOW - timedelta(minutes=30)
                assert row.window_end == NOW - timedelta(minutes=15)
                payload = json.dumps(
                    {column.key: str(getattr(row, column.key)) for column in row.__table__.columns}
                )
                assert "longitude" not in payload and "latitude" not in payload
                for key in ("driver", "vehicle", "trip", "assignment"):
                    assert str(driving_graph[key].id) not in payload

    asyncio.run(history())


def test_audit_commit_failure_does_not_release_positions(
    db_client, db_sessionmaker, driving_graph, monkeypatch
):
    add_point(db_sessionmaker, driving_graph)
    headers = auth_headers(db_client, "map-owner@example.com", PASSWORD)
    record = campaign_live_positions.record_disclosure

    async def fail_commit():
        raise RuntimeError("synthetic audit persistence failure")

    async def failing_record(session, **kwargs):
        monkeypatch.setattr(session, "commit", fail_commit)
        await record(session, **kwargs)

    monkeypatch.setattr(campaign_live_positions, "record_disclosure", failing_record)
    with TestClient(db_client.app, raise_server_exceptions=False) as http:
        response = http.get(
            f"/api/v1/advertiser/campaigns/{driving_graph['campaign'].id}/live-positions",
            headers=headers,
        )
    assert response.status_code == 500
    assert "positions" not in response.text
    assert "longitude" not in response.text and "latitude" not in response.text

    async def no_history():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(DisclosureQueryDecision.id)) is None

    asyncio.run(no_history())


@pytest.mark.parametrize(
    "age,received_age,visible",
    [(15, 15, True), (30, 30, True), (14.99, 20, False), (20, 14.99, False), (30.01, 31, False)],
)
def test_recorded_received_and_stale_boundaries(
    db_client, db_sessionmaker, driving_graph, age, received_age, visible
):
    add_point(db_sessionmaker, driving_graph, age=age, received_age=received_age)
    response = read(db_client, driving_graph)
    assert response.status_code == 200
    assert bool(response.json()["positions"]) is visible


@pytest.mark.parametrize(
    "latest", [{"age": 19, "speed": 0}, {"age": 19, "lon": 3.7}, {"age": 19, "speed": None}]
)
def test_latest_delayed_point_is_selected_before_movement_and_area(
    db_client, db_sessionmaker, driving_graph, latest
):
    add_point(db_sessionmaker, driving_graph, age=22, received_age=22)
    add_point(db_sessionmaker, driving_graph, received_age=19, **latest)
    assert read(db_client, driving_graph).json()["positions"] == []


def test_current_reports_and_recent_backfill_do_not_hide_eligible_delayed_point(
    db_client, db_sessionmaker, driving_graph
):
    add_point(db_sessionmaker, driving_graph, age=22, received_age=22)
    add_point(db_sessionmaker, driving_graph, age=1, received_age=1, lon=3.7)
    add_point(db_sessionmaker, driving_graph, age=20, received_age=1, lon=3.7)
    assert read(db_client, driving_graph, "?at=2000-01-01&vehicle_id=ignored").json()[
        "positions"
    ] == [{"longitude": 3.4, "latitude": 6.5}]


def test_equal_recorded_timestamp_uses_received_then_internal_id(
    db_client, db_sessionmaker, driving_graph
):
    add_point(db_sessionmaker, driving_graph, age=20, received_age=19, ping_id=UUID(int=1))
    add_point(db_sessionmaker, driving_graph, age=20, received_age=18, ping_id=UUID(int=2), speed=0)
    assert read(db_client, driving_graph).json()["positions"] == []
    add_point(db_sessionmaker, driving_graph, age=20, received_age=18, ping_id=UUID(int=3), speed=5)
    assert len(read(db_client, driving_graph).json()["positions"]) == 1


def test_newer_excluded_point_does_not_resurrect_an_older_position(
    db_client, db_sessionmaker, driving_graph
):
    async def exclusion():
        async with db_sessionmaker() as session:
            geometry = {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[3.45, 6.55], [3.5, 6.55], [3.5, 6.6], [3.45, 6.6], [3.45, 6.55]]]
                ],
            }
            session.add(
                CampaignZone(
                    campaign_id=driving_graph["campaign"].id,
                    created_by_user_id=driving_graph["owner"].id,
                    name="Avoid",
                    zone_type=CampaignZoneType.EXCLUSION.value,
                    geom=geometry_expression(json.dumps(geometry)),
                    zone_metadata={},
                )
            )
            await session.commit()

    asyncio.run(exclusion())
    add_point(db_sessionmaker, driving_graph, age=22, received_age=22)
    add_point(db_sessionmaker, driving_graph, age=20, received_age=20, lon=3.48, lat=6.58)
    assert read(db_client, driving_graph).json()["positions"] == []


@pytest.mark.parametrize(
    "model,key,values",
    [
        (TripSession, "trip", {"status": "ended", "ended_at": NOW}),
        (CampaignAssignment, "assignment", {"status": "cancelled"}),
        (Campaign, "campaign", {"status": "paused"}),
        (Campaign, "campaign", {"end_at": NOW}),
    ],
)
def test_only_current_active_work_is_visible(
    db_client, db_sessionmaker, driving_graph, model, key, values
):
    add_point(db_sessionmaker, driving_graph)

    async def change():
        async with db_sessionmaker() as session:
            await session.execute(
                update(model).where(model.id == driving_graph[key].id).values(**values)
            )
            await session.commit()

    asyncio.run(change())
    assert read(db_client, driving_graph).json()["positions"] == []


@pytest.mark.parametrize(
    "model,key", [(AdvertiserOrganization, "org"), (OrganizationMembership, "membership")]
)
def test_inactive_membership_or_company_cannot_read(
    db_client, db_sessionmaker, driving_graph, model, key
):
    add_point(db_sessionmaker, driving_graph)
    headers = auth_headers(db_client, "map-owner@example.com", PASSWORD)

    async def disable():
        async with db_sessionmaker() as session:
            await session.execute(
                update(model).where(model.id == driving_graph[key].id).values(status="disabled")
            )
            await session.commit()

    asyncio.run(disable())
    assert db_client.get(
        f"/api/v1/advertiser/campaigns/{driving_graph['campaign'].id}/live-positions",
        headers=headers,
    ).status_code in {403, 404}


def test_other_tenant_and_other_roles_never_receive_positions(
    db_client, db_sessionmaker, driving_graph
):
    stranger = create_test_user(
        db_sessionmaker, email="other-map@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    create_test_organization(db_sessionmaker, owner_user_id=stranger.id, name="Other company")
    path = f"/api/v1/advertiser/campaigns/{driving_graph['campaign'].id}/live-positions"
    assert (
        db_client.get(path, headers=auth_headers(db_client, stranger.email, PASSWORD)).status_code
        == 404
    )
    assert (
        db_client.get(
            path, headers=auth_headers(db_client, driving_graph["driver"].email, PASSWORD)
        ).status_code
        == 403
    )
    assert db_client.get(path).status_code == 401


def test_campaign_pause_before_position_query_is_respected(
    db_client, db_sessionmaker, driving_graph, monkeypatch
):
    add_point(db_sessionmaker, driving_graph)
    owned_campaign = campaign_live_positions.get_advertiser_campaign

    async def pause_after_ownership(session, **kwargs):
        campaign = await owned_campaign(session, **kwargs)
        async with db_sessionmaker() as other:
            await other.execute(
                update(Campaign).where(Campaign.id == campaign.id).values(status="paused")
            )
            await other.commit()
        return campaign

    monkeypatch.setattr(campaign_live_positions, "get_advertiser_campaign", pause_after_ownership)
    assert read(db_client, driving_graph).json()["positions"] == []
