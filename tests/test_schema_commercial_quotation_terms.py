"""Current PostgreSQL schema: immutable commercial quotation authority."""

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


def test_commercial_authority_is_database_immutable(monkeypatch) -> None:
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
    finally:
        asyncio.run(drop_database(migration_url))
