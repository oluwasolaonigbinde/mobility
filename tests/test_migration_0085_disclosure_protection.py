"""Forward retention migration preserves existing protection and refuses lossy rollback."""

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

PREVIOUS = "0084_payout_conservation"
CURRENT = "0085_disclosure_protection"


def test_existing_disclosure_protection_loses_only_unsupported_expiry(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def execute(sql):
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                result = await connection.execute(text(sql))
                return result.all() if result.returns_rows else None
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        upgrade_to(url, CURRENT, monkeypatch)
        downgrade_to(url, PREVIOUS, monkeypatch)
        asyncio.run(
            execute(
                "INSERT INTO disclosure_query_decisions "
                "(principal_hash, scope_hash, query_hash, result_hash, output_class, decision, "
                "reason, window_start, window_end, expires_at) VALUES "
                "(repeat('a',64),repeat('b',64),repeat('c',64),repeat('d',64),"
                "'advertiser.campaign.heatmap','served','privacy_floor_passed',"
                "now()-interval '60 days',now()-interval '50 days',now()-interval '1 day')"
            )
        )
        before = asyncio.run(
            execute("SELECT to_jsonb(d)-'expires_at' FROM disclosure_query_decisions d")
        )
        upgrade_to(url, CURRENT, monkeypatch)
        after = asyncio.run(
            execute("SELECT to_jsonb(d)-'expires_at' FROM disclosure_query_decisions d")
        )
        assert after == before
        assert asyncio.run(execute("SELECT expires_at FROM disclosure_query_decisions")) == [
            (None,)
        ]
        with pytest.raises(RuntimeError, match="0085 downgrade blocked"):
            downgrade_to(url, PREVIOUS, monkeypatch)
        assert asyncio.run(execute("SELECT expires_at FROM disclosure_query_decisions")) == [
            (None,)
        ]
        assert asyncio.run(execute("SELECT version_num FROM alembic_version")) == [(CURRENT,)]
    finally:
        asyncio.run(drop_database(url))
