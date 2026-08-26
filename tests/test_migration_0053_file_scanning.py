"""Migration 0053: scan authority fields and fail-closed status set."""

import asyncio
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0051_canonical_impression_authority import (
    configured_postgres_url,
    create_temporary_database,
    drop_temporary_database,
)

_migration_path = Path(__file__).parents[1] / "alembic/versions/0053_file_scanning.py"
_migration_spec = importlib.util.spec_from_file_location("migration_0053", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def test_scan_columns_upgrade_and_populated_downgrade_preserve_file_authority() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE stored_files ("
            "id UUID PRIMARY KEY, scan_status VARCHAR(32) NOT NULL DEFAULT 'pending')"
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(stored_files)"))}
        assert {
            "actual_content_type",
            "scan_attempts",
            "scan_error_code",
            "malware_signature",
            "next_scan_at",
            "scanned_at",
        } <= columns
        connection.execute(
            text("INSERT INTO stored_files (id, scan_status) VALUES ('file-1', 'clean')")
        )

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(stored_files)"))}
        assert "actual_content_type" not in columns
        assert connection.scalar(text("SELECT scan_status FROM stored_files")) == "clean"


def test_postgres_scan_constraint_round_trip_maps_rejected_to_fail_closed_error() -> None:
    async def scenario() -> None:
        database_url = await create_temporary_database(configured_postgres_url())
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE TABLE stored_files ("
                        "id TEXT PRIMARY KEY, scan_status VARCHAR(32) NOT NULL DEFAULT 'pending', "
                        "CONSTRAINT ck_stored_files_scan_status CHECK "
                        "(scan_status IN ('pending','clean','infected','error')))"
                    )
                )
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync_connection: _run_migration(sync_connection, MIGRATION.upgrade)
                )
                await connection.execute(
                    text("INSERT INTO stored_files (id, scan_status) VALUES ('file-1','rejected')")
                )
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda sync_connection: _run_migration(sync_connection, MIGRATION.downgrade)
                )
                assert (
                    await connection.scalar(
                        text("SELECT scan_status FROM stored_files WHERE id='file-1'")
                    )
                    == "error"
                )
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.execute(
                            text(
                                "INSERT INTO stored_files (id, scan_status) "
                                "VALUES ('file-2','rejected')"
                            )
                        )
        finally:
            await engine.dispose()
            await drop_temporary_database(database_url)

    asyncio.run(scenario())


def _run_migration(connection, operation) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        operation()
