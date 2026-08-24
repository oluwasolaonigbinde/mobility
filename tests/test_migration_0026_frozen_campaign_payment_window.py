"""Migration 0026: accepted payout-v3 campaign-window authority."""

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

PRE_WINDOW_REVISION = "0025_fraud_disputes_notifications"


def test_frozen_campaign_window_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'assignment_rule_bindings' "
                "AND column_name LIKE 'campaign_window_%' ORDER BY column_name",
            )
        )
        by_column = {row[0]: (row[1], row[2]) for row in rows}
        assert by_column["campaign_window_start_at"] == ("YES", None)
        assert by_column["campaign_window_end_at"] == ("YES", None)
        assert by_column["campaign_window_frozen"][0] == "NO"
        assert "false" in by_column["campaign_window_frozen"][1]

        downgrade_to(migration_url, PRE_WINDOW_REVISION, monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'assignment_rule_bindings' "
                "AND column_name LIKE 'campaign_window_%'",
            )
        ) == [(0,)]
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_frozen_campaign_window_populated_downgrade_fails_closed(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO assignment_rule_bindings "
                        "(assignment_id, revision_id, hourly_rate_naira, eligibility_params, "
                        "resolved_eligibility_params, formula_version, premium_zone_ids, "
                        "premium_zone_geometry_hash, premium_zone_geometry_wkts, "
                        "exclusion_zone_ids, exclusion_zone_geometry_hash, "
                        "exclusion_zone_geometry_wkts, stationary_policy_marker, "
                        "campaign_window_frozen) VALUES "
                        "('26000000-0000-0000-0000-000000000001', "
                        "'26000000-0000-0000-0000-000000000002', 1000, '{}', '{}', "
                        "'payout_v3', '[]', 'hash', '[]', '[]', 'hash', '[]', "
                        "'stationary-v1', true)"
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(DBAPIError, match="downgrade blocked"):
            downgrade_to(migration_url, PRE_WINDOW_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
