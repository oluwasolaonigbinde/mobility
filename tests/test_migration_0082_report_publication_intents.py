"""Migration 0082: generation-scoped report publication intents."""

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

PRE_PUBLICATION_REVISION = "0081_payout_money_authority"
ISSUANCE = "82000000-0000-0000-0000-000000000001"
FIRST = "82000000-0000-0000-0000-000000000011"
SECOND = "82000000-0000-0000-0000-000000000012"


TOKEN = "'82000000-0000-0000-0000-0000000000ff'"
SEED_ISSUANCE = (
    "INSERT INTO report_issuances "
    "(id, organization_id, campaign_id, measurement_run_id, requested_by_user_id, "
    "client_request_id, request_fingerprint, version, snapshot, snapshot_sha256, "
    "authority_fingerprint, input_manifest_sha256, result_manifest_sha256, "
    "proof_manifest_sha256, report_snapshot_sha256, schema_version, renderer_version, "
    "method_revision, roi_decision, synthetic, status, worker_attempts) VALUES "
    f"('{ISSUANCE}', '{ISSUANCE}', '{ISSUANCE}', '{ISSUANCE}', '{ISSUANCE}', '{ISSUANCE}', "
    "repeat('a', 64), 1, '{}'::jsonb, repeat('b', 64), repeat('c', 64), repeat('d', 64), "
    "repeat('e', 64), repeat('f', 64), repeat('1', 64), 'campaign-performance-export-v1', "
    "'campaign-report-renderer-v1', 'measurement-contract-v1', 'OMIT', true, 'queued', 0)"
)
LEASED = {"prepared", "publishing", "cleaning"}


def seed_generation(intent_id: str, generation: int, state: str) -> str:
    """Insert one generation with foreign keys disabled, matching the 0071 seed pattern."""
    token = TOKEN if state in {"publishing", "cleaning"} else "NULL"
    lease = "now() + interval '2 minutes'" if state in LEASED else "NULL"
    completed = "now()" if state == "complete" else "NULL"
    abandoned = "now()" if state in {"abandoned", "cleaning", "cleaned"} else "NULL"
    cleaned = "now()" if state == "cleaned" else "NULL"
    return (
        "INSERT INTO report_publication_intents "
        "(id, report_issuance_id, generation, state, csv_object_key, pdf_object_key, "
        "publisher_token, lease_expires_at, completed_at, abandoned_at, cleaned_at) VALUES "
        f"('{intent_id}', '{ISSUANCE}', {generation}, '{state}', "
        f"'managed/o/reports/i/publications/{intent_id}/g{generation}/a.csv', "
        f"'managed/o/reports/i/publications/{intent_id}/g{generation}/a.pdf', "
        f"{token}, {lease}, {completed}, {abandoned}, {cleaned})"
    )


def test_report_publication_intents_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_PUBLICATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_PUBLICATION_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_report_publication_intent_model_has_no_owned_autogenerate_drift(monkeypatch) -> None:
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
        owned = []
        for diff in asyncio.run(compare()):
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name == "report_publication_intents":
                owned.append(diff)
        assert owned == []
    finally:
        asyncio.run(drop_database(migration_url))


def test_publication_fence_and_tombstone_are_enforced_in_the_database(monkeypatch) -> None:
    """The ORM guards are mirrored as triggers, so raw SQL cannot bypass the fence."""
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def exercise() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(text(SEED_ISSUANCE))
                await connection.execute(text(seed_generation(FIRST, 1, "prepared")))

            # Only one live generation per issuance may exist at a time.
            with pytest.raises(DBAPIError, match="uq_report_publication_intents_live"):
                async with engine.begin() as connection:
                    await connection.execute(text("SET LOCAL session_replication_role = replica"))
                    await connection.execute(text(seed_generation(SECOND, 2, "prepared")))

            # The declared transition is allowed.
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE report_publication_intents SET state = 'publishing', "
                        "publisher_token = '82000000-0000-0000-0000-0000000000ff' "
                        f"WHERE id = '{FIRST}'"
                    )
                )

            with pytest.raises(DBAPIError, match="identity is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE report_publication_intents SET csv_object_key = 'rewritten' "
                            f"WHERE id = '{FIRST}'"
                        )
                    )

            with pytest.raises(DBAPIError, match="state transition is invalid"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE report_publication_intents SET state = 'cleaned', "
                            "publisher_token = NULL, lease_expires_at = NULL, "
                            "abandoned_at = now(), cleaned_at = now() "
                            f"WHERE id = '{FIRST}'"
                        )
                    )

            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f"DELETE FROM report_publication_intents WHERE id = '{FIRST}'")
                    )

            # A cleaned tombstone can never become a published generation.
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE report_publication_intents SET state = 'abandoned', "
                        "publisher_token = NULL, lease_expires_at = NULL, abandoned_at = now() "
                        f"WHERE id = '{FIRST}'"
                    )
                )
                await connection.execute(
                    text(
                        "UPDATE report_publication_intents SET state = 'cleaning', "
                        "publisher_token = '82000000-0000-0000-0000-0000000000ff', "
                        "lease_expires_at = now() + interval '2 minutes' "
                        f"WHERE id = '{FIRST}'"
                    )
                )
                await connection.execute(
                    text(
                        "UPDATE report_publication_intents SET state = 'cleaned', "
                        "publisher_token = NULL, lease_expires_at = NULL, cleaned_at = now() "
                        f"WHERE id = '{FIRST}'"
                    )
                )
            with pytest.raises(DBAPIError, match="state transition is invalid"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE report_publication_intents SET state = 'complete', "
                            "cleaned_at = NULL, abandoned_at = NULL, completed_at = now() "
                            f"WHERE id = '{FIRST}'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(exercise())
        # Only cleaned tombstones remain, so nothing is stranded and downgrade may proceed.
        downgrade_to(migration_url, PRE_PUBLICATION_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_downgrade_is_blocked_while_unreclaimed_publication_objects_exist(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_abandoned() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(text(SEED_ISSUANCE))
                await connection.execute(text(seed_generation(FIRST, 1, "abandoned")))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_abandoned())
        with pytest.raises(RuntimeError, match="0082 downgrade blocked"):
            downgrade_to(migration_url, PRE_PUBLICATION_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
