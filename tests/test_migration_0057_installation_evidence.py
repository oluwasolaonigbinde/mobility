"""Migration 0057: assignment-bound installation evidence and display proofs."""

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

PRE_EVIDENCE_REVISION = "0056_creative_review"


def test_installation_evidence_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_EVIDENCE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_EVIDENCE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_installation_photo_is_append_only_and_populated_downgrade_refuses(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO installation_evidence_submissions "
                        "(id,assignment_id,campaign_id,driver_profile_id,vehicle_id,"
                        "submitted_by_user_id,revision,client_request_id,request_fingerprint,"
                        "device_id,captured_at,required_views,status,metadata) VALUES "
                        "('57000000-0000-0000-0000-000000000001',"
                        "'57000000-0000-0000-0000-000000000002',"
                        "'57000000-0000-0000-0000-000000000003',"
                        "'57000000-0000-0000-0000-000000000004',"
                        "'57000000-0000-0000-0000-000000000005',"
                        "'57000000-0000-0000-0000-000000000006',1,"
                        "'57000000-0000-0000-0000-000000000007',repeat('a',64),"
                        "'57000000-0000-0000-0000-000000000008',now(),"
                        "'[\"front\"]','pending_review','{}')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO installation_evidence_photos "
                        "(id,submission_id,view_code,stored_file_id) VALUES "
                        "('57000000-0000-0000-0000-000000000009',"
                        "'57000000-0000-0000-0000-000000000001','front',"
                        "'57000000-0000-0000-0000-000000000010')"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE installation_evidence_photos SET view_code=view_code "
                            "WHERE id='57000000-0000-0000-0000-000000000009'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="installation evidence is populated"):
            downgrade_to(migration_url, PRE_EVIDENCE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
