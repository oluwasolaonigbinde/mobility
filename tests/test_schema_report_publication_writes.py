import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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
from test_schema_report_publication_intents import (
    FIRST,
    SEED_ISSUANCE,
    seed_generation,
)

from app.db.base import Base

PREVIOUS = "head"
CURRENT = "head"


@pytest.fixture
def publication_database(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = create_async_engine(url, poolclass=NullPool)

    async def execute(sql):
        async with engine.begin() as connection:
            result = await connection.execute(text(sql))
            return result.all() if result.returns_rows else None

    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        yield url, engine, execute
    finally:
        asyncio.run(engine.dispose())
        asyncio.run(drop_database(url))


def test_write_receipts_and_terminal_guards_survive_raw_sql(publication_database, monkeypatch):
    url, engine, execute = publication_database
    upgrade_to(url, CURRENT, monkeypatch)

    async def exercise():
        async with engine.begin() as connection:
            changes = await connection.run_sync(
                lambda sync: compare_metadata(
                    MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                )
            )
            assert [
                change for change in changes if "report_publication_writes" in repr(change)
            ] == []
            await connection.execute(text("SET LOCAL session_replication_role=replica"))
            await connection.execute(text(SEED_ISSUANCE))
            await connection.execute(
                text(seed_generation(FIRST, 1, "publishing", write_protocol=1))
            )
        await execute(
            "INSERT INTO report_publication_writes(publication_intent_id,format) "
            f"VALUES ('{FIRST}','csv')"
        )
        for sql in (
            "UPDATE report_publication_intents SET write_protocol=0",
            "UPDATE report_publication_writes SET format='pdf'",
            "DELETE FROM report_publication_writes",
            "TRUNCATE report_publication_writes",
            "UPDATE report_publication_intents SET state='complete',publisher_token=NULL, "
            "lease_expires_at=NULL,completed_at=now()",
        ):
            with pytest.raises(DBAPIError):
                await execute(sql)
        await execute("UPDATE report_publication_writes SET state='uncertain',error_code='timeout'")
        with pytest.raises(DBAPIError, match="cannot be restated"):
            await execute("UPDATE report_publication_writes SET state='settled',settled_at=now()")
        await execute(
            "UPDATE report_publication_intents SET state='abandoned',publisher_token=NULL, "
            "lease_expires_at=NULL,abandoned_at=now()"
        )
        with pytest.raises(DBAPIError, match="unsettled report write"):
            await execute(
                "UPDATE report_publication_intents SET state='cleaning',publisher_token="
                "gen_random_uuid(),lease_expires_at=now()+interval '2 minutes'"
            )
        with pytest.raises(DBAPIError, match="live publishing generation"):
            await execute(
                "INSERT INTO report_publication_writes(publication_intent_id,format) "
                f"VALUES ('{FIRST}','pdf')"
            )

    asyncio.run(exercise())


def test_previous_publisher_cannot_register_an_untracked_generation(
    publication_database, monkeypatch
):
    url, engine, _ = publication_database
    upgrade_to(url, CURRENT, monkeypatch)

    async def attempt():
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role=replica"))
            await connection.execute(text(SEED_ISSUANCE))
        with pytest.raises(DBAPIError, match="write_protocol"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(seed_generation(FIRST, 1, "prepared", write_protocol=0))
                )

    asyncio.run(attempt())
