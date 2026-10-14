"""Current PostgreSQL schema: immutable invoice corrections and refund settlements."""

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


def test_correction_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO invoice_corrections
                          (id, invoice_id, sequence_number, correction_number,
                           correction_type, currency, net_amount, tax_amount, gross_amount,
                           reason, created_by_user_id, created_at,
                           correction_reference, request_fingerprint)
                        VALUES
                          ('39000000-0000-0000-0000-000000000001',
                           '39000000-0000-0000-0000-000000000002', 1, 'CN-39-001',
                           'credit_note', 'NGN', 10, 0, 10, 'migration evidence',
                           '39000000-0000-0000-0000-000000000003', now(),
                           'synthetic-reference', repeat('a', 64))
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE invoice_corrections SET reason = reason WHERE id = "
                            "'39000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
