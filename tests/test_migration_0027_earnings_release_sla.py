"""Migration 0027: review escalation and fraud-linked reversal authority."""

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

PRE_RELEASE_REVISION = "0026_frozen_campaign_payment_window"


def test_earnings_release_sla_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE (table_name = 'fraud_flags' AND column_name = 'escalated_at') "
                "OR (table_name = 'earnings_ledger_entries' "
                "AND column_name = 'source_fraud_flag_id') ORDER BY table_name",
            )
        )
        assert columns == [
            ("earnings_ledger_entries", "source_fraud_flag_id"),
            ("fraud_flags", "escalated_at"),
        ]
        downgrade_to(migration_url, PRE_RELEASE_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns "
                "WHERE column_name IN ('escalated_at', 'source_fraud_flag_id') "
                "AND table_name IN ('fraud_flags', 'earnings_ledger_entries')",
            )
        ) == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize(
    "seed_sqls",
    [
        ("""
        INSERT INTO fraud_flags
          (id, trip_session_id, assignment_id, campaign_id, driver_profile_id,
           vehicle_id, flag_type, severity, status, description, evidence,
           detected_at, escalated_at)
        VALUES
          ('27000000-0000-0000-0000-000000000001',
           '27000000-0000-0000-0000-000000000002',
           '27000000-0000-0000-0000-000000000003',
           '27000000-0000-0000-0000-000000000004',
           '27000000-0000-0000-0000-000000000005',
           '27000000-0000-0000-0000-000000000006',
           'impossible_speed', 'high', 'open', 'fixture', '{}'::jsonb,
           now() - interval '7 days', now())
        """,),
        ("""
        INSERT INTO fraud_flags
          (id, trip_session_id, assignment_id, campaign_id, driver_profile_id,
           vehicle_id, flag_type, severity, status, description, evidence, detected_at)
        VALUES
          ('27000000-0000-0000-0000-000000000011',
           '27000000-0000-0000-0000-000000000012',
           '27000000-0000-0000-0000-000000000013',
           '27000000-0000-0000-0000-000000000014',
           '27000000-0000-0000-0000-000000000015',
           '27000000-0000-0000-0000-000000000016',
           'impossible_speed', 'high', 'open', 'fixture', '{}'::jsonb, now())
        """,
        """
        INSERT INTO earnings_ledger_entries
          (id, driver_profile_id, driver_user_id, campaign_id, trip_session_id,
           entry_type, status, amount, currency, occurred_at, source_fraud_flag_id)
        VALUES
          ('27000000-0000-0000-0000-000000000017',
           '27000000-0000-0000-0000-000000000015',
           '27000000-0000-0000-0000-000000000018',
           '27000000-0000-0000-0000-000000000014',
           '27000000-0000-0000-0000-000000000012',
           'reversal', 'available', 10, 'NGN', now(),
           '27000000-0000-0000-0000-000000000011')
        """),
    ],
)
def test_earnings_release_sla_populated_downgrade_fails_closed(
    monkeypatch, seed_sqls
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                for seed_sql in seed_sqls:
                    await connection.execute(text(seed_sql))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="downgrade blocked"):
            downgrade_to(migration_url, PRE_RELEASE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
