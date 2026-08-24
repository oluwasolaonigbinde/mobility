"""Migration 0034: canonical immutable receipt authority."""

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

PRE_RECEIPT_REVISION = "0033_advertiser_company_profiles"


def test_receipt_authority_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables WHERE table_name IN "
                "('payment_receipts','receipt_reconciliations','receipt_lifecycle_events',"
                "'receipt_allocations') ORDER BY table_name",
            )
        ) == [
            ("payment_receipts",),
            ("receipt_allocations",),
            ("receipt_lifecycle_events",),
            ("receipt_reconciliations",),
        ]
        downgrade_to(migration_url, PRE_RECEIPT_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_receipts_are_database_immutable_and_block_downgrade(monkeypatch) -> None:
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
        with pytest.raises(RuntimeError, match="0034 downgrade blocked"):
            downgrade_to(migration_url, PRE_RECEIPT_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
