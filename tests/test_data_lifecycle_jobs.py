"""Data-lifecycle jobs (S4): premake, coverage alarm, retention, evidence.

Postgres-only (Style-B migrated databases); skipped without a configured
test database. Clock-sensitive paths use the injectable ``now``.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    seed_ping_graph,
    upgrade_to,
)

import app.db.session as db_session
from app.core.config import Settings, get_settings
from app.jobs import data_lifecycle as jobs
from app.services.data_lifecycle import (
    PREMAKE_LOCK_KEY,
    RETENTION_LOCK_KEY,
    add_months,
    check_partition_coverage,
    list_partitions,
    month_start,
    premake_partitions,
    run_ping_retention,
)

RETENTION_SETTINGS = {"ping_retention_months": 12, "partition_premake_months": 4}


def make_settings() -> Settings:
    return Settings(environment="test", **RETENTION_SETTINGS)


def make_db(monkeypatch) -> str:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    upgrade_to(migration_url, "head", monkeypatch)
    return migration_url


def run_async(coro):
    return asyncio.run(coro)


async def with_session(migration_url, fn):
    engine = create_async_engine(migration_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            return await fn(session)
    finally:
        await engine.dispose()


def exec_sql(migration_url: str, sql: str, params: dict | None = None) -> None:
    async def fn(session):
        await session.execute(text(sql), params or {})
        await session.commit()

    run_async(with_session(migration_url, fn))


def partition_names(migration_url: str) -> set[str]:
    rows = asyncio.run(
        fetch_all(
            migration_url,
            """
            SELECT child.relname
            FROM pg_inherits inh
            JOIN pg_class child ON child.oid = inh.inhrelid
            JOIN pg_class parent ON parent.oid = inh.inhparent
            WHERE parent.relname = 'location_pings'
            """,
        )
    )
    return {row[0] for row in rows}


def month_partition(offset: int) -> str:
    start = add_months(month_start(datetime.now(UTC)), offset)
    return f"location_pings_p{start.strftime('%Y_%m')}"


def test_premake_is_idempotent_and_coverage_based(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    settings = make_settings()
    try:
        # Fresh empty-branch DB already covers M0-1..M0+4: premake is a no-op.
        result = run_async(
            with_session(migration_url, lambda s: premake_partitions(s, settings=settings))
        )
        assert result["created"] == []

        # A hole in future coverage is refilled by name-independent coverage
        # logic.
        hole = month_partition(2)
        exec_sql(migration_url, f"DROP TABLE {hole}")
        result = run_async(
            with_session(migration_url, lambda s: premake_partitions(s, settings=settings))
        )
        assert result["created"] == [hole]

        # PARTITION_PREMAKE_MONTHS=4 means five target months (current + 4).
        # With an injected now two months ahead, exactly the two uncovered
        # tail months are created.
        future_now = add_months(month_start(datetime.now(UTC)), 2) + timedelta(days=14)
        result = run_async(
            with_session(
                migration_url,
                lambda s: premake_partitions(s, settings=settings, now=future_now),
            )
        )
        assert result["created"] == [month_partition(5), month_partition(6)]
        result = run_async(
            with_session(
                migration_url,
                lambda s: premake_partitions(s, settings=settings, now=future_now),
            )
        )
        assert result["created"] == []
    finally:
        asyncio.run(drop_database(migration_url))


def test_concurrent_premake_waits_and_refreshes_coverage(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    settings = make_settings()
    hole = month_partition(2)
    try:
        exec_sql(migration_url, f"DROP TABLE {hole}")

        async def run_concurrently():
            engine = create_async_engine(migration_url, poolclass=NullPool)
            sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with sessionmaker() as blocker:
                    await blocker.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": PREMAKE_LOCK_KEY},
                    )
                    async with sessionmaker() as waiting:
                        task = asyncio.create_task(
                            premake_partitions(waiting, settings=settings)
                        )
                        with pytest.raises(TimeoutError):
                            await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
                        await blocker.commit()
                        return await task
            finally:
                await engine.dispose()

        result = asyncio.run(run_concurrently())
        assert result["created"] == [hole]

        # A second worker refreshes coverage after acquiring the lock and
        # observes the committed partition instead of attempting CREATE.
        result = run_async(
            with_session(migration_url, lambda s: premake_partitions(s, settings=settings))
        )
        assert result["created"] == []
    finally:
        asyncio.run(drop_database(migration_url))


def test_coverage_alarm_captures_and_raises(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    settings = make_settings()
    try:
        for offset in range(1, 5):
            exec_sql(migration_url, f"DROP TABLE {month_partition(offset)}")
        covered, upper = run_async(
            with_session(migration_url, lambda s: check_partition_coverage(s))
        )
        assert covered is False
        assert upper == add_months(month_start(datetime.now(UTC)), 1)

        captured: list[Exception] = []
        monkeypatch.setattr(jobs, "capture_exception", captured.append)

        engine = create_async_engine(migration_url, poolclass=NullPool)
        ctx = {
            "engine": engine,
            "sessionmaker": async_sessionmaker(engine, expire_on_commit=False),
            "settings": settings,
        }
        try:
            with pytest.raises(jobs.PartitionCoverageError):
                run_async(jobs.check_ping_partition_coverage(ctx))
            assert len(captured) == 1
            assert isinstance(captured[0], jobs.PartitionCoverageError)

            # The premake job restores coverage and its inline check passes.
            result = run_async(jobs.premake_ping_partitions(ctx))
            assert result["created"] == [month_partition(offset) for offset in range(1, 5)]
        finally:
            run_async(engine.dispose())
    finally:
        asyncio.run(drop_database(migration_url))


def make_client(migration_url: str, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", migration_url)
    get_settings.cache_clear()
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_sessionmaker", None)
    from app.main import create_app

    return TestClient(create_app())


def test_health_partitions_endpoint_reports_coverage(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    try:
        client = make_client(migration_url, monkeypatch)
        ok = client.get("/api/v1/health/partitions")
        assert ok.status_code == 200
        body = ok.json()
        assert body["partitions"] == "ok"
        assert body["covered_until"] is not None

        for offset in range(1, 5):
            exec_sql(migration_url, f"DROP TABLE {month_partition(offset)}")
        # Fresh client: TestClient runs each request on a new event loop, so
        # the pooled engine connection from the first request is unusable
        # (test-harness artifact; production serves one loop).
        client = make_client(migration_url, monkeypatch)
        degraded = client.get("/api/v1/health/partitions")
        assert degraded.status_code == 503
        body = degraded.json()
        assert body["status"] == "degraded"
        assert body["partitions"] == "uncovered"
    finally:
        get_settings.cache_clear()
        asyncio.run(drop_database(migration_url))


def test_health_partitions_without_database_is_not_configured(client) -> None:
    response = client.get("/api/v1/health/partitions")
    assert response.status_code == 200
    assert response.json()["partitions"] == "not_configured"


def purge_events(migration_url: str) -> list[tuple[str, str | None, int | None]]:
    return [
        (row[0], row[1], row[2])
        for row in asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT event, partition_name, row_count
                FROM data_purge_audit ORDER BY created_at, id
                """,
            )
        )
    ]


