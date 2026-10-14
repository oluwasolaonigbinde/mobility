"""Current PostgreSQL schema: governed aggregate facts and delivery approvals."""

import asyncio

import pytest
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def test_delivery_approval_is_append_only(
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
    finally:
        asyncio.run(drop_database(migration_url))
