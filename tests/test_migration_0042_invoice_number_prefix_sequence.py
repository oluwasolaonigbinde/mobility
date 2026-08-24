"""Migration 0042: rendered-prefix invoice sequence backfill."""

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
    upgrade_to,
)


def test_shared_prefix_backfill_uses_max_issued_suffix_and_blocks_downgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                for suffix in (1, 2):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO invoice_issuer_profiles
                              (id, legal_name, tax_identification_number, registered_address,
                               country_code, invoice_wording, numbering_prefix,
                               verification_status, external_input_reference,
                               recorded_by_user_id, recorded_at)
                            VALUES
                              (:id, 'Terrax Media', :tin, 'Test', 'NG', 'Test', 'SHARED',
                               'synthetic', :reference, :actor, now())
                            """
                        ),
                        {
                            "id": f"42000000-0000-0000-0000-00000000000{suffix}",
                            "tin": f"TIN-{suffix}",
                            "reference": f"SYNTHETIC-42-{suffix}",
                            "actor": "42000000-0000-0000-0000-000000000009",
                        },
                    )
                await connection.execute(
                    text(
                        """
                        INSERT INTO invoice_number_sequences
                          (id, issuer_profile_id, calendar_year, next_number)
                        VALUES
                          ('42000000-0000-0000-0000-000000000011',
                           '42000000-0000-0000-0000-000000000001', 2026, 2),
                          ('42000000-0000-0000-0000-000000000012',
                           '42000000-0000-0000-0000-000000000002', 2026, 5)
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO invoices
                          (id, commercial_terms_id, campaign_id, organization_id,
                           issuer_profile_id, invoice_number, status, customer_snapshot,
                           issuer_snapshot, line_items, currency, net_amount, tax_rate,
                           tax_amount, gross_amount, created_by_user_id, created_at,
                           issued_by_user_id, issued_at)
                        VALUES
                          ('42000000-0000-0000-0000-000000000021',
                           '42000000-0000-0000-0000-000000000022',
                           '42000000-0000-0000-0000-000000000023',
                           '42000000-0000-0000-0000-000000000024',
                           '42000000-0000-0000-0000-000000000001',
                           'TEST-SHARED-2026-000007', 'issued', '{}'::jsonb, '{}'::jsonb,
                           '[]'::jsonb, 'NGN', 100, 0, 0, 100,
                           '42000000-0000-0000-0000-000000000009', now(),
                           '42000000-0000-0000-0000-000000000009', now())
                        """
                    )
                )
        finally:
            await engine.dispose()

    async def verify() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text(
                            "SELECT number_prefix, calendar_year, next_number "
                            "FROM invoice_number_sequences"
                        )
                    )
                ).all()
                assert rows == [("TEST-SHARED", 2026, 8)]
                assert (
                    await connection.scalar(text("SELECT invoice_number FROM invoices"))
                    == "TEST-SHARED-2026-000007"
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0041_invoice_correction_retry_identity", monkeypatch)
        asyncio.run(seed())
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(verify())
        with pytest.raises(RuntimeError, match="0042 downgrade blocked"):
            downgrade_to(migration_url, "0041_invoice_correction_retry_identity", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
