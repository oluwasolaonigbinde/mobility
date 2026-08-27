"""Migration 0069: exact payout verification and applicant mutation authority."""

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

PRE_AUTHORITY_REVISION = "0068_driver_person_payee_review"


def test_w3_04b_review_authority_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_AUTHORITY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_AUTHORITY_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_w3_04b_backfills_only_admin_account_versions_and_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_before_upgrade() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                        "VALUES "
                        "('69000000-0000-0000-0000-000000000001', 'admin@migration.test', "
                        "'hash', 'Admin', 'admin', 'active'), "
                        "('69000000-0000-0000-0000-000000000002', 'driver@migration.test', "
                        "'hash', 'Driver', 'driver', 'invited')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO payee_bank_accounts (id, payee_id, created_by_user_id) "
                        "VALUES "
                        "('69000000-0000-0000-0000-000000000021', "
                        "'69000000-0000-0000-0000-000000000051', "
                        "'69000000-0000-0000-0000-000000000001'), "
                        "('69000000-0000-0000-0000-000000000022', "
                        "'69000000-0000-0000-0000-000000000052', "
                        "'69000000-0000-0000-0000-000000000002')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO audit_events "
                        "(id, actor_user_id, action, entity_type, entity_id, metadata) VALUES "
                        "('69000000-0000-0000-0000-000000000041', "
                        "'69000000-0000-0000-0000-000000000001', "
                        "'admin.bank_account.verified', 'payee_bank_account', "
                        "'69000000-0000-0000-0000-000000000021', "
                        "'{\"bank_account_version\": 1}'::jsonb), "
                        "('69000000-0000-0000-0000-000000000042', "
                        "'69000000-0000-0000-0000-000000000002', "
                        "'driver_application.bank_account.verified', 'payee_bank_account', "
                        "'69000000-0000-0000-0000-000000000022', "
                        "'{\"bank_account_version\": 1}'::jsonb)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO payee_bank_account_versions "
                        "(id, bank_account_id, payee_version_id, version, encrypted_details, "
                        "encryption_algorithm, encryption_key_version, "
                        "verification_reference_sha256, verified_by_user_id) VALUES "
                        "('69000000-0000-0000-0000-000000000011', "
                        "'69000000-0000-0000-0000-000000000021', "
                        "'69000000-0000-0000-0000-000000000031', 1, '{}'::jsonb, "
                        "'AES-256-GCM', 1, repeat('a', 64), "
                        "'69000000-0000-0000-0000-000000000001'), "
                        "('69000000-0000-0000-0000-000000000012', "
                        "'69000000-0000-0000-0000-000000000022', "
                        "'69000000-0000-0000-0000-000000000032', 1, '{}'::jsonb, "
                        "'AES-256-GCM', 1, repeat('b', 64), "
                        "'69000000-0000-0000-0000-000000000002')"
                    )
                )
        finally:
            await engine.dispose()

    async def inspect_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text(
                            "SELECT bank_account_version_id FROM "
                            "payee_bank_account_payout_verifications ORDER BY 1"
                        )
                    )
                ).all()
            assert [str(row[0]) for row in rows] == [
                "69000000-0000-0000-0000-000000000011"
            ]
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payee_bank_account_payout_verifications "
                            "SET verification_reference_sha256 = verification_reference_sha256"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_AUTHORITY_REVISION, monkeypatch)
        asyncio.run(seed_before_upgrade())
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(inspect_and_mutate())
        with pytest.raises(RuntimeError, match="0069 downgrade blocked"):
            downgrade_to(migration_url, PRE_AUTHORITY_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_w3_04b_review_authority_model_has_no_autogenerate_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def compare() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={"compare_type": False, "compare_server_default": False},
                        ),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        diffs = asyncio.run(compare())
        owned_tables = {
            "driver_application_access_tokens",
            "payee_bank_account_payout_verifications",
        }
        owned_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name in owned_tables:
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
