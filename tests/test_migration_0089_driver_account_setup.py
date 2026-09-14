import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

from app.db.base import Base

PREVIOUS = "0088_report_publication_writes"
CURRENT = "0089_driver_account_setup"


@pytest.fixture
def setup_database(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        yield url, engine
    finally:
        asyncio.run(engine.dispose())
        asyncio.run(drop_database(url))


def test_driver_setup_migration_round_trip_and_metadata(setup_database, monkeypatch) -> None:
    url, engine = setup_database
    upgrade_to(url, CURRENT, monkeypatch)

    async def inspect():
        async with engine.begin() as connection:
            columns = {
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='driver_account_setup_tokens'"
                        )
                    )
                ).all()
            }
            access_columns = {
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name='driver_application_access_tokens'"
                        )
                    )
                ).all()
            }
            changes = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )
            return columns, access_columns, changes

    columns, access_columns, changes = asyncio.run(inspect())
    assert {
        "token_sha256",
        "evidence_sha256",
        "session_version",
        "superseded_at",
        "used_at",
    } <= columns
    assert "invalidated_at" in access_columns
    assert [change for change in changes if "driver_account_setup" in repr(change)] == []
    downgrade_to(url, PREVIOUS, monkeypatch)
    upgrade_to(url, CURRENT, monkeypatch)
