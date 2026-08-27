"""Migration 0070: immutable vehicle revisions and review decisions."""

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

PRE_VEHICLE_REVISION = "0069_w3_04b_review_authority"


def test_vehicle_approval_empty_down_up_cycle(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_VEHICLE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, PRE_VEHICLE_REVISION, monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_vehicle_approval_backfill_is_untrusted_and_authority_is_append_only(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_legacy_revision() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO vehicles "
                        "(id, driver_profile_id, plate_number, plate_number_normalized, "
                        "plate_country_code, vehicle_type, make, model, year, color, status) "
                        "VALUES ('70000000-0000-0000-0000-000000000001', "
                        "'70000000-0000-0000-0000-000000000002', 'ABC-123-XY', "
                        "'ABC123XY', 'NG', 'car', 'Toyota', 'Corolla', 2021, 'White', 'pending')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO vehicle_evidence_submissions "
                        "(id, vehicle_id, version, client_request_id, status, created_by_user_id) "
                        "VALUES ('70000000-0000-0000-0000-000000000003', "
                        "'70000000-0000-0000-0000-000000000001', 1, "
                        "'70000000-0000-0000-0000-000000000004', 'pending_review', "
                        "'70000000-0000-0000-0000-000000000005')"
                    )
                )
        finally:
            await engine.dispose()

    async def inspect_and_mutate() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT snapshot_trusted, plate_number_snapshot "
                            "FROM vehicle_evidence_submissions"
                        )
                    )
                ).one()
                assert row == (False, "ABC-123-XY")
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO vehicle_evidence_review_decisions "
                        "(id, submission_id, sequence, client_request_id, request_fingerprint, "
                        "decision, reason_code, owner_match_confirmed, vehicle_identity_confirmed, "
                        "roadworthy_confirmed, pilot_car_confirmed, documents_readable_confirmed, "
                        "valid_until, decided_by_user_id) VALUES "
                        "('70000000-0000-0000-0000-000000000010', "
                        "'70000000-0000-0000-0000-000000000003', 1, "
                        "'70000000-0000-0000-0000-000000000011', repeat('a', 64), "
                        "'approved', 'complete_current_evidence', true, true, true, true, true, "
                        "'2099-01-01T00:00:00Z', '70000000-0000-0000-0000-000000000012')"
                    )
                )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE vehicle_evidence_review_decisions SET decision = decision")
                    )
            with pytest.raises(DBAPIError, match="snapshots are immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE vehicle_evidence_submissions "
                            "SET plate_number_snapshot = 'CHANGED'"
                        )
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_VEHICLE_REVISION, monkeypatch)
        asyncio.run(seed_legacy_revision())
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(inspect_and_mutate())
        with pytest.raises(RuntimeError, match="0070 downgrade blocked"):
            downgrade_to(migration_url, PRE_VEHICLE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_vehicle_approval_model_has_no_owned_autogenerate_drift(monkeypatch) -> None:
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
        owned = {"vehicle_evidence_submissions", "vehicle_evidence_review_decisions"}
        owned_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name in owned:
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
