"""Migration 0078: one active campaign assignment per driver."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_DRIVER_EXCLUSIVITY_REVISION = "0077_stored_object_deletions"
DRIVER_EXCLUSIVITY_REVISION = "0078_campaign_assignment_driver_active"
INDEX_NAME = "uq_campaign_assignments_driver_active"


async def _rows(migration_url: str, statement: str) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(text(statement))).all())
    finally:
        await engine.dispose()


async def _seed_duplicate_active_drivers(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text(
                    """
                    INSERT INTO campaign_assignments
                      (id, campaign_id, driver_profile_id, vehicle_id,
                       assigned_by_user_id, status, offered_at, metadata)
                    VALUES
                      ('78000000-0000-0000-0000-000000000001',
                       '78000000-0000-0000-0000-000000000011',
                       '78000000-0000-0000-0000-000000000021',
                       '78000000-0000-0000-0000-000000000031',
                       '78000000-0000-0000-0000-000000000041',
                       'active', now(), '{}'::jsonb),
                      ('78000000-0000-0000-0000-000000000002',
                       '78000000-0000-0000-0000-000000000012',
                       '78000000-0000-0000-0000-000000000021',
                       '78000000-0000-0000-0000-000000000032',
                       '78000000-0000-0000-0000-000000000041',
                       'active', now(), '{}'::jsonb)
                    """
                )
            )
    finally:
        await engine.dispose()


def test_driver_active_index_empty_down_up_cycle_and_catalog(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_DRIVER_EXCLUSIVITY_REVISION, monkeypatch)
        upgrade_to(migration_url, DRIVER_EXCLUSIVITY_REVISION, monkeypatch)
        assert asyncio.run(
            _rows(
                migration_url,
                f"""
                SELECT indisunique, pg_get_expr(indpred, indrelid)
                FROM pg_index
                WHERE indexrelid = '{INDEX_NAME}'::regclass
                """,
            )
        ) == [(True, "((status)::text = 'active'::text)")]
        downgrade_to(migration_url, PRE_DRIVER_EXCLUSIVITY_REVISION, monkeypatch)
        assert asyncio.run(
            _rows(
                migration_url,
                f"SELECT to_regclass('{INDEX_NAME}')",
            )
        ) == [(None,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_driver_active_index_preflight_refuses_duplicates_without_mutation(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_DRIVER_EXCLUSIVITY_REVISION, monkeypatch)
        asyncio.run(_seed_duplicate_active_drivers(migration_url))

        with pytest.raises(
            DBAPIError,
            match="duplicate active campaign assignments exist for a driver",
        ):
            upgrade_to(migration_url, DRIVER_EXCLUSIVITY_REVISION, monkeypatch)

        assert asyncio.run(
            _rows(
                migration_url,
                """
                SELECT id::text, status
                FROM campaign_assignments
                ORDER BY id
                """,
            )
        ) == [
            ("78000000-0000-0000-0000-000000000001", "active"),
            ("78000000-0000-0000-0000-000000000002", "active"),
        ]
        assert asyncio.run(_rows(migration_url, "SELECT version_num FROM alembic_version")) == [
            (PRE_DRIVER_EXCLUSIVITY_REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))
