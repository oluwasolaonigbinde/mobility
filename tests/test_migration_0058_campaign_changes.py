"""Migration 0058: governed effective-dated campaign changes."""

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

PRE_CAMPAIGN_CHANGES_REVISION = "0057_installation_evidence"


def test_campaign_changes_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_CAMPAIGN_CHANGES_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_CAMPAIGN_CHANGES_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_campaign_change_revision_is_append_only_and_populated_downgrade_refuses(
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
                        "INSERT INTO campaign_change_requests "
                        "(id,campaign_id,organization_id,requested_by_user_id,"
                        "client_request_id,request_fingerprint,proposed_changes,"
                        "classifications,impact_preview,status,requested_liability_amount,"
                        "reserved_liability_amount,applied_at) VALUES "
                        "('58000000-0000-0000-0000-000000000001',"
                        "'58000000-0000-0000-0000-000000000002',"
                        "'58000000-0000-0000-0000-000000000003',"
                        "'58000000-0000-0000-0000-000000000004',"
                        "'58000000-0000-0000-0000-000000000005',repeat('a',64),"
                        "'{\"budget_amount\":\"1200.00\"}', '[\"expansion\"]',"
                        "'{\"before\":{}}','applied',0,0,now())"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_change_revisions "
                        "(id,campaign_id,request_id,revision_number,effective_from,snapshot,"
                        "snapshot_sha256,applied_by_user_id) VALUES "
                        "('58000000-0000-0000-0000-000000000006',"
                        "'58000000-0000-0000-0000-000000000002',"
                        "'58000000-0000-0000-0000-000000000001',1,now(),"
                        "'{\"budget_amount\":\"1200.00\"}',repeat('b',64),"
                        "'58000000-0000-0000-0000-000000000004')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_change_requests "
                        "(id,campaign_id,organization_id,requested_by_user_id,"
                        "client_request_id,request_fingerprint,proposed_changes,"
                        "classifications,impact_preview,status,requested_liability_amount) VALUES "
                        "('58000000-0000-0000-0000-000000000007',"
                        "'58000000-0000-0000-0000-000000000008',"
                        "'58000000-0000-0000-0000-000000000003',"
                        "'58000000-0000-0000-0000-000000000004',"
                        "'58000000-0000-0000-0000-000000000009',repeat('c',64),"
                        "'{\"end_at\":\"2099-01-01T00:00:00+00:00\"}',"
                        "'[\"date_change\",\"expansion\"]','{\"before\":{}}',"
                        "'pending_admin',10)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO campaign_change_requests "
                        "(id,campaign_id,organization_id,requested_by_user_id,"
                        "client_request_id,request_fingerprint,proposed_changes,"
                        "classifications,impact_preview,status,requested_liability_amount,"
                        "reviewed_by_user_id,reviewed_at,review_reason) VALUES "
                        "('58000000-0000-0000-0000-000000000010',"
                        "'58000000-0000-0000-0000-000000000011',"
                        "'58000000-0000-0000-0000-000000000003',"
                        "'58000000-0000-0000-0000-000000000004',"
                        "'58000000-0000-0000-0000-000000000012',repeat('d',64),"
                        "'{\"end_at\":\"2099-01-02T00:00:00+00:00\"}',"
                        "'[\"date_change\",\"expansion\"]','{\"before\":{}}',"
                        "'pending_funding',10,'58000000-0000-0000-0000-000000000004',"
                        "now(),'approved pending funding')"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_change_revisions SET revision_number=2 "
                            "WHERE id='58000000-0000-0000-0000-000000000006'"
                        )
                    )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_change_requests "
                            "SET proposed_changes='{\"budget_amount\":\"1300.00\"}' "
                            "WHERE id='58000000-0000-0000-0000-000000000001'"
                        )
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE campaign_change_requests SET status='pending_funding' "
                        "WHERE id='58000000-0000-0000-0000-000000000007'"
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="review evidence is immutable"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_change_requests "
                            "SET review_reason='changed approval evidence' "
                            "WHERE id='58000000-0000-0000-0000-000000000010'"
                        )
                    )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="transition is invalid"):
                    await connection.execute(
                        text(
                            "UPDATE campaign_change_requests SET status='pending_admin' "
                            "WHERE id='58000000-0000-0000-0000-000000000007'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="campaign changes are populated"):
            downgrade_to(migration_url, PRE_CAMPAIGN_CHANGES_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
