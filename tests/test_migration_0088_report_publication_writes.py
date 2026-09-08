import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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
from test_migration_0082_report_publication_intents import (
    FIRST,
    SEED_ISSUANCE,
    seed_generation,
)

from app.db.base import Base

PREVIOUS = "0087_kyc_payload_retention"
CURRENT = "0088_report_publication_writes"


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


@pytest.mark.parametrize(
    "state", ["prepared", "publishing", "abandoned", "cleaning", "cleaned", "complete"]
)
def test_legacy_publication_claims_are_preserved_and_untracked_writes_stay_unknown(
    publication_database, monkeypatch, state
):
    url, engine, execute = publication_database

    async def seed():
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role=replica"))
            await connection.execute(text(SEED_ISSUANCE))
            await connection.execute(text(seed_generation(FIRST, 1, state)))

    asyncio.run(seed())
    before = asyncio.run(execute("SELECT to_jsonb(p) FROM report_publication_intents p"))
    upgrade_to(url, CURRENT, monkeypatch)
    assert (
        asyncio.run(
            execute("SELECT to_jsonb(p)-'write_protocol' FROM report_publication_intents p")
        )
        == before
    )
    assert asyncio.run(execute("SELECT write_protocol FROM report_publication_intents")) == [(0,)]
    receipts = asyncio.run(
        execute(
            "SELECT format,state,error_code,settled_at FROM report_publication_writes "
            "ORDER BY format"
        )
    )
    assert receipts == (
        []
        if state == "complete"
        else [(fmt, "uncertain", "legacy_untracked_write", None) for fmt in ("csv", "pdf")]
    )
    if state != "complete":
        with pytest.raises(RuntimeError, match="0088 downgrade blocked"):
            downgrade_to(url, PREVIOUS, monkeypatch)
    else:
        downgrade_to(url, PREVIOUS, monkeypatch)


def test_write_receipts_and_terminal_guards_survive_raw_sql_and_downgrade_races(
    publication_database, monkeypatch
):
    url, engine, execute = publication_database
    upgrade_to(url, CURRENT, monkeypatch)
    downgrade_to(url, PREVIOUS, monkeypatch)
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
        async with engine.begin() as writer:
            await writer.execute(text("SELECT id FROM report_publication_intents FOR UPDATE"))
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await asyncio.to_thread(downgrade_to, url, PREVIOUS, monkeypatch)

    asyncio.run(exercise())
    with pytest.raises(RuntimeError, match="0088 downgrade blocked"):
        downgrade_to(url, PREVIOUS, monkeypatch)


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
                await connection.execute(text(seed_generation(FIRST, 1, "prepared")))

    asyncio.run(attempt())
