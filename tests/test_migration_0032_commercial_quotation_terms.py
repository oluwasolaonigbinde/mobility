"""Migration 0032: immutable commercial quotation authority."""

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

PRE_COMMERCIAL_REVISION = "0031_carry_forward_payout_debt"


def test_commercial_terms_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'commercial_%' ORDER BY table_name",
            )
        ) == [
            ("commercial_quotation_revisions",),
            ("commercial_quote_requests",),
            ("commercial_terms",),
        ]
        downgrade_to(migration_url, PRE_COMMERCIAL_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_commercial_authority_is_database_immutable_and_blocks_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO commercial_quote_requests
                          (id, campaign_id, organization_id, source, requested_by_user_id)
                        VALUES
                          ('32000000-0000-0000-0000-000000000001',
                           '32000000-0000-0000-0000-000000000002',
                           '32000000-0000-0000-0000-000000000003',
                           'external_recorded',
                           '32000000-0000-0000-0000-000000000004')
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO commercial_quotation_revisions
                          (id, quote_request_id, campaign_id, organization_id,
                           revision_number, quote_reference, currency, line_items,
                           production_scope, production_cost_amount, payment_class,
                           payment_terms, standard_production_wait_hours, net_amount,
                           tax_rate, tax_amount, gross_amount, created_by_user_id)
                        VALUES
                          ('32000000-0000-0000-0000-000000000005',
                           '32000000-0000-0000-0000-000000000001',
                           '32000000-0000-0000-0000-000000000002',
                           '32000000-0000-0000-0000-000000000003',
                           1, 'Q-1', 'NGN', '[]'::jsonb, '{}'::jsonb, 0,
                           'standard_prepaid', '{}'::jsonb, 24, 100, 0.075,
                           7.50, 107.50,
                           '32000000-0000-0000-0000-000000000004')
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE commercial_quotation_revisions "
                            "SET quote_reference = quote_reference"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0032 downgrade blocked"):
            downgrade_to(migration_url, PRE_COMMERCIAL_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
