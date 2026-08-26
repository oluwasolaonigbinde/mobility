"""Migration 0055: subject-scoped files and protected KYC authority."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

_migration_path = Path(__file__).parents[1] / "alembic/versions/0055_kyc_key_custody.py"
_migration_spec = importlib.util.spec_from_file_location("migration_0055", _migration_path)
assert _migration_spec is not None and _migration_spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(MIGRATION)


def _create_pre_0055_schema(connection) -> None:
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE advertiser_organizations (id UUID PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE driver_profiles (id UUID PRIMARY KEY, user_id UUID NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE payee_bank_account_versions (id UUID PRIMARY KEY)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE vehicles (id UUID PRIMARY KEY, driver_profile_id UUID NOT NULL)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE file_upload_intents ("
        "id UUID PRIMARY KEY, organization_id UUID NOT NULL, uploader_user_id UUID NOT NULL, "
        "client_request_id UUID NOT NULL, request_fingerprint VARCHAR(64) NOT NULL, "
        "purpose VARCHAR(32) NOT NULL CONSTRAINT ck_file_upload_intents_purpose "
        "CHECK (purpose IN ('creative')), original_filename VARCHAR(255) NOT NULL, "
        "declared_content_type VARCHAR(255) NOT NULL, declared_size_bytes BIGINT NOT NULL, "
        "declared_sha256 VARCHAR(64) NOT NULL, object_key VARCHAR(1024) NOT NULL, "
        "expires_at DATETIME NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending', "
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "CONSTRAINT uq_file_upload_intents_scope_request UNIQUE "
        "(organization_id,uploader_user_id,client_request_id))"
    )
    connection.exec_driver_sql(
        "CREATE TABLE stored_files ("
        "id UUID PRIMARY KEY, upload_intent_id UUID NOT NULL, organization_id UUID NOT NULL, "
        "uploader_user_id UUID NOT NULL, purpose VARCHAR(32) NOT NULL "
        "CONSTRAINT ck_stored_files_purpose CHECK (purpose IN ('creative')), "
        "original_filename VARCHAR(255) NOT NULL, storage_key VARCHAR(1024) NOT NULL, "
        "content_type VARCHAR(255) NOT NULL, size_bytes BIGINT NOT NULL, "
        "checksum_sha256 VARCHAR(64) NOT NULL, scan_status VARCHAR(32) NOT NULL, "
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )


def test_populated_creative_scope_survives_and_protected_authority_blocks_downgrade() -> None:
    engine = create_engine("sqlite://")
    user_id, organization_id, profile_id, bank_id = (uuid4().hex for _ in range(4))
    intent_id, file_id, submission_id = (uuid4().hex for _ in range(3))
    with engine.begin() as connection:
        _create_pre_0055_schema(connection)
        connection.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
        connection.execute(
            text("INSERT INTO advertiser_organizations (id) VALUES (:id)"),
            {"id": organization_id},
        )
        connection.execute(
            text("INSERT INTO driver_profiles (id,user_id) VALUES (:id,:user_id)"),
            {"id": profile_id, "user_id": user_id},
        )
        connection.execute(
            text("INSERT INTO payee_bank_account_versions (id) VALUES (:id)"), {"id": bank_id}
        )
        connection.execute(
            text(
                "INSERT INTO file_upload_intents "
                "(id,organization_id,uploader_user_id,client_request_id,request_fingerprint,"
                "purpose,original_filename,declared_content_type,declared_size_bytes,"
                "declared_sha256,object_key,expires_at,status) VALUES "
                "(:id,:org,:user,:request,:fingerprint,'creative','legacy.png','image/png',68,"
                ":sha,:key,'2026-08-27T00:00:00Z','confirmed')"
            ),
            {
                "id": intent_id,
                "org": organization_id,
                "user": user_id,
                "request": uuid4().hex,
                "fingerprint": "f" * 64,
                "sha": "a" * 64,
                "key": f"unconfirmed/{organization_id}/{intent_id}",
            },
        )
        connection.execute(
            text(
                "INSERT INTO stored_files "
                "(id,upload_intent_id,organization_id,uploader_user_id,purpose,original_filename,"
                "storage_key,content_type,size_bytes,checksum_sha256,scan_status) VALUES "
                "(:id,:intent,:org,:user,'creative','legacy.png',:key,'image/png',68,:sha,'clean')"
            ),
            {
                "id": file_id,
                "intent": intent_id,
                "org": organization_id,
                "user": user_id,
                "key": f"managed/{organization_id}/{intent_id}",
                "sha": "a" * 64,
            },
        )
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()
        preserved = connection.execute(
            text("SELECT organization_id,subject_user_id,purpose FROM stored_files WHERE id=:id"),
            {"id": file_id},
        ).one()
        assert preserved == (organization_id, None, "creative")

        connection.execute(
            text(
                "INSERT INTO driver_kyc_submissions "
                "(id,driver_profile_id,nin_record_id,version,client_request_id,status,"
                "encrypted_nin,encryption_algorithm,encryption_key_version,nin_last_four,"
                "bank_account_version_id,created_by_user_id) VALUES "
                "(:id,:profile,:record,1,:request,'pending_review','{}','AES-256-GCM',1,'8901',"
                ":bank,:user)"
            ),
            {
                "id": submission_id,
                "profile": profile_id,
                "record": uuid4().hex,
                "request": uuid4().hex,
                "bank": bank_id,
                "user": user_id,
            },
        )
        with pytest.raises(RuntimeError, match="0055 downgrade blocked"):
            with Operations.context(MigrationContext.configure(connection)):
                MIGRATION.downgrade()
        connection.execute(text("DELETE FROM driver_kyc_submissions"))
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.downgrade()
        restored = connection.execute(
            text("SELECT organization_id,purpose FROM stored_files WHERE id=:id"), {"id": file_id}
        ).one()
        assert restored == (organization_id, "creative")
        assert "subject_user_id" not in {
            row[1] for row in connection.execute(text("PRAGMA table_info(stored_files)"))
        }


def test_subject_scope_constraints_and_retry_identity_are_enforced() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_0055_schema(connection)
        with Operations.context(MigrationContext.configure(connection)):
            MIGRATION.upgrade()
        user_id = uuid4().hex
        connection.execute(text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
        values = {
            "id": uuid4().hex,
            "user": user_id,
            "request": uuid4().hex,
            "fingerprint": "f" * 64,
            "sha": "a" * 64,
            "key": f"unconfirmed/subject/{user_id}/{uuid4().hex}",
        }
        statement = text(
            "INSERT INTO file_upload_intents "
            "(id,organization_id,subject_user_id,uploader_user_id,client_request_id,"
            "request_fingerprint,purpose,original_filename,declared_content_type,"
            "declared_size_bytes,declared_sha256,object_key,expires_at,status) VALUES "
            "(:id,NULL,:user,:user,:request,:fingerprint,'driver_kyc','id.png','image/png',68,"
            ":sha,:key,'2026-08-27T00:00:00Z','pending')"
        )
        connection.execute(statement, values)
        with pytest.raises(IntegrityError):
            connection.execute(statement, values | {"id": uuid4().hex, "key": str(uuid4())})
