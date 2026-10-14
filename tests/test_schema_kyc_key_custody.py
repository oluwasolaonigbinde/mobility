"""Current PostgreSQL subject-scoped upload retry identity."""

import asyncio
from uuid import uuid4

import pytest
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def test_subject_scope_constraints_and_retry_identity_are_enforced(monkeypatch) -> None:
    database_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def exercise():
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                user_id = uuid4().hex
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                        "VALUES (:id, :email, 'unused', 'KYC subject', 'driver', 'active')"
                    ),
                    {"id": user_id, "email": f"{user_id}@example.test"},
                )
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
                await connection.execute(statement, values)
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        statement, values | {"id": uuid4().hex, "key": str(uuid4())}
                    )
        finally:
            await engine.dispose()

    try:
        upgrade_to(database_url, "head", monkeypatch)
        asyncio.run(exercise())
    finally:
        asyncio.run(drop_database(database_url))