def test_retention_purges_expired_partitions_with_evidence(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, "0013_payout_v2_hourly_caps", monkeypatch)
        seeded = seed_ping_graph(migration_url)
        upgrade_to(migration_url, "head", monkeypatch)

        current_month = month_start(datetime.now(UTC))
        next_month = add_months(current_month, 1)
        straddling_batch_id = seeded["batches"]["straddling"][0]

        # Give the straddling batch a ping in the retained next-month
        # partition, so it spans expired (legacy) and retained partitions.
        async def add_future_ping(session):
            await session.execute(
                text(
                    """
                    INSERT INTO location_pings
                        (trip_session_id, batch_id, recorded_at, received_at,
                         latitude, longitude, geom, metadata)
                    VALUES
                        (:trip_id, :batch_id, :recorded_at, :recorded_at, 6.45, 3.39,
                         ST_SetSRID(ST_MakePoint(3.39, 6.45), 4326), '{}'::jsonb)
                    """
                ),
                {
                    "trip_id": seeded["trip_id"],
                    "batch_id": straddling_batch_id,
                    "recorded_at": next_month + timedelta(hours=1),
                },
            )
            await session.commit()

        run_async(with_session(migration_url, add_future_ping))

        injected_now = add_months(current_month, 13) + timedelta(days=1)

        # A recent zero-ping batch must survive (idempotent-replay contract).
        async def add_recent_empty_batch(session):
            await session.execute(
                text(
                    """
                    INSERT INTO location_ping_batches
                        (trip_session_id, idempotency_key, payload_hash,
                         pings_accepted, received_at, metadata)
                    VALUES (:trip_id, 'recent-empty', 'hash-recent-empty', 0,
                            :received_at, '{}'::jsonb)
                    """
                ),
                {
                    "trip_id": seeded["trip_id"],
                    "received_at": injected_now - timedelta(hours=1),
                },
            )
            await session.commit()

        run_async(with_session(migration_url, add_recent_empty_batch))

        # Quarantined payloads are raw location data (RM3): a retention-expired
        # row must purge with evidence; a recent one must survive.
        async def add_quarantines(session):
            await session.execute(
                text(
                    """
                    INSERT INTO quarantined_ping_batches
                        (trip_session_id, idempotency_key, payload_hash, payload,
                         ping_count, received_at, status)
                    VALUES
                        (:trip_id, 'quarantine-old', 'hash-q-old', '{"pings": []}'::jsonb,
                         1, :old_received, 'quarantined'),
                        (:trip_id, 'quarantine-recent', 'hash-q-new', '{"pings": []}'::jsonb,
                         1, :recent_received, 'quarantined')
                    """
                ),
                {
                    "trip_id": seeded["trip_id"],
                    "old_received": current_month,
                    "recent_received": injected_now - timedelta(days=1),
                },
            )
            await session.commit()

        run_async(with_session(migration_url, add_quarantines))

        legacy_ping_count = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM location_pings_legacy")
        )[0][0]

        settings = make_settings()

        async def run_retention():
            engine = create_async_engine(migration_url, poolclass=NullPool)
            sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
            try:
                return await run_ping_retention(
                    engine, sessionmaker, settings=settings, now=injected_now
                )
            finally:
                await engine.dispose()

        result = asyncio.run(run_retention())
        assert result["dropped"] == ["location_pings_legacy"]
        assert result["finalized"] == []
        assert result["batches_purged"] == 2  # oldest + middle: zero pings remain
        assert result["quarantines_purged"] == 1  # the retention-expired row only

        names = partition_names(migration_url)
        assert "location_pings_legacy" not in names
        assert f"location_pings_p{next_month.strftime('%Y_%m')}" in names

        # The straddling batch survives with exactly its retained ping.
        batches = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT idempotency_key FROM location_ping_batches ORDER BY idempotency_key",
            )
        )
        assert [row[0] for row in batches] == ["batch-straddling", "recent-empty"]
        remaining_pings = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT batch_id::text, recorded_at FROM location_pings",
            )
        )
        assert len(remaining_pings) == 1
        assert remaining_pings[0][0] == straddling_batch_id

        # Sessions and derived rows survive retention.
        trips = asyncio.run(fetch_all(migration_url, "SELECT count(*) FROM trip_sessions"))
        assert trips == [(1,)]

        surviving_quarantines = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT idempotency_key FROM quarantined_ping_batches",
            )
        )
        assert [row[0] for row in surviving_quarantines] == ["quarantine-recent"]

        events = purge_events(migration_url)
        assert ("purge_started", "location_pings_legacy", legacy_ping_count) in events
        assert ("dropped", "location_pings_legacy", None) in events
        assert ("batches_purged", None, 2) in events
        assert ("quarantined_batches_purged", None, 1) in events
        # Evidence precedes destruction: purge_started ordered before dropped.
        event_kinds = [event for event, name, _ in events if name == "location_pings_legacy"]
        assert event_kinds.index("purge_started") < event_kinds.index("dropped")

        # Re-run: idempotent, no duplicate evidence.
        result = asyncio.run(run_retention())
        assert result["dropped"] == []
        assert result["batches_purged"] == 0
        assert result["quarantines_purged"] == 0
        assert purge_events(migration_url) == events
    finally:
        asyncio.run(drop_database(migration_url))


