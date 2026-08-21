"""Migration 0014: location_pings monthly partitioning (S4).

Style-B tests: each creates a throwaway Postgres database and runs the real
Alembic chain from empty. Skipped when no Postgres test database is
configured (same convention as the 0013 tests).
"""

import asyncio
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from app.models.trip import LocationPing, LocationPingBatch
from app.models.user import UserRole
from app.services.data_lifecycle import add_months, month_start
from app.services.trips import point_value

REVISION_0014 = "0014_location_pings_partitioning"
REVISION_0013 = "0013_payout_v2_hourly_caps"

EXPECTED_CHECKS = {
    "ck_location_pings_sequence_number_non_negative",
    "ck_location_pings_latitude",
    "ck_location_pings_longitude",
    "ck_location_pings_accuracy_non_negative",
    "ck_location_pings_speed_non_negative",
    "ck_location_pings_heading_degrees",
    "ck_location_pings_altitude_m",
}
EXPECTED_INDEXES = {
    "ix_location_pings_trip_session_id",
    "ix_location_pings_trip_recorded_at",
    "ix_location_pings_batch_id",
    "ix_location_pings_geom",
}


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_0014_migration_{uuid4().hex}"
    maintenance_url = source_url.set(database="postgres")
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()
    return source_url.set(database=database_name).render_as_string(hide_password=False)


async def drop_database(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database
    if database_name is None:
        return
    maintenance_url = url.set(database="postgres")
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


def upgrade_to(migration_url: str, revision: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migration_url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)
    get_settings.cache_clear()


def downgrade_to(migration_url: str, revision: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migration_url)
    get_settings.cache_clear()
    command.downgrade(Config("alembic.ini"), revision)
    get_settings.cache_clear()


async def fetch_all(migration_url: str, query: str, params: dict | None = None) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(query), params or {})
            return list(result.all())
    finally:
        await engine.dispose()


def partition_rows(migration_url: str) -> list[tuple[str, str]]:
    return asyncio.run(
        fetch_all(
            migration_url,
            """
            SELECT child.relname, pg_get_expr(child.relpartbound, child.oid)
            FROM pg_inherits inh
            JOIN pg_class child ON child.oid = inh.inhrelid
            JOIN pg_class parent ON parent.oid = inh.inhparent
            WHERE parent.relname = 'location_pings'
            ORDER BY child.relname
            """,
        )
    )


def test_0014_migration_static_shape() -> None:
    migration = Path("alembic/versions/0014_location_pings_partitioning.py").read_text()
    assert f'revision: str = "{REVISION_0014}"' in migration
    assert f'down_revision: str | Sequence[str] | None = "{REVISION_0013}"' in migration
    assert "PARTITION BY RANGE (recorded_at)" in migration
    assert "MIGRATION_PREMAKE_MONTHS = 4" in migration
    # The initial premake horizon is frozen — never deployment config.
    assert "get_settings" not in migration
    assert "partition_premake_months" not in migration
    assert "os.environ" not in migration
    assert "DEFAULT PARTITION" not in migration.upper().replace(
        "NO DEFAULT PARTITION", ""
    )
    assert '"data_purge_audit"' in migration
    for name in EXPECTED_CHECKS | EXPECTED_INDEXES:
        assert name in migration
    for forbidden_table in ["notifications", "fraud_disputes", "payout_batches", "heatmaps"]:
        assert f'"{forbidden_table}"' not in migration


