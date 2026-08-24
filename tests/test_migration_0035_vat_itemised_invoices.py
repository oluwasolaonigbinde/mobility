"""Migration 0035: verified issuer facts and numbered invoices."""

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

PRE_INVOICE_REVISION = "0034_canonical_receipts_allocations"


def test_invoice_authority_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            fetch_all(
                migration_url,
                "SELECT table_name FROM information_schema.tables WHERE table_name IN "
                "('invoices','invoice_issuer_profiles','invoice_number_sequences') "
                "ORDER BY table_name",
            )
        ) == [
            ("invoice_issuer_profiles",),
            ("invoice_number_sequences",),
            ("invoices",),
        ]
        downgrade_to(migration_url, PRE_INVOICE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_issued_invoice_is_database_immutable_and_blocks_downgrade(monkeypatch) -> None:
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
        upgrade_to(migration_url, "0036_invoice_authority_hardening", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0036 downgrade blocked"):
            downgrade_to(migration_url, PRE_INVOICE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