def test_retention_is_a_noop_while_lock_is_held(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    settings = make_settings()
    try:

        async def scenario():
            engine = create_async_engine(migration_url, poolclass=NullPool)
            sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
            holder = await engine.connect()
            try:
                holder_autocommit = await holder.execution_options(
                    isolation_level="AUTOCOMMIT"
                )
                acquired = (
                    await holder_autocommit.execute(
                        text("SELECT pg_try_advisory_lock(:key)"),
                        {"key": RETENTION_LOCK_KEY},
                    )
                ).scalar_one()
                assert acquired is True
                result = await run_ping_retention(engine, sessionmaker, settings=settings)
                assert result == {"skipped": "lock_held"}
            finally:
                await holder.close()
                await engine.dispose()

        asyncio.run(scenario())
    finally:
        asyncio.run(drop_database(migration_url))


def induce_pending_detach(migration_url: str, partition: str) -> None:
    """Leave a real interrupted DETACH ... CONCURRENTLY behind: hold a
    repeatable-read snapshot over the parent so the detach blocks between
    its two internal transactions, then cancel it."""

    async def interrupt_detach():
        engine = create_async_engine(migration_url, poolclass=NullPool)
        blocker = await engine.connect()
        detacher = await engine.connect()
        try:
            blocker_ac = await blocker.execution_options(isolation_level="REPEATABLE READ")
            await blocker_ac.execute(text("SELECT count(*) FROM location_pings"))

            detacher_ac = await detacher.execution_options(isolation_level="AUTOCOMMIT")
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    detacher_ac.execute(
                        text(
                            "ALTER TABLE location_pings DETACH PARTITION"
                            f" {partition} CONCURRENTLY"
                        )
                    ),
                    timeout=2.0,
                )
        finally:
            await blocker.close()
            await detacher.close()
            await engine.dispose()

    asyncio.run(interrupt_detach())
    assert detach_pending_flags(migration_url, partition) == [True]


