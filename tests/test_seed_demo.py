import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverProfile
from app.models.impression import ImpressionEstimate
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import LocationPing, LocationPingBatch, TripSession
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.models.user import User
from app.models.vehicle import Vehicle
from app.seeds.demo import (
    DEMO_BBOX,
    DEMO_PASSWORDS,
    SEED_VERSION,
    build_demo_graph,
    ensure_seed_allowed,
    required_migration_head,
)
from app.seeds.rich import F7_DRIVER_PASSWORDS, F7_SEED_VERSION


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

    assert not any(getattr(route, "path", "").endswith("/seed") for route in app.routes)


def test_no_seed_or_demo_migrations() -> None:
    versions = {path.name for path in Path("alembic/versions").glob("*.py")}

    assert "0010_payouts_and_earnings.py" in versions
    assert not any("seed" in name or "demo" in name for name in versions)


def test_demo_seed_requires_the_code_migration_head() -> None:
    assert required_migration_head() == "0013_payout_v2_hourly_caps"


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
    login_request_schema = schema["paths"]["/api/v1/auth/login"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    component_name = login_request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    assert (
        schema["components"]["schemas"][component_name]["examples"][0]["email"]
        == "advertiser@demo.mobility.local"
    )
    assert (
        "3.35,6.43,3.47,6.56"
        in schema["paths"]["/api/v1/advertiser/campaigns/{campaign_id}/heatmap"]["get"][
            "description"
        ]
    )


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
                    await session.scalar(select(func.count(OrganizationMembership.id))) or 0
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
                "legacy_driver_f7_assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id))
                        .join(
                            DriverProfile,
                            DriverProfile.id == CampaignAssignment.driver_profile_id,
                        )
                        .join(User, User.id == DriverProfile.user_id)
                        .where(
                            User.email == "driver@demo.mobility.local",
                            CampaignAssignment.assignment_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION,
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


def fetch_rich_snapshot(sessionmaker: async_sessionmaker[AsyncSession]) -> dict:
    async def fetch() -> dict:
        async with sessionmaker() as session:
            trips_result = await session.execute(
                select(TripSession).where(
                    TripSession.trip_metadata["seed_version"].as_string() == F7_SEED_VERSION
                )
            )
            trips = list(trips_result.scalars().all())
            trip_ids = [trip.id for trip in trips]
            flag_types = set(
                (
                    await session.execute(
                        select(FraudFlag.flag_type).where(FraudFlag.trip_session_id.in_(trip_ids))
                    )
                ).scalars()
            )
            severities = set(
                (
                    await session.execute(
                        select(FraudFlag.severity).where(FraudFlag.trip_session_id.in_(trip_ids))
                    )
                ).scalars()
            )
            fraud_flag_count = int(
                await session.scalar(
                    select(func.count(FraudFlag.id)).where(FraudFlag.trip_session_id.in_(trip_ids))
                )
                or 0
            )
            metadata_groups = [
                [trip.trip_metadata for trip in trips],
                list(
                    (
                        await session.execute(
                            select(LocationPingBatch.batch_metadata).where(
                                LocationPingBatch.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(TripAnalytics.analytics_metadata).where(
                                TripAnalytics.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(ImpressionEstimate.estimate_metadata).where(
                                ImpressionEstimate.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(PayoutCalculation.payout_metadata).where(
                                PayoutCalculation.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(EarningsLedgerEntry.ledger_metadata).where(
                                EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(FraudFlag.evidence).where(
                                FraudFlag.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
            ]
            f7_batch_keys = set(
                (
                    await session.execute(
                        select(LocationPingBatch.idempotency_key).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                ).scalars()
            )
            return {
                "users": int(
                    await session.scalar(
                        select(func.count(User.id)).where(User.email.in_(list(F7_DRIVER_PASSWORDS)))
                    )
                    or 0
                ),
                "password_flags": set(
                    (
                        await session.execute(
                            select(User.must_change_password).where(
                                User.email.in_(
                                    [*DEMO_PASSWORDS.keys(), *F7_DRIVER_PASSWORDS.keys()]
                                )
                            )
                        )
                    ).scalars()
                ),
                "profiles": int(
                    await session.scalar(
                        select(func.count(DriverProfile.id))
                        .join(User, User.id == DriverProfile.user_id)
                        .where(User.email.in_(list(F7_DRIVER_PASSWORDS)))
                    )
                    or 0
                ),
                "vehicles": int(
                    await session.scalar(
                        select(func.count(Vehicle.id)).where(
                            Vehicle.plate_number.in_([f"DEMO-{index}" for index in range(101, 110)])
                        )
                    )
                    or 0
                ),
                "campaign_statuses": set(
                    (
                        await session.execute(
                            select(Campaign.status).where(
                                Campaign.campaign_metadata["seed_version"].as_string()
                                == F7_SEED_VERSION
                            )
                        )
                    ).scalars()
                ),
                "campaigns": int(
                    await session.scalar(
                        select(func.count(Campaign.id)).where(
                            Campaign.campaign_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id)).where(
                            CampaignAssignment.assignment_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "trips": len(trips),
                "trip_ids": {trip.id for trip in trips},
                "trip_keys": {trip.trip_metadata["seed_trip_key"] for trip in trips},
                "batch_keys": f7_batch_keys,
                "trip_days": {trip.started_at.date() for trip in trips},
                "metadata_namespaced": all(
                    metadata.get("seed_version") == F7_SEED_VERSION
                    for group in metadata_groups
                    for metadata in group
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
                "audit_events": int(
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.event_metadata["seed_version"].as_string() == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "flag_types": flag_types,
                "severities": severities,
                "fraud_flags": fraud_flag_count,
            }

    return asyncio.run(fetch())


def fetch_legacy_derived_snapshot(sessionmaker: async_sessionmaker[AsyncSession]) -> dict:
    async def fetch() -> dict:
        async with sessionmaker() as session:
            trips_result = await session.execute(
                select(TripSession).where(
                    TripSession.trip_metadata["seed_version"].as_string() == SEED_VERSION
                )
            )
            trips = list(trips_result.scalars().all())
            trip_ids = [trip.id for trip in trips]
            batches = (
                (
                    await session.execute(
                        select(LocationPingBatch).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            return {
                "batch_ids": {batch.id for batch in batches},
                "batch_keys": {batch.idempotency_key for batch in batches},
                "analytics": list(
                    (
                        await session.execute(
                            select(TripAnalytics.trip_session_id, TripAnalytics.distance_m)
                            .where(TripAnalytics.trip_session_id.in_(trip_ids))
                            .order_by(TripAnalytics.trip_session_id)
                        )
                    ).all()
                ),
                "impressions": list(
                    (
                        await session.execute(
                            select(
                                ImpressionEstimate.trip_session_id,
                                ImpressionEstimate.estimated_impressions,
                            )
                            .where(ImpressionEstimate.trip_session_id.in_(trip_ids))
                            .order_by(ImpressionEstimate.trip_session_id)
                        )
                    ).all()
                ),
                "payouts": list(
                    (
                        await session.execute(
                            select(
                                PayoutCalculation.trip_session_id,
                                PayoutCalculation.final_payout,
                            )
                            .where(PayoutCalculation.trip_session_id.in_(trip_ids))
                            .order_by(PayoutCalculation.trip_session_id)
                        )
                    ).all()
                ),
                "ledger": list(
                    (
                        await session.execute(
                            select(
                                EarningsLedgerEntry.trip_session_id,
                                EarningsLedgerEntry.amount,
                            )
                            .where(EarningsLedgerEntry.trip_session_id.in_(trip_ids))
                            .order_by(EarningsLedgerEntry.trip_session_id)
                        )
                    ).all()
                ),
            }

    return asyncio.run(fetch())


def fetch_lifecycle_violation_count(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> int:
    async def fetch() -> int:
        async with sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(TripSession.id))
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .join(
                        CampaignAssignment,
                        CampaignAssignment.id == TripSession.assignment_id,
                    )
                    .where(
                        or_(
                            TripSession.started_at < Campaign.start_at,
                            TripSession.ended_at > Campaign.end_at,
                            CampaignAssignment.status.not_in(["active", "completed"]),
                        )
                    )
                )
                or 0
            )

    return asyncio.run(fetch())


def test_demo_seed_is_idempotent_with_postgis(
    postgis_db_sessionmaker,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "2")
    seed_demo_graph(postgis_db_sessionmaker, settings)
    first_counts = fetch_seed_counts(postgis_db_sessionmaker)
    first_rich = fetch_rich_snapshot(postgis_db_sessionmaker)
    first_legacy = fetch_legacy_derived_snapshot(postgis_db_sessionmaker)
    seed_demo_graph(postgis_db_sessionmaker, settings)
    second_counts = fetch_seed_counts(postgis_db_sessionmaker)
    second_rich = fetch_rich_snapshot(postgis_db_sessionmaker)
    second_legacy = fetch_legacy_derived_snapshot(postgis_db_sessionmaker)

    assert first_counts == second_counts
    assert second_counts == {
        "users": 4,
        "organizations": 1,
        "memberships": 2,
        "driver_profiles": 10,
        "vehicles": 1,
        "campaigns": 1,
        "creatives": 1,
        "zones": 3,
        "assignments": 1,
        "legacy_driver_f7_assignments": 0,
        "trips": 2,
        "batches": 2,
        "pings": 12,
        "analytics": 2,
        "estimates": 2,
        "payouts": 2,
        "ledger": 2,
    }
    assert first_rich == second_rich
    assert first_legacy == second_legacy
    assert all(key.startswith(f"{SEED_VERSION}:") for key in second_legacy["batch_keys"])
    assert second_rich["users"] == 9
    assert second_rich["password_flags"] == {False}
    assert second_rich["profiles"] == 9
    assert second_rich["vehicles"] == 9
    assert second_rich["campaigns"] == 4
    assert second_rich["assignments"] == 11
    assert second_rich["campaign_statuses"] == {"active", "paused", "completed", "draft"}
    assert len(second_rich["trip_days"]) >= 25
    assert second_rich["trips"] == 318
    assert all(key.startswith(f"{F7_SEED_VERSION}:f7:") for key in second_rich["batch_keys"])
    assert second_rich["metadata_namespaced"] is True
    assert second_rich["analytics"] == second_rich["trips"]
    assert second_rich["estimates"] == second_rich["trips"]
    assert second_rich["payouts"] == second_rich["trips"]
    assert second_rich["ledger"] == second_rich["trips"]
    assert second_rich["audit_events"] == 30
    assert len(second_rich["flag_types"]) >= 5
    assert second_rich["severities"] == {"low", "medium", "high"}
    assert 10 <= second_rich["fraud_flags"] <= 15
    assert fetch_lifecycle_violation_count(postgis_db_sessionmaker) == 0


def test_rich_seed_later_rerun_only_appends_valid_rolling_trips(
    postgis_db_sessionmaker,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.seeds import rich

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    first_now = datetime(2026, 7, 12, 12, tzinfo=UTC)
    monkeypatch.setattr(rich, "utc_now", lambda: first_now)
    seed_demo_graph(postgis_db_sessionmaker, settings)
    first = fetch_rich_snapshot(postgis_db_sessionmaker)

    async def completed_trip_count() -> int:
        async with postgis_db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(TripSession.id))
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .where(Campaign.name == "F7 Festive Island Wrap")
                )
                or 0
            )

    completed_before = asyncio.run(completed_trip_count())
    monkeypatch.setattr(rich, "utc_now", lambda: first_now + timedelta(days=40))
    seed_demo_graph(postgis_db_sessionmaker, settings)
    second = fetch_rich_snapshot(postgis_db_sessionmaker)

    assert first["trip_ids"] < second["trip_ids"]
    assert first["trip_keys"] < second["trip_keys"]
    assert asyncio.run(completed_trip_count()) == completed_before
    assert fetch_lifecycle_violation_count(postgis_db_sessionmaker) == 0
