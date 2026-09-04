import asyncio
import json
from uuid import uuid4

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
    upgrade_to,
)

PREVIOUS_REVISION = "0080_trip_evidence_partial_disposition"
REVISION = "0081_payout_money_authority"

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


async def seed_revision_chain(
    database_url: str,
    *,
    rule_currency: str = "NGN",
    offer_currency: str | None = "NGN",
    null_payout_currency: bool = False,
    offer_terms_sql_null: bool = False,
    calculation_currency: str | None = None,
    ledger_currency: str | None = None,
    include_rule: bool = True,
    include_revision: bool = True,
    include_binding: bool = True,
) -> dict[str, str]:
    ids = {
        key: str(uuid4())
        for key in (
            "rule",
            "revision",
            "campaign",
            "organization",
            "user",
            "assignment",
            "driver",
            "vehicle",
            "trip",
            "analytics",
            "estimate",
            "calculation",
            "ledger",
        )
    }
    statements = ["SET LOCAL session_replication_role = replica"]
    statements.append(
        """
        INSERT INTO campaigns (
          id, organization_id, created_by_user_id, name, status, currency,
          metadata
        ) VALUES (
          :campaign, :organization, :user, 'R18 migration test', 'draft',
          'NGN', '{}'::jsonb
        )
        """
    )
    if include_rule:
        statements.append(
            """
            INSERT INTO campaign_payout_rules (
              id, campaign_id, created_by_user_id, formula_version, status,
              currency, hourly_rate_naira, daily_payable_hours_cap,
              eligibility_params, metadata
            ) VALUES (
              :rule, :campaign, :user, 'payout_v2', 'active', :rule_currency,
              1000.00, 8.00, '{}'::jsonb, '{}'::jsonb
            )
            """
        )
    if include_revision:
        statements.append(
            """
            INSERT INTO campaign_payout_rule_revisions (
              id, campaign_id, payout_rule_id, revision_number, effective_from,
              hourly_rate_naira, premium_hourly_rate_naira,
              daily_payable_hours_cap, eligibility_params, formula_version,
              reason, created_by_user_id
            ) VALUES (
              :revision, :campaign, :rule, 1, now(), 1000.00, 1500.00,
              8.00, '{}'::jsonb, 'payout_v3', 'R18 migration test', :user
            )
            """
        )
    if include_binding:
        if offer_terms_sql_null:
            offer_terms = None
        else:
            offer_terms = {
                **({"currency": offer_currency} if offer_currency is not None else {}),
                "payout": ({"currency": None} if null_payout_currency else {}),
            }
        statements.extend(
            (
                """
                INSERT INTO campaign_assignments (
                  id, campaign_id, driver_profile_id, vehicle_id,
                  assigned_by_user_id, status, offered_at, metadata,
                  offer_terms, offer_terms_sha256
                ) VALUES (
                  :assignment, :campaign, :driver, :vehicle, :user,
                  'offered', now(), '{}'::jsonb, CAST(:offer_terms AS json),
                  :offer_terms_sha256
                )
                """,
                """
                INSERT INTO assignment_rule_bindings (
                  assignment_id, revision_id, hourly_rate_naira,
                  premium_hourly_rate_naira, daily_payable_hours_cap,
                  eligibility_params, formula_version,
                  premium_zone_geometry_hash
                ) VALUES (
                  :assignment, :revision, 1000.00, 1500.00, 8.00,
                  '{}'::jsonb, 'payout_v3', repeat('b', 64)
                )
                """,
            )
        )
        ids["offer_terms"] = json.dumps(offer_terms) if offer_terms is not None else None
        ids["offer_terms_sha256"] = "a" * 64 if offer_terms is not None else None
    if calculation_currency is not None:
        statements.append(
            """
            INSERT INTO payout_calculations (
              id, trip_session_id, trip_analytics_id, impression_estimate_id,
              payout_rule_id, assignment_id, campaign_id, driver_profile_id,
              vehicle_id, formula_version, status, currency, gross_payout,
              final_payout, calculated_at, metadata
            ) VALUES (
              :calculation, :trip, :analytics, :estimate, :rule, :assignment,
              :campaign, :driver, :vehicle, 'payout_v3', 'calculated',
              :calculation_currency, 10.00, 10.00, now(), '{}'::jsonb
            )
            """
        )
        ids["calculation_currency"] = calculation_currency
    if ledger_currency is not None:
        statements.append(
            """
            INSERT INTO earnings_ledger_entries (
              id, payout_calculation_id, driver_profile_id, driver_user_id,
              campaign_id, trip_session_id, vehicle_id, entry_type, status,
              amount, currency, occurred_at, metadata
            ) VALUES (
              :ledger, :calculation, :driver, :user, :campaign, :trip, :vehicle,
              'trip_payout', 'pending', 10.00, :ledger_currency, now(), '{}'::jsonb
            )
            """
        )
        ids["ledger_currency"] = ledger_currency
    ids["rule_currency"] = rule_currency
    await execute(database_url, tuple(statements), ids)
    return ids


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
              id, campaign_id, created_by_user_id, formula_version, status,
              currency, hourly_rate_naira, daily_payable_hours_cap,
              eligibility_params, metadata
            ) VALUES (
              :rule, :campaign, :user, 'payout_v2', 'active', 'NGN', 1000.00,
              8.00, '{}'::jsonb, '{}'::jsonb
            )
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
              hourly_rate_naira, premium_hourly_rate_naira,
              daily_payable_hours_cap, currency, eligibility_params,
              formula_version, reason, created_by_user_id
            ) VALUES (
              :revision, :campaign, :rule, 1, now(), 1000.00, 1500.00,
              8.00, 'NGN', '{}'::jsonb, 'payout_v3', 'R18 test', :user
            )
            """,
            """
            INSERT INTO assignment_rule_bindings (
              id, assignment_id, revision_id, hourly_rate_naira,
              premium_hourly_rate_naira, daily_payable_hours_cap, currency,
              eligibility_params, formula_version, premium_zone_geometry_hash
            ) VALUES (
              :binding, :assignment, :revision, 1000.00, 1500.00, 8.00,
              'NGN', '{}'::jsonb, 'payout_v3', repeat('b', 64)
            )
            """,
            """
            INSERT INTO payout_calculations (
              id, trip_session_id, trip_analytics_id, impression_estimate_id,
              payout_rule_id, assignment_id, campaign_id, driver_profile_id,
              vehicle_id, formula_version, status, currency, gross_payout,
              final_payout, calculated_at, metadata
            ) VALUES (
              :calculation, :trip, :analytics, :estimate, :rule, :assignment,
              :campaign, :driver, :vehicle, 'payout_v1', 'calculated', 'NGN',
              10.00, 10.00, now(), '{}'::jsonb
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


def test_currency_backfill_and_refusal_cases(monkeypatch) -> None:
    source_url = configured_postgres_url()

    valid_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(valid_url, PREVIOUS_REVISION, monkeypatch)
        ids = asyncio.run(seed_revision_chain(valid_url))
        upgrade_to(valid_url, REVISION, monkeypatch)
        rows = asyncio.run(
            fetch_all(
                valid_url,
                "SELECT revision.currency, binding.currency "
                "FROM campaign_payout_rule_revisions revision "
                "JOIN assignment_rule_bindings binding "
                "ON binding.revision_id = revision.id",
            )
        )
        assert rows == [("NGN", "NGN")]
        assert ids["rule_currency"] == "NGN"
    finally:
        asyncio.run(drop_database(valid_url))

    cases = (
        {"include_rule": False, "include_binding": False},
        {"include_revision": False},
        {"rule_currency": "usd", "include_binding": False},
        {"offer_currency": "USD"},
        {"null_payout_currency": True},
        {"offer_terms_sql_null": True},
        {"calculation_currency": "USD"},
        {"calculation_currency": "NGN", "ledger_currency": "USD"},
    )
    for case in cases:
        migration_url = asyncio.run(create_database_from_url(source_url))
        try:
            upgrade_to(migration_url, PREVIOUS_REVISION, monkeypatch)
            asyncio.run(seed_revision_chain(migration_url, **case))
            with pytest.raises(DBAPIError, match="0081 upgrade blocked"):
                upgrade_to(migration_url, REVISION, monkeypatch)
            version_rows = asyncio.run(
                fetch_all(migration_url, "SELECT version_num FROM alembic_version")
            )
            assert version_rows == [(PREVIOUS_REVISION,)]
        finally:
            asyncio.run(drop_database(migration_url))


def test_upgrade_locks_currency_sources_before_validation(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, PREVIOUS_REVISION, monkeypatch)
        ids = asyncio.run(seed_revision_chain(migration_url))

        async def race_writer_against_upgrade() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            migration_task = None
            try:
                async with engine.begin() as connection:
                    await connection.execute(text("SET LOCAL session_replication_role = replica"))
                    await connection.execute(
                        text(
                            "UPDATE campaign_assignments "
                            "SET offer_terms = '{\"currency\":\"USD\",\"payout\":{}}'::jsonb "
                            "WHERE id = :assignment_id"
                        ),
                        {"assignment_id": ids["assignment"]},
                    )
                    migration_task = asyncio.create_task(
                        asyncio.to_thread(upgrade_to, migration_url, REVISION, monkeypatch)
                    )
                    waiting_on_source_lock = False
                    for _ in range(100):
                        waiting_on_source_lock = bool(
                            await connection.scalar(
                                text(
                                    "SELECT EXISTS ("
                                    "SELECT 1 FROM pg_locks lock "
                                    "JOIN pg_class relation ON relation.oid = lock.relation "
                                    "WHERE relation.relname = 'campaign_assignments' "
                                    "AND lock.mode = 'ShareRowExclusiveLock' "
                                    "AND NOT lock.granted "
                                    "AND lock.pid <> pg_backend_pid()"
                                    ")"
                                )
                            )
                        )
                        if waiting_on_source_lock or migration_task.done():
                            break
                        await asyncio.sleep(0.05)
                assert migration_task is not None
                with pytest.raises(DBAPIError, match="0081 upgrade blocked"):
                    await migration_task
                assert waiting_on_source_lock
            finally:
                await engine.dispose()

        asyncio.run(race_writer_against_upgrade())
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (PREVIOUS_REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))


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
                statement = (
                    "UPDATE earnings_ledger_entries SET status = :status WHERE id = :id"
                )
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

        with pytest.raises(RuntimeError, match="0081 downgrade blocked"):
            downgrade_to(migration_url, PREVIOUS_REVISION, monkeypatch)
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))


def test_empty_downgrade_and_reupgrade(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, REVISION, monkeypatch)
        downgrade_to(migration_url, PREVIOUS_REVISION, monkeypatch)
        upgrade_to(migration_url, REVISION, monkeypatch)
        assert asyncio.run(fetch_all(migration_url, "SELECT version_num FROM alembic_version")) == [
            (REVISION,)
        ]
    finally:
        asyncio.run(drop_database(migration_url))