def detach_pending_flags(migration_url: str, partition: str) -> list[bool]:
    return [
        bool(row[0])
        for row in asyncio.run(
            fetch_all(
                migration_url,
                """
                SELECT inh.inhdetachpending
                FROM pg_inherits inh
                JOIN pg_class child ON child.oid = inh.inhrelid
                WHERE child.relname = :partition
                """,
                {"partition": partition},
            )
        )
    ]


def insert_purge_started(
    migration_url: str,
    partition: str,
    *,
    complete: bool = True,
    mismatched_bounds: bool = False,
) -> None:
    range_from = None
    range_to = None
    row_count = None
    if complete:
        partitions = run_async(
            with_session(migration_url, lambda session: list_partitions(session))
        )
        info = next((item for item in partitions if item.name == partition), None)
        if info is not None:
            range_from = info.lower
            range_to = info.upper
        else:
            match = partition.removeprefix("location_pings_p")
            range_from = datetime.strptime(match, "%Y_%m").replace(tzinfo=UTC)
            range_to = add_months(range_from, 1)
        if mismatched_bounds:
            range_from = add_months(range_from, -1)
        row_count = asyncio.run(
            fetch_all(migration_url, f"SELECT count(*) FROM {partition}")
        )[0][0]
    exec_sql(
        migration_url,
        "INSERT INTO data_purge_audit"
        " (partition_name, range_from, range_to, event, row_count,"
        "  retention_months, initiated_by, job_run_id)"
        " VALUES (:partition, :range_from, :range_to, 'purge_started', :row_count,"
        "         12, 'system', 'test-crash-run')",
        {
            "partition": partition,
            "range_from": range_from,
            "range_to": range_to,
            "row_count": row_count,
        },
    )


