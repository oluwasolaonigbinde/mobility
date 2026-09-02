"""Migration 0028: protected payee and verified account authority."""

import asyncio

import pytest
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

PRE_PAYEE_REVISION = "0027_earnings_release_sla"
TABLES = (
    "payee_bank_account_versions",
    "payee_bank_accounts",
    "payee_versions",
    "payees",
)


def test_protected_payee_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "0028_protected_payee_accounts", monkeypatch)
        tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'payee%' ORDER BY table_name",
            )
        )
        assert tables == [(table,) for table in TABLES]
        upgrade_to(migration_url, "head", monkeypatch)
        current_tables = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN "
                "('payee_bank_account_versions', 'payee_bank_accounts', "
                "'payee_versions', 'payees') ORDER BY table_name",
            )
        )
        assert current_tables == [(table,) for table in TABLES]
        downgrade_to(migration_url, PRE_PAYEE_REVISION, monkeypatch)
        assert (
            asyncio.run(
                fetch_all(
                    migration_url,
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name LIKE 'payee%'",
                )
            )
            == []
        )
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


@pytest.mark.parametrize("table_name", TABLES)
def test_protected_payee_populated_downgrade_fails_closed(monkeypatch, table_name: str) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                identifiers = {
                    "payees": (
                        "INSERT INTO payees "
                        "(id, tenant_id, payee_type, subject_id, created_by_user_id) VALUES "
                        "('28000000-0000-0000-0000-000000000001', "
                        "'28000000-0000-0000-0000-000000000002', 'driver', "
                        "'28000000-0000-0000-0000-000000000003', "
                        "'28000000-0000-0000-0000-000000000004')"
                    ),
                    "payee_versions": (
                        "INSERT INTO payee_versions "
                        "(id, payee_id, version, payee_type, subject_id, "
                        "created_by_user_id) VALUES "
                        "('28000000-0000-0000-0000-000000000011', "
                        "'28000000-0000-0000-0000-000000000012', 1, 'driver', "
                        "'28000000-0000-0000-0000-000000000013', "
                        "'28000000-0000-0000-0000-000000000014')"
                    ),
                    "payee_bank_accounts": (
                        "INSERT INTO payee_bank_accounts "
                        "(id, payee_id, created_by_user_id) VALUES "
                        "('28000000-0000-0000-0000-000000000021', "
                        "'28000000-0000-0000-0000-000000000022', "
                        "'28000000-0000-0000-0000-000000000023')"
                    ),
                    "payee_bank_account_versions": (
                        "INSERT INTO payee_bank_account_versions "
                        "(id, bank_account_id, payee_version_id, version, encrypted_details, "
                        "encryption_algorithm, encryption_key_version, "
                        "verification_reference_sha256, verified_by_user_id) VALUES "
                        "('28000000-0000-0000-0000-000000000031', "
                        "'28000000-0000-0000-0000-000000000032', "
                        "'28000000-0000-0000-0000-000000000033', 1, '{}'::jsonb, "
                        "'AES-256-GCM', 1, repeat('a', 64), "
                        "'28000000-0000-0000-0000-000000000034')"
                    ),
                }
                await connection.execute(text(identifiers[table_name]))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="downgrade blocked"):
            downgrade_to(migration_url, PRE_PAYEE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
