"""Migration 0044: shared notification outbox and organization preferences."""

import asyncio

import pytest
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

from app.models.notification import NotificationChannel, NotificationType
from app.services.notifications import notification_dedupe_fingerprint

PRE_OUTBOX_REVISION = "0043_campaign_review_lifecycle"
NOTICE_ID = "44000000-0000-0000-0000-000000000001"
RECIPIENT_ID = "44000000-0000-0000-0000-000000000002"


async def _seed_legacy_notification(migration_url: str) -> None:
    engine = create_async_engine(migration_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                    "VALUES (:id, 'migration-0044@example.com', 'hash', 'Migration User', "
                    "'driver', 'active')"
                ),
                {"id": RECIPIENT_ID},
            )
            await connection.execute(
                text(
                    "INSERT INTO notifications "
                    "(id, recipient_user_id, type_key, template_version, payload, dedupe_key, "
                    "created_at) VALUES (:id, :recipient, 'fraud_hold_raised', 'v1', "
                    "'{\"fraud_flag_id\": \"legacy\", \"trip_session_id\": \"trip\"}'::jsonb, "
                    "'legacy-notice', '2026-08-24 10:00:00+00')"
                ),
                {"id": NOTICE_ID, "recipient": RECIPIENT_ID},
            )
    finally:
        await engine.dispose()


def test_notification_outbox_backfill_has_exact_fingerprint_and_lossless_downgrade(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def verify_upgrade() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT recipient_user_id, type_key, template_version, payload, "
                            "channel, status, attempt_count, provider_message_id, "
                            "dedupe_fingerprint, sent_at, delivered_at, read_at, created_at "
                            "FROM notifications WHERE id = :id"
                        ),
                        {"id": NOTICE_ID},
                    )
                ).mappings().one()
                assert row["channel"] == "in_app"
                assert row["status"] == "sent"
                assert row["attempt_count"] == 0
                assert row["provider_message_id"] is None
                assert row["sent_at"] == row["created_at"]
                assert row["delivered_at"] is None
                assert row["read_at"] is None
                assert row["dedupe_fingerprint"] == notification_dedupe_fingerprint(
                    recipient_user_id=row["recipient_user_id"],
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    template_version="v1",
                    channel=NotificationChannel.IN_APP,
                    payload=row["payload"],
                )
        finally:
            await engine.dispose()

    async def verify_downgrade() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT type_key, template_version, payload, dedupe_key, created_at "
                            "FROM notifications WHERE id = :id"
                        ),
                        {"id": NOTICE_ID},
                    )
                ).one()
                assert row[0:4] == (
                    "fraud_hold_raised",
                    "v1",
                    {"fraud_flag_id": "legacy", "trip_session_id": "trip"},
                    "legacy-notice",
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_OUTBOX_REVISION, monkeypatch)
        asyncio.run(_seed_legacy_notification(migration_url))
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(verify_upgrade())
        downgrade_to(migration_url, PRE_OUTBOX_REVISION, monkeypatch)
        asyncio.run(verify_downgrade())
    finally:
        asyncio.run(drop_database(migration_url))


def test_notification_evidence_is_frozen_and_new_authority_blocks_downgrade(
    monkeypatch,
) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def verify_guards_and_create_preference() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="immutable"):
                    await connection.execute(
                        text(
                            "UPDATE notifications SET payload = '{\"changed\": true}'::jsonb "
                            "WHERE id = :id"
                        ),
                        {"id": NOTICE_ID},
                    )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text("DELETE FROM notifications WHERE id = :id"), {"id": NOTICE_ID}
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE notifications SET provider_message_id = 'provider-0044' "
                        "WHERE id = :id"
                    ),
                    {"id": NOTICE_ID},
                )
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="provider_message_id"):
                    await connection.execute(
                        text(
                            "INSERT INTO notifications "
                            "(id, recipient_user_id, type_key, template_version, payload, "
                            "dedupe_key, channel, status, attempt_count, provider_message_id, "
                            "dedupe_fingerprint, sent_at) VALUES "
                            "('44000000-0000-0000-0000-000000000005', :recipient, "
                            "'fraud_hold_raised', 'v1', '{}'::jsonb, 'provider-conflict', "
                            "'transactional_email', 'sent', 1, 'provider-0044', "
                            "repeat('b', 64), now())"
                        ),
                        {"recipient": RECIPIENT_ID},
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE notifications SET read_at = now() WHERE id = :id"),
                    {"id": NOTICE_ID},
                )
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO advertiser_organization_notification_preferences "
                        "(id, advertiser_organization_id) VALUES "
                        "('44000000-0000-0000-0000-000000000003', "
                        "'44000000-0000-0000-0000-000000000004')"
                    )
                )
                assert await connection.scalar(
                    text(
                        "SELECT transactional_email_enabled FROM "
                        "advertiser_organization_notification_preferences"
                    )
                ) is True
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_OUTBOX_REVISION, monkeypatch)
        asyncio.run(_seed_legacy_notification(migration_url))
        upgrade_to(migration_url, "head", monkeypatch)
        asyncio.run(verify_guards_and_create_preference())
        with pytest.raises(RuntimeError, match="0044 downgrade blocked"):
            downgrade_to(migration_url, PRE_OUTBOX_REVISION, monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
