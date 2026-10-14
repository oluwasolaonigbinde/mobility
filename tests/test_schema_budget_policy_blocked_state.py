"""Current PostgreSQL schema: durable fail-closed budget-policy evidence."""

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

BUDGET_POLICY_REVISION = "head"


def test_budget_policy_state_is_append_only(monkeypatch) -> None:
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
                           policy_revision, billing_spend_amount, alert_threshold_amount,
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
    finally:
        asyncio.run(drop_database(migration_url))
