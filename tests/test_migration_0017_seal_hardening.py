"""Migration 0017: backfilled-seal audit events + quarantine resolution CHECKs.

Style-B: throwaway Postgres database, real Alembic chain. Verifies the 0016
backfill's audit gap is healed (one system-actor `trip.sealed` event per
backfilled trip, idempotently) and the new resolution constraints hold.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    upgrade_to,
)

from app.models.user import UserRole

REVISION_PRE_SEAL = "0015_payout_day_allocation"


def seed_pre_seal_ended_trip(migration_url: str) -> SimpleNamespace:
    """Minimal FK graph at 0015 with one `ended` trip (raw SQL — the current
    ORM would write seal columns that do not exist before 0016)."""
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    admin = create_test_user(sessionmaker, email="m17-admin@example.com")
    advertiser = create_test_user(
        sessionmaker, email="m17-advertiser@example.com", role=UserRole.ADVERTISER
    )
    driver = create_test_user(sessionmaker, email="m17-driver@example.com", role=UserRole.DRIVER)
    organization, _ = create_test_organization(
        sessionmaker, owner_user_id=advertiser.id, legacy_schema=True
    )
    campaign = create_test_campaign(
        sessionmaker, organization_id=organization.id, created_by_user_id=advertiser.id
    )
    profile = create_test_driver_profile(sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(sessionmaker, driver_profile_id=profile.id)
    assignment = create_test_campaign_assignment(
        sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    trip_id = uuid4()
    started_at = datetime.now(UTC) - timedelta(hours=3)

    async def add_trip() -> None:
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO trip_sessions (id, assignment_id, campaign_id,"
                    " driver_profile_id, vehicle_id, started_by_user_id, status,"
                    " started_at, ended_at, metadata)"
                    " VALUES (:id, :assignment_id, :campaign_id, :driver_profile_id,"
                    " :vehicle_id, :started_by_user_id, 'ended', :started_at,"
                    " :ended_at, '{}')"
                ),
                {
                    "id": trip_id,
                    "assignment_id": assignment.id,
                    "campaign_id": campaign.id,
                    "driver_profile_id": profile.id,
                    "vehicle_id": vehicle.id,
                    "started_by_user_id": driver.id,
                    "started_at": started_at,
                    "ended_at": started_at + timedelta(minutes=45),
                },
            )
            await session.commit()

    asyncio.run(add_trip())
    return SimpleNamespace(trip_id=trip_id)


def test_backfilled_seal_gains_exactly_one_audit_event(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, REVISION_PRE_SEAL, monkeypatch)
        seeded = seed_pre_seal_ended_trip(migration_url)
        upgrade_to(migration_url, "head", monkeypatch)

        rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT status, seal_reason FROM trip_sessions WHERE id = :id",
                {"id": seeded.trip_id},
            )
        )
        assert rows == [("sealed", "migration_backfill")]

        events = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT actor_user_id, metadata->>'seal_reason' FROM audit_events"
                " WHERE action = 'trip.sealed' AND entity_type = 'trip_session'"
                " AND entity_id = :entity_id",
                {"entity_id": str(seeded.trip_id)},
            )
        )
        assert events == [(None, "migration_backfill")], (
            "every backfilled seal carries exactly one system-actor audit event (D15)"
        )
    finally:
        asyncio.run(drop_database(migration_url))


def test_quarantine_resolution_constraints_hold(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        constraints = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    migration_url,
                    "SELECT conname FROM pg_constraint"
                    " WHERE conrelid = 'quarantined_ping_batches'::regclass",
                )
            )
        }
        assert "ck_quarantined_ping_batches_resolution_actor" in constraints
        assert "ck_quarantined_ping_batches_applied_batch" in constraints
    finally:
        asyncio.run(drop_database(migration_url))
