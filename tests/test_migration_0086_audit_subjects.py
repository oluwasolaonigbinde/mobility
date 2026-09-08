import asyncio
import threading
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import create_test_driver_profile, create_test_user
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

from app.db.base import Base
from app.models.user import UserRole

PREVIOUS = "0085_disclosure_protection"
CURRENT = "0086_audit_subjects"


def test_audit_subject_and_disclosure_models_match_forward_schema(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def inspect():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync: compare_metadata(
                        MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, CURRENT, monkeypatch)
        differences = asyncio.run(inspect())
        assert [
            diff
            for diff in differences
            if any(
                name in repr(diff)
                for name in ("audit_event_subject_resolutions", "disclosure_query_decisions")
            )
        ] == []
    finally:
        asyncio.run(drop_database(url))


@pytest.mark.parametrize("race_target_delete", [False, True])
def test_audit_backfill_preserves_immutable_events_and_explicitly_records_gaps(
    monkeypatch, race_target_delete
):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    subject, missing, event_id = uuid4(), uuid4(), uuid4()

    async def execute(sql, **values):
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                result = await connection.execute(text(sql), values)
                return result.all() if result.returns_rows else None
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        upgrade_to(url, CURRENT, monkeypatch)
        downgrade_to(url, PREVIOUS, monkeypatch)
        seed_engine = create_async_engine(url, poolclass=NullPool)
        factory = async_sessionmaker(seed_engine, expire_on_commit=False)
        actor = create_test_user(factory, email="backfill-actor@example.test")
        owner = create_test_user(factory, email="backfill-owner@example.test", role=UserRole.DRIVER)
        profile = create_test_driver_profile(factory, user_id=owner.id)
        asyncio.run(
            execute(
                "INSERT INTO audit_events (id,action,entity_type,entity_id) VALUES "
                "(:id,'synthetic.deleted_user','user',:subject),"
                "(gen_random_uuid(),'synthetic.missing_target','driver_profile',:missing)",
                id=event_id,
                subject=str(subject),
                missing=str(missing),
            )
        )
        asyncio.run(
            execute(
                "INSERT INTO audit_events (id,actor_user_id,action,entity_type,entity_id) "
                "VALUES (gen_random_uuid(),:actor,'synthetic.existing_profile',"
                "'driver_profile',:profile)",
                actor=actor.id,
                profile=str(profile.id),
            )
        )
        before = asyncio.run(execute("SELECT to_jsonb(a) FROM audit_events a ORDER BY id"))
        writer = None
        failures = []
        attempted = threading.Event()

        def observe(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("DELETE FROM driver_profiles"):
                attempted.set()

        def delete_target():
            try:
                asyncio.run(execute("DELETE FROM driver_profiles WHERE id=:id", id=profile.id))
            except BaseException as exc:
                failures.append(exc)

        original_execute = Operations.execute

        def pause_after_lock(operation, sql, *args, **kwargs):
            nonlocal writer
            result = original_execute(operation, sql, *args, **kwargs)
            if str(sql).startswith("LOCK TABLE") and "audit_events" in str(sql):
                writer = threading.Thread(target=delete_target)
                writer.start()
                assert attempted.wait(5)
                writer.join(0.1)
                assert writer.is_alive(), "Target deletion crossed the backfill authority lock"
            return result

        if race_target_delete:
            event.listen(Engine, "before_cursor_execute", observe)
            monkeypatch.setattr(Operations, "execute", pause_after_lock)
        try:
            upgrade_to(url, CURRENT, monkeypatch)
        finally:
            if race_target_delete:
                monkeypatch.setattr(Operations, "execute", original_execute)
                event.remove(Engine, "before_cursor_execute", observe)
            if writer is not None:
                writer.join(10)
                assert not writer.is_alive()
                assert failures == []
        assert asyncio.run(execute("SELECT to_jsonb(a) FROM audit_events a ORDER BY id")) == before
        assert set(
            asyncio.run(
                execute(
                    "SELECT subject_user_id FROM audit_event_subject_resolutions "
                    "WHERE role='target' AND outcome='resolved'"
                )
            )
        ) == {(subject,), (owner.id,)}
        assert asyncio.run(
            execute(
                "SELECT count(*) FROM audit_event_subject_resolutions "
                "WHERE role='target' AND outcome='unresolved' AND subject_user_id IS NULL"
            )
        ) == [(1,)]
        assert asyncio.run(
            execute(
                "SELECT count(*) FROM audit_event_subject_resolutions WHERE outcome='not_recorded'"
            )
        ) == [(2,)]
        for sql in (
            "UPDATE audit_event_subject_resolutions SET outcome=outcome",
            "DELETE FROM audit_event_subject_resolutions",
            "TRUNCATE audit_event_subject_resolutions",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                asyncio.run(execute(sql))
        with pytest.raises(RuntimeError, match="0086 downgrade blocked"):
            downgrade_to(url, PREVIOUS, monkeypatch)
        assert asyncio.run(execute("SELECT count(*) FROM audit_event_subject_resolutions")) == [
            (6,)
        ]
        asyncio.run(execute("DELETE FROM driver_profiles WHERE id=:id", id=profile.id))
        asyncio.run(execute("DELETE FROM users WHERE id=:id", id=actor.id))
        assert set(
            asyncio.run(
                execute(
                    "SELECT subject_user_id FROM audit_event_subject_resolutions "
                    "WHERE outcome='resolved'"
                )
            )
        ) == {(subject,), (owner.id,), (actor.id,)}
    finally:
        asyncio.run(drop_database(url))
