"""Migration 0031: carry-forward payout debt authority."""

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

PRE_DEBT_REVISION = "0030_provider_line_reconciliation"


def test_carry_forward_debt_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'payout_debt_%' "
                "OR table_name = 'driver_currency_debt_accounts' ORDER BY table_name",
            )
        ) == [
            ("driver_currency_debt_accounts",),
            ("payout_debt_allocations",),
            ("payout_debt_obligations",),
            ("payout_debt_paid_sources",),
            ("payout_debt_settlements",),
        ]
        downgrade_to(migration_url, PRE_DEBT_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'driver_currency_debt_accounts'",
            )
        ) == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize(
    "seed_sql",
    [
        """
        INSERT INTO driver_currency_debt_accounts
          (id, driver_profile_id, driver_user_id, currency, outstanding_amount,
           lifetime_incurred_amount, lifetime_allocated_amount)
        VALUES
          ('31000000-0000-0000-0000-000000000001',
           '31000000-0000-0000-0000-000000000002',
           '31000000-0000-0000-0000-000000000003', 'NGN', 10, 10, 0)
        """,
        """
        INSERT INTO earnings_ledger_entries
          (id, driver_profile_id, driver_user_id, campaign_id, trip_session_id,
           entry_type, status, amount, currency, occurred_at)
        VALUES
          ('31000000-0000-0000-0000-000000000011',
           '31000000-0000-0000-0000-000000000012',
           '31000000-0000-0000-0000-000000000013',
           '31000000-0000-0000-0000-000000000014',
           '31000000-0000-0000-0000-000000000015',
           'debt_remainder', 'available', 1, 'NGN', now())
        """,
    ],
)
def test_carry_forward_debt_populated_downgrade_fails_closed(monkeypatch, seed_sql: str) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(text(seed_sql))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="0031 downgrade blocked"):
            downgrade_to(migration_url, PRE_DEBT_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
