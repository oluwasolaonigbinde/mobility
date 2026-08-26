"""Migration 0052: private upload intents and managed stored-file authority."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

_migration_path = Path(__file__).parents[1] / "alembic/versions/0052_stored_files.py"
_migration_spec = importlib.util.spec_from_file_location("migration_0052", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def test_private_file_tables_enforce_retry_scope_and_populated_downgrade_guard() -> None:
    engine = create_engine("sqlite://")
    organization_id = uuid4()
    uploader_id = uuid4()
    upload_id = uuid4()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE advertiser_organizations (id UUID PRIMARY KEY)"
        )
        connection.execute(
            text("INSERT INTO users (id) VALUES (:id)"), {"id": uploader_id.hex}
        )
        connection.execute(
            text("INSERT INTO advertiser_organizations (id) VALUES (:id)"),
            {"id": organization_id.hex},
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()

        values = {
            "id": upload_id.hex,
            "organization_id": organization_id.hex,
            "uploader_user_id": uploader_id.hex,
            "client_request_id": uuid4().hex,
            "request_fingerprint": "f" * 64,
            "object_key": f"unconfirmed/{organization_id}/{upload_id}",
            "expires_at": "2026-08-27T00:00:00Z",
        }
        connection.execute(
            text(
                "INSERT INTO file_upload_intents "
                "(id,organization_id,uploader_user_id,client_request_id,request_fingerprint,"
                "purpose,original_filename,declared_content_type,declared_size_bytes,"
                "declared_sha256,object_key,expires_at,status) VALUES "
                "(:id,:organization_id,:uploader_user_id,:client_request_id,"
                ":request_fingerprint,'creative','art.png','image/png',68,:sha256,"
                ":object_key,:expires_at,'pending')"
            ),
            values | {"sha256": "a" * 64},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO file_upload_intents "
                    "(id,organization_id,uploader_user_id,client_request_id,request_fingerprint,"
                    "purpose,original_filename,declared_content_type,declared_size_bytes,"
                    "declared_sha256,object_key,expires_at,status) VALUES "
                    "(:second_id,:organization_id,:uploader_user_id,:client_request_id,"
                    ":request_fingerprint,'creative','art.png','image/png',68,:sha256,"
                    ":second_key,:expires_at,'pending')"
                ),
                values
                | {
                    "second_id": uuid4().hex,
                    "second_key": f"unconfirmed/{organization_id}/{uuid4()}",
                    "sha256": "a" * 64,
                },
            )

    # Re-open after the expected uniqueness failure rolled back its transaction.
    with engine.begin() as connection:
        count = connection.scalar(text("SELECT count(*) FROM file_upload_intents"))
        assert count == 1
        with pytest.raises(RuntimeError, match="0052 downgrade blocked"):
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()
        connection.execute(text("DELETE FROM file_upload_intents"))
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        assert connection.scalar(
            text(
                "SELECT count(*) FROM sqlite_master WHERE type='table' "
                "AND name IN ('file_upload_intents','stored_files')"
            )
        ) == 0
