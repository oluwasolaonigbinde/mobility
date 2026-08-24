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


def test_carry_forward_debt_backfills_eligible_paid_reversals_idempotently(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        WITH inserted_user AS (
                          INSERT INTO users (id, email, password_hash, full_name, role, status)
                          VALUES ('31000000-0000-0000-0000-000000000103',
                                  'debt-backfill@example.test', 'x', 'Debt Backfill',
                                  'driver', 'active')
                          RETURNING id
                        )
                        INSERT INTO driver_profiles (id, user_id, onboarding_status, metadata)
                        SELECT '31000000-0000-0000-0000-000000000102', id, 'active', '{}'::jsonb
                        FROM inserted_user
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO earnings_ledger_entries
                          (id, driver_profile_id, driver_user_id, campaign_id, trip_session_id,
                           entry_type, status, amount, currency, occurred_at)
                        VALUES
                          ('31000000-0000-0000-0000-000000000101',
                           '31000000-0000-0000-0000-000000000102',
                           '31000000-0000-0000-0000-000000000103',
                           '31000000-0000-0000-0000-000000000104',
                           '31000000-0000-0000-0000-000000000105',
                           'adjustment', 'paid', 100, 'NGN', now()),
                          ('31000000-0000-0000-0000-000000000106',
                           '31000000-0000-0000-0000-000000000102',
                           '31000000-0000-0000-0000-000000000103',
                           '31000000-0000-0000-0000-000000000104',
                           '31000000-0000-0000-0000-000000000105',
                           'reversal', 'available', 60, 'NGN', now()),
                          ('31000000-0000-0000-0000-000000000107',
                           '31000000-0000-0000-0000-000000000102',
                           '31000000-0000-0000-0000-000000000103',
                           '31000000-0000-0000-0000-000000000104',
                           '31000000-0000-0000-0000-000000000105',
                           'reversal', 'available', 15, 'NGN', now()),
                          ('31000000-0000-0000-0000-000000000108',
                           '31000000-0000-0000-0000-000000000102',
                           '31000000-0000-0000-0000-000000000103',
                           '31000000-0000-0000-0000-000000000104',
                           '31000000-0000-0000-0000-000000000109',
                           'reversal', 'available', 25, 'NGN', now()),
                          ('31000000-0000-0000-0000-000000000110',
                           '31000000-0000-0000-0000-000000000102',
                           '31000000-0000-0000-0000-000000000103',
                           '31000000-0000-0000-0000-000000000104',
                           '31000000-0000-0000-0000-000000000105',
                           'reversal', 'pending', 30, 'NGN', now())
                        """
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_DEBT_REVISION, monkeypatch)
        asyncio.run(seed())
        upgrade_to(migration_url, "head", monkeypatch)
        first = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT account.outstanding_amount, account.lifetime_incurred_amount,
                       count(obligation.id), count(source.id)
                FROM driver_currency_debt_accounts account
                LEFT JOIN payout_debt_obligations obligation
                  ON obligation.debt_account_id = account.id
                LEFT JOIN payout_debt_paid_sources source
                  ON source.debt_obligation_id = obligation.id
                GROUP BY account.outstanding_amount, account.lifetime_incurred_amount
                """,
            )
        )
        upgrade_to(migration_url, "head", monkeypatch)
        second = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT account.outstanding_amount, account.lifetime_incurred_amount,
                       count(obligation.id), count(source.id)
                FROM driver_currency_debt_accounts account
                LEFT JOIN payout_debt_obligations obligation
                  ON obligation.debt_account_id = account.id
                LEFT JOIN payout_debt_paid_sources source
                  ON source.debt_obligation_id = obligation.id
                GROUP BY account.outstanding_amount, account.lifetime_incurred_amount
                """,
            )
        )
        assert first == [(100, 100, 3, 2)]
        assert second == first
    finally:
        asyncio.run(drop_database(migration_url))


def test_carry_forward_debt_backfill_refuses_unsafe_active_reservation(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        WITH inserted_user AS (
                          INSERT INTO users (id, email, password_hash, full_name, role, status)
                          VALUES ('31000000-0000-0000-0000-000000000203',
                                  'debt-reservation@example.test', 'x', 'Debt Reservation',
                                  'driver', 'active')
                          RETURNING id
                        )
                        INSERT INTO driver_profiles (id, user_id, onboarding_status, metadata)
                        SELECT '31000000-0000-0000-0000-000000000202', id, 'active', '{}'::jsonb
                        FROM inserted_user
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO earnings_ledger_entries
                          (id, driver_profile_id, driver_user_id, campaign_id, trip_session_id,
                           entry_type, status, amount, currency, occurred_at)
                        VALUES
                          ('31000000-0000-0000-0000-000000000201',
                           '31000000-0000-0000-0000-000000000202',
                           '31000000-0000-0000-0000-000000000203',
                           '31000000-0000-0000-0000-000000000204',
                           '31000000-0000-0000-0000-000000000205',
                           'adjustment', 'paid', 100, 'NGN', now()),
                          ('31000000-0000-0000-0000-000000000206',
                           '31000000-0000-0000-0000-000000000202',
                           '31000000-0000-0000-0000-000000000203',
                           '31000000-0000-0000-0000-000000000204',
                           '31000000-0000-0000-0000-000000000205',
                           'reversal', 'available', 60, 'NGN', now())
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO payout_batches
                          (id, status, currency, total_amount, instruction_set_fingerprint,
                           created_by_user_id)
                        VALUES
                          ('31000000-0000-0000-0000-000000000207', 'reserved', 'NGN', 100,
                           repeat('a', 64), '31000000-0000-0000-0000-000000000203')
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO payout_batch_lines
                          (id, batch_id, ledger_entry_id, payee_version_id, bank_account_version_id,
                           amount, currency, instruction, instruction_fingerprint, idempotency_key,
                           status, reservation_active)
                        VALUES
                          ('31000000-0000-0000-0000-000000000208',
                           '31000000-0000-0000-0000-000000000207',
                           '31000000-0000-0000-0000-000000000201',
                           '31000000-0000-0000-0000-000000000209',
                           '31000000-0000-0000-0000-000000000210',
                           100, 'NGN', '{}'::jsonb, repeat('b', 64), repeat('c', 64),
                           'reserved', true)
                        """
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_DEBT_REVISION, monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="0031 upgrade blocked: active payout reservation"):
            upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'driver_currency_debt_accounts'",
            )
        ) == [(0,)]
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
