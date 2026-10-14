"""Current PostgreSQL schema: durable report jobs and immutable CSV/PDF artifacts."""

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


def test_report_frozen_authority_artifacts_are_guarded(
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
                        "INSERT INTO report_issuances "
                        "(id, organization_id, campaign_id, measurement_run_id, "
                        "requested_by_user_id, client_request_id, request_fingerprint, version, "
                        "snapshot, snapshot_sha256, authority_fingerprint, input_manifest_sha256, "
                        "result_manifest_sha256, proof_manifest_sha256, report_snapshot_sha256, "
                        "schema_version, renderer_version, method_revision, roi_decision, "
                        "synthetic, "
                        "status, worker_attempts) VALUES "
                        "('71000000-0000-0000-0000-000000000001', "
                        "'71000000-0000-0000-0000-000000000002', "
                        "'71000000-0000-0000-0000-000000000003', "
                        "'71000000-0000-0000-0000-000000000004', "
                        "'71000000-0000-0000-0000-000000000005', "
                        "'71000000-0000-0000-0000-000000000006', repeat('a', 64), 1, "
                        "'{}'::jsonb, repeat('b', 64), repeat('c', 64), repeat('d', 64), "
                        "repeat('e', 64), repeat('f', 64), repeat('1', 64), "
                        "'campaign-performance-export-v1', 'campaign-report-renderer-v1', "
                        "'measurement-contract-v1', 'OMIT', true, 'queued', 0)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO stored_files "
                        "(id, upload_intent_id, organization_id, uploader_user_id, purpose, "
                        "original_filename, storage_key, content_type, size_bytes, "
                        "checksum_sha256, scan_status, actual_content_type, scan_attempts) VALUES "
                        "('71000000-0000-0000-0000-000000000007', NULL, "
                        "'71000000-0000-0000-0000-000000000002', "
                        "'71000000-0000-0000-0000-000000000005', 'report_export', "
                        "'cardvert-campaign-performance-analysis-v1.csv', "
                        "'managed/71000000/reports/71000000/artifact.csv', 'text/csv', 10, "
                        "repeat('2', 64), 'clean', 'text/csv', 0)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO report_artifacts "
                        "(id, report_issuance_id, stored_file_id, format, content_type, "
                        "size_bytes, checksum_sha256, renderer_version) VALUES "
                        "('71000000-0000-0000-0000-000000000008', "
                        "'71000000-0000-0000-0000-000000000001', "
                        "'71000000-0000-0000-0000-000000000007', 'csv', 'text/csv', 10, "
                        "repeat('2', 64), 'campaign-report-renderer-v1')"
                    )
                )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE report_issuances SET worker_attempts = 1 "
                        "WHERE id = '71000000-0000-0000-0000-000000000001'"
                    )
                )
            with pytest.raises(DBAPIError, match="frozen authority is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE report_issuances SET method_revision = 'changed' "
                            "WHERE id = '71000000-0000-0000-0000-000000000001'"
                        )
                    )
            with pytest.raises(DBAPIError, match="report artifacts are immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE report_artifacts SET size_bytes = size_bytes")
                    )
            with pytest.raises(DBAPIError, match="stored file is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE stored_files SET purpose = 'creative' "
                            "WHERE id = '71000000-0000-0000-0000-000000000007'"
                        )
                    )
            with pytest.raises(DBAPIError, match="stored file is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM stored_files "
                            "WHERE id = '71000000-0000-0000-0000-000000000007'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(text("DELETE FROM report_issuances"))
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(seed_and_mutate())
    finally:
        asyncio.run(drop_database(migration_url))
