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

SLICE7_REVISION = "0008_route_analytics_and_fraud_flags"


def configured_postgres_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if database_url is None or not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("PostGIS test database is not configured")
    return database_url


async def create_database_from_url(database_url: str) -> str:
    source_url = make_url(database_url)
    database_name = f"test_slice7_migration_{uuid4().hex}"
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


def test_slice7_migration_contains_only_route_analytics_and_fraud_tables() -> None:
    migration = Path("alembic/versions/0008_route_analytics_and_fraud_flags.py").read_text()

    assert 'down_revision: str | None = "0007_trip_tracking"' in migration
    assert migration.count("op.create_table(") == 2
    assert '"trip_analytics"' in migration
    assert '"fraud_flags"' in migration
    for required in [
        "uq_trip_analytics_trip_session_id",
        "ck_trip_analytics_status",
        "ck_trip_analytics_quality_score_range",
        "ix_trip_analytics_campaign_computed_at",
        "ix_trip_analytics_driver_profile_computed_at",
        "ck_fraud_flags_flag_type",
        "ck_fraud_flags_severity",
        "ck_fraud_flags_status",
        "uq_fraud_flags_trip_open_flag_type",
        "postgresql_where=sa.text(\"status = 'open'\")",
        "'route_analytics_v1'",
        "'{}'::jsonb",
        "gen_random_uuid()",
    ]:
        assert required in migration
    for required_column in [
        '"trip_session_id"',
        '"assignment_id"',
        '"campaign_id"',
        '"driver_profile_id"',
        '"vehicle_id"',
        '"formula_version"',
        '"status"',
        '"ping_count"',
        '"valid_ping_count"',
        '"invalid_ping_count"',
        '"duration_seconds"',
        '"active_tracking_seconds"',
        '"moving_seconds"',
        '"stationary_seconds"',
        '"distance_m"',
        '"avg_speed_mps"',
        '"max_observed_speed_mps"',
        '"avg_accuracy_m"',
        '"poor_accuracy_ping_count"',
        '"target_zone_distance_m"',
        '"bonus_zone_distance_m"',
        '"exclusion_zone_distance_m"',
        '"target_zone_seconds"',
        '"bonus_zone_seconds"',
        '"exclusion_zone_seconds"',
        '"quality_score"',
        '"computed_at"',
        '"metadata"',
        '"flag_type"',
        '"severity"',
        '"description"',
        '"evidence"',
        '"detected_at"',
    ]:
        assert required_column in migration
    for forbidden_table in [
        "traffic_density",
        "impression_estimates",
        "impressions",
        "payouts",
        "earnings_ledgers",
        "campaign_daily_metrics",
        "advertiser_reports",
        "heatmaps",
        "heatmap_cache",
        "map_tiles",
        "seed_trips",
    ]:
        assert f'"{forbidden_table}"' not in migration
    for forbidden_term in [
        "estimated_impression",
        "estimated_impressions",
        "impression_count",
        "impression_estimate",
        "payout",
        "payout_amount",
        "earning",
        "earnings",
        "heatmap",
        "heat_map",
        "reporting",
        "report_",
        "ledger",
        "seed",
        "audience",
        "attribution",
    ]:
        assert forbidden_term not in migration.lower()


def test_slice7_migration_upgrades_postgres_and_creates_expected_schema(monkeypatch) -> None:
    source_url = configured_postgres_url()
    try:
        migration_url = asyncio.run(create_database_from_url(source_url))
    except Exception as exc:  # pragma: no cover - exercised only without local DB privilege
        pytest.fail(f"Could not create temporary Postgres migration database: {exc}")

    try:
        monkeypatch.setenv("DATABASE_URL", migration_url)
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), SLICE7_REVISION)

        async def inspect_schema() -> dict[str, object]:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    version = await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                    version_length = await connection.scalar(
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
                                      AND table_name IN ('trip_analytics', 'fraud_flags')
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
                                      AND table_name IN ('trip_analytics', 'fraud_flags')
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
                                      AND tablename IN ('trip_analytics', 'fraud_flags')
                                    """
                                )
                            )
                        )
                    }
                    return {
                        "version": version,
                        "version_length": version_length,
                        "tables": tables,
                        "constraints": constraints,
                        "indexes": indexes,
                    }
            finally:
                await engine.dispose()

        schema = asyncio.run(inspect_schema())
        indexes = schema["indexes"]

        assert schema["version"] == SLICE7_REVISION
        assert schema["version_length"] >= len(SLICE7_REVISION)
        assert schema["tables"] == {"trip_analytics", "fraud_flags"}
        assert "uq_trip_analytics_trip_session_id" in schema["constraints"]
        assert "ck_trip_analytics_quality_score_range" in schema["constraints"]
        assert "ck_fraud_flags_flag_type" in schema["constraints"]
        assert "ck_fraud_flags_status" in schema["constraints"]
        assert "ix_trip_analytics_campaign_computed_at" in indexes
        assert "ix_trip_analytics_driver_profile_computed_at" in indexes
        assert "uq_fraud_flags_trip_open_flag_type" in indexes
        assert "UNIQUE" in indexes["uq_fraud_flags_trip_open_flag_type"]
        assert "WHERE ((status)::text = 'open'::text)" in indexes[
            "uq_fraud_flags_trip_open_flag_type"
        ]
    finally:
        get_settings.cache_clear()
        asyncio.run(drop_database(migration_url))
