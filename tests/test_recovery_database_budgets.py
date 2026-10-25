"""Real PG cancellation and pool recovery; shortened timers keep failures deterministic."""

import asyncio
import json
from contextlib import AsyncExitStack

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, TimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import session as database
from app.jobs.worker import WorkerSettings


def _engine(maker, *, worker=False):
    return database.create_database_engine(
        maker.kw["bind"].url.render_as_string(hide_password=False), worker=worker
    )


@pytest.mark.parametrize("worker,capacity", [(False, 10), (True, 11)])
def test_actual_production_server_bounds_and_pool_capacity(
    postgis_db_sessionmaker, monkeypatch, worker, capacity
):
    assert database.DATABASE_POOL_WAIT_SECONDS == 10
    # Only the failure wait is scaled; the real production pool capacities stay intact.
    monkeypatch.setattr(database, "DATABASE_POOL_WAIT_SECONDS", 0.05)

    async def scenario():
        engine = _engine(postgis_db_sessionmaker, worker=worker)
        try:
            async with AsyncExitStack() as stack:
                connections = [
                    await stack.enter_async_context(engine.connect()) for _ in range(capacity)
                ]
                assert await connections[0].scalar(text("SHOW statement_timeout")) == "2min"
                assert await connections[0].scalar(text("SHOW lock_timeout")) == "10s"
                assert (
                    await connections[0].scalar(text("SHOW idle_in_transaction_session_timeout"))
                    == "1min"
                )
                with pytest.raises(TimeoutError):
                    async with engine.connect():
                        pytest.fail("exhausted pool unexpectedly admitted a connection")
            async with engine.connect() as recovered:
                assert await recovered.scalar(text("SELECT 1")) == 1
            assert engine.pool.size() == 5
            assert WorkerSettings.max_jobs == 10
            assert WorkerSettings.job_timeout == 300
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["statement", "advisory", "row"])
def test_pg_cancellation_rolls_back_and_reuses_connections(postgis_db_sessionmaker, operation):
    schema = postgis_db_sessionmaker.kw["bind"].get_execution_options()["schema_translate_map"][
        None
    ]

    async def scenario():
        engine = _engine(postgis_db_sessionmaker)
        try:
            async with engine.begin() as setup:
                await setup.execute(
                    text(f'CREATE TABLE "{schema}".budget_lock (id int PRIMARY KEY)')
                )
                await setup.execute(text(f'INSERT INTO "{schema}".budget_lock VALUES (1)'))
            async with engine.connect() as owner, engine.connect() as waiter:
                if operation == "row":
                    await owner.execute(text(f'SELECT * FROM "{schema}".budget_lock FOR UPDATE'))
                elif operation == "advisory":
                    await owner.execute(text("SELECT pg_advisory_xact_lock(92746103)"))
                await waiter.execute(text("SET LOCAL statement_timeout = '150ms'"))
                await waiter.execute(text("SET LOCAL lock_timeout = '50ms'"))
                statement = {
                    "statement": "SELECT pg_sleep(1)",
                    "advisory": "SELECT pg_advisory_xact_lock(92746103)",
                    "row": f'SELECT * FROM "{schema}".budget_lock FOR UPDATE',
                }[operation]
                with pytest.raises(DBAPIError) as failure:
                    await waiter.execute(text(statement))
                assert failure.value.orig.sqlstate == (
                    "57014" if operation == "statement" else "55P03"
                )
                await waiter.rollback()
                await owner.rollback()
                assert await waiter.scalar(text("SELECT 1")) == 1
                assert await waiter.scalar(text("SELECT pg_try_advisory_xact_lock(92746103)"))
            async with engine.connect() as recovered:
                assert await recovered.scalar(text("SELECT 1")) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_idle_transaction_termination_invalidates_and_reconnects(postgis_db_sessionmaker):
    async def scenario():
        engine = _engine(postgis_db_sessionmaker)
        try:
            async with engine.connect() as connection:
                await connection.execute(
                    text("SET LOCAL idle_in_transaction_session_timeout='50ms'")
                )
                await asyncio.sleep(0.15)
                with pytest.raises(DBAPIError) as failure:
                    await connection.execute(text("SELECT 1"))
                assert failure.value.connection_invalidated
                await connection.rollback()
                assert await connection.scalar(text("SELECT 1")) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cancelled_payment_worker_rolls_back_then_retry_commits_once(
    postgis_db_sessionmaker, monkeypatch
):
    from uuid import uuid4

    from test_payment_gateway import _payload

    from app.adapters.payments import FakePaymentGatewayAdapter
    from app.jobs import payment_gateway as jobs
    from app.models.billing import PaymentGatewayProcessingAttempt
    from app.services.billing.gateway import ingest_payment_gateway_webhook

    schema = postgis_db_sessionmaker.kw["bind"].get_execution_options()["schema_translate_map"][
        None
    ]
    original = jobs.process_payment_gateway_event

    async def scenario():
        engine = _engine(postgis_db_sessionmaker, worker=True)
        engine.update_execution_options(schema_translate_map={None: schema})
        maker = async_sessionmaker(engine, expire_on_commit=False)
        entered = asyncio.Event()
        adapter = FakePaymentGatewayAdapter()
        payload = json.loads(_payload(uuid4(), event_id="cancelled", transaction_id="cancelled"))
        payload["event_type"] = "payment_failed"
        encoded = json.dumps(payload).encode()
        async with maker() as session:
            event, _ = await ingest_payment_gateway_webhook(
                session, adapter=adapter, payload=encoded, signature=adapter.sign_webhook(encoded)
            )
            await session.commit()
            event_id = event.id

        async def before_commit(session, **kwargs):
            # Exercise the actual worker's transaction/cancellation boundary.
            await original(session, **kwargs)
            await session.execute(text("SELECT pg_advisory_xact_lock(92746104)"))
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(jobs, "process_payment_gateway_event", before_commit)
        try:
            task = asyncio.create_task(
                jobs.process_payment_gateway_event_job({"sessionmaker": maker}, str(event_id))
            )
            await asyncio.wait_for(entered.wait(), 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async with maker() as session:
                assert await session.scalar(text("SELECT pg_try_advisory_xact_lock(92746104)"))
                assert list(await session.scalars(select(PaymentGatewayProcessingAttempt))) == []
            monkeypatch.setattr(jobs, "process_payment_gateway_event", original)
            result = await jobs.process_payment_gateway_event_job(
                {"sessionmaker": maker}, str(event_id)
            )
            assert result == {
                "event_id": str(event_id),
                "outcome": "ignored_failed",
                "attempt_number": 1,
            }
            async with maker() as session:
                assert (
                    len(list(await session.scalars(select(PaymentGatewayProcessingAttempt)))) == 1
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())
