"""Fail-closed downgrade guards for governed historical authority."""

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


async def wait_for_pending_access_exclusive_lock(
    migration_url: str, table_name: str, *, timeout: float = 4.0
) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while loop.time() < deadline:
            async with engine.connect() as connection:
                waiting = await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_locks "
                        "WHERE relation = to_regclass(:table_name) "
                        "AND mode = 'AccessExclusiveLock' AND NOT granted"
                        ")"
                    ),
                    {"table_name": table_name},
                )
            if waiting:
                return
            await asyncio.sleep(0.01)
    finally:
        await engine.dispose()
    raise AssertionError(f"downgrade did not wait for {table_name} ACCESS EXCLUSIVE lock")


POPULATED_GUARD_CASES = (
    pytest.param(
        "0010_payouts_and_earnings",
        "0009_impression_estimation",
        """
        INSERT INTO campaign_payout_rules
            (id, campaign_id, created_by_user_id, status, currency)
        VALUES
            ('80000000-0000-0000-0000-000000000001',
             '80000000-0000-0000-0000-000000000002',
             '80000000-0000-0000-0000-000000000003', 'active', 'NGN')
        """,
        "SELECT count(*) FROM campaign_payout_rules",
        id="0010-payout-rule",
    ),
    pytest.param(
        "0010_payouts_and_earnings",
        "0009_impression_estimation",
        """
        INSERT INTO payout_calculations
            (id, trip_session_id, trip_analytics_id, impression_estimate_id,
             payout_rule_id, assignment_id, campaign_id, driver_profile_id,
             vehicle_id, status, currency, quality_multiplier,
             fraud_multiplier, calculated_at)
        VALUES
            ('80100000-0000-0000-0000-000000000001',
             '80100000-0000-0000-0000-000000000002',
             '80100000-0000-0000-0000-000000000003',
             '80100000-0000-0000-0000-000000000004',
             '80100000-0000-0000-0000-000000000005',
             '80100000-0000-0000-0000-000000000006',
             '80100000-0000-0000-0000-000000000007',
             '80100000-0000-0000-0000-000000000008',
             '80100000-0000-0000-0000-000000000009',
             'calculated', 'NGN', 1.0, 1.0, now())
        """,
        "SELECT count(*) FROM payout_calculations",
        id="0010-payout-calculation",
    ),
    pytest.param(
        "0010_payouts_and_earnings",
        "0009_impression_estimation",
        """
        INSERT INTO earnings_ledger_entries
            (id, driver_profile_id, driver_user_id, campaign_id, entry_type,
             status, amount, currency, occurred_at)
        VALUES
            ('80200000-0000-0000-0000-000000000001',
             '80200000-0000-0000-0000-000000000002',
             '80200000-0000-0000-0000-000000000003',
             '80200000-0000-0000-0000-000000000004', 'adjustment', 'pending',
             1.00, 'NGN', now())
        """,
        "SELECT count(*) FROM earnings_ledger_entries",
        id="0010-ledger-entry",
    ),
    pytest.param(
        "0014_location_pings_partitioning",
        "0013_payout_v2_hourly_caps",
        """
        INSERT INTO data_purge_audit
            (event, retention_months, job_run_id)
        VALUES
            ('batches_purged', 1, '0014-guard-fixture')
        """,
        "SELECT count(*) FROM data_purge_audit",
        id="0014-purge-audit",
    ),
    pytest.param(
        "0016_trip_seal_protocol",
        "0015_payout_day_allocation",
        """
        INSERT INTO quarantined_ping_batches
            (id, trip_session_id, idempotency_key, payload_hash, payload,
             ping_count, received_at, status)
        VALUES
            ('80600000-0000-0000-0000-000000000001',
             '80600000-0000-0000-0000-000000000002', 'guard-fixture',
             'guard-hash', '{"pings": []}'::jsonb, 0, now(), 'quarantined')
        """,
        "SELECT count(*) FROM quarantined_ping_batches",
        id="0016-quarantined-batch",
    ),
    pytest.param(
        "0016_trip_seal_protocol",
        "0015_payout_day_allocation",
        """
        INSERT INTO trip_sessions
            (id, assignment_id, campaign_id, driver_profile_id, vehicle_id,
             started_by_user_id, status, started_at, ended_at, sealed_at,
             seal_reason)
        VALUES
            ('80700000-0000-0000-0000-000000000001',
             '80700000-0000-0000-0000-000000000002',
             '80700000-0000-0000-0000-000000000003',
             '80700000-0000-0000-0000-000000000004',
             '80700000-0000-0000-0000-000000000005',
             '80700000-0000-0000-0000-000000000006', 'sealed', now(), now(),
             now(), 'client_complete')
        """,
        "SELECT count(*) FROM trip_sessions WHERE status = 'sealed'",
        id="0016-sealed-trip",
    ),
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
def test_populated_governed_authority_downgrade_fails_closed(
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


@pytest.mark.parametrize(
    ("revision", "predecessor", "removed_shape_query", "restored_empty_query"),
    (
        pytest.param(
            "0010_payouts_and_earnings",
            "0009_impression_estimation",
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('campaign_payout_rules', 'payout_calculations', "
            "'earnings_ledger_entries')",
            "SELECT count(*) FROM campaign_payout_rules",
            id="0010",
        ),
        pytest.param(
            "0014_location_pings_partitioning",
            "0013_payout_v2_hourly_caps",
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'data_purge_audit'",
            "SELECT count(*) FROM data_purge_audit",
            id="0014",
        ),
        pytest.param(
            "0016_trip_seal_protocol",
            "0015_payout_day_allocation",
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'quarantined_ping_batches'",
            "SELECT count(*) FROM quarantined_ping_batches",
            id="0016",
        ),
    ),
)
def test_historical_empty_downgrade_and_reupgrade_cycle(
    monkeypatch,
    revision: str,
    predecessor: str,
    removed_shape_query: str,
    restored_empty_query: str,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, revision, monkeypatch)
        assert asyncio.run(fetch_all(migration_url, restored_empty_query)) == [(0,)]

        downgrade_to(migration_url, predecessor, monkeypatch)
        assert asyncio.run(fetch_all(migration_url, removed_shape_query)) == [(0,)]

        upgrade_to(migration_url, revision, monkeypatch)
        assert asyncio.run(fetch_all(migration_url, restored_empty_query)) == [(0,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_0014_concurrent_insert_is_serialized_before_downgrade_guard(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def exercise_race() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                await connection.execute(
                    text(
                        "INSERT INTO data_purge_audit "
                        "(event, retention_months, job_run_id) "
                        "VALUES ('batches_purged', 1, '0014-concurrent-guard')"
                    )
                )

                loop = asyncio.get_running_loop()
                downgrade = loop.run_in_executor(
                    None,
                    downgrade_to,
                    migration_url,
                    "0013_payout_v2_hourly_caps",
                    monkeypatch,
                )
                await wait_for_pending_access_exclusive_lock(migration_url, "data_purge_audit")
                await transaction.commit()

                with pytest.raises(DBAPIError, match="0014 downgrade blocked"):
                    await asyncio.wait_for(downgrade, timeout=5.0)
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0014_location_pings_partitioning", monkeypatch)
        asyncio.run(exercise_race())

        assert asyncio.run(fetch_all(migration_url, "SELECT count(*) FROM data_purge_audit")) == [
            (1,)
        ]
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            ("0014_location_pings_partitioning",)
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
