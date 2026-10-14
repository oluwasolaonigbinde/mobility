"""Current PostgreSQL schema: provider-neutral gateway events."""

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


def test_gateway_event_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO payment_gateway_events
                          (id, provider, provider_event_id, external_transaction_id,
                           event_type, commercial_terms_reference, amount, currency,
                           payer_name, occurred_at, evidence_fingerprint, payload, received_at)
                        VALUES
                          ('38000000-0000-0000-0000-000000000001', 'synthetic-gateway',
                           'event-38', 'transaction-38', 'payment_confirmed',
                           '38000000-0000-0000-0000-000000000002', 10, 'NGN', 'Payer',
                           now(), repeat('a', 64), '{}', now())
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE payment_gateway_events SET amount = amount WHERE id = "
                            "'38000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
