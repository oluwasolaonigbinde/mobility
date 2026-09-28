"""Migration 0092: payout_v4 daily-rate shape on top of seeded payout_v3 history."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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

from app.db.base import Base

PREVIOUS = "0091_budget_urgent_threshold"
CURRENT = "0092_payout_v4_daily_rate"
TABLES = (
    "campaign_payout_rules",
    "campaign_payout_rule_revisions",
    "assignment_rule_bindings",
    "payout_calculations",
)

# Foreign keys are not what this migration changes; seed rows without their
# parents (session_replication_role = replica) exactly like the older guards.
V3_HISTORY = """
INSERT INTO campaign_payout_rules
    (id, campaign_id, created_by_user_id, formula_version, status, currency,
     hourly_rate_naira, daily_payable_hours_cap)
VALUES ('92000000-0000-0000-0000-000000000001', '92000000-0000-0000-0000-00000000000c',
        '92000000-0000-0000-0000-00000000000a', 'payout_v2', 'active', 'NGN', 1200, 8);
INSERT INTO campaign_payout_rule_revisions
    (id, campaign_id, payout_rule_id, revision_number, effective_from,
     hourly_rate_naira, premium_hourly_rate_naira, daily_payable_hours_cap, currency,
     eligibility_params, formula_version, reason, created_by_user_id)
VALUES ('92000000-0000-0000-0000-000000000002', '92000000-0000-0000-0000-00000000000c',
        '92000000-0000-0000-0000-000000000001', 1, now(), 1000, 2000, 8, 'NGN', '{}',
        'payout_v3', 'seeded v3', '92000000-0000-0000-0000-00000000000a');
INSERT INTO assignment_rule_bindings
    (id, assignment_id, revision_id, hourly_rate_naira, premium_hourly_rate_naira,
     daily_payable_hours_cap, currency, eligibility_params, formula_version,
     premium_zone_ids, premium_zone_geometry_hash, stationary_policy_marker)
VALUES ('92000000-0000-0000-0000-000000000003', '92000000-0000-0000-0000-00000000000b',
        '92000000-0000-0000-0000-000000000002', 1000, 2000, 8, 'NGN', '{}', 'payout_v3',
        '[]', 'seed-hash', 'stationary-rd-v1');
INSERT INTO payout_calculations
    (id, trip_session_id, trip_analytics_id, impression_estimate_id, payout_rule_id,
     assignment_id, campaign_id, driver_profile_id, vehicle_id, formula_version, status,
     currency, gross_payout, final_payout, eligible_seconds, payable_seconds,
     payable_seconds_by_day, excluded_seconds_by_reason, inputs_fingerprint, calculated_at)
VALUES ('92000000-0000-0000-0000-000000000004', '92000000-0000-0000-0000-000000000005',
        '92000000-0000-0000-0000-000000000006', '92000000-0000-0000-0000-000000000007',
        '92000000-0000-0000-0000-000000000001', '92000000-0000-0000-0000-00000000000b',
        '92000000-0000-0000-0000-00000000000c', '92000000-0000-0000-0000-000000000008',
        '92000000-0000-0000-0000-000000000009', 'payout_v3', 'calculated', 'NGN', 500, 500,
        1800, 1800, '{"2026-07-20": 1800}', '{}', 'seed-fingerprint', now());
"""

V4_REVISION = """
INSERT INTO campaign_payout_rule_revisions
    (id, campaign_id, payout_rule_id, revision_number, effective_from, currency,
     eligibility_params, formula_version, reason, created_by_user_id,
     hourly_rate_naira, daily_rate_naira, daily_target_miles, shortfall_strategy,
     deduction_per_mile_naira, minimum_miles, outside_area_weight)
VALUES (gen_random_uuid(), '92000000-0000-0000-0000-00000000000c',
        '92000000-0000-0000-0000-000000000001', {number}, now() + interval '{number} hours',
        'NGN', '{{}}', 'payout_v4', 'synthetic', '92000000-0000-0000-0000-00000000000a',
        {hourly}, {rate}, 70, '{strategy}', {deduction}, {minimum}, {weight})
