"""Migration 0080: durable ping dispositions and final evidence adjudication."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

PRE_REVISION = "0079_traffic_density_profile_revisions"
DISPOSITION_REVISION = "0080_trip_evidence_partial_disposition"

TRIP_ID = "80000000-0000-0000-0000-000000000001"
LEGACY_BATCH_ID = "80000000-0000-0000-0000-000000000011"
PARTIAL_BATCH_ID = "80000000-0000-0000-0000-000000000012"
BROKEN_BATCH_ID = "80000000-0000-0000-0000-000000000013"


async def _execute(migration_url: str, statement: str) -> list:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(statement))
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _seed_pre_revision_batch(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL session_replication_role = replica"))
            await connection.execute(
                text(
                    f"""
                    INSERT INTO trip_sessions
                      (id, assignment_id, campaign_id, driver_profile_id, vehicle_id,
                       started_by_user_id, status, started_at, evidence_protocol_version,
                       metadata)
                    VALUES
                      ('{TRIP_ID}', '80000000-0000-0000-0000-000000000002',
                       '80000000-0000-0000-0000-000000000003',
                       '80000000-0000-0000-0000-000000000004',
                       '80000000-0000-0000-0000-000000000005',
                       '80000000-0000-0000-0000-000000000006',
                       'active', now(), 2, '{{}}'::jsonb)
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    INSERT INTO location_ping_batches
                      (id, trip_session_id, idempotency_key, batch_sequence, payload_hash,
                       payload_hash_version, pings_submitted, pings_accepted, pings_rejected,
                       evidence_scope, receipt_format_version, receipt_key_version,
                       receipt_signature, receipt_outcome, received_at, metadata)
                    VALUES
                      ('{LEGACY_BATCH_ID}', '{TRIP_ID}', 'pre-0080-batch', 0,
                       repeat('a', 64), 2, 3, 3, 0, 'manifest', 2, 1,
                       'pre-0080-signature', 'accepted', now(), '{{}}'::jsonb)
                    """
                )
            )
    finally:
        await engine.dispose()


def test_disposition_migration_catalog_backfill_and_immutability(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_REVISION, monkeypatch)
        asyncio.run(_seed_pre_revision_batch(migration_url))
        upgrade_to(migration_url, DISPOSITION_REVISION, monkeypatch)

        # Catalog: the disposition columns exist with the exact declared types.
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'location_ping_batches'
                  AND column_name IN ('rejection_manifest', 'rejection_digest')
                ORDER BY column_name
                """,
            )
        ) == [
            ("rejection_digest", "character varying", "YES"),
            ("rejection_manifest", "jsonb", "YES"),
        ]

        # Backfill: rows written before this revision keep a real SQL NULL, so
        # the receipt value they were signed over is unchanged.
        assert asyncio.run(
            _execute(
                migration_url,
                f"""
                SELECT rejection_manifest IS NULL, rejection_digest IS NULL,
                       receipt_signature
                FROM location_ping_batches WHERE id = '{LEGACY_BATCH_ID}'
                """,
            )
        ) == [(True, True, "pre-0080-signature")]

        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'location_ping_batches'::regclass
                  AND conname IN (
                    'ck_location_ping_batches_rejection_cluster',
                    'ck_location_ping_batches_rejection_digest_length'
                  )
                ORDER BY conname
                """,
            )
        ) == [
            ("ck_location_ping_batches_rejection_cluster",),
            ("ck_location_ping_batches_rejection_digest_length",),
        ]
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'location_ping_batches'::regclass AND NOT tgisinternal
                ORDER BY tgname
                """,
            )
        ) == [
            ("trg_location_ping_batch_disposition_immutable",),
            ("trip_batch_receipt_guard",),
        ]

        # A manifest and its digest may not travel alone.
        with pytest.raises(IntegrityError, match="rejection_cluster"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    INSERT INTO location_ping_batches
                      (id, trip_session_id, idempotency_key, batch_sequence, payload_hash,
                       payload_hash_version, pings_submitted, pings_accepted, pings_rejected,
                       evidence_scope, received_at, rejection_manifest, metadata)
                    VALUES
                      ('{BROKEN_BATCH_ID}', '{TRIP_ID}', 'broken-cluster', 2, repeat('e', 64),
                       2, 1, 1, 0, 'manifest', now(),
                       '{{"version": 1, "results": []}}'::jsonb, '{{}}'::jsonb)
                    """,
                )
            )
        with pytest.raises(DBAPIError, match="dispositions are immutable"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    UPDATE location_ping_batches
                    SET rejection_manifest = '{{"version": 1, "results": []}}'::jsonb,
                        rejection_digest = repeat('d', 64)
                    WHERE id = '{LEGACY_BATCH_ID}'
                    """,
                )
            )

        # Reversible while no durable rejection exists yet.
        downgrade_to(migration_url, PRE_REVISION, monkeypatch)
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'location_ping_batches'
                  AND column_name IN ('rejection_manifest', 'rejection_digest')
                """,
            )
        ) == [(0,)]
        upgrade_to(migration_url, DISPOSITION_REVISION, monkeypatch)

        asyncio.run(
            _execute(
                migration_url,
                f"""
                INSERT INTO location_ping_batches
                  (id, trip_session_id, idempotency_key, batch_sequence, payload_hash,
                   payload_hash_version, pings_submitted, pings_accepted, pings_rejected,
                   evidence_scope, received_at, rejection_manifest, rejection_digest,
                   metadata)
                VALUES
                  ('{PARTIAL_BATCH_ID}', '{TRIP_ID}', 'partial-batch', 1, repeat('b', 64),
                   2, 2, 1, 1, 'manifest', now(),
                   '{{"version": 1, "results": [
                       {{"index": 0, "sequence_number": 0, "status": "accepted",
                         "rejection_code": null}},
                       {{"index": 1, "sequence_number": 1, "status": "rejected",
                         "rejection_code": "INVALID_SPEED"}}
                     ]}}'::jsonb,
                   repeat('c', 64), '{{}}'::jsonb)
                """,
            )
        )

        # Immutability: a stored disposition can never be rewritten, while
        # unrelated columns on the same row stay updatable until it is signed.
        with pytest.raises(DBAPIError, match="dispositions are immutable"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    UPDATE location_ping_batches
                    SET rejection_manifest = '{{"version": 1, "results": []}}'::jsonb,
                        rejection_digest = repeat('d', 64)
                    WHERE id = '{PARTIAL_BATCH_ID}'
                    """,
                )
            )
        asyncio.run(
            _execute(
                migration_url,
                f"""
                UPDATE location_ping_batches
                SET receipt_format_version = 2, receipt_key_version = 1,
                    receipt_signature = 'signed-after-insert', receipt_outcome = 'accepted'
                WHERE id = '{PARTIAL_BATCH_ID}'
                """,
            )
        )

        # Replay: the stored disposition still reads back exactly as written.
        assert asyncio.run(
            _execute(
                migration_url,
                f"""
                SELECT rejection_manifest->'results'->1->>'rejection_code',
                       rejection_digest, receipt_signature
                FROM location_ping_batches WHERE id = '{PARTIAL_BATCH_ID}'
                """,
            )
        ) == [("INVALID_SPEED", "c" * 64, "signed-after-insert")]

        # --- OFF-006 final adjudication ---------------------------------
        assert asyncio.run(
            _execute(
                migration_url,
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'trip_sessions'
                  AND column_name LIKE 'evidence_adjudicat%'
                ORDER BY column_name
                """,
            )
        ) == [
            ("evidence_adjudicated_at", "timestamp with time zone", "YES"),
            ("evidence_adjudication_outcome", "character varying", "YES"),
            ("evidence_adjudication_receipt_format_version", "integer", "YES"),
            ("evidence_adjudication_receipt_key_version", "integer", "YES"),
            ("evidence_adjudication_receipt_signature", "text", "YES"),
        ]
        # Existing trips are not backfilled: an adjudication is a statement the
        # server makes, never one a migration invents.
        assert asyncio.run(
            _execute(
                migration_url,
                f"SELECT evidence_adjudicated_at IS NULL FROM trip_sessions "
                f"WHERE id = '{TRIP_ID}'",
            )
        ) == [(True,)]

        # An adjudication travels as a signed cluster with a constrained outcome.
        for bad in (
            "evidence_adjudicated_at = now()",
            "evidence_adjudicated_at = now(), "
            "evidence_adjudication_outcome = 'looks_fine_to_me', "
            "evidence_adjudication_receipt_format_version = 2, "
            "evidence_adjudication_receipt_key_version = 1, "
            "evidence_adjudication_receipt_signature = 'sig'",
        ):
            with pytest.raises(IntegrityError, match="adjudication_cluster"):
                asyncio.run(
                    _execute(
                        migration_url,
                        f"UPDATE trip_sessions SET {bad} WHERE id = '{TRIP_ID}'",
                    )
                )

        adjudicate = (
            "evidence_adjudicated_at = now(), "
            "evidence_adjudication_outcome = 'incomplete_grace_expired', "
            "evidence_adjudication_receipt_format_version = 2, "
            "evidence_adjudication_receipt_key_version = 1, "
            "evidence_adjudication_receipt_signature = 'signed-adjudication'"
        )
        asyncio.run(
            _execute(
                migration_url,
                f"UPDATE trip_sessions SET {adjudicate} WHERE id = '{TRIP_ID}'",
            )
        )
        # An adjudicated trip can never also hold the verified-manifest
        # authority the money chain reads.
        with pytest.raises(IntegrityError, match="adjudication_excludes_verification"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    UPDATE trip_sessions
                    SET evidence_manifest_complete = true,
                        evidence_manifest_verified_at = now(),
                        evidence_manifest_receipt_format_version = 2,
                        evidence_manifest_receipt_key_version = 1,
                        evidence_manifest_receipt_signature = 'verified'
                    WHERE id = '{TRIP_ID}'
                    """,
                )
            )

        with pytest.raises(DBAPIError, match="adjudications are immutable"):
            asyncio.run(
                _execute(
                    migration_url,
                    f"""
                    UPDATE trip_sessions
                    SET evidence_adjudicated_at = NULL,
                        evidence_adjudication_outcome = NULL,
                        evidence_adjudication_receipt_format_version = NULL,
                        evidence_adjudication_receipt_key_version = NULL,
                        evidence_adjudication_receipt_signature = NULL
                    WHERE id = '{TRIP_ID}'
                    """,
                )
            )
        with pytest.raises(RuntimeError, match="signed final trip evidence adjudications"):
            downgrade_to(migration_url, PRE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))