def test_empty_database_upgrade_downgrade_cycle(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)

        relkind = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT relkind::text FROM pg_class WHERE relname = 'location_pings'",
            )
        )
        assert relkind == [("p",)]

        rows = partition_rows(migration_url)
        names = [name for name, _ in rows]
        assert "location_pings_legacy" not in names
        assert all(re.fullmatch(r"location_pings_p\d{4}_\d{2}", name) for name in names)
        assert not any("DEFAULT" in bound for _, bound in rows)
        # Empty branch covers three prior months (rich-seed history depth is
        # 56 days) through the frozen 4-month horizon.
        now_month = month_start(datetime.now(UTC))
        expected = {
            f"location_pings_p{add_months(now_month, offset).strftime('%Y_%m')}"
            for offset in range(-3, 5)
        }
        assert set(names) == expected

        constraints = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    migration_url,
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'location_pings'::regclass
                    """,
                )
            )
        }
        assert EXPECTED_CHECKS <= constraints
        assert "location_pings_pkey" in constraints
        assert {"location_pings_trip_session_id_fkey", "location_pings_batch_id_fkey"} <= (
            constraints
        )
        pk_cols = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid
                    AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'location_pings'::regclass AND i.indisprimary
                ORDER BY a.attname
                """,
            )
        )
        assert {row[0] for row in pk_cols} == {"id", "recorded_at"}

        indexes = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    migration_url,
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'location_pings'",
                )
            )
        }
        assert EXPECTED_INDEXES <= indexes

        purge_indexes = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    migration_url,
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'data_purge_audit'",
                )
            )
        }
        assert {"uq_data_purge_audit_dropped", "ix_data_purge_audit_partition_created_at"} <= (
            purge_indexes
        )

        downgrade_to(migration_url, REVISION_0013, monkeypatch)
        relkind = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT relkind::text FROM pg_class WHERE relname = 'location_pings'",
            )
        )
        assert relkind == [("r",)]
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'data_purge_audit'",
            )
        )
        assert tables == []

        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def seed_ping_graph(migration_url: str) -> dict:
    """Build the minimal FK graph at revision 0013 and insert pings across
    three UTC months, including a batch straddling two months."""
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    months = [add_months(month_start(now), -2), add_months(month_start(now), -1), month_start(now)]

    admin = create_test_user(sessionmaker, email="mig-admin@example.com")
    advertiser = create_test_user(
        sessionmaker, email="mig-advertiser@example.com", role=UserRole.ADVERTISER
    )
    driver = create_test_user(sessionmaker, email="mig-driver@example.com", role=UserRole.DRIVER)
    organization, _ = create_test_organization(sessionmaker, owner_user_id=advertiser.id)
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
    # Raw SQL: this seed runs at revision 0013, before the 0016 seal columns
    # exist — the current ORM model would INSERT columns the old schema lacks.
    trip_id = uuid4()

    async def add_trip() -> None:
        async with sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO trip_sessions (id, assignment_id, campaign_id,"
                    " driver_profile_id, vehicle_id, started_by_user_id, status,"
                    " started_at, metadata)"
                    " VALUES (:id, :assignment_id, :campaign_id, :driver_profile_id,"
                    " :vehicle_id, :started_by_user_id, 'active', :started_at, '{}')"
                ),
                {
                    "id": trip_id,
                    "assignment_id": assignment.id,
                    "campaign_id": campaign.id,
                    "driver_profile_id": profile.id,
                    "vehicle_id": vehicle.id,
                    "started_by_user_id": driver.id,
                    "started_at": months[0] + timedelta(hours=8),
                },
            )
            await session.commit()

    asyncio.run(add_trip())
    trip = SimpleNamespace(id=trip_id)

    async def add_batch(key: str, recorded_ats: list[datetime]) -> tuple[str, list[str]]:
        async with sessionmaker() as session:
            batch = LocationPingBatch(
                trip_session_id=trip.id,
                idempotency_key=key,
                payload_hash=f"hash-{key}",
                pings_accepted=len(recorded_ats),
                received_at=recorded_ats[0],
                batch_metadata={},
            )
            session.add(batch)
            await session.flush()
            ping_ids = []
            for sequence, recorded_at in enumerate(recorded_ats):
                ping = LocationPing(
                    trip_session_id=trip.id,
                    batch_id=batch.id,
                    recorded_at=recorded_at,
                    received_at=recorded_at,
                    sequence_number=sequence,
                    latitude=6.45,
                    longitude=3.39,
                    accuracy_m=10,
                    geom=point_value(session, lon=3.39, lat=6.45),
                    ping_metadata={},
                )
                session.add(ping)
                await session.flush()
                ping_ids.append(str(ping.id))
            await session.commit()
            return str(batch.id), ping_ids

    batches = {}
    batches["oldest"] = asyncio.run(
        add_batch("batch-oldest", [months[0] + timedelta(hours=9, minutes=m) for m in range(3)])
    )
    batches["middle"] = asyncio.run(
        add_batch("batch-middle", [months[1] + timedelta(hours=9, minutes=m) for m in range(3)])
    )
    # Straddles the previous and current month.
    batches["straddling"] = asyncio.run(
        add_batch(
            "batch-straddling",
            [months[2] - timedelta(minutes=1), months[2] + timedelta(minutes=1)],
        )
    )
    asyncio.run(engine.dispose())
    return {"trip_id": str(trip.id), "batches": batches, "months": months}


