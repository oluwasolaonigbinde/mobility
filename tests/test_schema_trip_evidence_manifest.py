"""PostgreSQL migration coverage for the R34 evidence authority."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from database_helpers import (
    BASELINE_REVISION,
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    fetch_all,
    seed_ping_graph,
    upgrade_to,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.services.data_lifecycle import add_months, month_start, run_ping_retention

EVIDENCE_REVISION = "head"
TRIP_ID = "74000000-0000-0000-0000-000000000001"


def test_manifest_entry_insert_serializes_with_manifest_commit(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def exercise_race() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO trip_sessions "
                        "(id, assignment_id, campaign_id, driver_profile_id, vehicle_id, "
                        "started_by_user_id, status, started_at, evidence_protocol_version, "
                        "metadata) VALUES "
                        "(:trip, '76000000-0000-0000-0000-000000000002', "
                        "'76000000-0000-0000-0000-000000000003', "
                        "'76000000-0000-0000-0000-000000000004', "
                        "'76000000-0000-0000-0000-000000000005', "
                        "'76000000-0000-0000-0000-000000000006', "
                        "'active', now(), 2, '{}'::jsonb)"
                    ),
                    {"trip": TRIP_ID},
                )

            end_connection = await engine.connect()
            insert_connection = await engine.connect()
            end_transaction = await end_connection.begin()
            insert_transaction = await insert_connection.begin()
            try:
                await end_connection.execute(
                    text("SELECT id FROM trip_sessions WHERE id=:trip FOR UPDATE"),
                    {"trip": TRIP_ID},
                )
                await end_connection.execute(
                    text(
                        "UPDATE trip_sessions SET status='ended', ended_at=now(), "
                        "end_reason='driver_ended', evidence_manifest_version=2, "
                        "evidence_manifest_root_sha256=repeat('a', 64), "
                        "evidence_manifest_batch_count=0, evidence_manifest_ping_count=0, "
                        "evidence_manifest_committed_at=now() WHERE id=:trip"
                    ),
                    {"trip": TRIP_ID},
                )
                insert_task = asyncio.create_task(
                    insert_connection.execute(
                        text(
                            "INSERT INTO trip_evidence_manifest_entries "
                            "(trip_session_id, batch_sequence, idempotency_key, "
                            "payload_hash_version, payload_hash, submitted_count) VALUES "
                            "(:trip, 0, 'racing-entry', 2, repeat('b', 64), 1)"
                        ),
                        {"trip": TRIP_ID},
                    )
                )
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(insert_task), timeout=0.25)
                await end_transaction.commit()
                with pytest.raises(DBAPIError, match="manifest entries are immutable"):
                    await insert_task
                await insert_transaction.rollback()
            finally:
                if end_transaction.is_active:
                    await end_transaction.rollback()
                if insert_transaction.is_active:
                    await insert_transaction.rollback()
                await end_connection.close()
                await insert_connection.close()

            async with engine.connect() as connection:
                count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM trip_evidence_manifest_entries "
                        "WHERE trip_session_id=:trip"
                    ),
                    {"trip": TRIP_ID},
                )
                assert count == 0
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, EVIDENCE_REVISION, monkeypatch)
        asyncio.run(exercise_race())
    finally:
        asyncio.run(drop_database(migration_url))


def test_signed_v2_batches_follow_audited_partition_retention(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def sign_seeded_evidence(seeded: dict, received_at: datetime) -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                batch_rows = [
                    (0, seeded["batches"]["oldest"][0], "a"),
                    (1, seeded["batches"]["middle"][0], "b"),
                    (2, seeded["batches"]["straddling"][0], "c"),
                ]
                for sequence, batch_id, digest_character in batch_rows:
                    digest = digest_character * 64
                    await connection.execute(
                        text(
                            "UPDATE location_ping_batches SET "
                            "batch_sequence=:sequence, payload_hash_version=2, "
                            "payload_hash=:digest, pings_submitted=pings_accepted, "
                            "pings_rejected=0, evidence_scope='manifest', "
                            "receipt_format_version=2, receipt_key_version=1, "
                            "receipt_signature=:signature, receipt_outcome='accepted' "
                            "WHERE id=:batch_id"
                        ),
                        {
                            "sequence": sequence,
                            "digest": digest,
                            "signature": f"batch-signature-{sequence}",
                            "batch_id": batch_id,
                        },
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO trip_evidence_manifest_entries "
                            "(trip_session_id, batch_sequence, idempotency_key, "
                            "payload_hash_version, payload_hash, submitted_count) "
                            "SELECT trip_session_id, batch_sequence, idempotency_key, "
                            "payload_hash_version, payload_hash, pings_submitted "
                            "FROM location_ping_batches WHERE id=:batch_id"
                        ),
                        {"batch_id": batch_id},
                    )
                await connection.execute(
                    text(
                        "UPDATE trip_sessions SET status='sealed', ended_at=:ended_at, "
                        "end_reason='driver_ended', sealed_at=:ended_at, "
                        "seal_reason='client_complete', evidence_protocol_version=2, "
                        "evidence_manifest_version=2, "
                        "evidence_manifest_root_sha256=repeat('d', 64), "
                        "evidence_manifest_batch_count=3, evidence_manifest_ping_count=8, "
                        "evidence_manifest_committed_at=:ended_at, "
                        "evidence_manifest_complete=true, "
                        "evidence_manifest_verified_at=:ended_at, "
                        "evidence_manifest_receipt_format_version=2, "
                        "evidence_manifest_receipt_key_version=1, "
                        "evidence_manifest_receipt_signature='manifest-signature' "
                        "WHERE id=:trip_id"
                    ),
                    {
                        "trip_id": seeded["trip_id"],
                        "ended_at": received_at,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO quarantined_ping_batches "
                        "(trip_session_id, idempotency_key, batch_sequence, "
                        "payload_hash_version, payload_hash, payload, ping_count, "
                        "pings_submitted, pings_rejected, receipt_format_version, "
                        "receipt_key_version, receipt_signature, receipt_outcome, received_at) "
                        "VALUES (:trip_id, 'signed-expired-quarantine', 3, 2, "
                        "repeat('e', 64), '{\"pings\": []}'::jsonb, 1, 1, 1, "
                        "2, 1, 'quarantine-signature', 'quarantined', :received_at)"
                    ),
                    {
                        "trip_id": seeded["trip_id"],
                        "received_at": received_at,
                    },
                )
        finally:
            await engine.dispose()

    async def run_retention(injected_now: datetime) -> dict[str, object]:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            return await run_ping_retention(
                engine,
                sessionmaker,
                settings=Settings(
                    environment="test",
                    ping_retention_months=12,
                    partition_premake_months=4,
                ),
                now=injected_now,
            )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, BASELINE_REVISION, monkeypatch)
        seeded = seed_ping_graph(migration_url)
        upgrade_to(migration_url, EVIDENCE_REVISION, monkeypatch)
        current_month = month_start(datetime.now(UTC))
        asyncio.run(sign_seeded_evidence(seeded, current_month))

        result = asyncio.run(run_retention(add_months(current_month, 13) + timedelta(days=1)))

        oldest_partition = f"location_pings_p{seeded['months'][0].strftime('%Y_%m')}"
        assert oldest_partition in result["dropped"]
        assert result["batches_purged"] == 3
        assert result["quarantines_purged"] == 1
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM location_ping_batches")
        ) == [(0,)]
        assert asyncio.run(
            fetch_all(migration_url, "SELECT count(*) FROM quarantined_ping_batches")
        ) == [(0,)]
        manifest = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT evidence_manifest_receipt_signature, "
                "evidence_manifest_complete, count(e.batch_sequence) "
                "FROM trip_sessions t JOIN trip_evidence_manifest_entries e "
                "ON e.trip_session_id=t.id WHERE t.id=:trip_id "
                "GROUP BY t.id",
                {"trip_id": seeded["trip_id"]},
            )
        )
        assert manifest == [("manifest-signature", True, 3)]
        events = asyncio.run(
            fetch_all(
                migration_url,
                "SELECT event, partition_name, row_count FROM data_purge_audit "
                "ORDER BY created_at, id",
            )
        )
        assert ("purge_started", oldest_partition, 3) in events
        assert ("dropped", oldest_partition, None) in events
        assert ("batches_purged", None, 3) in events
        assert ("quarantined_batches_purged", None, 1) in events
    finally:
        asyncio.run(drop_database(migration_url))
