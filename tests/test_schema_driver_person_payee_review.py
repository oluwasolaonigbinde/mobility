"""Current PostgreSQL schema: immutable driver person/payee review decisions."""

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

from app.models.kyc import DriverKycReviewDecision  # noqa: F401


def test_driver_person_payee_decision_is_append_only(
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
    finally:
        asyncio.run(drop_database(migration_url))
