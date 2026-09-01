"""Migration 0073: frozen refund cancellation provenance."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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

from app.db.base import Base

PRE_PROVENANCE_REVISION = "0072_driver_application_terminal_status"
PROVENANCE_REVISION = "0073_refund_cancellation_provenance"

MATCHED_CANCELLATION_ID = "73000000-0000-0000-0000-000000000001"
MATCHED_SETTLEMENT_ID = "73000000-0000-0000-0000-000000000002"
UNMATCHED_SETTLEMENT_ID = "73000000-0000-0000-0000-000000000102"
MATCHED_CUTOFF = "2026-01-01 01:00:00+00"


async def _fetch_all(migration_url: str, statement: str) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list((await connection.execute(text(statement))).all())
    finally:
        await engine.dispose()


async def _seed_legacy_refunds(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text(
                    """
                    INSERT INTO campaign_cancellations (
                        id, campaign_id, organization_id, requested_by_user_id,
                        client_request_id, request_fingerprint, reason, prior_status,
                        cutoff_at, commercial_terms_id, production_start_id,
                        funding_authorized_at, refund_eligibility_ends_at, disposition,
                        refundable_amount, currency, released_liability_amount,
                        cancelled_assignment_count
                    ) VALUES
                    (
                        '73000000-0000-0000-0000-000000000001',
                        '73000000-0000-0000-0000-000000000011',
                        '73000000-0000-0000-0000-000000000021',
                        '73000000-0000-0000-0000-000000000031',
                        '73000000-0000-0000-0000-000000000041', repeat('a', 64),
                        'legacy exact cancellation', 'active',
                        '2026-01-01 01:00:00+00',
                        '73000000-0000-0000-0000-000000000051', NULL,
                        '2026-01-01 00:00:00+00', '2026-01-02 00:00:00+00',
                        'cash_refund_due', 100.00, 'NGN', 0.00, 0
                    ),
                    (
                        '73000000-0000-0000-0000-000000000101',
                        '73000000-0000-0000-0000-000000000111',
                        '73000000-0000-0000-0000-000000000121',
                        '73000000-0000-0000-0000-000000000131',
                        '73000000-0000-0000-0000-000000000141', repeat('b', 64),
                        'legacy cancellation recorded after settlement', 'active',
                        '2026-01-01 03:00:00+00',
                        '73000000-0000-0000-0000-000000000151', NULL,
                        '2026-01-01 00:00:00+00', '2026-01-02 00:00:00+00',
                        'cash_refund_due', 100.00, 'NGN', 0.00, 0
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO refund_settlements (
                        id, commercial_terms_id, campaign_id, receipt_id,
                        production_start_id, waiver_id, disposition, amount, currency,
                        funding_authorized_at, eligibility_ends_at, settlement_provider,
                        external_reference, reason, recorded_by_user_id, recorded_at
                    ) VALUES
                    (
                        '73000000-0000-0000-0000-000000000002',
                        '73000000-0000-0000-0000-000000000051',
                        '73000000-0000-0000-0000-000000000011',
                        '73000000-0000-0000-0000-000000000061', NULL, NULL,
                        'refund_recorded', 60.00, 'NGN',
                        '2026-01-01 00:00:00+00', '2026-01-02 00:00:00+00',
                        'bank', 'legacy-exact-refund', 'legacy exact refund',
                        '73000000-0000-0000-0000-000000000071',
                        '2026-01-01 02:00:00+00'
                    ),
                    (
                        '73000000-0000-0000-0000-000000000102',
                        '73000000-0000-0000-0000-000000000151',
                        '73000000-0000-0000-0000-000000000111',
                        '73000000-0000-0000-0000-000000000161', NULL, NULL,
                        'refund_recorded', 40.00, 'NGN',
                        '2026-01-01 00:00:00+00', '2026-01-02 00:00:00+00',
                        'bank', 'legacy-temporal-mismatch',
                        'legacy settlement before cancellation',
                        '73000000-0000-0000-0000-000000000171',
                        '2026-01-01 02:00:00+00'
                    )
                    """
                )
            )
    finally:
        await engine.dispose()


def test_refund_provenance_empty_upgrade_downgrade_and_reupgrade(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_PROVENANCE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            _fetch_all(migration_url, "SELECT version_num FROM alembic_version")
        ) == [(PROVENANCE_REVISION,)]

        downgrade_to(migration_url, PRE_PROVENANCE_REVISION, monkeypatch)
        columns = asyncio.run(
            _fetch_all(
                migration_url,
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'refund_settlements'
                  AND column_name IN ('cancellation_id', 'eligibility_evaluated_at')
                ORDER BY column_name
                """,
            )
        )
        assert columns == []
        assert asyncio.run(
            _fetch_all(migration_url, "SELECT version_num FROM alembic_version")
        ) == [(PRE_PROVENANCE_REVISION,)]

        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(
            _fetch_all(migration_url, "SELECT version_num FROM alembic_version")
        ) == [(PROVENANCE_REVISION,)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_refund_provenance_backfill_catalog_and_downgrade_guard(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_PROVENANCE_REVISION, monkeypatch)
        asyncio.run(_seed_legacy_refunds(migration_url))
        upgrade_to(migration_url, "head", monkeypatch)

        provenance = asyncio.run(
            _fetch_all(
                migration_url,
                """
                SELECT id::text, cancellation_id::text,
                       to_char(
                           eligibility_evaluated_at AT TIME ZONE 'UTC',
                           'YYYY-MM-DD HH24:MI:SS'
                       ) || '+00'
                FROM refund_settlements
                ORDER BY id
                """,
            )
        )
        assert provenance == [
            (MATCHED_SETTLEMENT_ID, MATCHED_CANCELLATION_ID, MATCHED_CUTOFF),
            (UNMATCHED_SETTLEMENT_ID, None, None),
        ]

        constraints = dict(
            asyncio.run(
                _fetch_all(
                    migration_url,
                    """
                    SELECT conname, pg_get_constraintdef(oid)
                    FROM pg_constraint
                    WHERE conrelid = 'refund_settlements'::regclass
                      AND conname IN (
                          'ck_refund_settlements_authority',
                          'ck_refund_settlements_frozen_provenance',
                          'ck_refund_settlements_eligibility_window',
                          'fk_refund_settlements_cancellation_id'
                      )
                    ORDER BY conname
                    """,
                )
            )
        )
        assert set(constraints) == {
            "ck_refund_settlements_authority",
            "ck_refund_settlements_frozen_provenance",
            "ck_refund_settlements_eligibility_window",
            "fk_refund_settlements_cancellation_id",
        }
        assert "eligibility_evaluated_at" in constraints["ck_refund_settlements_eligibility_window"]
        assert "recorded_at" not in constraints["ck_refund_settlements_eligibility_window"]
        assert (
            "FOREIGN KEY (cancellation_id)" in constraints["fk_refund_settlements_cancellation_id"]
        )
        assert "ON DELETE RESTRICT" in constraints["fk_refund_settlements_cancellation_id"]

        catalog = asyncio.run(
            _fetch_all(
                migration_url,
                """
                SELECT
                    to_regclass('ix_refund_settlements_cancellation_id')::text,
                    EXISTS (
                        SELECT 1
                        FROM pg_trigger
                        WHERE tgrelid = 'refund_settlements'::regclass
                          AND tgname = 'refund_settlements_append_only'
                          AND NOT tgisinternal
                          AND tgenabled = 'O'
                    )
                """,
            )
        )
        assert catalog == [("ix_refund_settlements_cancellation_id", True)]

        with pytest.raises(RuntimeError, match="0073 downgrade blocked"):
            downgrade_to(migration_url, PRE_PROVENANCE_REVISION, monkeypatch)

        assert asyncio.run(
            _fetch_all(migration_url, "SELECT version_num FROM alembic_version")
        ) == [(PROVENANCE_REVISION,)]
        assert asyncio.run(
            _fetch_all(
                migration_url,
                """
                SELECT cancellation_id::text,
                       to_char(
                           eligibility_evaluated_at AT TIME ZONE 'UTC',
                           'YYYY-MM-DD HH24:MI:SS'
                       ) || '+00',
                       amount
                FROM refund_settlements
                WHERE id = '73000000-0000-0000-0000-000000000002'
                """,
            )
        ) == [(MATCHED_CANCELLATION_ID, MATCHED_CUTOFF, 60)]
    finally:
        asyncio.run(drop_database(migration_url))


def test_refund_provenance_model_has_no_owned_autogenerate_drift(monkeypatch) -> None:
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
        owned_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name == "refund_settlements":
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
