"""Migration 0060: recurring proof challenges and spot-check authority."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_VERIFICATION_REVISION = "0059_campaign_cancellations"


def test_evidence_verification_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_VERIFICATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_VERIFICATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_populated_evidence_verification_downgrade_refuses(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO evidence_verifications "
                        "(id,assignment_id,campaign_id,driver_profile_id,vehicle_id,"
                        "source_trip_session_id,verification_type,status,issued_by_user_id,"
                        "client_request_id,request_fingerprint,metadata,issued_at) VALUES "
                        "('60000000-0000-0000-0000-000000000001',"
                        "'60000000-0000-0000-0000-000000000002',"
                        "'60000000-0000-0000-0000-000000000003',"
                        "'60000000-0000-0000-0000-000000000004',"
                        "'60000000-0000-0000-0000-000000000005',"
                        "'60000000-0000-0000-0000-000000000006','physical_spot_check',"
                        "'pending','60000000-0000-0000-0000-000000000007',"
                        "'60000000-0000-0000-0000-000000000008',repeat('a',64),'{}',now())"
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="evidence verification"):
            downgrade_to(migration_url, PRE_VERIFICATION_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
