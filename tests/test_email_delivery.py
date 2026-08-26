import asyncio
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from starlette import status

from app.adapters.messaging import EmailMessage, EmailSendError, EmailSubmission
from app.core.config import Settings
from app.core.errors import AppError
from app.jobs.email_delivery import process_email_notification
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationDeliveryReceipt,
    NotificationStatus,
    NotificationType,
)
from app.models.organization import (
    AdvertiserOrganization,
    AdvertiserOrganizationNotificationPreference,
    MembershipRole,
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.services.notifications import (
    create_advertiser_email_notification,
    email_receipt_fingerprint,
    record_email_delivery_receipt,
)


class RecordingEmailAdapter:
    def __init__(self, failures: list[EmailSendError] | None = None) -> None:
        self.failures = failures or []
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> EmailSubmission:
        self.messages.append(message)
        if self.failures:
            raise self.failures.pop(0)
        return EmailSubmission(provider_message_id=f"provider-{message.idempotency_key}")


async def _seed_advertiser(sessionmaker, *, enabled: bool = True):
    async with sessionmaker() as session:
        user = User(
            email=f"advertiser-{uuid4()}@example.test",
            password_hash="hash",
            full_name="Advertiser",
            role=UserRole.ADVERTISER,
            status=UserStatus.ACTIVE,
        )
        organization = AdvertiserOrganization(
            name="Test advertiser",
            status=OrganizationStatus.ACTIVE,
            currency="NGN",
        )
        session.add_all([user, organization])
        await session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=MembershipRole.OWNER,
                    status=MembershipStatus.ACTIVE,
                ),
                AdvertiserOrganizationNotificationPreference(
                    advertiser_organization_id=organization.id,
                    transactional_email_enabled=enabled,
                ),
            ]
        )
        await session.commit()
        return user.id, organization.id


def _settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "payout_crypto_keyring_b64": '{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}',
        "email_delivery_retry_base_seconds": 10,
        "email_delivery_claim_seconds": 30,
        "email_delivery_max_attempts": 3,
        "email_provider": "",
        "email_sender_address": "",
        "email_smtp_host": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_advertiser_email_creation_honors_org_preference_and_exact_retry(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            first = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": str(uuid4())},
                dedupe_key="email:test:1",
            )
            assert first is not None
            retry = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": first.payload["fraud_flag_id"]},
                dedupe_key="email:test:1",
            )
            assert retry is not None and retry.id == first.id
            preference = await session.scalar(
                select(AdvertiserOrganizationNotificationPreference).where(
                    AdvertiserOrganizationNotificationPreference.advertiser_organization_id
                    == organization_id
                )
            )
            preference.transactional_email_enabled = False
            await session.flush()
            suppressed = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": str(uuid4())},
                dedupe_key="email:test:2",
            )
            await session.commit()
            assert suppressed is None
            assert (
                await session.scalar(
                    select(func.count()).select_from(Notification).where(
                        Notification.channel
                        == NotificationChannel.TRANSACTIONAL_EMAIL.value
                    )
                )
                == 1
            )

    asyncio.run(run())


def test_email_worker_retries_with_same_idempotency_key_then_sends(db_sessionmaker) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": str(uuid4())},
                dedupe_key="email:worker:1",
            )
            await session.commit()
            notice_id = notice.id
        adapter = RecordingEmailAdapter(
            [EmailSendError("synthetic_outage", retryable=True)]
        )
        now = datetime.now(UTC)
        ctx = {
            "sessionmaker": db_sessionmaker,
            "settings": _settings(),
            "email_adapter": adapter,
        }
        assert (
            await process_email_notification(ctx, str(notice_id), now=now)
            == "retry_scheduled"
        )
        assert (
            await process_email_notification(ctx, str(notice_id), now=now)
            == "skipped"
        )
        assert (
            await process_email_notification(
                ctx, str(notice_id), now=now + timedelta(seconds=10)
            )
            == "sent"
        )
        assert [message.idempotency_key for message in adapter.messages] == [
            str(notice_id),
            str(notice_id),
        ]
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored.status == NotificationStatus.SENT.value
            assert stored.attempt_count == 2
            assert stored.provider_message_id == f"provider-{notice_id}"

    asyncio.run(run())


def test_email_worker_fails_closed_when_preference_changes_before_send(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:preference:1",
            )
            preference = await session.scalar(
                select(AdvertiserOrganizationNotificationPreference).where(
                    AdvertiserOrganizationNotificationPreference.advertiser_organization_id
                    == organization_id
                )
            )
            preference.transactional_email_enabled = False
            await session.commit()
            notice_id = notice.id
        adapter = RecordingEmailAdapter()
        result = await process_email_notification(
            {
                "sessionmaker": db_sessionmaker,
                "settings": _settings(),
                "email_adapter": adapter,
            },
            str(notice_id),
        )
        assert result == "skipped"
        assert adapter.messages == []
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored.status == NotificationStatus.FAILED.value
            assert stored.last_error_code == "email_preference_disabled"

    asyncio.run(run())


