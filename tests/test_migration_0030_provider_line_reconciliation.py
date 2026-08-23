"""Migration 0030: verified provider line reconciliation authority."""

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

PRE_RECONCILIATION_REVISION = "0029_payout_batch_reservation"


def test_provider_reconciliation_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'payout_batch_lines' "
                "AND column_name IN ('status', 'provider_transfer_reference', "
                "'reconciled_by_user_id', 'reconciled_at', 'last_provider_evidence_at') "
                "ORDER BY column_name",
            )
        ) == [
            ("last_provider_evidence_at",),
            ("provider_transfer_reference",),
            ("reconciled_at",),
            ("reconciled_by_user_id",),
            ("status",),
        ]
        downgrade_to(migration_url, PRE_RECONCILIATION_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'payout_line_reconciliation_events'",
            )
        ) == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize(
    "seed_sql",
    [
        """
        INSERT INTO payout_line_reconciliation_events
          (id, line_id, provider_event_id, source, outcome, evidence_fingerprint,
           provider_occurred_at, applied)
        VALUES
          ('30000000-0000-0000-0000-000000000001',
           '30000000-0000-0000-0000-000000000002', 'event-0030', 'webhook',
           'succeeded', repeat('a', 64), now(), true)
        """,
        """
        INSERT INTO payout_batch_lines
          (id, batch_id, ledger_entry_id, payee_version_id, bank_account_version_id,
           amount, currency, instruction, instruction_fingerprint, idempotency_key,
           status, provider_transfer_reference)
        VALUES
          ('30000000-0000-0000-0000-000000000011',
           '30000000-0000-0000-0000-000000000012',
           '30000000-0000-0000-0000-000000000013',
           '30000000-0000-0000-0000-000000000014',
           '30000000-0000-0000-0000-000000000015', 1, 'NGN', '{}'::jsonb,
           repeat('b', 64), repeat('c', 64), 'submitted', 'provider-line-0030')
        """,
        """
        INSERT INTO earnings_ledger_entries
          (id, driver_profile_id, driver_user_id, campaign_id, trip_session_id,
           entry_type, status, amount, currency, occurred_at)
        VALUES
          ('30000000-0000-0000-0000-000000000021',
           '30000000-0000-0000-0000-000000000022',
           '30000000-0000-0000-0000-000000000023',
           '30000000-0000-0000-0000-000000000024',
           '30000000-0000-0000-0000-000000000025',
           'adjustment', 'paid', 1, 'NGN', now())
        """,
    ],
)
def test_provider_reconciliation_populated_downgrade_fails_closed(
    monkeypatch, seed_sql: str
) -> None:
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
        with pytest.raises(RuntimeError, match="0030 downgrade blocked"):
            downgrade_to(migration_url, PRE_RECONCILIATION_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