def run_retention_once(migration_url: str, now=None):
    settings = make_settings()

    async def run():
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            return await run_ping_retention(engine, sessionmaker, settings=settings, now=now)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def seeded_migrated_db(monkeypatch) -> str:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    upgrade_to(migration_url, "0013_payout_v2_hourly_caps", monkeypatch)
    seed_ping_graph(migration_url)
    upgrade_to(migration_url, "head", monkeypatch)
    return migration_url


def expired_now():
    return add_months(month_start(datetime.now(UTC)), 13) + timedelta(days=1)


def test_authorized_expired_pending_detach_is_finalized_and_completed(monkeypatch) -> None:
    migration_url = seeded_migrated_db(monkeypatch)
    try:
        # Simulate this job crashing after writing its evidence: the
        # purge_started row exists, the detach was interrupted.
        insert_purge_started(migration_url, "location_pings_legacy")
        induce_pending_detach(migration_url, "location_pings_legacy")

        result = run_retention_once(migration_url, now=expired_now())
        assert result["finalized"] == ["location_pings_legacy"]
        assert "location_pings_legacy" in result["dropped"]

        events = purge_events(migration_url)
        kinds = [event for event, name, _ in events if name == "location_pings_legacy"]
        assert kinds.index("detach_finalized") < kinds.index("dropped")
        assert "location_pings_legacy" not in partition_names(migration_url)
    finally:
        asyncio.run(drop_database(migration_url))


def test_unclaimed_pending_detach_is_refused_and_left_untouched(monkeypatch) -> None:
    migration_url = seeded_migrated_db(monkeypatch)
    try:
        # No purge_started evidence: this detach is not ours (e.g. manual).
        induce_pending_detach(migration_url, "location_pings_legacy")

        captured: list[Exception] = []
        import app.services.data_lifecycle as service

        monkeypatch.setattr(service, "capture_exception", captured.append)

        batches_before = asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM location_ping_batches")
        )
        result = run_retention_once(migration_url, now=expired_now())
        assert result["finalized"] == []
        assert result["dropped"] == []
        assert result["refused_pending"] == ["location_pings_legacy"]
        # Untouched: still a partition, still pending.
        assert "location_pings_legacy" in partition_names(migration_url)
        assert detach_pending_flags(migration_url, "location_pings_legacy") == [True]
        # Alerted.
        assert len(captured) == 1
        assert "location_pings_legacy" in str(captured[0])
        # No destruction evidence was fabricated, and the batch purge was
        # skipped (a pending partition is invisible through the parent — a
        # purge here would cascade-delete its pings).
        assert purge_events(migration_url) == []
        assert (
            asyncio.run(
                fetch_all(migration_url, "SELECT count(*) FROM location_ping_batches")
            )
            == batches_before
        )
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize("evidence", ["null_bounds", "mismatched_bounds", "terminal"])
def test_nonmatching_pending_detach_evidence_is_refused(monkeypatch, evidence) -> None:
    migration_url = seeded_migrated_db(monkeypatch)
    try:
        insert_purge_started(
            migration_url,
            "location_pings_legacy",
            complete=evidence != "null_bounds",
            mismatched_bounds=evidence == "mismatched_bounds",
        )
        if evidence == "terminal":
            exec_sql(
                migration_url,
                "INSERT INTO data_purge_audit"
                " (partition_name, event, retention_months, initiated_by, job_run_id)"
                " VALUES ('location_pings_legacy', 'dropped', 12, 'system', 'old-run')",
            )
        induce_pending_detach(migration_url, "location_pings_legacy")

        result = run_retention_once(migration_url, now=expired_now())
        assert result["finalized"] == []
        assert result["dropped"] == []
        assert result["refused_pending"] == ["location_pings_legacy"]
        assert "location_pings_legacy" in partition_names(migration_url)
        assert detach_pending_flags(migration_url, "location_pings_legacy") == [True]
    finally:
        asyncio.run(drop_database(migration_url))


