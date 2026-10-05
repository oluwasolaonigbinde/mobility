"""Real migration/cursor constraint round-trip; no financial schema changes."""

import asyncio

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    fetch_all,
    upgrade_to,
)

from alembic import command

PREVIOUS = "0098_paystack_edge_case_evidence"
CURRENT = "0099_automatic_payout_scan_cursor"


def test_0099_cursor_round_trip_constraint_and_current_model(monkeypatch):
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(url, PREVIOUS, monkeypatch)
        upgrade_to(url, CURRENT, monkeypatch)
        # Use the real Alembic filters for extension tables/runtime partitions.
        command.check(Config("alembic.ini"))
        assert asyncio.run(
            fetch_all(
                url,
                "SELECT candidate_cursor_at, candidate_cursor_id FROM payout_automatic_controls",
            )
        ) == [(None, None)]

        async def inspect_and_write():
            engine = create_async_engine(url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    with pytest.raises(IntegrityError):
                        async with connection.begin_nested():
                            await connection.execute(
                                text(
                                    "UPDATE payout_automatic_controls "
                                    "SET candidate_cursor_at = now()"
                                )
                            )
                    await connection.execute(
                        text(
                            "UPDATE payout_automatic_controls SET candidate_cursor_at = now(), "
                            "candidate_cursor_id = '99000000-0000-0000-0000-000000000001'"
                        )
                    )
            finally:
                await engine.dispose()

        asyncio.run(inspect_and_write())
        downgrade_to(url, PREVIOUS, monkeypatch)
        # Operational cursor can be discarded without touching money/history.
        upgrade_to(url, CURRENT, monkeypatch)
        assert asyncio.run(
            fetch_all(
                url,
                "SELECT candidate_cursor_at, candidate_cursor_id FROM payout_automatic_controls",
            )
        ) == [(None, None)]
    finally:
        asyncio.run(drop_database(url))
