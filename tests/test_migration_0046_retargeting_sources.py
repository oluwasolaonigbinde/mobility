"""Migration 0046: typed source authority is append-only and downgrade-safe."""

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

PRE_SOURCE_REVISION = "0045_disclosure_query_history"


def test_source_empty_roundtrip_append_only_and_populated_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_verify() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO users (email, password_hash, full_name, role, status) "
                        "VALUES ('source-migration@example.com', 'hash', 'Source Migration', "
                        "'advertiser', 'active') RETURNING id"
                    )
                )
                organization_id = await connection.scalar(
                    text(
                        "INSERT INTO advertiser_organizations "
                        "(name, currency, status) VALUES "
                        "('Source Migration Org', 'NGN', 'active') RETURNING id"
                    )
                )
                source_id = await connection.scalar(
                    text(
                        "INSERT INTO retargeting_sources "
                        "(organization_id, source_type, snapshot, snapshot_sha256, expires_at) "
                        "VALUES (:organization_id, 'manual-insight', '{}'::jsonb, "
                        "repeat('a', 64), now() + interval '30 days') RETURNING id"
                    ),
                    {"organization_id": organization_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO retargeting_source_events "
                        "(source_id, sequence_number, event_type, snapshot, snapshot_sha256) "
                        "VALUES (:source_id, 1, 'created', '{}'::jsonb, repeat('a', 64))"
                    ),
                    {"source_id": source_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO retargeting_source_idempotency "
                        "(actor_user_id, operation, idempotency_key, request_fingerprint, "
                        "source_id) VALUES (:user_id, 'create', 'migration-key', "
                        "repeat('b', 64), :source_id)"
                    ),
                    {"user_id": user_id, "source_id": source_id},
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE retargeting_source_events SET event_type = 'deactivated' "
                            "WHERE source_id = :source_id"
                        ),
                        {"source_id": source_id},
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_SOURCE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_SOURCE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_verify())
        with pytest.raises(RuntimeError, match="Refusing to drop populated"):
            downgrade_to(migration_url, PRE_SOURCE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
