"""Migration 0077: recoverable stored-object deletion intents and receipts."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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

from app.db.base import Base

PRE_DELETION_RECEIPT_REVISION = "0076_dsr_assessment_truth"


def test_stored_object_deletions_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_DELETION_RECEIPT_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_DELETION_RECEIPT_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_stored_object_deletion_model_has_no_owned_autogenerate_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def compare() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={
                                "compare_type": False,
                                "compare_server_default": False,
                            },
                        ),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        owned_diffs = []
        for diff in asyncio.run(compare()):
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name == "stored_object_deletions":
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))


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
            "display_proofs",
            "report_artifacts",
        )
    }
