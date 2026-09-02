"""Migration 0040: durable fail-closed budget-policy evidence."""

import asyncio

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_BUDGET_REVISION = "0039_billing_corrections_refunds"
BUDGET_POLICY_REVISION = "0040_budget_policy_blocked_state"


async def _version_rows(migration_url: str) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list(
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version ORDER BY version_num")
                    )
                ).all()
            )
    finally:
        await engine.dispose()


def test_budget_policy_state_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, BUDGET_POLICY_REVISION, monkeypatch)
        downgrade_to(migration_url, PRE_BUDGET_REVISION, monkeypatch)
        upgrade_to(migration_url, BUDGET_POLICY_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_budget_policy_state_is_append_only_and_blocks_populated_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO budget_policy_evaluations
                          (id, campaign_id, evaluation_key, state, external_gate,
                           campaign_budget_amount, campaign_daily_budget_amount, currency,
                           policy_version, billing_spend_amount, alert_threshold_amount,
                           pause_threshold_amount, pause_applied, evaluated_at)
                        VALUES
                          ('40000000-0000-0000-0000-000000000001',
                           '40000000-0000-0000-0000-000000000002', repeat('a', 64),
                           'blocked_external_policy', 'EXT-BUDGET-POLICY', 1000, 100, 'NGN',
                           NULL, NULL, NULL, NULL, false, now())
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE budget_policy_evaluations SET state = state WHERE id = "
                            "'40000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, BUDGET_POLICY_REVISION, monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0040 downgrade blocked"):
            downgrade_to(migration_url, PRE_BUDGET_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_budget_policy_state_survives_current_head_upgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, BUDGET_POLICY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(_version_rows(migration_url)) == [
            (revision,)
            for revision in sorted(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
        ]
    finally:
        asyncio.run(drop_database(migration_url))
