"""Migration 0048: one deterministic authority row per trip/methodology."""

import asyncio
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_migration_path = (
    Path(__file__).parents[1] / "alembic/versions/0048_canonical_impression_authority.py"
)
_migration_spec = importlib.util.spec_from_file_location("migration_0048", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostgreSQL test database is not configured")
    return database_url


async def create_temporary_database(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_0048_authority_{uuid4().hex}"
    engine = create_async_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()
    return source_url.set(database=database_name).render_as_string(hide_password=False)


async def drop_temporary_database(database_url: str) -> None:
    url = make_url(database_url)
    engine = create_async_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": url.database},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}"'))
    finally:
        await engine.dispose()


def test_authority_backfill_is_deterministic_and_sqlite_index_stays_partial() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE traffic_density_profiles ("
            "id TEXT PRIMARY KEY, status TEXT NOT NULL, is_default BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE impression_estimates ("
            "id TEXT PRIMARY KEY, trip_session_id TEXT NOT NULL, "
            "formula_version TEXT NOT NULL, traffic_density_profile_id TEXT NOT NULL, "
            "estimated_at TEXT NOT NULL)"
        )
        connection.execute(
            text(
                "INSERT INTO traffic_density_profiles (id,status,is_default) VALUES "
                "('default','active',1),('scenario','inactive',0),"
                "('active-scenario','active',0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO impression_estimates "
                "(id,trip_session_id,formula_version,traffic_density_profile_id,estimated_at) "
                "VALUES ('scenario-row','trip-1','impressions_v1','scenario','2026-01-02'),"
                "('default-row','trip-1','impressions_v1','default','2026-01-01'),"
                "('other-row','trip-1','impressions_v1','scenario','2026-01-03'),"
                "('scenario-only-row','trip-2','impressions_v1','active-scenario','2026-01-04')"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()

        rows = connection.execute(
            text(
                "SELECT id,is_authoritative FROM impression_estimates "
                "WHERE trip_session_id='trip-1' ORDER BY id"
            )
        ).all()
        assert [(row[0], row[1]) for row in rows] == [
            ("default-row", 1),
            ("other-row", 0),
            ("scenario-row", 0),
        ]
        scenario_only = connection.execute(
            text(
                "SELECT is_authoritative FROM impression_estimates "
                "WHERE trip_session_id='trip-2'"
            )
        ).scalar_one()
        assert scenario_only == 0
        index_sql = connection.scalar(
            text(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND name='uq_impression_estimates_authoritative_trip_formula'"
            )
        )
        assert index_sql is not None
        assert "WHERE is_authoritative = 1" in index_sql

        with pytest.raises(RuntimeError, match="Refusing to drop populated"):
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()

        connection.execute(text("DELETE FROM impression_estimates"))
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        columns = connection.execute(text("PRAGMA table_info(impression_estimates)")).all()
        assert "is_authoritative" not in {row[1] for row in columns}


def test_authority_backfill_and_partial_index_on_isolated_postgres() -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_temporary_database(source_url))

    async def exercise() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE TABLE traffic_density_profiles ("
                        "id UUID PRIMARY KEY, status TEXT NOT NULL, "
                        "is_default BOOLEAN NOT NULL)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE TABLE impression_estimates ("
                        "id UUID PRIMARY KEY, trip_session_id UUID NOT NULL, "
                        "formula_version TEXT NOT NULL, "
                        "traffic_density_profile_id UUID NOT NULL, "
                        "estimated_at TIMESTAMPTZ NOT NULL)"
                    )
                )
                default_profile_id = uuid4()
                scenario_profile_id = uuid4()
                trip_with_default_id = uuid4()
                scenario_only_trip_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO traffic_density_profiles (id,status,is_default) "
                        "VALUES (:default_id,'active',true),(:scenario_id,'active',false)"
                    ),
                    {
                        "default_id": default_profile_id,
                        "scenario_id": scenario_profile_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO impression_estimates "
                        "(id,trip_session_id,formula_version,"
                        "traffic_density_profile_id,estimated_at) VALUES "
                        "(:default_row,:trip_with_default,'impressions_v1',"
                        ":default_profile,now()),"
                        "(:scenario_row,:trip_with_default,'impressions_v1',"
                        ":scenario_profile,now()),"
                        "(:scenario_only_row,:scenario_only_trip,'impressions_v1',"
                        ":scenario_profile,now())"
                    ),
                    {
                        "default_row": uuid4(),
                        "scenario_row": uuid4(),
                        "scenario_only_row": uuid4(),
                        "trip_with_default": trip_with_default_id,
                        "scenario_only_trip": scenario_only_trip_id,
                        "default_profile": default_profile_id,
                        "scenario_profile": scenario_profile_id,
                    },
                )

                def run_upgrade(sync_connection) -> None:
                    with Operations.context(MigrationContext.configure(sync_connection)):
                        MIGRATION.upgrade()

                await connection.run_sync(run_upgrade)
                rows = (
                    await connection.execute(
                        text(
                            "SELECT trip_session_id, traffic_density_profile_id, "
                            "is_authoritative FROM impression_estimates "
                            "ORDER BY trip_session_id, traffic_density_profile_id"
                        )
                    )
                ).all()
                assert sum(row.is_authoritative for row in rows) == 1
                assert any(
                    row.trip_session_id == trip_with_default_id
                    and row.traffic_density_profile_id == default_profile_id
                    and row.is_authoritative
                    for row in rows
                )
                assert not any(
                    row.trip_session_id == scenario_only_trip_id and row.is_authoritative
                    for row in rows
                )
                index_definition = await connection.scalar(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE indexname="
                        "'uq_impression_estimates_authoritative_trip_formula'"
                    )
                )
                assert index_definition is not None
                assert "UNIQUE INDEX" in index_definition
                assert "WHERE (is_authoritative = true)" in index_definition
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(
                            text(
                                "UPDATE impression_estimates SET is_authoritative=true "
                                "WHERE trip_session_id=:trip_id "
                                "AND traffic_density_profile_id=:scenario_profile_id"
                            ),
                            {
                                "trip_id": trip_with_default_id,
                                "scenario_profile_id": scenario_profile_id,
                            },
                        )
        finally:
            await engine.dispose()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(drop_temporary_database(migration_url))
