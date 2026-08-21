"""Migration 0024: serialized fraud-review states and active-hold dedup."""

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
    fetch_all,
    upgrade_to,
)

PRE_REVIEW_REVISION = "0023_route_replay_signatures"


async def seed_flag(
    migration_url: str,
    *,
    status: str,
    reviewed: bool = False,
) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            columns = ""
            values = ""
            if reviewed:
                columns = ", reviewed_by_user_id, reviewed_at, resolution_note"
                values = (
                    ", '20000000-0000-0000-0000-000000000006',"
                    " now(), 'confirmed by migration fixture'"
                )
            await connection.execute(
                text(
                    "INSERT INTO fraud_flags ("
                    " trip_session_id, assignment_id, campaign_id,"
                    " driver_profile_id, vehicle_id, flag_type, severity, status,"
                    f" description, evidence, detected_at{columns}) VALUES ("
                    " '20000000-0000-0000-0000-000000000001',"
                    " '20000000-0000-0000-0000-000000000002',"
                    " '20000000-0000-0000-0000-000000000003',"
                    " '20000000-0000-0000-0000-000000000004',"
                    " '20000000-0000-0000-0000-000000000005',"
                    f" 'impossible_speed', 'high', '{status}', 'migration fixture',"
                    f" '{{}}'::jsonb, now(){values})"
                )
            )
    finally:
        await engine.dispose()


def test_fraud_review_schema_upgrade_downgrade_and_reupgrade(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        before = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'fraud_flags'"
                " AND column_name IN ('reviewed_by_user_id', 'reviewed_at', 'resolution_note')",
            )
        )
        assert before == []

        upgrade_to(migration_url, "head", monkeypatch)
        columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'fraud_flags' ORDER BY column_name",
            )
        )
        assert {row[0] for row in columns} >= {
            "reviewed_by_user_id",
            "reviewed_at",
            "resolution_note",
        }
        constraints = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid = 'fraud_flags'::regclass",
            )
        )
        by_name = dict(constraints)
        assert "confirmed" in by_name["ck_fraud_flags_status"]
        assert "reviewed_at" in by_name["ck_fraud_flags_review_evidence"]
        indexes = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT indexname, indexdef FROM pg_indexes"
                " WHERE tablename = 'fraud_flags'",
            )
        )
        by_index = dict(indexes)
        assert "uq_fraud_flags_trip_open_flag_type" not in by_index
        assert "= ANY" in by_index["uq_fraud_flags_trip_nonterminal_flag_type"]
        assert all(
            status in by_index["uq_fraud_flags_trip_nonterminal_flag_type"]
            for status in ("open", "acknowledged", "confirmed")
        )

        asyncio.run(seed_flag(migration_url, status="confirmed", reviewed=True))
        downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        downgraded = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT status FROM fraud_flags WHERE flag_type = 'impossible_speed'",
            )
        )
        assert downgraded == [("acknowledged",)]
        downgraded_columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'fraud_flags'"
                " AND column_name IN ('reviewed_by_user_id', 'reviewed_at', 'resolution_note')",
            )
        )
        assert downgraded_columns == []

        async def remove_fixture() -> None:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.begin() as connection:
                    await connection.execute(text("DELETE FROM fraud_flags"))
            finally:
                await engine.dispose()

        asyncio.run(remove_fixture())
        upgrade_to(migration_url, "head", monkeypatch)
        restored_columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'fraud_flags'"
                " AND column_name IN ('reviewed_by_user_id', 'reviewed_at', 'resolution_note')",
            )
        )
        assert {row[0] for row in restored_columns} == {
            "reviewed_by_user_id",
            "reviewed_at",
            "resolution_note",
        }
    finally:
        asyncio.run(drop_database(migration_url))


def test_fraud_review_upgrade_rejects_legacy_non_open_rows(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        asyncio.run(seed_flag(migration_url, status="dismissed"))

        with pytest.raises(DBAPIError, match="cannot attribute pre-existing"):
            upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