def test_non_expired_pending_detach_is_refused_and_left_untouched(monkeypatch) -> None:
    migration_url = seeded_migrated_db(monkeypatch)
    try:
        # Evidence exists, but under current settings the partition is no
        # longer retention-expired (e.g. the window was widened after a
        # crash): refuse.
        insert_purge_started(migration_url, "location_pings_legacy")
        induce_pending_detach(migration_url, "location_pings_legacy")

        captured: list[Exception] = []
        import app.services.data_lifecycle as service

        monkeypatch.setattr(service, "capture_exception", captured.append)

        # A refused run must block ALL destruction — including quarantine
        # purge — and say so explicitly in its result.
        exec_sql(
            migration_url,
            "INSERT INTO quarantined_ping_batches"
            " (trip_session_id, idempotency_key, payload_hash, payload, ping_count,"
            "  received_at, status)"
            " SELECT id, 'quarantine-blocked', 'hash-qb', '{\"pings\": []}'::jsonb, 1,"
            "        now() - interval '20 months', 'quarantined'"
            " FROM trip_sessions LIMIT 1",
        )

        result = run_retention_once(migration_url)  # real clock: not expired
        assert result["finalized"] == []
        assert result["dropped"] == []
        assert result["refused_pending"] == ["location_pings_legacy"]
        assert result["quarantines_purged"] == 0
        assert result["purge_blocked_reason"] == "refused_pending_detach"
        assert "location_pings_legacy" in partition_names(migration_url)
        assert detach_pending_flags(migration_url, "location_pings_legacy") == [True]
        assert len(captured) == 1
        events = purge_events(migration_url)
        assert [e for e, _, _ in events] == ["purge_started"]
        # The retention-expired quarantine row survived the blocked run.
        quarantines = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT idempotency_key FROM quarantined_ping_batches",
            )
        )
        assert [row[0] for row in quarantines] == ["quarantine-blocked"]
    finally:
        asyncio.run(drop_database(migration_url))


def test_drop_refused_when_dropped_evidence_conflicts(monkeypatch) -> None:
    migration_url = make_db(monkeypatch)
    try:
        # A standalone table matching the partition pattern, with a purge
        # trail AND a pre-existing 'dropped' evidence row: the evidence
        # cannot account for this table existing — fail closed.
        exec_sql(migration_url, "CREATE TABLE location_pings_p2020_01 (id int)")
        insert_purge_started(migration_url, "location_pings_p2020_01")
        exec_sql(
            migration_url,
            "INSERT INTO data_purge_audit"
            " (partition_name, event, retention_months, initiated_by, job_run_id)"
            " VALUES ('location_pings_p2020_01', 'dropped', 12, 'system', 'old-run')",
        )

        with pytest.raises(RuntimeError, match="Refusing to drop location_pings_p2020_01"):
            run_retention_once(migration_url)

        # The table remains present; no second 'dropped' row was written.
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT 1 FROM information_schema.tables"
                " WHERE table_name = 'location_pings_p2020_01'",
            )
        )
        assert tables == [(1,)]
        dropped_rows = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM data_purge_audit"
                " WHERE partition_name = 'location_pings_p2020_01'"
                " AND event = 'dropped'",
            )
        )
        assert dropped_rows == [(1,)]

        # The advisory lock was released despite the failure: a subsequent
        # run still acquires it (and fails the same way, loudly).
        with pytest.raises(RuntimeError):
            run_retention_once(migration_url)
    finally:
        asyncio.run(drop_database(migration_url))