def test_downgrade_refuses_an_all_valid_signed_disposition(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    try:
        upgrade_to(migration_url, PRE_REVISION, monkeypatch)
        asyncio.run(_seed_pre_revision_batch(migration_url))
        upgrade_to(migration_url, DISPOSITION_REVISION, monkeypatch)
        asyncio.run(
            _execute(
                migration_url,
                f"""
                INSERT INTO location_ping_batches
                  (id, trip_session_id, idempotency_key, batch_sequence, payload_hash,
                   payload_hash_version, pings_submitted, pings_accepted, pings_rejected,
                   evidence_scope, receipt_format_version, receipt_key_version,
                   receipt_signature, receipt_outcome, received_at,
                   rejection_manifest, rejection_digest, metadata)
                VALUES
                  ('{PARTIAL_BATCH_ID}', '{TRIP_ID}', 'all-valid-batch', 1, repeat('b', 64),
                   2, 1, 1, 0, 'manifest', 2, 1, 'signed-all-valid', 'accepted', now(),
                   '{{"version": 1, "results": [
                       {{"index": 0, "sequence_number": 0, "status": "accepted",
                         "rejection_code": null}}
                     ]}}'::jsonb,
                   repeat('c', 64), '{{}}'::jsonb)
                """,
            )
        )

        with pytest.raises(RuntimeError, match="durable ping batch rejection"):
            downgrade_to(migration_url, PRE_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