def test_email_worker_missing_provider_schedules_retry_without_claiming_send(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:disabled-provider:1",
            )
            await session.commit()
            notice_id = notice.id
        result = await process_email_notification(
            {"sessionmaker": db_sessionmaker, "settings": _settings()}, str(notice_id)
        )
        assert result == "retry_scheduled"
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored.status == NotificationStatus.PENDING.value
            assert stored.last_error_code == "email_provider_unconfigured"
            assert stored.delivery_claim_token is None
            assert stored.next_attempt_at is not None

    asyncio.run(run())


def test_email_worker_concurrent_claim_dispatches_once(postgis_db_sessionmaker) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(postgis_db_sessionmaker)
        async with postgis_db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:race:1",
            )
            await session.commit()
            notice_id = notice.id
        adapter = RecordingEmailAdapter()
        ctx = {
            "sessionmaker": postgis_db_sessionmaker,
            "settings": _settings(),
            "email_adapter": adapter,
        }
        results = await asyncio.gather(
            process_email_notification(ctx, str(notice_id)),
            process_email_notification(ctx, str(notice_id)),
        )
        assert sorted(results) == ["sent", "skipped"]
        assert len(adapter.messages) == 1

    asyncio.run(run())


def test_signed_receipt_is_exactly_idempotent_and_first_terminal_wins(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:receipt:1",
            )
            notice.status = NotificationStatus.SENT.value
            notice.provider_message_id = "provider-message-1"
            notice.sent_at = datetime.now(UTC)
            await session.commit()
        payload = {
            "provider_event_id": "provider-event-1",
            "provider_message_id": "provider-message-1",
            "outcome": "delivered",
            "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        canonical, _ = email_receipt_fingerprint(payload)
        signature = hmac.new(b"receipt-secret", canonical, hashlib.sha256).hexdigest()
        async with db_sessionmaker() as session:
            first = await record_email_delivery_receipt(
                session,
                payload=payload,
                signature=f"sha256={signature}",
                signing_key_id="local-v1",
                signing_secret=b"receipt-secret",
                configured_key_id="local-v1",
            )
            await session.commit()
            retry = await record_email_delivery_receipt(
                session,
                payload=payload,
                signature=signature,
                signing_key_id="local-v1",
                signing_secret=b"receipt-secret",
                configured_key_id="local-v1",
            )
            assert retry.id == first.id
            assert (
                await session.scalar(
                    select(func.count()).select_from(NotificationDeliveryReceipt)
                )
                == 1
            )
            notice = await session.scalar(
                select(Notification).where(
                    Notification.provider_message_id == "provider-message-1"
                )
            )
            assert notice.status == NotificationStatus.DELIVERED.value
            with pytest.raises(ValueError, match="immutable"):
                first.outcome = "failed"
                await session.flush()
            await session.rollback()

        changed = dict(payload, outcome="failed")
        changed_canonical, _ = email_receipt_fingerprint(changed)
        changed_signature = hmac.new(
            b"receipt-secret", changed_canonical, hashlib.sha256
        ).hexdigest()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as caught:
                await record_email_delivery_receipt(
                    session,
                    payload=changed,
                    signature=changed_signature,
                    signing_key_id="local-v1",
                    signing_secret=b"receipt-secret",
                    configured_key_id="local-v1",
                )
            assert caught.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(run())


def test_receipt_verification_fails_closed_without_config_or_valid_signature(
    db_sessionmaker,
) -> None:
    payload = {
        "provider_event_id": "event",
        "provider_message_id": "message",
        "outcome": "delivered",
        "occurred_at": datetime.now(UTC).isoformat(),
    }

    async def run() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as unconfigured:
                await record_email_delivery_receipt(
                    session,
                    payload=payload,
                    signature="bad",
                    signing_key_id="",
                    signing_secret=None,
                    configured_key_id="",
                )
            assert unconfigured.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            with pytest.raises(AppError) as invalid:
                await record_email_delivery_receipt(
                    session,
                    payload=payload,
                    signature="bad",
                    signing_key_id="local-v1",
                    signing_secret=b"secret",
                    configured_key_id="local-v1",
                )
            assert invalid.value.status_code == status.HTTP_401_UNAUTHORIZED

    asyncio.run(run())
