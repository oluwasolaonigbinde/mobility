"""Current PostgreSQL schema: budget transitions and recovery/contact evidence."""

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


def test_budget_evaluation_and_transition_are_append_only(monkeypatch) -> None:
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
                          (id, campaign_id, evaluation_key, state,
                           campaign_budget_amount, campaign_daily_budget_amount, currency,
                           policy_id, policy_revision, policy_source, budget_basis,
                           billing_fact_source, billing_spend_amount, alert_threshold_amount,
                           pause_threshold_amount, resume_threshold_amount, alert_applied,
                           pause_applied, resume_allowed, evaluated_at)
                        VALUES
                          ('64000000-0000-0000-0000-000000000001',
                           '64000000-0000-0000-0000-000000000002', repeat('a', 64),
                           'pause_threshold', 1000, NULL, 'NGN',
                           'synthetic-policy', 'synthetic-r1', 'synthetic_test', 'total',
                           'confirmed_funding', 1000, 800, 1000, 700, true, true, false, now())
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO budget_campaign_transitions
                          (id, campaign_id, evaluation_id, action, prior_status, new_status,
                           actor_user_id, reason, created_at)
                        VALUES
                          ('64000000-0000-0000-0000-000000000003',
                           '64000000-0000-0000-0000-000000000002',
                           '64000000-0000-0000-0000-000000000001',
                           'pause', 'active', 'paused', NULL, 'threshold reached', now())
                        """
                    )
                )
            for statement in (
                "UPDATE budget_campaign_transitions SET reason = reason WHERE id = "
                "'64000000-0000-0000-0000-000000000003'",
                "UPDATE budget_policy_evaluations SET state = state WHERE id = "
                "'64000000-0000-0000-0000-000000000001'",
            ):
                with pytest.raises(DBAPIError, match="append-only"):
                    async with engine.begin() as connection:
                        await connection.execute(text(statement))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
