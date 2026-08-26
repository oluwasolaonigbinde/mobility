"""Migration 0062: manual cross-store DSR evidence."""

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

PRE_DSR_REVISION = "0061_email_delivery"


def test_dsr_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_DSR_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_DSR_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_populated_dsr_downgrade_refuses_and_assessment_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO data_subject_requests "
                        "(id,subject_user_id,request_type,status,opened_by_user_id,"
                        "client_request_id,request_fingerprint,requested_at,"
                        "identity_verified_at,identity_verified_by_user_id) VALUES "
                        "('62000000-0000-0000-0000-000000000001',"
                        "'62000000-0000-0000-0000-000000000002','access','identity_verified',"
                        "'62000000-0000-0000-0000-000000000003',"
                        "'62000000-0000-0000-0000-000000000004',repeat('a',64),now(),now(),"
                        "'62000000-0000-0000-0000-000000000003')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO data_subject_location_assessments "
                        "(id,request_id,location,disposition,record_count,data_class_counts,"
                        "evidence_reference,assessed_by_user_id,client_request_id,"
                        "request_fingerprint) VALUES "
                        "('62000000-0000-0000-0000-000000000005',"
                        "'62000000-0000-0000-0000-000000000001','database','provided',1,"
                        "jsonb_build_object('account_identity', 1),'synthetic',"
                        "'62000000-0000-0000-0000-000000000003',"
                        "'62000000-0000-0000-0000-000000000006',repeat('b',64))"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE data_subject_location_assessments SET record_count = 2"
                        )
                    )
            with pytest.raises(DBAPIError, match="identity is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE data_subject_requests SET request_type = 'rectification'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only evidence"):
                async with engine.begin() as connection:
                    await connection.execute(text("DELETE FROM data_subject_requests"))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="data-subject request evidence"):
            downgrade_to(migration_url, PRE_DSR_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
