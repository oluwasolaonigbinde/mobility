"""Current PostgreSQL schema: immutable measurement runs and proof bindings."""

import asyncio

import pytest
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


def test_measurement_rows_are_append_only(
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
                        "request_fingerprint,test_only,formula_version,method_revision,"
                        "period_start_at,period_end_at,input_manifest,input_manifest_sha256,"
                        "result_manifest,result_manifest_sha256,proof_manifest,"
                        "proof_manifest_sha256,report_snapshot,report_snapshot_sha256) VALUES "
                        "('63000000-0000-0000-0000-000000000001',"
                        "'63000000-0000-0000-0000-000000000002',"
                        "'63000000-0000-0000-0000-000000000003',"
                        "'63000000-0000-0000-0000-000000000004',"
                        "'63000000-0000-0000-0000-000000000005',repeat('a',64),"
                        "true,'measurement-result-v1',"
                        "'measurement-contract-v1',now(),now() + interval '1 day',"
                        "'{}'::jsonb,repeat('b',64),'{}'::jsonb,repeat('c',64),"
                        "'{}'::jsonb,repeat('d',64),'{}'::jsonb,repeat('e',64))"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE measurement_runs SET method_revision = 'modified-after-issue'")
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
    finally:
        asyncio.run(drop_database(migration_url))
