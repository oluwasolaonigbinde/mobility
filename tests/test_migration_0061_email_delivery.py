"""Migration 0061: provider-neutral email delivery authority."""

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

PRE_EMAIL_REVISION = "0060_evidence_verifications"


def test_email_delivery_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_EMAIL_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_EMAIL_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_populated_email_delivery_downgrade_refuses(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO notification_delivery_receipts "
                        "(id,notification_id,provider_event_id,provider_message_id,outcome,"
                        "occurred_at,evidence_fingerprint,signing_key_id) VALUES "
                        "('61000000-0000-0000-0000-000000000001',"
                        "'61000000-0000-0000-0000-000000000002','event-1','message-1',"
                        "'delivered',now(),repeat('a',64),'test-v1')"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE notification_delivery_receipts SET outcome = 'failed' "
                            "WHERE provider_event_id = 'event-1'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="email delivery authority"):
            downgrade_to(migration_url, PRE_EMAIL_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
