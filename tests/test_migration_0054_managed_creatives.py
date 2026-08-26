"""Migration 0054: managed stored-file binding for campaign creatives."""

import asyncio
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0051_canonical_impression_authority import (
    configured_postgres_url,
    create_temporary_database,
    drop_temporary_database,
)

_migration_path = Path(__file__).parents[1] / "alembic/versions/0054_managed_creatives.py"
_migration_spec = importlib.util.spec_from_file_location("migration_0054", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def test_legacy_creatives_upgrade_losslessly_and_managed_binding_blocks_downgrade() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE stored_files (id UUID PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE campaign_creatives ("
            "id UUID PRIMARY KEY, asset_url TEXT, mime_type TEXT, checksum TEXT)"
        )
        connection.execute(
            text(
                "INSERT INTO campaign_creatives (id,asset_url,mime_type,checksum) "
                "VALUES ('legacy','https://legacy.example/file.png','image/png','abc')"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()
        legacy = connection.execute(
            text(
                "SELECT asset_url,mime_type,checksum,stored_file_id "
                "FROM campaign_creatives WHERE id='legacy'"
            )
        ).one()
        assert legacy == ("https://legacy.example/file.png", "image/png", "abc", None)
        connection.execute(text("INSERT INTO stored_files (id) VALUES ('file-1')"))
        connection.execute(
            text(
                "INSERT INTO campaign_creatives "
                "(id,asset_url,mime_type,checksum,stored_file_id) "
                "VALUES ('managed',NULL,'image/png','def','file-1')"
            )
        )
        with pytest.raises(RuntimeError, match="0054 downgrade blocked"):
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()
        connection.execute(text("DELETE FROM campaign_creatives WHERE id='managed'"))
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        assert "stored_file_id" not in {
            row[1] for row in connection.execute(text("PRAGMA table_info(campaign_creatives)"))
        }


def test_postgres_populated_round_trip_enforces_unique_restrictive_binding() -> None:
    async def scenario() -> None:
        database_url = await create_temporary_database(configured_postgres_url())
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("CREATE TABLE stored_files (id UUID PRIMARY KEY)"))
                await connection.execute(
                    text(
                        "CREATE TABLE campaign_creatives ("
                        "id UUID PRIMARY KEY, asset_url TEXT, mime_type TEXT, checksum TEXT)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_creatives (id,asset_url,mime_type,checksum) VALUES "
                        "('00000000-0000-4000-8000-000000000001',"
                        "'https://legacy.example/file.png','image/png','abc')"
                    )
                )
                await connection.run_sync(
                    lambda sync_connection: _run_migration(sync_connection, MIGRATION.upgrade)
                )
                await connection.execute(
                    text(
                        "INSERT INTO stored_files (id) VALUES "
                        "('00000000-0000-4000-8000-000000000010')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_creatives "
                        "(id,asset_url,mime_type,checksum,stored_file_id) VALUES "
                        "('00000000-0000-4000-8000-000000000002',NULL,'image/png','def',"
                        "'00000000-0000-4000-8000-000000000010')"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(RuntimeError, match="0054 downgrade blocked"):
                    await connection.run_sync(
                        lambda sync_connection: _run_migration(
                            sync_connection, MIGRATION.downgrade
                        )
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "DELETE FROM campaign_creatives "
                        "WHERE stored_file_id IS NOT NULL"
                    )
                )
                await connection.run_sync(
                    lambda sync_connection: _run_migration(sync_connection, MIGRATION.downgrade)
                )
                assert not await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='campaign_creatives' AND column_name='stored_file_id')"
                    )
                )
                assert await connection.scalar(
                    text(
                        "SELECT asset_url FROM campaign_creatives WHERE "
                        "id='00000000-0000-4000-8000-000000000001'"
                    )
                ) == "https://legacy.example/file.png"
        finally:
            await engine.dispose()
            await drop_temporary_database(database_url)

    asyncio.run(scenario())


def _run_migration(connection, operation) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        operation()
