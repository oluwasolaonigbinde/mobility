"""Migration 0056: governed managed-creative review authority."""

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

PRE_REVIEW_REVISION = "0055_kyc_key_custody"


def test_creative_review_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_creative_review_evidence_is_append_only_and_blocks_populated_downgrade(
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
                        "INSERT INTO campaign_creatives "
                        "(id,campaign_id,name,creative_type,placement,status,metadata) VALUES "
                        "('56000000-0000-0000-0000-000000000001',"
                        "'56000000-0000-0000-0000-000000000002','Review creative',"
                        "'image','vehicle_exterior','pending_review','{}')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO creative_review_events "
                        "(id,creative_id,actor_user_id,prior_status,new_status,"
                        "reviewed_snapshot,reviewed_snapshot_sha256) VALUES "
                        "('56000000-0000-0000-0000-000000000003',"
                        "'56000000-0000-0000-0000-000000000001',"
                        "'56000000-0000-0000-0000-000000000004','draft',"
                        "'pending_review','{\"name\":\"Review creative\"}',repeat('a',64))"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE creative_review_events SET prior_status=prior_status "
                            "WHERE id='56000000-0000-0000-0000-000000000003'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="creative review authority is populated"):
            downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
