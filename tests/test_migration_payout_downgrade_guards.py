"""Fail-closed downgrade guards for populated payout-authority migrations."""

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


async def execute_seed(migration_url: str, statement: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


POPULATED_GUARD_CASES = (
    pytest.param(
        "0018_payout_rule_revisions",
        "0017_seal_review_hardening",
        """
        INSERT INTO campaign_payout_rule_revisions
            (id, campaign_id, payout_rule_id, revision_number, effective_from,
             hourly_rate_naira, daily_payable_hours_cap, eligibility_params,
             formula_version, reason, created_by_user_id)
        VALUES
            ('81000000-0000-0000-0000-000000000001',
             '81000000-0000-0000-0000-000000000002',
             '81000000-0000-0000-0000-000000000003', 1, now(),
             1000.00, 8.00, '{}'::jsonb, 'payout_v3', 'guard fixture',
             '81000000-0000-0000-0000-000000000004')
        """,
        "SELECT count(*) FROM campaign_payout_rule_revisions",
        id="0018-rule-revision",
    ),
    pytest.param(
        "0019_assignment_rule_bindings",
        "0018_payout_rule_revisions",
        """
        INSERT INTO assignment_rule_bindings
            (id, assignment_id, revision_id, hourly_rate_naira,
             daily_payable_hours_cap, eligibility_params, formula_version,
             premium_zone_ids, premium_zone_geometry_hash,
             stationary_policy_marker)
        VALUES
            ('82000000-0000-0000-0000-000000000001',
             '82000000-0000-0000-0000-000000000002',
             '82000000-0000-0000-0000-000000000003', 1000.00,
             8.00, '{}'::jsonb, 'payout_v3', '[]'::jsonb, 'fixture-hash',
             'ext-rm2-fail-closed')
        """,
        "SELECT count(*) FROM assignment_rule_bindings",
        id="0019-assignment-binding",
    ),
    pytest.param(
        "0020_payout_correction_orders",
        "0019_assignment_rule_bindings",
        """
        INSERT INTO payout_correction_orders
            (id, campaign_id, lagos_day, status, created_by_user_id, reason)
        VALUES
            ('83000000-0000-0000-0000-000000000001',
             '83000000-0000-0000-0000-000000000002', CURRENT_DATE, 'draft',
             '83000000-0000-0000-0000-000000000003', 'guard fixture')
        """,
        "SELECT count(*) FROM payout_correction_orders",
        id="0020-correction-order",
    ),
    pytest.param(
        "0020_payout_correction_orders",
        "0019_assignment_rule_bindings",
        """
        INSERT INTO earnings_ledger_entries
            (id, driver_profile_id, driver_user_id, campaign_id, entry_type,
             status, amount, currency, occurred_at, release_at)
        VALUES
            ('84000000-0000-0000-0000-000000000001',
             '84000000-0000-0000-0000-000000000002',
             '84000000-0000-0000-0000-000000000003',
             '84000000-0000-0000-0000-000000000004', 'adjustment', 'pending',
             1.00, 'NGN', now(), now())
        """,
        "SELECT count(*) FROM earnings_ledger_entries WHERE release_at IS NOT NULL",
        id="0020-release-date",
    ),
    pytest.param(
        "0021_frozen_payout_v3_terms",
        "0020_payout_correction_orders",
        """
        INSERT INTO assignment_rule_bindings
            (id, assignment_id, revision_id, hourly_rate_naira,
             daily_payable_hours_cap, eligibility_params, formula_version,
             premium_zone_ids, premium_zone_geometry_hash,
             stationary_policy_marker)
        VALUES
            ('85000000-0000-0000-0000-000000000001',
             '85000000-0000-0000-0000-000000000002',
             '85000000-0000-0000-0000-000000000003', 1000.00,
             8.00, '{}'::jsonb, 'payout_v3', '[]'::jsonb, 'fixture-hash',
             'ext-rm2-fail-closed')
        """,
        "SELECT count(*) FROM assignment_rule_bindings",
        id="0021-frozen-binding",
    ),
)


@pytest.mark.parametrize(
    ("revision", "predecessor", "seed_statement", "retention_query"),
    POPULATED_GUARD_CASES,
)
def test_populated_payout_authority_downgrade_fails_closed(
    monkeypatch,
    revision: str,
    predecessor: str,
    seed_statement: str,
    retention_query: str,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, revision, monkeypatch)
        asyncio.run(execute_seed(migration_url, seed_statement))

        with pytest.raises(DBAPIError, match="downgrade blocked"):
            downgrade_to(migration_url, predecessor, monkeypatch)

        assert asyncio.run(fetch_all(migration_url, retention_query)) == [(1,)]
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (revision,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))


def test_0018_empty_downgrade_and_reupgrade_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "0018_payout_rule_revisions", monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM campaign_payout_rule_revisions")
        ) == [(0,)]

        downgrade_to(migration_url, "0017_seal_review_hardening", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'campaign_payout_rule_revisions'",
            )
        ) == [(0,)]

        upgrade_to(migration_url, "0018_payout_rule_revisions", monkeypatch)
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM campaign_payout_rule_revisions")
        ) == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))
