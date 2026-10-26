"""Current PostgreSQL schema: recoverable stored-object deletion intents and receipts."""

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


def test_stored_object_deletion_receipt_identity_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO stored_object_deletions
                          (id, organization_id, owner_type, owner_id, storage_key,
                           storage_key_sha256, object_checksum_sha256, reason,
                           request_fingerprint)
                        VALUES
                          ('77000000-0000-0000-0000-000000000001',
                           '77000000-0000-0000-0000-000000000002', 'synthetic_test',
                           '77000000-0000-0000-0000-000000000003', 'private/key',
                           repeat('a', 64), repeat('c', 64), 'synthetic_receipt',
                           repeat('b', 64))
                        """
                    )
                )
            with pytest.raises(DBAPIError, match="identity is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE stored_object_deletions SET reason = 'tampered' "
                            "WHERE id = '77000000-0000-0000-0000-000000000001'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM stored_object_deletions "
                            "WHERE id = '77000000-0000-0000-0000-000000000001'"
                        )
                    )
            with pytest.raises(DBAPIError, match="timestamps are write-once"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE stored_object_deletions "
                            "SET provider_deleted_at = now() "
                            "WHERE id = '77000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(mutate())
    finally:
        asyncio.run(drop_database(migration_url))


def test_stored_object_reference_tables_have_database_deletion_fences(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def trigger_names() -> set[str]:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(
                    text(
                        """
                        SELECT tgname FROM pg_trigger
                        WHERE NOT tgisinternal AND tgname LIKE '%_deletion_fence'
                        """
                    )
                )
                return set(rows.scalars())
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert trigger_names_expected() <= asyncio.run(trigger_names())
    finally:
        asyncio.run(drop_database(migration_url))


def trigger_names_expected() -> set[str]:
    return {
        f"trg_{table_name}_deletion_fence"
        for table_name in (
            "campaign_creatives",
            "driver_kyc_documents",
            "vehicle_evidence_documents",
            "installation_evidence_photos",
            "report_artifacts",
        )
    }
