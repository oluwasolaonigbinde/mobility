"""Migration 0043: governed campaign review lifecycle and immutable evidence."""

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

PRE_REVIEW_REVISION = "0042_invoice_number_prefix_sequence"


def test_campaign_review_empty_down_up_preserves_existing_campaigns(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO campaigns "
                        "(id, organization_id, created_by_user_id, name, status, currency, "
                        "metadata) "
                        "VALUES ('41000000-0000-0000-0000-000000000001', "
                        "'41000000-0000-0000-0000-000000000002', "
                        "'41000000-0000-0000-0000-000000000003', "
                        "'Preserved campaign', 'draft', 'NGN', '{}')"
                    )
                )
        finally:
            await engine.dispose()

    async def read() -> tuple[str, str]:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT name, status FROM campaigns WHERE id = "
                            "'41000000-0000-0000-0000-000000000001'"
                        )
                    )
                ).one()
                return row[0], row[1]
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        asyncio.run(seed())
        assert asyncio.run(read()) == ("Preserved campaign", "draft")
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(read()) == ("Preserved campaign", "draft")
    finally:
        asyncio.run(drop_database(migration_url))


def test_campaign_review_evidence_is_append_only_and_blocks_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO campaigns "
                        "(id, organization_id, created_by_user_id, name, status, currency, "
                        "metadata) "
                        "VALUES ('41000000-0000-0000-0000-000000000011', "
                        "'41000000-0000-0000-0000-000000000012', "
                        "'41000000-0000-0000-0000-000000000013', "
                        "'Review campaign', 'pending_review', 'NGN', '{}')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_review_events "
                        "(id, campaign_id, actor_user_id, prior_status, new_status, "
                        "reviewed_snapshot, reviewed_snapshot_sha256, created_at) VALUES "
                        "('41000000-0000-0000-0000-000000000014', "
                        "'41000000-0000-0000-0000-000000000011', "
                        "'41000000-0000-0000-0000-000000000013', 'draft', "
                        "'pending_review', '{\"name\": \"Review campaign\"}', "
                        "repeat('a', 64), now())"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_review_events SET prior_status = prior_status "
                            "WHERE id = '41000000-0000-0000-0000-000000000014'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0043 downgrade blocked"):
            downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
