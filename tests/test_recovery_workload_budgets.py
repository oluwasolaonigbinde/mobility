"""Real PostgreSQL and normal bounded workloads used to qualify fixed budgets."""

import asyncio
import inspect
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from arq.worker import Worker
from conftest import auth_headers
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from test_file_scanning import FakeScanner, advertiser_with_org, confirm_png
from test_req217_reports import PASSWORD, driving_trip, owner_graph
from test_stored_files import FakeStorageProvider

from app.api.v1.dependencies import get_storage_provider
from app.jobs import file_scanning
from app.services.campaign_report_delivery import publish_campaign_report
from app.services.data_lifecycle import run_ping_retention


def test_database_capacity_and_library_defaults(postgis_db_sessionmaker):
    async def observe():
        engine = postgis_db_sessionmaker.kw["bind"]
        async with engine.connect() as connection:
            actual = {
                name: await connection.scalar(text(f"SHOW {name}"))
                for name in (
                    "max_connections",
                    "superuser_reserved_connections",
                    "statement_timeout",
                    "lock_timeout",
                    "idle_in_transaction_session_timeout",
                )
            }
        defaults = create_async_engine(engine.url)
        actual.update(
            library_pool_size=defaults.pool.size(),
            library_max_overflow=defaults.pool._max_overflow,
            library_pool_wait=defaults.pool.timeout(),
            arq_job_timeout=inspect.signature(Worker).parameters["job_timeout"].default,
            arq_max_jobs=inspect.signature(Worker).parameters["max_jobs"].default,
        )
        await defaults.dispose()
        assert int(actual["max_connections"]) >= 31 + int(actual["superuser_reserved_connections"])
        assert actual["library_pool_size"] == 5
        assert actual["library_max_overflow"] == 10
        assert actual["library_pool_wait"] == 30
        assert actual["arq_job_timeout"] == 300
        assert actual["arq_max_jobs"] == 10
        print("RECOVERY_DATABASE_CAPACITY=" + json.dumps(actual, sort_keys=True))

    asyncio.run(observe())


def test_normal_report_scan_and_two_connection_maintenance(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
):
    timings = {}
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    owner, _, campaign = owner_graph(db_sessionmaker, "runtime-budgets")
    for index in range(3):
        driving_trip(
            db_sessionmaker,
            campaign=campaign,
            suffix=f"budget-{index}",
            ended_at=datetime(2020, 1, 2, 12, tzinfo=UTC),
        )
    started = time.monotonic()
    response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=auth_headers(db_client, owner.email, PASSWORD),
        json={
            "client_request_id": str(uuid4()),
            "campaign_id": str(campaign.id),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
        },
    )
    assert response.status_code == 202, response.text
    assert (
        asyncio.run(
            publish_campaign_report(
                db_sessionmaker,
                report_id=response.json()["id"],
                storage=storage,
            )
        )
        == "ready"
    )
    timings["populated_report_seconds"] = time.monotonic() - started

    scanner = FakeScanner()
    advertiser, _ = advertiser_with_org(db_sessionmaker, "runtime-scan@example.invalid")
    confirm_png(db_client, storage, advertiser.email)
    monkeypatch.setattr(file_scanning, "build_storage_provider", lambda _: storage)
    monkeypatch.setattr(file_scanning, "build_malware_scanner", lambda _: scanner)
    started = time.monotonic()
    assert asyncio.run(
        file_scanning.scan_pending_files({"settings": settings, "sessionmaker": db_sessionmaker})
    ) == {"selected": 1, "clean": 1, "unsafe": 0, "failed": 0}
    timings["clean_scan_seconds"] = time.monotonic() - started

    started = time.monotonic()
    result = asyncio.run(
        run_ping_retention(
            db_sessionmaker.kw["bind"],
            db_sessionmaker,
            settings=settings,
        )
    )
    assert "skipped" not in result
    timings["maintenance_seconds"] = time.monotonic() - started
    # Normal bounded local workloads must fit the already-existing report lease
    # and scanner bound before any new timeout constants are selected.
    assert timings["populated_report_seconds"] < 120
    assert timings["clean_scan_seconds"] < 30
    assert timings["maintenance_seconds"] < 120
    print("RECOVERY_NORMAL_WORKLOADS=" + json.dumps(timings, sort_keys=True))


