"""Migration 0059: immutable cancellation cutoff and liability release."""

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

PRE_CANCELLATION_REVISION = "0058_campaign_changes"


def test_campaign_cancellations_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_CANCELLATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_CANCELLATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_cancellation_and_settlement_are_append_only_and_release_is_terminal(
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
                        "INSERT INTO campaign_cancellations "
                        "(id,campaign_id,organization_id,requested_by_user_id,client_request_id,"
                        "request_fingerprint,reason,prior_status,cutoff_at,disposition,"
                        "refundable_amount,currency,released_liability_amount,"
                        "cancelled_assignment_count) VALUES "
                        "('59000000-0000-0000-0000-000000000001',"
                        "'59000000-0000-0000-0000-000000000002',"
                        "'59000000-0000-0000-0000-000000000003',"
                        "'59000000-0000-0000-0000-000000000004',"
                        "'59000000-0000-0000-0000-000000000005',repeat('a',64),"
                        "'synthetic cancellation','active',now(),'no_settlement',0,'NGN',20,1)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_cancellation_settlement_revisions "
                        "(id,cancellation_id,campaign_id,revision_number,effective_from,"
                        "snapshot,snapshot_sha256) VALUES "
                        "('59000000-0000-0000-0000-000000000006',"
                        "'59000000-0000-0000-0000-000000000001',"
                        "'59000000-0000-0000-0000-000000000002',1,now(),"
                        "'{\"disposition\":\"no_settlement\"}',repeat('b',64))"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_liability_reservations "
                        "(id,campaign_id,assignment_id,assignment_rule_binding_id,"
                        "authorization_id,status,covered_vehicle_days,hourly_rate,"
                        "daily_hours_cap,requested_amount,reserved_amount,requested_at,"
                        "reserved_at,formula_version) VALUES "
                        "('59000000-0000-0000-0000-000000000007',"
                        "'59000000-0000-0000-0000-000000000002',"
                        "'59000000-0000-0000-0000-000000000008',"
                        "'59000000-0000-0000-0000-000000000009',"
                        "'59000000-0000-0000-0000-000000000010','reserved',1,20,1,20,20,"
                        "now(),now(),'liability_v1')"
                    )
                )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE campaign_liability_reservations SET status='released',"
                        "released_at=now(),"
                        "release_cancellation_id='59000000-0000-0000-0000-000000000001' "
                        "WHERE id='59000000-0000-0000-0000-000000000007'"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="released liability is immutable"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_liability_reservations SET released_at=now() "
                            "WHERE id='59000000-0000-0000-0000-000000000007'"
                        )
                    )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_cancellations SET reason='changed' "
                            "WHERE id='59000000-0000-0000-0000-000000000001'"
                        )
                    )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_cancellation_settlement_revisions "
                            "SET revision_number=2 "
                            "WHERE id='59000000-0000-0000-0000-000000000006'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="campaign cancellations are populated"):
            downgrade_to(migration_url, PRE_CANCELLATION_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
