"""Execute the replacement against the real previous PostgreSQL schema."""

import asyncio

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    upgrade_to,
)

from alembic import command


def test_0100_expires_obsolete_challenges_and_matches_models(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_old():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text("""
                    INSERT INTO phone_verification_challenges
                    (id, phone_version_id, code_hash, status, attempt_count, max_attempts,
                     created_at, expires_at)
                    VALUES (gen_random_uuid(), gen_random_uuid(), repeat('a',64),
                     'pending_operator', 0, 3, now(), now()+interval '10 minutes')
                """)
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(url, "0099_automatic_payout_scan_cursor", monkeypatch)
        asyncio.run(seed_old())
        upgrade_to(url, "0100_reverse_phone_verification", monkeypatch)
        assert asyncio.run(
            fetch_all(
                url,
                "SELECT status, code_hash, verified_by_user_id FROM phone_verification_challenges",
            )
        ) == [("expired", "a" * 64, None)]
        columns = {
            row[0]
            for row in asyncio.run(
                fetch_all(
                    url,
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='phone_verification_challenges'",
                )
            )
        }
        assert not columns & {
            "sent_by_user_id",
            "sent_channel",
            "sent_at",
            "operator_evidence_reference",
            "provider_message_id",
        }
        assert "verified_by_user_id" in columns
        command.check(Config("alembic.ini"))
    finally:
        asyncio.run(drop_database(url))
