import asyncio
import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, text
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
from test_migration_0082_report_publication_intents import FIRST, SEED_ISSUANCE, seed_generation

ROOT = Path(__file__).resolve().parents[1]
DELETION_SEED = """
    INSERT INTO stored_object_deletions
      (organization_id, owner_type, owner_id, storage_key, storage_key_sha256,
       object_checksum_sha256, reason, request_fingerprint, state,
       provider_deleted_at, completed_at)
    VALUES (gen_random_uuid(), 'synthetic_test', gen_random_uuid(), 'private/key',
            repeat('a',64), repeat('b',64), 'synthetic_test', repeat('c',64), CAST(:state AS text),
            CASE WHEN CAST(:state AS text) = 'pending' THEN NULL ELSE now() END,
            CASE WHEN CAST(:state AS text) = 'completed' THEN now() ELSE NULL END)
"""


@pytest.mark.parametrize("state", ["pending", "provider_deleted", "completed"])
def test_0077_downgrade_retains_every_populated_authority_state(monkeypatch, state):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(DELETION_SEED), {"state": state})
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, "0077_stored_object_deletions", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="0077 downgrade blocked"):
            downgrade_to(url, "0076_dsr_assessment_truth", monkeypatch)
    finally:
        asyncio.run(drop_database(url))


@pytest.mark.parametrize(
    "revision", ["0077_stored_object_deletions", "0082_report_publication_intents"]
)
def test_downgrade_serializes_a_writer_across_the_check_to_ddl_interval(monkeypatch, revision):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    reached_ddl = threading.Event()
    release_ddl = threading.Event()
    spec = importlib.util.spec_from_file_location(
        "guarded_migration", ROOT / "alembic" / "versions" / f"{revision}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def migrate():
        engine = create_async_engine(url, poolclass=NullPool)

        def barrier(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("DROP TRIGGER") and not reached_ddl.is_set():
                reached_ddl.set()
                assert release_ddl.wait(10), "DDL barrier was not released"

        event.listen(engine.sync_engine, "before_cursor_execute", barrier)
        try:
            async with engine.begin() as connection:

                def apply(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.downgrade()

                await connection.run_sync(apply)
        finally:
            await engine.dispose()

    async def write():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                if revision.startswith("0077"):
                    await connection.execute(text(DELETION_SEED), {"state": "pending"})
                else:
                    await connection.execute(text("SET LOCAL session_replication_role = replica"))
                    await connection.execute(text(seed_generation(FIRST, 1, "prepared")))
        finally:
            await engine.dispose()

    async def seed_issuance():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(text(SEED_ISSUANCE))
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, revision, monkeypatch)
        if revision.startswith("0082"):
            asyncio.run(seed_issuance())
        with ThreadPoolExecutor(max_workers=2) as pool:
            migration = pool.submit(asyncio.run, migrate())
            try:
                assert reached_ddl.wait(10)
                writer = pool.submit(asyncio.run, write())
                with pytest.raises(TimeoutError):
                    writer.result(timeout=0.25)
            finally:
                release_ddl.set()
            migration.result(timeout=10)
            with pytest.raises(DBAPIError, match="does not exist"):
                writer.result(timeout=10)
    finally:
        release_ddl.set()
        asyncio.run(drop_database(url))
