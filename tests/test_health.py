import asyncio
import base64
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)


def test_root_health_returns_service_status(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "mobility-adtech-api",
        "environment": "test",
        "status": "ok",
    }


def test_api_health_returns_versioned_service_status(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "mobility-adtech-api",
        "environment": "test",
        "status": "ok",
        "api_version": "v1",
    }


def test_api_ready_without_database_url_is_deterministic(client) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "components": {
            "database": "not_configured",
            "redis": "not_configured",
            "worker": "not_configured",
            "storage": "not_configured",
            "scanner": "not_configured",
            "trip_evidence_signing": "ok",
        },
    }


def test_api_ready_fails_closed_without_trip_evidence_signing_authority(client) -> None:
    from app.core.config import Settings, get_settings

    settings = Settings(
        environment="production",
        jwt_secret_key="production-secret-with-at-least-32-characters",
        database_url=(
            "postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require"
        ),
        redis_url="rediss://:synthetic-redis-secret@redis:6379/0",
        trip_evidence_signing_keyring_b64=None,
    )
    previous = client.app.dependency_overrides.get(get_settings)
    client.app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        if previous is None:
            client.app.dependency_overrides.pop(get_settings, None)
        else:
            client.app.dependency_overrides[get_settings] = previous

    assert response.status_code == 503
    assert response.json()["components"]["trip_evidence_signing"] == "not_configured"


def test_api_ready_fails_closed_when_database_references_a_removed_signing_key(
    client, monkeypatch
) -> None:
    from app.core.config import Settings, get_settings

    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = None
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        engine = create_async_engine(migration_url, poolclass=NullPool)

        async def seed_referenced_key() -> None:
            assert engine is not None
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO trip_sessions "
                        "(id, assignment_id, campaign_id, driver_profile_id, vehicle_id, "
                        "started_by_user_id, status, started_at, metadata) VALUES "
                        "('75000000-0000-0000-0000-000000000001', "
                        "'75000000-0000-0000-0000-000000000002', "
                        "'75000000-0000-0000-0000-000000000003', "
                        "'75000000-0000-0000-0000-000000000004', "
                        "'75000000-0000-0000-0000-000000000005', "
                        "'75000000-0000-0000-0000-000000000006', "
                        "'active', now(), '{}'::jsonb)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO location_ping_batches "
                        "(id, trip_session_id, idempotency_key, payload_hash, "
                        "payload_hash_version, pings_submitted, pings_accepted, "
                        "pings_rejected, evidence_scope, receipt_format_version, "
                        "receipt_key_version, receipt_signature, receipt_outcome, "
                        "received_at, metadata) VALUES "
                        "('75000000-0000-0000-0000-000000000011', "
                        "'75000000-0000-0000-0000-000000000001', 'old-key-batch', "
                        "repeat('a', 64), 2, 1, 1, 0, 'manifest', 2, 2, "
                        "'old-key-signature', 'accepted', now(), '{}'::jsonb)"
                    )
                )

        asyncio.run(seed_referenced_key())
        encoded = base64.b64encode(b"a" * 32).decode()
        settings = Settings(
            database_url=migration_url,
            trip_evidence_signing_keyring_b64=json.dumps({"1": encoded}),
            trip_evidence_signing_key_version=1,
        )

        previous = client.app.dependency_overrides.get(get_settings)
        client.app.dependency_overrides[get_settings] = lambda: settings
        try:
            response = client.get("/api/v1/health/ready")
        finally:
            if previous is None:
                client.app.dependency_overrides.pop(get_settings, None)
            else:
                client.app.dependency_overrides[get_settings] = previous

        assert response.status_code == 503
        assert response.json()["components"]["database"] == "ok"
        assert response.json()["components"]["trip_evidence_signing"] == "unavailable"
    finally:
        if engine is not None:
            asyncio.run(engine.dispose())
        asyncio.run(drop_database(migration_url))
