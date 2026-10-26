"""Real PG cancellation and pool recovery; shortened timers keep failures deterministic."""

import asyncio
import json
from contextlib import AsyncExitStack

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, TimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.db import session as database
from app.jobs.worker import WorkerSettings


def _engine(maker, *, worker=False):
    return database.create_database_engine(
        maker.kw["bind"].url.render_as_string(hide_password=False), worker=worker
    )


def test_api_session_readiness_and_cleanup_use_the_configured_real_pool(
    postgis_db_sessionmaker, monkeypatch
):
    configured = Settings(
        environment="test",
        database_url=postgis_db_sessionmaker.kw["bind"].url.render_as_string(hide_password=False),
    )
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_sessionmaker", None)
    monkeypatch.setattr(database, "get_settings", lambda: configured)

    async def scenario():
        engine = None
        try:
            yielded = 0
            async for session in database.get_session():
                engine = database.get_engine(configured)
                assert await session.scalar(text("SELECT 1")) == 1
                yielded += 1
            assert yielded == 1
            engine = database.get_engine(configured)
            assert engine.pool.checkedout() == 0
            assert await database.check_database(configured) is True
            assert engine.pool.checkedout() == 0
            assert (
                await database.check_database(Settings(environment="test", database_url=None))
                is False
            )
            assert engine.pool.checkedout() == 0
        finally:
            if engine is not None:
                await engine.dispose()

    asyncio.run(scenario())


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


