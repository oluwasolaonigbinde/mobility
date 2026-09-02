"""Migration 0075: governed aggregate facts and delivery approvals."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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

from app.db.base import Base

PRE_GOVERNED_DELIVERY_REVISION = "0074_trip_evidence_manifest"


def test_governed_audience_delivery_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_GOVERNED_DELIVERY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_GOVERNED_DELIVERY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_delivery_approval_is_append_only_and_blocks_populated_downgrade(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO audience_delivery_approvals
                          (id, organization_id, campaign_id, segment_id,
                           approved_by_user_id, operation, purpose_code, provider,
                           legal_approval_reference, idempotency_key,
                           request_fingerprint, snapshot, snapshot_sha256, synthetic,
                           valid_from, valid_until, created_at)
                        VALUES
                          ('75000000-0000-0000-0000-000000000001',
                           '75000000-0000-0000-0000-000000000002',
                           '75000000-0000-0000-0000-000000000003',
                           '75000000-0000-0000-0000-000000000004',
                           '75000000-0000-0000-0000-000000000005',
                           'csv_export', 'aggregate_campaign_planning',
                           'controlled-csv-v1', 'synthetic-test-migration',
                           'migration-approval', repeat('a', 64), '{}'::jsonb,
                           repeat('b', 64), true, now(), now() + interval '1 day', now())
                        """
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE audience_delivery_approvals SET provider = provider "
                            "WHERE id = '75000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0075 downgrade blocked"):
            downgrade_to(migration_url, PRE_GOVERNED_DELIVERY_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_governed_audience_models_have_no_owned_autogenerate_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def compare() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={
                                "compare_type": False,
                                "compare_server_default": False,
                            },
                        ),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        diffs = asyncio.run(compare())
        owned_tables = {
            "audience_deliveries",
            "audience_delivery_approvals",
            "exposure_segments",
            "exposure_segment_cells",
        }
        owned_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(
                candidate, "name", None
            )
            if table_name in owned_tables:
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