def test_seeded_conversion_preserves_rows_and_routes_inserts(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, REVISION_0013, monkeypatch)
        seeded = seed_ping_graph(migration_url)
        all_ping_ids = sorted(
            ping_id for _, ping_ids in seeded["batches"].values() for ping_id in ping_ids
        )

        upgrade_to(migration_url, "head", monkeypatch)

        rows = partition_rows(migration_url)
        names = [name for name, _ in rows]
        assert "location_pings_legacy" in names
        assert not any("DEFAULT" in bound for _, bound in rows)

        surviving = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT id::text, tableoid::regclass::text FROM location_pings ORDER BY id::text",
            )
        )
        assert sorted(row[0] for row in surviving) == all_ping_ids
        # Every pre-existing row lives in the legacy partition (it owns the
        # whole historical range including the current month).
        assert {row[1] for row in surviving} == {"location_pings_legacy"}

        # FK integrity survived: every ping still joins its batch and trip.
        orphans = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT count(*) FROM location_pings p
                WHERE NOT EXISTS (SELECT 1 FROM location_ping_batches b WHERE b.id = p.batch_id)
                   OR NOT EXISTS (SELECT 1 FROM trip_sessions t WHERE t.id = p.trip_session_id)
                """,
            )
        )
        assert orphans == [(0,)]

        # UTC month-boundary routing of new inserts: current-month rows land
        # in legacy; rows at and after the next boundary land in the premade
        # monthly partition.
        next_month = add_months(month_start(datetime.now(UTC)), 1)
        batch_id = seeded["batches"]["straddling"][0]
        checks = [
            (datetime.now(UTC), "location_pings_legacy"),
            (next_month - timedelta(microseconds=1), "location_pings_legacy"),
            (next_month, f"location_pings_p{next_month.strftime('%Y_%m')}"),
        ]

        async def insert_and_locate(recorded_at: datetime) -> str:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    result = await connection.execute(
                        text(
                            """
                            INSERT INTO location_pings
                                (trip_session_id, batch_id, recorded_at, received_at,
                                 latitude, longitude, geom, metadata)
                            VALUES
                                (:trip_id, :batch_id, :recorded_at, :recorded_at,
                                 6.45, 3.39,
                                 ST_SetSRID(ST_MakePoint(3.39, 6.45), 4326), '{}'::jsonb)
                            RETURNING tableoid::regclass::text
                            """
                        ),
                        {
                            "trip_id": seeded["trip_id"],
                            "batch_id": batch_id,
                            "recorded_at": recorded_at,
                        },
                    )
                    return result.scalar_one()
            finally:
                await engine.dispose()

        for recorded_at, expected_partition in checks:
            assert asyncio.run(insert_and_locate(recorded_at)) == expected_partition

        expected_total = len(all_ping_ids) + len(checks)
        count = asyncio.run(fetch_all(migration_url, "SELECT count(*) FROM location_pings"))
        assert count == [(expected_total,)]

        # Downgrade restores the unpartitioned shape losslessly.
        downgrade_to(migration_url, REVISION_0013, monkeypatch)
        count = asyncio.run(fetch_all(migration_url, "SELECT count(*) FROM location_pings"))
        assert count == [(expected_total,)]
        pk_cols = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'location_pings'::regclass AND i.indisprimary
                """,
            )
        )
        assert {row[0] for row in pk_cols} == {"id"}

        upgrade_to(migration_url, "head", monkeypatch)
        count = asyncio.run(fetch_all(migration_url, "SELECT count(*) FROM location_pings"))
        assert count == [(expected_total,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_autogenerate_diff_is_empty_with_runtime_partitions_filtered(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "head", monkeypatch)

        # Mirrors alembic/env.py's include_object (env.py executes only under
        # an Alembic invocation, so the filter is replicated here), plus the
        # reflection-only PostGIS catalog table.
        runtime_names = re.compile(
            r"^location_pings_p\d{4}_\d{2}$|^location_pings_legacy$|^spatial_ref_sys$"
        )

        def include_object(obj, name, type_, reflected, compare_to):
            if type_ == "table" and name is not None and runtime_names.match(name):
                return False
            return True

        def compare(sync_connection):
            context = MigrationContext.configure(
                sync_connection,
                opts={
                    "compare_type": False,
                    "compare_server_default": False,
                    "include_object": include_object,
                },
            )
            return compare_metadata(context, Base.metadata)

        async def run() -> list:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    return await connection.run_sync(compare)
            finally:
                await engine.dispose()

        diffs = asyncio.run(run())

        # Pre-existing model<->migration drift, discovered by this gate and
        # outside S4's approved scope (indexes/uniques declared only in
        # migrations 0002-0010, never on the models). Quarantined by name so
        # NEW drift still fails; closing these is reported follow-up work.
        known_drift_indexes = {
            "ix_campaign_creatives_campaign_status",
            "ix_campaign_creatives_creative_type",
            "ix_campaign_zones_campaign_zone_type",
            "ix_campaign_zones_geom",
            "ix_campaigns_organization_status",
            "ix_campaigns_start_end",
            "ix_driver_profiles_country_city",
            "ix_driver_profiles_onboarding_status",
            "ix_driver_profiles_user_id",
            "ix_vehicles_plate_country_normalized",
            "ix_vehicles_status",
        }
        known_drift_constraints = {"uq_driver_profiles_user_id", "uq_users_email"}

        unexpected = []
        for diff in diffs:
            kind = diff[0]
            if kind in {"remove_index", "add_index"} and diff[1].name in known_drift_indexes:
                continue
            if kind == "remove_constraint" and diff[1].name in known_drift_constraints:
                continue
            unexpected.append(diff)

        # S4's own tables must be exactly in sync — no quarantine applies.
        s4_tables = {"location_pings", "location_ping_batches", "data_purge_audit", "audit_events"}
        for diff in diffs:
            target = getattr(diff[1], "table", None) if len(diff) > 1 else None
            table_name = getattr(target, "name", None) or getattr(diff[1], "name", None)
            assert table_name not in s4_tables, f"S4 table drift: {diff}"

        assert unexpected == [], f"autogenerate diff not empty: {unexpected}"
    finally:
        asyncio.run(drop_database(migration_url))
