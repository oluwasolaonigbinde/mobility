"""Current PostgreSQL schema: immutable aggregate delivery receipts."""

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


def test_audience_delivery_is_append_only(
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
                        INSERT INTO audience_deliveries
                          (id, organization_id, campaign_id, segment_id, actor_user_id,
                           operation, idempotency_key, request_fingerprint, payload,
                           payload_sha256, result, result_sha256, adapter_name, synthetic,
                           status, created_at)
                        VALUES
                          ('66000000-0000-0000-0000-000000000001',
                           '66000000-0000-0000-0000-000000000002',
                           '66000000-0000-0000-0000-000000000003',
                           '66000000-0000-0000-0000-000000000004',
                           '66000000-0000-0000-0000-000000000005',
                           'csv_export', 'migration-receipt', repeat('a', 64),
                           '{}'::jsonb, repeat('b', 64), '{}'::jsonb, repeat('c', 64),
                           'controlled-csv-v1', false, 'completed', now())
                        """
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE audience_deliveries SET status = status WHERE id = "
                            "'66000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
