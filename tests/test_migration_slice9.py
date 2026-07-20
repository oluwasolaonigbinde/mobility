import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import get_settings

SLICE9_REVISION = "0010_payouts_and_earnings"
SLICE8_REVISION = "0009_impression_estimation"
SLICE9_TABLES = {
    "campaign_payout_rules",
    "payout_calculations",
    "earnings_ledger_entries",
}


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_slice9_migration_{uuid4().hex}"
    maintenance_url = source_url.set(database="postgres")
    engine = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()
    return source_url.set(database=database_name).render_as_string(hide_password=False)


async def drop_database(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database
    if database_name is None:
        return
    maintenance_url = url.set(database="postgres")
    engine = create_async_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


def test_slice9_migration_contains_only_payout_and_ledger_tables() -> None:
    migration = Path("alembic/versions/0010_payouts_and_earnings.py").read_text()

    assert f'down_revision: str | None = "{SLICE8_REVISION}"' in migration
    assert migration.count("op.create_table(") == 3
    for table_name in SLICE9_TABLES:
        assert f'"{table_name}"' in migration
    for required in [
        "ck_campaign_payout_rules_status",
        "ck_campaign_payout_rules_max_gte_min",
        "uq_campaign_payout_rules_active_campaign",
        "postgresql_where=sa.text(\"status = 'active'\")",
        "ck_payout_calculations_status",
        "uq_payout_calculations_trip_formula_rule",
        "ix_payout_calculations_campaign_calculated_at",
        "ck_earnings_ledger_entries_entry_type",
        "ck_earnings_ledger_entries_status",
        "uq_earnings_ledger_entries_payout_calculation_id",
        "payout_calculation_id IS NOT NULL",
        "'payout_v1'",
        "'{}'::jsonb",
        "gen_random_uuid()",
    ]:
        assert required in migration
    for forbidden_table in [
        "campaign_daily_metrics",
        "advertiser_reports",
        "heatmaps",
        "heatmap_cache",
        "billing",
        "invoices",
        "settlements",
        "withdrawals",
        "payments",
        "audiences",
        "retargeting",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration


def test_slice9_migration_upgrades_postgres_and_creates_expected_schema(monkeypatch) -> None:
    source_url = configured_postgres_url()
    try:
        migration_url = asyncio.run(create_database_from_url(source_url))
    except Exception as exc:  # pragma: no cover - exercised only without local DB privilege
        pytest.fail(f"Could not create temporary Postgres migration database: {exc}")

    try:
        monkeypatch.setenv("DATABASE_URL", migration_url)
        get_settings.cache_clear()
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, SLICE8_REVISION)

        async def public_base_tables() -> set[str]:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    return set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT table_name
                                    FROM information_schema.tables
                                    WHERE table_schema = 'public'
                                      AND table_type = 'BASE TABLE'
                                    """
                                )
                            )
                        ).scalars()
                    )
            finally:
                await engine.dispose()

        base_tables = asyncio.run(public_base_tables())
        command.upgrade(alembic_config, SLICE9_REVISION)

        async def inspect_schema() -> dict[str, object]:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    all_tables = set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT table_name
                                    FROM information_schema.tables
                                    WHERE table_schema = 'public'
                                      AND table_type = 'BASE TABLE'
                                    """
                                )
                            )
                        ).scalars()
                    )
                    version = await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                    constraints = set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT constraint_name
                                    FROM information_schema.table_constraints
                                    WHERE table_schema = 'public'
                                      AND table_name IN (
                                        'campaign_payout_rules',
                                        'payout_calculations',
                                        'earnings_ledger_entries'
                                      )
                                    """
                                )
                            )
                        ).scalars()
                    )
                    indexes = {
                        row.indexname: row.indexdef
                        for row in (
                            await connection.execute(
                                text(
                                    """
                                    SELECT indexname, indexdef
                                    FROM pg_indexes
                                    WHERE schemaname = 'public'
                                      AND tablename IN (
                                        'campaign_payout_rules',
                                        'payout_calculations',
                                        'earnings_ledger_entries'
                                      )
                                    """
                                )
                            )
                        )
                    }
                    columns = {
                        (row["table_name"], row["column_name"]): dict(row)
                        for row in (
                            await connection.execute(
                                text(
                                    """
                                    SELECT
                                      table_name,
                                      column_name,
                                      is_nullable,
                                      column_default,
                                      data_type,
                                      udt_name
                                    FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                      AND table_name IN (
                                        'campaign_payout_rules',
                                        'payout_calculations',
                                        'earnings_ledger_entries'
                                      )
                                    """
                                )
                            )
                        ).mappings()
                    }
                    foreign_keys = [
                        dict(row)
                        for row in (
                            await connection.execute(
                                text(
                                    """
                                    SELECT
                                      con.conname,
                                      rel.relname AS table_name,
                                      foreign_rel.relname AS foreign_table_name,
                                      pg_get_constraintdef(con.oid) AS definition
                                    FROM pg_constraint con
                                    JOIN pg_class rel ON rel.oid = con.conrelid
                                    JOIN pg_class foreign_rel ON foreign_rel.oid = con.confrelid
                                    WHERE con.contype = 'f'
                                      AND con.conrelid IN (
                                        'public.campaign_payout_rules'::regclass,
                                        'public.payout_calculations'::regclass,
                                        'public.earnings_ledger_entries'::regclass
                                      )
                                    """
                                )
                            )
                        ).mappings()
                    ]
                    forbidden = set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT table_name
                                    FROM information_schema.tables
                                    WHERE table_schema = 'public'
                                      AND table_name IN (
                                        'campaign_daily_metrics',
                                        'advertiser_reports',
                                        'heatmaps',
                                        'heatmap_cache',
                                        'billing',
                                        'invoices',
                                        'settlements',
                                        'withdrawals',
                                        'payments',
                                        'audiences',
                                        'retargeting',
                                        'seed_trips'
                                      )
                                    """
                                )
                            )
                        ).scalars()
                    )
                    return {
                        "version": version,
                        "new_tables": all_tables - base_tables,
                        "constraints": constraints,
                        "indexes": indexes,
                        "columns": columns,
                        "foreign_keys": foreign_keys,
                        "forbidden": forbidden,
                    }
            finally:
                await engine.dispose()

        schema = asyncio.run(inspect_schema())
        indexes = schema["indexes"]
        columns = schema["columns"]
        foreign_keys = schema["foreign_keys"]

        def column(table_name: str, column_name: str) -> dict[str, object]:
            return columns[(table_name, column_name)]

        def assert_fk(
            *,
            table_name: str,
            column_name: str,
            target_table: str,
            on_delete: str | None = None,
        ) -> None:
            matching = [
                fk
                for fk in foreign_keys
                if fk["table_name"] == table_name
                and f"FOREIGN KEY ({column_name}) REFERENCES {target_table}(id)"
                in fk["definition"]
            ]
            assert matching
            if on_delete is not None:
                assert any(on_delete in fk["definition"] for fk in matching)

        assert schema["version"] == SLICE9_REVISION
        assert schema["new_tables"] == SLICE9_TABLES
        assert schema["forbidden"] == set()
        assert column("campaign_payout_rules", "campaign_id")["is_nullable"] == "NO"
        assert column("campaign_payout_rules", "currency")["is_nullable"] == "NO"
        assert column("campaign_payout_rules", "max_payout_per_trip")["is_nullable"] == "YES"
        assert "payout_v1" in column("campaign_payout_rules", "formula_version")[
            "column_default"
        ]
        assert column("campaign_payout_rules", "base_rate_per_km")["column_default"] == "0"
        assert "0.9000" in column("campaign_payout_rules", "low_fraud_multiplier")[
            "column_default"
        ]
        assert "'{}'::jsonb" in column("campaign_payout_rules", "metadata")[
            "column_default"
        ]
        assert column("payout_calculations", "trip_session_id")["is_nullable"] == "NO"
        assert column("payout_calculations", "trip_analytics_id")["is_nullable"] == "NO"
        assert column("payout_calculations", "impression_estimate_id")["is_nullable"] == "NO"
        assert column("payout_calculations", "payout_rule_id")["is_nullable"] == "NO"
        assert column("payout_calculations", "quality_multiplier")["is_nullable"] == "NO"
        assert column("payout_calculations", "final_payout")["column_default"] == "0"
        assert column("earnings_ledger_entries", "payout_calculation_id")[
            "is_nullable"
        ] == "YES"
        assert column("earnings_ledger_entries", "driver_profile_id")["is_nullable"] == "NO"
        assert column("earnings_ledger_entries", "trip_session_id")["is_nullable"] == "YES"
        assert column("earnings_ledger_entries", "vehicle_id")["is_nullable"] == "YES"
        assert column("earnings_ledger_entries", "amount")["is_nullable"] == "NO"
        assert "ck_campaign_payout_rules_status" in schema["constraints"]
        assert "ck_campaign_payout_rules_currency" in schema["constraints"]
        assert "ck_campaign_payout_rules_max_gte_min" in schema["constraints"]
        assert "ck_payout_calculations_status" in schema["constraints"]
        assert "ck_payout_calculations_currency" in schema["constraints"]
        assert "ck_payout_calculations_final_non_negative" in schema["constraints"]
        assert "ck_earnings_ledger_entries_entry_type" in schema["constraints"]
        assert "ck_earnings_ledger_entries_currency" in schema["constraints"]
        assert "uq_payout_calculations_trip_formula_rule" in schema["constraints"]
        assert_fk(
            table_name="campaign_payout_rules",
            column_name="campaign_id",
            target_table="campaigns",
            on_delete="ON DELETE CASCADE",
        )
        assert_fk(
            table_name="payout_calculations",
            column_name="trip_session_id",
            target_table="trip_sessions",
            on_delete="ON DELETE CASCADE",
        )
        assert_fk(
            table_name="payout_calculations",
            column_name="payout_rule_id",
            target_table="campaign_payout_rules",
            on_delete="ON DELETE RESTRICT",
        )
        assert_fk(
            table_name="earnings_ledger_entries",
            column_name="payout_calculation_id",
            target_table="payout_calculations",
            on_delete="ON DELETE RESTRICT",
        )
        assert_fk(
            table_name="earnings_ledger_entries",
            column_name="trip_session_id",
            target_table="trip_sessions",
            on_delete="ON DELETE SET NULL",
        )
        assert "uq_campaign_payout_rules_active_campaign" in indexes
        assert "UNIQUE" in indexes["uq_campaign_payout_rules_active_campaign"]
        assert "WHERE ((status)::text = 'active'::text)" in indexes[
            "uq_campaign_payout_rules_active_campaign"
        ]
        assert "uq_earnings_ledger_entries_payout_calculation_id" in indexes
        assert "payout_calculation_id IS NOT NULL" in indexes[
            "uq_earnings_ledger_entries_payout_calculation_id"
        ]
        assert "ix_payout_calculations_campaign_calculated_at" in indexes
        assert "ix_earnings_ledger_entries_driver_occurred_at" in indexes
    finally:
        get_settings.cache_clear()
        asyncio.run(drop_database(migration_url))