"""


async def execute(url: str, statement: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            for part in statement.split(";"):
                if part.strip():
                    await connection.execute(text(part))
    finally:
        await engine.dispose()


def v4_revision(number: int, **overrides) -> str:
    values = {
        "number": number,
        "hourly": "NULL",
        "rate": "10000",
        "strategy": "per_mile_deduction",
        "deduction": "140",
        "minimum": "0",
        "weight": "0.5",
    }
    values.update(overrides)
    return V4_REVISION.format(**values)


@pytest.fixture
def migration_url(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        asyncio.run(execute(url, V3_HISTORY))
        yield url
    finally:
        asyncio.run(drop_database(url))


def test_0092_keeps_v3_history_enforces_v4_shape_and_blocks_lossy_downgrade(
    migration_url, monkeypatch
) -> None:
    upgrade_to(migration_url, CURRENT, monkeypatch)

    async def model_drift():
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                return await connection.run_sync(
                    lambda sync: compare_metadata(
                        MigrationContext.configure(sync, opts={"compare_type": True}),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    changes = asyncio.run(model_drift())
    assert [change for change in changes if any(t in repr(change) for t in TABLES)] == []
    # Seeded payout_v3 history is untouched and still satisfies the new checks.
    for table in TABLES:
        assert asyncio.run(fetch_all(migration_url, f"SELECT count(*) FROM {table}")) == [(1,)]
    assert asyncio.run(
        fetch_all(
            migration_url,
            "SELECT hourly_rate_naira, daily_rate_naira FROM assignment_rule_bindings",
        )
    ) == [(1000, None)]

    invalid = (
        # A daily-rate revision may not carry an hourly rate, ...
        v4_revision(2, hourly="1000"),
        # ... nor omit its deduction under per-mile, nor carry one when proportional.
        v4_revision(2, deduction="NULL"),
        # Every required daily-rate value must be present (NULL never passes).
        v4_revision(2, rate="NULL"),
        v4_revision(2, minimum="NULL"),
        v4_revision(2, weight="NULL"),
        v4_revision(2, strategy="NULL").replace("'NULL'", "NULL"),
        v4_revision(2, strategy="proportional"),
        v4_revision(2, weight="1.5"),
        v4_revision(2, minimum="71"),
        v4_revision(2, rate="0"),
        # An hourly (v3) revision may not carry daily-rate terms.
        "INSERT INTO campaign_payout_rule_revisions (id, campaign_id, payout_rule_id,"
        " revision_number, effective_from, hourly_rate_naira, currency, eligibility_params,"
        " formula_version, reason, created_by_user_id, daily_rate_naira) VALUES"
        " (gen_random_uuid(), '92000000-0000-0000-0000-00000000000c',"
        " '92000000-0000-0000-0000-000000000001', 2, now() + interval '2 hours', 1000, 'NGN',"
        " '{}', 'payout_v3', 'mixed', '92000000-0000-0000-0000-00000000000a', 10000)",
        # A payout_v4 rule row carries no rates at all.
        "INSERT INTO campaign_payout_rules (id, campaign_id, created_by_user_id,"
        " formula_version, status, currency, hourly_rate_naira) VALUES (gen_random_uuid(),"
        " '92000000-0000-0000-0000-00000000000d', '92000000-0000-0000-0000-00000000000a',"
        " 'payout_v4', 'active', 'NGN', 1200)",
    )
    for statement in invalid:
        with pytest.raises(IntegrityError):
            asyncio.run(execute(migration_url, statement))

    # With only v3 rows the migration round-trips without loss.
    downgrade_to(migration_url, PREVIOUS, monkeypatch)
    assert asyncio.run(
        fetch_all(migration_url, "SELECT count(*) FROM campaign_payout_rule_revisions")
    ) == [(1,)]
    upgrade_to(migration_url, CURRENT, monkeypatch)

    asyncio.run(
        execute(
            migration_url,
            "INSERT INTO campaign_payout_rules (id, campaign_id, created_by_user_id,"
            " formula_version, status, currency) VALUES (gen_random_uuid(),"
            " '92000000-0000-0000-0000-00000000000d', '92000000-0000-0000-0000-00000000000a',"
            " 'payout_v4', 'active', 'NGN')",
        )
    )
    asyncio.run(execute(migration_url, v4_revision(2)))
    asyncio.run(
        execute(
            migration_url,
            v4_revision(3, strategy="proportional", deduction="NULL", weight="1", minimum="70"),
        )
    )
    with pytest.raises(RuntimeError, match="0092 downgrade blocked"):
        downgrade_to(migration_url, PREVIOUS, monkeypatch)
