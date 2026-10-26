import asyncio
from uuid import uuid4

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

PREVIOUS_REVISION = "0106_development_baseline"
REVISION = "0106_development_baseline"

RESTRICTED_FOREIGN_KEYS = {
    "campaign_payout_rule_revisions_campaign_id_fkey",
    "campaign_payout_rule_revisions_payout_rule_id_fkey",
    "assignment_rule_bindings_assignment_id_fkey",
    "assignment_rule_bindings_revision_id_fkey",
    "payout_calculations_trip_session_id_fkey",
    "payout_calculations_trip_analytics_id_fkey",
    "payout_calculations_impression_estimate_id_fkey",
    "payout_calculations_assignment_id_fkey",
    "payout_calculations_campaign_id_fkey",
    "payout_calculations_driver_profile_id_fkey",
    "payout_calculations_vehicle_id_fkey",
    "earnings_ledger_entries_driver_profile_id_fkey",
    "earnings_ledger_entries_campaign_id_fkey",
    "earnings_ledger_entries_trip_session_id_fkey",
    "earnings_ledger_entries_vehicle_id_fkey",
}


async def execute(
    database_url: str,
    statements: str | tuple[str, ...],
    params: dict | None = None,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            for statement in (statements,) if isinstance(statements, str) else statements:
                await connection.execute(text(statement), params or {})
    finally:
        await engine.dispose()


async def fetch_all(database_url: str, statement: str) -> list:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(text(statement))).all())
    finally:
        await engine.dispose()


async def rejected(
    database_url: str,
    statement: str | tuple[str, ...],
    params: dict | None = None,
) -> None:
    with pytest.raises(DBAPIError):
        await execute(database_url, statement, params)


async def seed_immutable_authority(database_url: str) -> dict[str, str]:
    ids = {
        key: str(uuid4())
        for key in (
            "revision",
            "rule",
            "campaign",
            "user",
            "binding",
            "assignment",
            "trip",
            "analytics",
            "estimate",
            "driver",
            "vehicle",
            "calculation",
            "ledger_pending",
            "ledger_pending_forbidden",
            "ledger_available",
            "ledger_paid",
            "ledger_reversed",
            "ledger_voided",
        )
    }
    await execute(
        database_url,
        (
            "SET LOCAL session_replication_role = replica",
            """
            INSERT INTO campaign_payout_rules (
              id, campaign_id, created_by_user_id, formula_version, status, currency, metadata
            ) VALUES (:rule, :campaign, :user, 'payout_v4', 'active', 'NGN', '{}'::jsonb)
            """,
            """
            INSERT INTO campaign_assignments (
              id, campaign_id, driver_profile_id, vehicle_id,
              assigned_by_user_id, status, offered_at, accepted_at, metadata
            ) VALUES (
              :assignment, :campaign, :driver, :vehicle, :user, 'accepted',
              now(), now(), '{}'::jsonb
            )
            """,
            """
            INSERT INTO campaign_payout_rule_revisions (
              id, campaign_id, payout_rule_id, revision_number, effective_from,
              daily_rate_naira, daily_target_miles, minimum_miles, outside_area_weight,
              shortfall_strategy, currency, eligibility_params,
              formula_version, reason, created_by_user_id
            ) VALUES (
              :revision, :campaign, :rule, 1, now(), 1000.00, 10.00, 0, 0,
              'proportional', 'NGN', '{}'::jsonb, 'payout_v4', 'R18 test', :user
            )
            """,
            """
            INSERT INTO assignment_rule_bindings (
              id, assignment_id, revision_id, daily_rate_naira, daily_target_miles,
              minimum_miles, outside_area_weight, shortfall_strategy, currency,
              eligibility_params, formula_version, premium_zone_geometry_hash
            ) VALUES (
              :binding, :assignment, :revision, 1000.00, 10.00, 0, 0, 'proportional',
              'NGN', '{}'::jsonb, 'payout_v4', repeat('b', 64)
            )
            """,
            """
            INSERT INTO payout_calculations (
              id, trip_session_id, trip_analytics_id, impression_estimate_id,
              payout_rule_id, assignment_id, campaign_id, driver_profile_id,
              vehicle_id, formula_version, status, currency, gross_payout,
              final_payout, calculated_at, metadata, eligible_seconds,
              excluded_seconds_by_reason, inputs_fingerprint, distance_m_by_day, amount_by_day
            ) VALUES (
              :calculation, :trip, :analytics, :estimate, :rule, :assignment,
              :campaign, :driver, :vehicle, 'payout_v4', 'calculated', 'NGN',
              10.00, 10.00, now(), '{}'::jsonb, 3600,
              '{}'::jsonb, repeat('a', 64), '{}'::jsonb, '{}'::jsonb
            )
            """,
            """
            INSERT INTO earnings_ledger_entries (
              id, payout_calculation_id, driver_profile_id, driver_user_id,
              campaign_id, trip_session_id, vehicle_id, entry_type, status,
              amount, currency, occurred_at, metadata
            ) VALUES (
              :ledger_pending, :calculation, :driver, :user, :campaign, :trip,
              :vehicle, 'trip_payout', 'pending', 10.00, 'NGN', now(),
              '{}'::jsonb
            )
            """,
            """
            INSERT INTO earnings_ledger_entries (
              id, driver_profile_id, driver_user_id, campaign_id, entry_type,
              status, amount, currency, occurred_at, metadata
            ) VALUES
              (:ledger_available, :driver, :user, :campaign, 'adjustment',
               'available', 1.00, 'NGN', now(), '{}'::jsonb),
              (:ledger_pending_forbidden, :driver, :user, :campaign, 'adjustment',
               'pending', 1.00, 'NGN', now(), '{}'::jsonb),
              (:ledger_paid, :driver, :user, :campaign, 'adjustment',
               'paid', 1.00, 'NGN', now(), '{}'::jsonb),
              (:ledger_reversed, :driver, :user, :campaign, 'adjustment',
               'reversed', 1.00, 'NGN', now(), '{}'::jsonb),
              (:ledger_voided, :driver, :user, :campaign, 'adjustment',
               'voided', 1.00, 'NGN', now(), '{}'::jsonb)
            """,
        ),
        ids,
    )
    return ids


