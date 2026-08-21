"""Migration 0023: indexed route-replay signatures and fraud evidence type."""

import asyncio

from sqlalchemy import text
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

PRE_REPLAY_REVISION = "0022_current_fraud_assessments"


async def seed_fk_bypassed_replay_flag(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text(
                    "INSERT INTO fraud_flags ("
                    " trip_session_id, assignment_id, campaign_id,"
                    " driver_profile_id, vehicle_id, flag_type, severity, status,"
                    " description, evidence, detected_at) VALUES ("
                    " '10000000-0000-0000-0000-000000000001',"
                    " '10000000-0000-0000-0000-000000000002',"
                    " '10000000-0000-0000-0000-000000000003',"
                    " '10000000-0000-0000-0000-000000000004',"
                    " '10000000-0000-0000-0000-000000000005',"
                    " 'route_replay', 'high', 'open', 'migration fixture',"
                    " '{}'::jsonb, now())"
                )
            )
    finally:
        await engine.dispose()


def test_route_replay_schema_upgrade_downgrade_and_reupgrade(monkeypatch) -> None:
    source_url = configured_postgres_url()
    migration_url = asyncio.run(create_database_from_url(source_url))
    try:
        upgrade_to(migration_url, PRE_REPLAY_REVISION, monkeypatch)
        before = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT to_regclass('public.route_replay_signatures')",
            )
        )
        assert before == [(None,)]

        upgrade_to(migration_url, "head", monkeypatch)
        columns = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'route_replay_signatures'"
                " ORDER BY column_name",
            )
        )
        assert {row[0] for row in columns} >= {
            "trip_session_id",
            "trip_analytics_id",
            "status",
            "detector_version",
            "detector_config_fingerprint",
            "source_analytics_fingerprint",
            "payload_fingerprint",
            "normalized_fingerprint",
            "point_count",
            "error_code",
            "computed_at",
        }
        indexes = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT indexname FROM pg_indexes"
                " WHERE tablename = 'route_replay_signatures'",
            )
        )
        assert {row[0] for row in indexes} >= {
            "uq_route_replay_signatures_trip_session_id",
            "ix_route_replay_signatures_payload_lookup",
            "ix_route_replay_signatures_normalized_lookup",
        }
        flag_constraint = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_fraud_flags_flag_type'",
            )
        )
        assert "route_replay" in flag_constraint[0][0]

        asyncio.run(seed_fk_bypassed_replay_flag(migration_url))
        replay_flag_count = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM fraud_flags WHERE flag_type = 'route_replay'",
            )
        )
        assert replay_flag_count == [(1,)]

        downgrade_to(migration_url, PRE_REPLAY_REVISION, monkeypatch)
        removed = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT to_regclass('public.route_replay_signatures')",
            )
        )
        assert removed == [(None,)]
        restored_constraint = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_fraud_flags_flag_type'",
            )
        )
        assert "route_replay" not in restored_constraint[0][0]
        replay_flag_count = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT count(*) FROM fraud_flags WHERE flag_type = 'route_replay'",
            )
        )
        assert replay_flag_count == [(0,)]

        upgrade_to(migration_url, "head", monkeypatch)
        restored = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT to_regclass('public.route_replay_signatures')",
            )
        )
        assert restored == [("route_replay_signatures",)]
    finally:
        asyncio.run(drop_database(migration_url))
