"""Current PostgreSQL schema: immutable formula-versioned exposure scores."""

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

from app.models.exposure_score import ExposureScore  # noqa: F401


def test_exposure_score_is_append_only(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO exposure_scores
                          (id, organization_id, campaign_id, measurement_run_id,
                           issued_by_user_id, formula_version, formula_fingerprint,
                           input_snapshot, input_fingerprint, result_snapshot,
                           result_fingerprint, measurement_input_sha256,
                           measurement_result_sha256, measurement_proof_sha256)
                        VALUES
                          ('67000000-0000-0000-0000-000000000001',
                           '67000000-0000-0000-0000-000000000002',
                           '67000000-0000-0000-0000-000000000003',
                           '67000000-0000-0000-0000-000000000004',
                           '67000000-0000-0000-0000-000000000005',
                           'exposure_v1', repeat('a', 64), '{}'::jsonb,
                           repeat('b', 64), '{}'::jsonb, repeat('c', 64),
                           repeat('d', 64), repeat('e', 64), repeat('f', 64))
                        """
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE exposure_scores SET formula_version = formula_version "
                            "WHERE id = '67000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
