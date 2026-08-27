"""Migration 0068: immutable driver person/payee review decisions."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
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

from app.db.base import Base
from app.models.kyc import DriverKycReviewDecision  # noqa: F401

PRE_REVIEW_REVISION = "0067_exposure_scores"


def test_driver_person_payee_review_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_driver_person_payee_decision_is_append_only_and_blocks_populated_downgrade(
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
                        INSERT INTO driver_kyc_review_decisions
                          (id, submission_id, client_request_id, request_fingerprint,
                           decision, reason_code, identity_match_confirmed,
                           bank_account_match_confirmed, documents_readable_confirmed,
                           decided_by_user_id)
                        VALUES
                          ('68000000-0000-0000-0000-000000000001',
                           '68000000-0000-0000-0000-000000000002',
                           '68000000-0000-0000-0000-000000000003', repeat('a', 64),
                           'approved', 'complete_current_evidence', true, true, true,
                           '68000000-0000-0000-0000-000000000004')
                        """
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE driver_kyc_review_decisions SET decision = decision "
                            "WHERE id = '68000000-0000-0000-0000-000000000001'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
        with pytest.raises(RuntimeError, match="0068 downgrade blocked"):
            downgrade_to(migration_url, PRE_REVIEW_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_driver_person_payee_review_model_has_no_autogenerate_drift(monkeypatch) -> None:
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
        review_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name == "driver_kyc_review_decisions":
                review_diffs.append(diff)
        assert review_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
