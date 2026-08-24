"""Migration 0041: populated correction retry identity."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)


def test_populated_correction_backfill_restores_append_only_and_blocks_downgrade(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
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
                           reason, created_by_user_id, created_at)
                        VALUES
                          ('41000000-0000-0000-0000-000000000001',
                           '41000000-0000-0000-0000-000000000002', 1, 'COR-LEGACY-001',
                           'credit_note', 'NGN', 10, 0, 10, 'legacy correction',
                           '41000000-0000-0000-0000-000000000003', now())
                        """
                    )
                )
        finally:
            await engine.dispose()

    async def verify() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT correction_reference, request_fingerprint "
                            "FROM invoice_corrections"
                        )
                    )
                ).one()
                assert row.correction_reference == "legacy:41000000-0000-0000-0000-000000000001"
                assert len(row.request_fingerprint) == 64
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text("UPDATE invoice_corrections SET reason = reason")
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0040_budget_policy_blocked_state", monkeypatch)
        asyncio.run(seed())
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(verify())
        with pytest.raises(RuntimeError, match="0041 downgrade blocked"):
            from test_migration_0014_partitioning import downgrade_to

            downgrade_to(migration_url, "0040_budget_policy_blocked_state", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