def test_trip_worker_real_deadlock_rolls_back_and_requests_redelivery(
    postgis_db_sessionmaker, settings, monkeypatch
):
    from arq import Retry
    from sqlalchemy import func
    from test_trip_processing import (
        add_pings,
        build_graph,
        create_test_daily_payout_authority,
        moving_points,
    )

    from app.core.observability import exception_diagnostic
    from app.jobs import trip_processing as jobs
    from app.models.audit import AuditEvent
    from app.models.fraud_assessment import FraudAssessment
    from app.models.impression import ImpressionEstimate
    from app.models.payout import EarningsLedgerEntry, PayoutCalculation
    from app.models.trip import TripSession
    from app.models.trip_analytics import TripAnalytics

    graph = build_graph(postgis_db_sessionmaker, "transaction-redelivery")
    create_test_daily_payout_authority(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())
    original = jobs.process_ended_trip
    models = (
        TripAnalytics,
        FraudAssessment,
        ImpressionEstimate,
        PayoutCalculation,
        EarningsLedgerEntry,
    )

    async def scenario():
        completed = asyncio.Event()
        close_cycle = asyncio.Event()
        worker_pid = None
        captured = []
        fault_pending = True
        key = int.from_bytes(graph.trip.id.bytes[:8], "big", signed=True)

        async def abort_after_real_processing(session, **kwargs):
            nonlocal worker_pid, fault_pending
            if not fault_pending:
                return await original(session, **kwargs)
            fault_pending = False
            await session.execute(text("SET LOCAL deadlock_timeout='50ms'"))
            worker_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            result = await original(session, **kwargs)
            completed.set()
            await close_cycle.wait()
            try:
                await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            except DBAPIError as exc:
                captured.append(exception_diagnostic(exc))
                raise
            return result

        monkeypatch.setattr(jobs, "process_ended_trip", abort_after_real_processing)
        ctx = {"settings": settings, "sessionmaker": postgis_db_sessionmaker, "job_try": 1}
        async with postgis_db_sessionmaker() as owner, postgis_db_sessionmaker() as observer:
            await owner.execute(text("SET LOCAL deadlock_timeout='5s'"))
            owner_pid = await owner.scalar(text("SELECT pg_backend_pid()"))
            await owner.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            task = asyncio.create_task(jobs.process_trip(ctx, str(graph.trip.id)))
            row_wait = None
            try:
                await asyncio.wait_for(completed.wait(), 5)
                row_wait = asyncio.create_task(
                    owner.scalar(
                        select(TripSession.id)
                        .where(TripSession.id == graph.trip.id)
                        .with_for_update()
                    )
                )
                async with asyncio.timeout(5):
                    while not await observer.scalar(
                        text("SELECT :worker = ANY(pg_blocking_pids(:owner))"),
                        {"owner": owner_pid, "worker": worker_pid},
                    ):
                        assert not task.done(), "worker ended before the real blocker was observed"
                        await observer.rollback()
                        await asyncio.sleep(0)
                # Worker closes the cycle only after its real row blocker is proven.
                close_cycle.set()
                first_failure = (
                    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
                )[0]
                await asyncio.wait_for(row_wait, 5)
                await owner.rollback()
                assert captured[0]["sqlstate"] == "40P01"
                assert any(
                    frame["function"] == "abort_after_real_processing"
                    for frame in captured[0]["frames"]
                )
                async with postgis_db_sessionmaker() as session:
                    for model in models:
                        assert await session.scalar(select(func.count()).select_from(model)) == 0
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(AuditEvent)
                            .where(AuditEvent.action == "worker.trip_processing.completed")
                        )
                        == 0
                    )
                requested_redelivery = isinstance(first_failure, Retry)
                assert requested_redelivery, (
                    "a proven transient PostgreSQL abort must request broker redelivery"
                )
            finally:
                for pending in (task, row_wait):
                    if pending is not None:
                        if not pending.done():
                            pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                await owner.rollback()
        ctx["job_try"] = 2
        assert (await jobs.process_trip(ctx, str(graph.trip.id)))["overall"] == "completed"
        assert (await jobs.process_trip(ctx, str(graph.trip.id)))["overall"] == "completed"
        async with postgis_db_sessionmaker() as session:
            for model in models:
                assert await session.scalar(select(func.count()).select_from(model)) == 1
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "worker.trip_processing.completed")
                )
                == 1
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_kind", ["serialization", "permanent", "cancelled"])
def test_trip_transaction_abort_classification_keeps_domain_writes_atomic(
    postgis_db_sessionmaker, settings, monkeypatch, failure_kind
):
    from arq import Retry
    from sqlalchemy import func
    from test_trip_processing import (
        add_pings,
        build_graph,
        create_test_daily_payout_authority,
        moving_points,
    )

    from app.db.integrity import database_sqlstate
    from app.jobs import trip_processing as jobs
    from app.models.payout import EarningsLedgerEntry, PayoutCalculation
    from app.models.trip_analytics import TripAnalytics

    graph = build_graph(postgis_db_sessionmaker, f"abort-{failure_kind}")
    create_test_daily_payout_authority(
        postgis_db_sessionmaker,
        campaign_id=graph.campaign.id,
        created_by_user_id=graph.admin.id,
    )
    add_pings(postgis_db_sessionmaker, trip_id=graph.trip.id, points=moving_points())
    original = jobs.process_ended_trip
    captured = []

    async def scenario():
        async with postgis_db_sessionmaker() as setup:
            await setup.execute(text("CREATE TABLE abort_guard (id int PRIMARY KEY, value int)"))
            await setup.execute(text("INSERT INTO abort_guard VALUES (1, 0)"))
            await setup.commit()

        async def abort_after_domain_writes(session, **kwargs):
            if failure_kind == "serialization":
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                assert await session.scalar(text("SELECT value FROM abort_guard WHERE id=1")) == 0
                async with postgis_db_sessionmaker() as updater:
                    await updater.execute(text("UPDATE abort_guard SET value=1 WHERE id=1"))
                    await updater.commit()
            await original(session, **kwargs)
            if failure_kind == "cancelled":
                raise asyncio.CancelledError()
            try:
                await session.execute(
                    text(
                        "UPDATE abort_guard SET value=value+1 WHERE id=1"
                        if failure_kind == "serialization"
                        else "SELECT 1/0"
                    )
                )
            except DBAPIError as exc:
                captured.append(database_sqlstate(exc))
                raise

        monkeypatch.setattr(jobs, "process_ended_trip", abort_after_domain_writes)
        ctx = {"settings": settings, "sessionmaker": postgis_db_sessionmaker, "job_try": 1}
        failure = (
            await asyncio.gather(jobs.process_trip(ctx, str(graph.trip.id)), return_exceptions=True)
        )[0]
        if failure_kind == "serialization":
            assert captured == ["40001"]
            assert isinstance(failure, Retry)
        elif failure_kind == "permanent":
            assert captured == ["22012"]
            assert isinstance(failure, DBAPIError)
            assert not isinstance(failure, Retry)
        else:
            assert isinstance(failure, asyncio.CancelledError)
            assert not isinstance(failure, Retry)
        async with postgis_db_sessionmaker() as session:
            for model in (TripAnalytics, PayoutCalculation, EarningsLedgerEntry):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(text("SELECT value FROM abort_guard WHERE id=1")) == (
                1 if failure_kind == "serialization" else 0
            )

    asyncio.run(scenario())
