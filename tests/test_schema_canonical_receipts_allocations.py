"""Current PostgreSQL schema: canonical immutable receipt authority."""

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


def test_receipts_are_database_immutable(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO payment_receipts
                          (id, organization_id, method, provider, external_transaction_id,
                           amount, currency, payer_name, evidence_reference, observed_at)
                        VALUES
                          ('34000000-0000-0000-0000-000000000001',
                           '34000000-0000-0000-0000-000000000002', 'manual_transfer',
                           'bank-transfer', 'TX-34', 10, 'NGN', 'Payer', 'line-1', now())
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE payment_receipts SET amount = amount WHERE id = "
                            "'34000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
