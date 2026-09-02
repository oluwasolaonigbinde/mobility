"""Migration 0076: truthful DSR assessment invariants."""

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
    upgrade_to,
)

PRE_DSR_TRUTH_REVISION = "0075_governed_audience_delivery"


def test_dsr_assessment_truth_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_DSR_TRUTH_REVISION, monkeypatch)
        upgrade_to(migration_url, "0076_dsr_assessment_truth", monkeypatch)
        downgrade_to(migration_url, PRE_DSR_TRUTH_REVISION, monkeypatch)
        upgrade_to(migration_url, "0076_dsr_assessment_truth", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_dsr_assessment_database_rejects_nonzero_erased_claim(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def violate_constraint() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO data_subject_location_assessments
                          (id, request_id, location, disposition, record_count,
                           data_class_counts, evidence_reference, assessed_by_user_id,
                           client_request_id, request_fingerprint)
                        VALUES
                          ('76000000-0000-0000-0000-000000000001',
                           '76000000-0000-0000-0000-000000000002',
                           'processors', 'erased', 1, '{}'::jsonb, 'synthetic-proof',
                           '76000000-0000-0000-0000-000000000003',
                           '76000000-0000-0000-0000-000000000004', repeat('a', 64))
                        """
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0076_dsr_assessment_truth", monkeypatch)
        with pytest.raises(DBAPIError, match="ck_data_subject_assessments_zero_claim"):
            asyncio.run(violate_constraint())
    finally:
        asyncio.run(drop_database(migration_url))


def test_dsr_truth_upgrade_fails_closed_on_legacy_false_erasure(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_invalid_legacy_row() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO data_subject_location_assessments
                          (id, request_id, location, disposition, record_count,
                           data_class_counts, evidence_reference, assessed_by_user_id,
                           client_request_id, request_fingerprint)
                        VALUES
                          ('76100000-0000-0000-0000-000000000001',
                           '76100000-0000-0000-0000-000000000002',
                           'processors', 'erased', 1, '{}'::jsonb, 'legacy-false-erasure',
                           '76100000-0000-0000-0000-000000000003',
                           '76100000-0000-0000-0000-000000000004', repeat('e', 64))
                        """
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_DSR_TRUTH_REVISION, monkeypatch)
        asyncio.run(seed_invalid_legacy_row())
        with pytest.raises(Exception, match="ck_data_subject_assessments_zero_claim"):
            upgrade_to(migration_url, "0076_dsr_assessment_truth", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
