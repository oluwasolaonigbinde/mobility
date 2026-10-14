"""Current PostgreSQL schema: governed campaign review lifecycle and immutable evidence."""

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


def test_campaign_review_evidence_is_append_only(monkeypatch) -> None:
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
    finally:
        asyncio.run(drop_database(migration_url))
