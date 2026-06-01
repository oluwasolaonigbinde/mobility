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

SLICE8_REVISION = "0009_impression_estimation"
SLICE7_REVISION = "0008_route_analytics_and_fraud_flags"
SLICE8_TABLES = {"traffic_density_profiles", "impression_estimates"}


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_slice8_migration_{uuid4().hex}"
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


def test_slice8_migration_contains_only_impression_tables() -> None:
    migration = Path("alembic/versions/0009_impression_estimation.py").read_text()

    assert f'down_revision: str | None = "{SLICE7_REVISION}"' in migration
    assert migration.count("op.create_table(") == 2
    assert '"traffic_density_profiles"' in migration
    assert '"impression_estimates"' in migration
    for required in [
        "ck_traffic_density_profiles_profile_type",
        "ck_traffic_density_profiles_status",
        "ck_traffic_density_profiles_density_non_negative",
        "uq_traffic_density_profiles_active_default",
        "postgresql_where=sa.text(\"is_default = true AND status = 'active'\")",
        "ck_impression_estimates_status",
        "ck_impression_estimates_quality_multiplier_range",
        "ck_impression_estimates_fraud_multiplier_range",
        "ck_impression_estimates_confidence_score_range",
        "uq_impression_estimates_trip_formula_profile",
        "ix_impression_estimates_campaign_estimated_at",
        "ix_impression_estimates_campaign_status",
        "'impressions_v1'",
        "'{}'::jsonb",
        "gen_random_uuid()",
    ]:
        assert required in migration
    for required_column in [
        '"traffic_density_per_km"',
        '"dwell_impressions_per_minute"',
        '"road_category_weight"',
        '"morning_weight"',
        '"midday_weight"',
        '"evening_weight"',
        '"night_weight"',
        '"target_zone_weight"',
        '"bonus_zone_weight"',
        '"exclusion_zone_weight"',
        '"trip_session_id"',
        '"trip_analytics_id"',
        '"assignment_id"',
        '"campaign_id"',
        '"driver_profile_id"',
        '"vehicle_id"',
        '"traffic_density_profile_id"',
        '"estimated_impressions"',
        '"base_distance_impressions"',
        '"dwell_impressions"',
        '"target_zone_impressions"',
        '"bonus_zone_impressions"',
        '"exclusion_zone_adjustment"',
        '"quality_multiplier"',
        '"fraud_adjustment_multiplier"',
        '"confidence_score"',
        '"estimated_at"',
    ]:
        assert required_column in migration
    for forbidden_table in [
        "campaign_payout_rules",
        "payout_calculations",
        "earnings_ledger_entries",
        "payouts",
        "earnings_ledgers",
        "campaign_daily_metrics",
        "advertiser_reports",
        "heatmaps",
        "heatmap_cache",
        "billing",
        "settlements",
        "audiences",
        "retargeting",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration


def test_slice8_migration_upgrades_postgres_and_creates_expected_schema(monkeypatch) -> None:
    source_url = configured_postgres_url()
    try:
        migration_url = asyncio.run(create_database_from_url(source_url))
    except Exception as exc:  # pragma: no cover - exercised only without local DB privilege
        pytest.fail(f"Could not create temporary Postgres migration database: {exc}")

    try:
        monkeypatch.setenv("DATABASE_URL", migration_url)
        get_settings.cache_clear()
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, SLICE7_REVISION)

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
        command.upgrade(alembic_config, SLICE8_REVISION)

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
                    version_column_length = await connection.scalar(
                        text(
                            """
                            SELECT character_maximum_length
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'alembic_version'
                              AND column_name = 'version_num'
                            """
                        )
                    )
                    tables = set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT table_name
                                    FROM information_schema.tables
                                    WHERE table_schema = 'public'
                                      AND table_type = 'BASE TABLE'
                                      AND table_name IN (
                                        'traffic_density_profiles',
                                        'impression_estimates'
                                      )
                                    """
                                )
                            )
                        ).scalars()
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
                                        'traffic_density_profiles',
                                        'impression_estimates'
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
                                        'traffic_density_profiles',
                                        'impression_estimates'
                                      )
                                    """
                                )
                            )
                        )
                    }
                    forbidden = set(
                        (
                            await connection.execute(
                                text(
                                    """
                                    SELECT table_name
                                    FROM information_schema.tables
                                    WHERE table_schema = 'public'
                                      AND table_name IN (
                                        'campaign_payout_rules',
                                        'payout_calculations',
                                        'earnings_ledger_entries',
                                        'payouts',
                                        'earnings_ledgers',
                                        'campaign_daily_metrics',
                                        'advertiser_reports',
                                        'heatmaps',
                                        'heatmap_cache',
                                        'seed_trips'
                                      )
                                    """
                                )
                            )
                        ).scalars()
                    )
                    return {
                        "version": version,
                        "version_column_length": version_column_length,
                        "new_tables": all_tables - base_tables,
                        "tables": tables,
                        "constraints": constraints,
                        "indexes": indexes,
                        "forbidden": forbidden,
                    }
            finally:
                await engine.dispose()

        schema = asyncio.run(inspect_schema())
        indexes = schema["indexes"]

        assert schema["version"] == SLICE8_REVISION
        assert schema["version_column_length"] >= len(SLICE7_REVISION)
        assert schema["new_tables"] == SLICE8_TABLES
        assert schema["tables"] == SLICE8_TABLES
        assert schema["forbidden"] == set()
        assert "ck_traffic_density_profiles_profile_type" in schema["constraints"]
        assert "ck_impression_estimates_status" in schema["constraints"]
        assert "uq_impression_estimates_trip_formula_profile" in schema["constraints"]
        assert "uq_traffic_density_profiles_active_default" in indexes
        assert "UNIQUE" in indexes["uq_traffic_density_profiles_active_default"]
        assert "ix_impression_estimates_campaign_estimated_at" in indexes
        assert "ix_impression_estimates_campaign_status" in indexes
    finally:
        get_settings.cache_clear()
        asyncio.run(drop_database(migration_url))
