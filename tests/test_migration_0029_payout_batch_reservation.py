"""Migration 0029: atomic payout batch reservation authority."""

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
    fetch_all,
    upgrade_to,
)

PRE_BATCH_REVISION = "0028_protected_payee_accounts"


def test_payout_batch_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('payout_batches', 'payout_batch_lines') "
                "ORDER BY table_name",
            )
        )
        assert tables == [("payout_batch_lines",), ("payout_batches",)]
        downgrade_to(migration_url, PRE_BATCH_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name IN ('payout_batches', 'payout_batch_lines')",
            )
        ) == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize("table_name", ["payout_batches", "payout_batch_lines"])
def test_payout_batch_populated_downgrade_fails_closed(monkeypatch, table_name: str) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                if table_name == "payout_batches":
                    sql = (
                        "INSERT INTO payout_batches "
                        "(id, status, currency, total_amount, created_by_user_id) VALUES "
                        "('29000000-0000-0000-0000-000000000001', 'draft', 'NGN', 0, "
                        "'29000000-0000-0000-0000-000000000002')"
                    )
                else:
                    sql = (
                        "INSERT INTO payout_batch_lines "
                        "(id, batch_id, ledger_entry_id, payee_version_id, "
                        "bank_account_version_id, amount, currency, instruction, "
                        "instruction_fingerprint, idempotency_key) VALUES "
                        "('29000000-0000-0000-0000-000000000011', "
                        "'29000000-0000-0000-0000-000000000012', "
                        "'29000000-0000-0000-0000-000000000013', "
                        "'29000000-0000-0000-0000-000000000014', "
                        "'29000000-0000-0000-0000-000000000015', 1, 'NGN', "
                        "'{}'::jsonb, repeat('a', 64), repeat('b', 64))"
                    )
                await connection.execute(text(sql))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="0029 downgrade blocked"):
            downgrade_to(migration_url, PRE_BATCH_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
