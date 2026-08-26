"""Migration 0063: immutable measurement runs and proof bindings."""

import asyncio

import pytest
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

PRE_MEASUREMENT_REVISION = "0062_data_subject_requests"


def test_measurement_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_MEASUREMENT_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_MEASUREMENT_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_populated_measurement_downgrade_refuses_and_rows_are_append_only(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO measurement_runs "
                        "(id,organization_id,campaign_id,created_by_user_id,client_request_id,"
                        "request_fingerprint,mode,test_only,formula_version,method_revision,"
                        "period_start_at,period_end_at,input_manifest,input_manifest_sha256,"
                        "result_manifest,result_manifest_sha256,proof_manifest,"
                        "proof_manifest_sha256,report_snapshot,report_snapshot_sha256) VALUES "
                        "('63000000-0000-0000-0000-000000000001',"
                        "'63000000-0000-0000-0000-000000000002',"
                        "'63000000-0000-0000-0000-000000000003',"
                        "'63000000-0000-0000-0000-000000000004',"
                        "'63000000-0000-0000-0000-000000000005',repeat('a',64),"
                        "'performance_only',true,'measurement-result-v1',"
                        "'measurement-contract-v1',now(),now() + interval '1 day',"
                        "'{}'::jsonb,repeat('b',64),'{}'::jsonb,repeat('c',64),"
                        "'{}'::jsonb,repeat('d',64),'{}'::jsonb,repeat('e',64))"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE measurement_runs SET mode = 'roi_enabled'")
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="immutable measurement evidence"):
            downgrade_to(migration_url, PRE_MEASUREMENT_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
