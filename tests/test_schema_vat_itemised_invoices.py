"""Current PostgreSQL schema: verified issuer facts and numbered invoices."""

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


def test_issued_invoice_is_database_immutable(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO invoice_issuer_profiles
                          (id, legal_name, tax_identification_number, registered_address,
                           country_code, invoice_wording, numbering_prefix,
                           verification_status, external_input_reference,
                           recorded_by_user_id, recorded_at)
                        VALUES
                          ('35000000-0000-0000-0000-000000000006', 'Terrax Media',
                           'TEST', 'Test', 'NG', 'Test', 'CV', 'synthetic', 'TEST-35',
                           '35000000-0000-0000-0000-000000000005', now())
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO invoices
                          (id, commercial_terms_id, campaign_id, organization_id,
                           issuer_profile_id, invoice_number, status, customer_snapshot,
                           issuer_snapshot,
                           line_items, currency, net_amount, tax_rate, tax_amount,
                           gross_amount, created_by_user_id, created_at, issued_by_user_id,
                           issued_at)
                        VALUES
                          ('35000000-0000-0000-0000-000000000001',
                           '35000000-0000-0000-0000-000000000002',
                           '35000000-0000-0000-0000-000000000003',
                           '35000000-0000-0000-0000-000000000004',
                           '35000000-0000-0000-0000-000000000006', 'CV-2026-000001',
                           'issued', '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, 'NGN',
                           100, 0.075, 7.50, 107.50,
                           '35000000-0000-0000-0000-000000000005', now(),
                           '35000000-0000-0000-0000-000000000005', now())
                        """
                    )
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="immutable"):
                    await connection.execute(
                        text(
                            "UPDATE invoices SET gross_amount = gross_amount WHERE id = "
                            "'35000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
