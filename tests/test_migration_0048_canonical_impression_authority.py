"""Migration 0048: one deterministic authority row per trip/methodology."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

_migration_path = (
    Path(__file__).parents[1] / "alembic/versions/0048_canonical_impression_authority.py"
)
_migration_spec = importlib.util.spec_from_file_location("migration_0048", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def test_authority_backfill_is_deterministic_and_sqlite_index_stays_partial() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE traffic_density_profiles ("
            "id TEXT PRIMARY KEY, status TEXT NOT NULL, is_default BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE impression_estimates ("
            "id TEXT PRIMARY KEY, trip_session_id TEXT NOT NULL, "
            "formula_version TEXT NOT NULL, traffic_density_profile_id TEXT NOT NULL, "
            "estimated_at TEXT NOT NULL)"
        )
        connection.execute(
            text(
                "INSERT INTO traffic_density_profiles (id,status,is_default) VALUES "
                "('default','active',1),('scenario','inactive',0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO impression_estimates "
                "(id,trip_session_id,formula_version,traffic_density_profile_id,estimated_at) "
                "VALUES ('scenario-row','trip-1','impressions_v1','scenario','2026-01-02'),"
                "('default-row','trip-1','impressions_v1','default','2026-01-01'),"
                "('other-row','trip-1','impressions_v1','scenario','2026-01-03')"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()

        rows = connection.execute(
            text(
                "SELECT id,is_authoritative FROM impression_estimates "
                "WHERE trip_session_id='trip-1' ORDER BY id"
            )
        ).all()
        assert [(row[0], row[1]) for row in rows] == [
            ("default-row", 1),
            ("other-row", 0),
            ("scenario-row", 0),
        ]
        index_sql = connection.scalar(
            text(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND name='uq_impression_estimates_authoritative_trip_formula'"
            )
        )
        assert index_sql is not None
        assert "WHERE is_authoritative = 1" in index_sql

        with pytest.raises(RuntimeError, match="Refusing to drop populated"):
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()

        connection.execute(text("DELETE FROM impression_estimates"))
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        columns = connection.execute(text("PRAGMA table_info(impression_estimates)")).all()
        assert "is_authoritative" not in {row[1] for row in columns}
