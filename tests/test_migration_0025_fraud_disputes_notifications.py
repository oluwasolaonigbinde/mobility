"""Migration 0025: fraud disputes and sanitized notification authority."""

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
    fetch_all,
    upgrade_to,
)

PRE_DISPUTE_REVISION = "0024_fraud_review_holds"


def test_dispute_notification_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('fraud_disputes', 'notifications') ORDER BY table_name",
            )
        )
        assert tables == [("fraud_disputes",), ("notifications",)]
        downgrade_to(migration_url, PRE_DISPUTE_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('fraud_disputes', 'notifications')",
            )
        ) == []
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_dispute_notification_populated_downgrade_fails_closed(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO notifications "
                        "(recipient_user_id, type_key, template_version, payload, dedupe_key) "
                        "VALUES ('20000000-0000-0000-0000-000000000001', "
                        "'fraud_hold_raised', 'v1', '{}'::jsonb, 'migration-fixture')"
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(DBAPIError, match="downgrade blocked"):
            downgrade_to(migration_url, PRE_DISPUTE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