def test_slow_storage_idle_termination_fails_safely_and_next_report_recovers(
    db_client, db_sessionmaker, monkeypatch
):
    from sqlalchemy import event, select
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import session as database
    from app.models.campaign_report import CampaignReport
    from app.models.stored_file import StoredFile
    from app.services import campaign_report_delivery as delivery

    owner, _, campaign = owner_graph(db_sessionmaker, "slow-storage-budget")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    payload = {
        "client_request_id": str(uuid4()),
        "campaign_id": str(campaign.id),
        "start_date": "2020-01-02",
        "end_date": "2020-01-02",
    }
    created = db_client.post("/api/v1/advertiser/reports", headers=headers, json=payload)
    assert created.status_code == 202
    identity = created.json()["id"]
    fixture_engine = db_sessionmaker.kw["bind"]
    options = fixture_engine.get_execution_options()
    # Scale only this test's idle timer; the production SHOW assertions are separate.
    production_idle = database.DATABASE_IDLE_TRANSACTION_TIMEOUT_MS
    monkeypatch.setattr(database, "DATABASE_IDLE_TRANSACTION_TIMEOUT_MS", 1000)
    failures = []
    original_failed = delivery._failed

    async def observed_failure(*args, **kwargs):
        failures.append(kwargs["error"])
        return await original_failed(*args, **kwargs)

    monkeypatch.setattr(delivery, "_failed", observed_failure)

    class SlowRead(FakeStorageProvider):
        reads = 0

        async def stat(self, key):
            self.reads += 1
            if self.reads == 3:
                await asyncio.sleep(1.5)
            return await super().stat(key)

    async def scenario():
        engine = database.create_database_engine(
            fixture_engine.url.render_as_string(hide_password=False), worker=True
        )
        # Restore the default immediately after constructing the fault engine.
        # Normal recovery below gets a separate pool with production timers.
        monkeypatch.setattr(database, "DATABASE_IDLE_TRANSACTION_TIMEOUT_MS", production_idle)
        engine.update_execution_options(**options)
        schema = options["schema_translate_map"][None]

        @event.listens_for(engine.sync_engine, "connect")
        def fixture_search_path(connection, _record):
            connection.run_async(lambda raw: raw.execute(f'SET search_path TO "{schema}",public'))

        maker = async_sessionmaker(engine, expire_on_commit=False)
        recovery_engine = None
        storage = SlowRead()
        try:
            assert (
                await publish_campaign_report(maker, report_id=identity, storage=storage)
                == "failed"
            )
            assert len(failures) == 1
            assert isinstance(failures[0], DBAPIError)
            assert failures[0].connection_invalidated
            async with maker() as session:
                report = await session.get(CampaignReport, identity)
                assert report.status == "failed"
                assert report.error_code == "REPORT_PREPARATION_FAILED"
                assert report.processing_token is None
                frozen = report.snapshot_sha256
                assert list(await session.scalars(select(StoredFile))) == []
            assert (
                await publish_campaign_report(maker, report_id=identity, storage=storage)
                == "skipped"
            )
            # The existing new-request path succeeds after the failed connection
            # is invalidated; no report lease or retry policy is changed.
            next_response = db_client.post(
                "/api/v1/advertiser/reports",
                headers=headers,
                json={**payload, "client_request_id": str(uuid4())},
            )
            assert next_response.status_code == 202
            next_id = next_response.json()["id"]
            recovery_engine = database.create_database_engine(
                fixture_engine.url.render_as_string(hide_password=False), worker=True
            )
            recovery_engine.update_execution_options(**options)
            event.listen(recovery_engine.sync_engine, "connect", fixture_search_path)
            recovery_maker = async_sessionmaker(recovery_engine, expire_on_commit=False)
            async with recovery_engine.connect() as connection:
                assert (
                    await connection.scalar(text("SHOW idle_in_transaction_session_timeout"))
                    == "1min"
                )
            assert (
                await publish_campaign_report(recovery_maker, report_id=next_id, storage=storage)
                == "ready"
            )
            async with recovery_maker() as session:
                original = await session.get(CampaignReport, identity)
                assert original.snapshot_sha256 == frozen
                assert original.status == "failed"
                assert await session.scalar(text("SELECT 1")) == 1
        finally:
            await engine.dispose()
            if recovery_engine is not None:
                await recovery_engine.dispose()

    asyncio.run(scenario())
