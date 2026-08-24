"""Migration 0033: canonical advertiser company profile fields."""

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

PRE_PROFILE_REVISION = "0032_commercial_quotation_terms"


def test_company_profile_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        names = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'advertiser_organizations' "
                "AND column_name IN ('industry', 'address_line_1', 'operational_contact_email', "
                "'billing_contact_name', 'profile_notes') ORDER BY column_name",
            )
        )
        assert names == [
            ("address_line_1",),
            ("billing_contact_name",),
            ("industry",),
            ("operational_contact_email",),
            ("profile_notes",),
        ]
        downgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_company_profile_populated_downgrade_fails_closed(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO advertiser_organizations
                          (id, name, currency, status, industry)
                        VALUES
                          ('33000000-0000-0000-0000-000000000001',
                           'Profile Authority', 'NGN', 'active', 'Mobility')
                        """
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed())
        with pytest.raises(RuntimeError, match="0033 downgrade blocked"):
            downgrade_to(migration_url, PRE_PROFILE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
