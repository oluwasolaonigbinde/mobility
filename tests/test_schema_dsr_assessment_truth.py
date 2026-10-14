"""Current PostgreSQL schema: truthful DSR assessment invariants."""

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
        upgrade_to(migration_url, "head", monkeypatch)
        with pytest.raises(DBAPIError, match="ck_data_subject_assessments_zero_claim"):
            asyncio.run(violate_constraint())
    finally:
        asyncio.run(drop_database(migration_url))
