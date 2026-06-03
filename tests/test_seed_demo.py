import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverProfile
from app.models.impression import ImpressionEstimate
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.models.trip_analytics import TripAnalytics
from app.models.user import User
from app.models.vehicle import Vehicle
from app.seeds.demo import (
    DEMO_BBOX,
    DEMO_PASSWORDS,
    SEED_VERSION,
    build_demo_graph,
    ensure_seed_allowed,
)


def test_demo_seed_refuses_production_even_with_override() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://mobility:mobility@localhost:5433/mobility",
        jwt_secret_key="production-demo-seed-test-secret-32-chars",
        allow_demo_seed=True,
    )

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)

    assert exc.value.code == "DEMO_SEED_DISALLOWED"


def test_demo_seed_requires_explicit_local_confirmation() -> None:
    settings = Settings(
        environment="local",
        database_url="postgresql+asyncpg://mobility:mobility@localhost:5433/mobility",
        allow_demo_seed=False,
    )

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)

    assert exc.value.code == "DEMO_SEED_NOT_CONFIRMED"


def test_demo_seed_allows_test_environment_without_override() -> None:
    settings = Settings(
        environment="test",
        database_url="postgresql+asyncpg://mobility:mobility@localhost:5433/mobility",
        allow_demo_seed=False,
    )

    ensure_seed_allowed(settings)


def test_demo_passwords_satisfy_policy(settings: Settings) -> None:
    assert all(
        len(password) >= settings.password_min_length for password in DEMO_PASSWORDS.values()
    )


def test_demo_seed_is_not_registered_on_app_startup(settings: Settings) -> None:
    app = create_app(settings)

    assert not any(route.path.endswith("/seed") for route in app.routes)


def test_slice_12_does_not_add_migration_or_seed_table() -> None:
    versions = {path.name for path in Path("alembic/versions").glob("*.py")}

    assert "0010_payouts_and_earnings.py" in versions
    assert not any("0011" in name or "seed" in name or "demo" in name for name in versions)


def test_readme_documents_demo_seed_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "python -m app.seeds.demo" in readme
    assert "advertiser@demo.mobility.local" in readme
    assert DEMO_BBOX in readme
    assert "GET /api/v1/driver/earnings/summary" in readme


def test_openapi_has_frontend_contract_tags_and_examples(client) -> None:
    schema = client.get("/openapi.json").json()
    operation_tags = {
        tag
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict)
        for tag in operation.get("tags", [])
    }

    assert {
        "Health",
        "Auth",
        "Admin Users",
        "Advertiser Organizations",
        "Drivers",
        "Vehicles",
        "Campaigns",
        "Campaign Zones",
        "Campaign Assignments",
        "Trips",
        "Analytics",
        "Impressions",
        "Payouts",
        "Advertiser Reports",
        "Heatmaps",
    }.issubset(operation_tags)
    login_request_schema = schema["paths"]["/api/v1/auth/login"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    component_name = login_request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    assert (
        schema["components"]["schemas"][component_name]["examples"][0]["email"]
        == "advertiser@demo.mobility.local"
    )
    assert "3.35,6.43,3.47,6.56" in schema["paths"][
        "/api/v1/advertiser/campaigns/{campaign_id}/heatmap"
    ]["get"]["description"]


def seed_demo_graph(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
):
    async def seed():
        async with sessionmaker() as session:
            graph = await build_demo_graph(session, settings)
            await session.commit()
            return graph

    return asyncio.run(seed())


def fetch_seed_counts(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async def fetch() -> dict[str, int]:
        async with sessionmaker() as session:
            campaign = await session.scalar(
                select(Campaign).where(Campaign.name == "Demo Lagos Mobility Campaign")
            )
            assert campaign is not None
            trip_result = await session.execute(
                select(TripSession).where(TripSession.campaign_id == campaign.id)
            )
            demo_trips = [
                trip
                for trip in trip_result.scalars().all()
                if trip.trip_metadata.get("seed_version") == SEED_VERSION
            ]
            trip_ids = [trip.id for trip in demo_trips]
            return {
                "users": int(
                    await session.scalar(
                        select(func.count(User.id)).where(
                            User.email.in_(list(DEMO_PASSWORDS.keys()))
                        )
                    )
                    or 0
                ),
                "organizations": int(
                    await session.scalar(
                        select(func.count(AdvertiserOrganization.id)).where(
                            AdvertiserOrganization.name == "Demo Mobility Advertiser"
                        )
                    )
                    or 0
                ),
                "memberships": int(
                    await session.scalar(select(func.count(OrganizationMembership.id)))
                    or 0
                ),
                "driver_profiles": int(
                    await session.scalar(select(func.count(DriverProfile.id))) or 0
                ),
                "vehicles": int(
                    await session.scalar(
                        select(func.count(Vehicle.id)).where(Vehicle.plate_number == "DEMO-001")
                    )
                    or 0
                ),
                "campaigns": int(
                    await session.scalar(
                        select(func.count(Campaign.id)).where(
                            Campaign.name == "Demo Lagos Mobility Campaign"
                        )
                    )
                    or 0
                ),
                "creatives": int(
                    await session.scalar(
                        select(func.count(CampaignCreative.id)).where(
                            CampaignCreative.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "zones": int(
                    await session.scalar(
                        select(func.count(CampaignZone.id)).where(
                            CampaignZone.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id)).where(
                            CampaignAssignment.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "trips": len(demo_trips),
                "batches": int(
                    await session.scalar(
                        select(func.count(LocationPingBatch.id)).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "pings": int(
                    await session.scalar(
                        select(func.count(LocationPing.id)).where(
                            LocationPing.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "analytics": int(
                    await session.scalar(
                        select(func.count(TripAnalytics.id)).where(
                            TripAnalytics.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "estimates": int(
                    await session.scalar(
                        select(func.count(ImpressionEstimate.id)).where(
                            ImpressionEstimate.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "payouts": int(
                    await session.scalar(
                        select(func.count(PayoutCalculation.id)).where(
                            PayoutCalculation.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "ledger": int(
                    await session.scalar(
                        select(func.count(EarningsLedgerEntry.id)).where(
                            EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
            }

    return asyncio.run(fetch())


def test_demo_seed_is_idempotent_with_postgis(postgis_db_sessionmaker, settings: Settings) -> None:
    seed_demo_graph(postgis_db_sessionmaker, settings)
    first_counts = fetch_seed_counts(postgis_db_sessionmaker)
    seed_demo_graph(postgis_db_sessionmaker, settings)
    second_counts = fetch_seed_counts(postgis_db_sessionmaker)

    assert first_counts == second_counts
    assert second_counts == {
        "users": 4,
        "organizations": 1,
        "memberships": 2,
        "driver_profiles": 1,
        "vehicles": 1,
        "campaigns": 1,
        "creatives": 1,
        "zones": 3,
        "assignments": 1,
        "trips": 2,
        "batches": 2,
        "pings": 12,
        "analytics": 2,
        "estimates": 2,
        "payouts": 2,
        "ledger": 2,
    }
