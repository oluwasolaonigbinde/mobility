"""Migration 0045: disclosure query history is empty-create and fail-closed on downgrade."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_DISCLOSURE_REVISION = "0044_notification_outbox"


def test_disclosure_history_empty_down_up_and_populated_downgrade_guard(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO disclosure_query_decisions "
                        "(principal_hash, scope_hash, query_hash, result_hash, output_class, "
                        "decision, reason, "
                        "window_start, window_end, expires_at) VALUES "
                        "(repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64), "
                        "'advertiser.campaign.heatmap', 'served', 'privacy_floor_passed', "
                        "now(), now(), now() + interval '30 days')"
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_DISCLOSURE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_DISCLOSURE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="Refusing to drop populated"):
            downgrade_to(migration_url, PRE_DISCLOSURE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