def test_schema_immutable_money_authority_and_ledger_transitions(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, REVISION, monkeypatch)
        ids = asyncio.run(seed_immutable_authority(migration_url))

        columns = asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT table_name, column_name, is_nullable
                FROM information_schema.columns
                WHERE (table_name, column_name) IN (
                  ('campaign_payout_rule_revisions', 'currency'),
                  ('assignment_rule_bindings', 'currency')
                )
                ORDER BY table_name
                """,
            )
        )
        assert columns == [
            ("assignment_rule_bindings", "currency", "NO"),
            ("campaign_payout_rule_revisions", "currency", "NO"),
        ]
        always_triggers = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname LIKE 'trg_%' AND tgenabled = 'A' "
                "AND tgname IN ("
                "'trg_campaign_payout_rule_revisions_immutable',"
                "'trg_campaign_payout_rule_revisions_no_truncate',"
                "'trg_assignment_rule_bindings_immutable',"
                "'trg_assignment_rule_bindings_no_truncate',"
                "'trg_payout_calculations_immutable',"
                "'trg_payout_calculations_no_truncate',"
                "'trg_earnings_ledger_entries_guard',"
                "'trg_earnings_ledger_entries_no_truncate')",
            )
        )
        assert always_triggers == [(8,)]
        foreign_keys = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT conname, confdeltype::text FROM pg_constraint "
                "WHERE conname = ANY(ARRAY["
                + ",".join(f"'{name}'" for name in sorted(RESTRICTED_FOREIGN_KEYS))
                + "]::text[])",
            )
        )
        assert {name for name, _ in foreign_keys} == RESTRICTED_FOREIGN_KEYS
        assert {action for _, action in foreign_keys} == {"r"}
        asyncio.run(
            rejected(
                migration_url,
                "UPDATE campaign_payout_rules SET currency = 'ÉÉÉ' WHERE id = :id",
                {"id": ids["rule"]},
            )
        )
        asyncio.run(
            rejected(
                migration_url,
                (
                    "SET LOCAL session_replication_role = replica",
                    """
                    INSERT INTO earnings_ledger_entries (
                      driver_profile_id, driver_user_id, campaign_id, entry_type,
                      status, amount, currency, occurred_at, metadata
                    ) VALUES (
                      :driver, :user, :campaign, 'adjustment', 'pending', 1.00,
                      'ÉÉÉ', now(), '{}'::jsonb
                    )
                    """,
                ),
                ids,
            )
        )
        for table, id_key in (
            ("campaign_payout_rules", "rule"),
            ("campaign_assignments", "assignment"),
        ):
            asyncio.run(
                rejected(
                    migration_url,
                    f"DELETE FROM {table} WHERE id = :id",
                    {"id": ids[id_key]},
                )
            )

        immutable_rows = (
            ("campaign_payout_rule_revisions", "revision", "reason"),
            ("assignment_rule_bindings", "binding", "formula_version"),
            ("payout_calculations", "calculation", "currency"),
        )
        for table, id_key, column in immutable_rows:
            asyncio.run(
                rejected(
                    migration_url,
                    (
                        "SET LOCAL session_replication_role = replica",
                        f"UPDATE {table} SET {column} = {column} WHERE id = :id",
                    ),
                    {"id": ids[id_key]},
                )
            )
            asyncio.run(
                rejected(
                    migration_url,
                    (
                        "SET LOCAL session_replication_role = replica",
                        f"DELETE FROM {table} WHERE id = :id",
                    ),
                    {"id": ids[id_key]},
                )
            )
            asyncio.run(
                rejected(
                    migration_url,
                    (
                        "SET LOCAL session_replication_role = replica",
                        f"TRUNCATE {table}",
                    ),
                )
            )

        asyncio.run(
            rejected(
                migration_url,
                (
                    "SET LOCAL session_replication_role = replica",
                    "UPDATE earnings_ledger_entries SET amount = amount + 1 WHERE id = :id",
                ),
                {"id": ids["ledger_pending"]},
            )
        )
        asyncio.run(
            rejected(
                migration_url,
                "UPDATE earnings_ledger_entries SET release_at = now() WHERE id = :id",
                {"id": ids["ledger_pending"]},
            )
        )
        asyncio.run(
            execute(
                migration_url,
                "UPDATE earnings_ledger_entries SET status = 'available' WHERE id = :id",
                {"id": ids["ledger_pending"]},
            )
        )
        asyncio.run(
            execute(
                migration_url,
                "UPDATE earnings_ledger_entries SET status = 'paid' WHERE id = :id",
                {"id": ids["ledger_pending"]},
            )
        )
        asyncio.run(
            execute(
                migration_url,
                "UPDATE earnings_ledger_entries SET status = 'reversed' WHERE id = :id",
                {"id": ids["ledger_available"]},
            )
        )
        asyncio.run(
            execute(
                migration_url,
                "UPDATE earnings_ledger_entries SET status = status WHERE id = :id",
                {"id": ids["ledger_paid"]},
            )
        )
        statuses = ("pending", "available", "paid", "reversed", "voided")
        allowed_transitions = {(status, status) for status in statuses} | {
            ("pending", "available"),
            ("available", "paid"),
            ("available", "reversed"),
        }
        for old_status in statuses:
            for new_status in statuses:
                entry_id = str(uuid4())
                asyncio.run(
                    execute(
                        migration_url,
                        (
                            "SET LOCAL session_replication_role = replica",
                            """
                            INSERT INTO earnings_ledger_entries (
                              id, driver_profile_id, driver_user_id, campaign_id,
                              entry_type, status, amount, currency, occurred_at, metadata
                            ) VALUES (
                              :id, :driver, :user, :campaign, 'adjustment',
                              :old_status, 1.00, 'NGN', now(), '{}'::jsonb
                            )
                            """,
                        ),
                        {
                            **ids,
                            "id": entry_id,
                            "old_status": old_status,
                        },
                    )
                )
                transition = (old_status, new_status)
                params = {"id": entry_id, "status": new_status}
                statement = "UPDATE earnings_ledger_entries SET status = :status WHERE id = :id"
                if transition in allowed_transitions:
                    asyncio.run(execute(migration_url, statement, params))
                else:
                    asyncio.run(rejected(migration_url, statement, params))
        asyncio.run(
            rejected(
                migration_url,
                "DELETE FROM earnings_ledger_entries WHERE id = :id",
                {"id": ids["ledger_paid"]},
            )
        )
        asyncio.run(rejected(migration_url, "TRUNCATE earnings_ledger_entries"))

        asyncio.run(
            execute(
                migration_url,
                (
                    "SET LOCAL session_replication_role = replica",
                    """
                    INSERT INTO earnings_ledger_entries (
                      driver_profile_id, driver_user_id, campaign_id, entry_type,
                      status, amount, currency, occurred_at, metadata
                    ) VALUES (
                      :driver, :user, :campaign, 'adjustment', 'pending', 2.00,
                      'NGN', now(), '{"correction": true}'::jsonb
                    )
                    """,
                ),
                ids,
            )
        )

        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))
