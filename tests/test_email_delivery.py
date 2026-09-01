import asyncio
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from starlette import status

from app.adapters.messaging import (
    DisabledEmailAdapter,
    EmailMessage,
    EmailSendError,
    EmailSubmission,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.models.driver_application import DriverApplicationStatus
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
from app.schemas.driver_applications import DriverApplicationCreate
from app.services.driver_applications import (
    issue_driver_application_access,
    submit_driver_application,
)
from app.services.email_delivery import process_email_notification
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


async def _seed_advertiser(sessionmaker, *, enabled: bool | None = True):
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
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
        )
        if enabled is not None:
            session.add(
                AdvertiserOrganizationNotificationPreference(
                    advertiser_organization_id=organization.id,
                    transactional_email_enabled=enabled,
                )
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
        settings = _settings()
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=now,
            )
            == "retry_scheduled"
        )
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=now,
            )
            == "skipped"
        )
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=now + timedelta(seconds=10),
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
            db_sessionmaker,
            notification_id=notice_id,
            settings=_settings(),
            email_adapter=adapter,
            now=datetime.now(UTC),
        )
        assert result == "skipped"
        assert adapter.messages == []
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored.status == NotificationStatus.FAILED.value
            assert stored.last_error_code == "email_preference_disabled"

    asyncio.run(run())


@pytest.mark.parametrize(
    "terminal_status",
    [DriverApplicationStatus.APPROVED, DriverApplicationStatus.REJECTED],
)
def test_driver_onboarding_email_is_not_delivered_after_terminal_application(
    db_sessionmaker,
    settings,
    terminal_status,
) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            submission = await submit_driver_application(
                session,
                DriverApplicationCreate(
                    email=f"terminal-email-{terminal_status.value}@example.test",
                    full_name="Terminal Email Applicant",
                ),
            )
            assert submission.application is not None
            access = await issue_driver_application_access(
                session,
                application=submission.application,
                settings=settings,
            )
            assert access is not None
            notice = await session.scalar(
                select(Notification).where(
                    Notification.type_key
                    == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value,
                    Notification.payload["driver_application_access_id"].as_string()
                    == str(access.id),
                )
            )
            assert notice is not None
            submission.application.status = terminal_status.value
            await session.commit()
            notice_id = notice.id

        adapter = RecordingEmailAdapter()
        result = await process_email_notification(
            db_sessionmaker,
            notification_id=notice_id,
            settings=settings,
            email_adapter=adapter,
            now=datetime.now(UTC),
        )

        assert result == "failed"
        assert adapter.messages == []
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == NotificationStatus.FAILED.value
            assert stored.last_error_code == "driver_onboarding_access_request_inactive"

    asyncio.run(run())


def test_email_service_missing_preference_defaults_to_enabled(db_sessionmaker) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker, enabled=None)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:default-preference:1",
            )
            await session.commit()
            notice_id = notice.id
        adapter = RecordingEmailAdapter()
        now = datetime.now(UTC)

        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=_settings(),
                email_adapter=adapter,
                now=now,
            )
            == "sent"
        )
        assert [message.recipient for message in adapter.messages] == [
            (await _recipient_email(db_sessionmaker, user_id))
        ]

    asyncio.run(run())


async def _recipient_email(sessionmaker, user_id) -> str:
    async with sessionmaker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user.email


def test_email_service_eligibility_and_template_failures_are_terminal(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        inactive_user_id, inactive_organization_id = await _seed_advertiser(
            db_sessionmaker
        )
        async with db_sessionmaker() as session:
            missing_context = Notification(
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v1",
                payload={},
                dedupe_key="email:missing-context:1",
                dedupe_fingerprint=uuid4().hex,
                channel=NotificationChannel.TRANSACTIONAL_EMAIL.value,
            )
            unsupported_template = Notification(
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v2",
                payload={"advertiser_organization_id": str(organization_id)},
                dedupe_key="email:unsupported-template:1",
                dedupe_fingerprint=uuid4().hex,
                channel=NotificationChannel.TRANSACTIONAL_EMAIL.value,
            )
            inactive_org_notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=inactive_organization_id,
                recipient_user_id=inactive_user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:inactive-org:1",
            )
            inactive_org = await session.get(
                AdvertiserOrganization, inactive_organization_id
            )
            assert inactive_org is not None
            inactive_org.status = OrganizationStatus.SUSPENDED.value
            session.add_all([missing_context, unsupported_template])
            await session.commit()
            ids = [
                missing_context.id,
                unsupported_template.id,
                inactive_org_notice.id,
            ]

        adapter = RecordingEmailAdapter()
        settings = _settings()
        now = datetime.now(UTC)
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=ids[0],
                settings=settings,
                email_adapter=adapter,
                now=now,
            )
            == "skipped"
        )
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=ids[1],
                settings=settings,
                email_adapter=adapter,
                now=now,
            )
            == "failed"
        )
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=ids[2],
                settings=settings,
                email_adapter=adapter,
                now=now,
            )
            == "skipped"
        )
        assert adapter.messages == []
        async with db_sessionmaker() as session:
            stored = [await session.get(Notification, notification_id) for notification_id in ids]
            assert all(item is not None for item in stored)
            assert [item.status for item in stored if item is not None] == [
                NotificationStatus.FAILED.value,
                NotificationStatus.FAILED.value,
                NotificationStatus.FAILED.value,
            ]
            assert [item.last_error_code for item in stored if item is not None] == [
                "email_organization_context_missing",
                "unsupported_email_template_version",
                "email_recipient_inactive",
            ]

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
            db_sessionmaker,
            notification_id=notice_id,
            settings=_settings(),
            email_adapter=DisabledEmailAdapter(),
            now=datetime.now(UTC),
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
        settings = _settings()
        now = datetime.now(UTC)
        results = await asyncio.gather(
            process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=now,
            ),
            process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=now,
            ),
        )
        assert sorted(results) == ["sent", "skipped"]
        assert len(adapter.messages) == 1

    asyncio.run(run())


def test_email_service_expired_claim_reclaims_and_stale_claimant_cannot_finish(
    postgis_db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(postgis_db_sessionmaker)
        async with postgis_db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:stale-claim:1",
            )
            await session.commit()
            notice_id = notice.id

        started = asyncio.Event()
        release = asyncio.Event()

        class BlockingEmailAdapter:
            def __init__(self) -> None:
                self.messages: list[EmailMessage] = []

            async def send(self, message: EmailMessage) -> EmailSubmission:
                self.messages.append(message)
                started.set()
                await release.wait()
                return EmailSubmission(provider_message_id="provider-stale")

        settings = _settings()
        claimed_at = datetime.now(UTC)
        stale_adapter = BlockingEmailAdapter()
        stale_task = asyncio.create_task(
            process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=stale_adapter,
                now=claimed_at,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)

        winning_adapter = RecordingEmailAdapter()
        assert (
            await process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=winning_adapter,
                now=claimed_at + timedelta(seconds=settings.email_delivery_claim_seconds),
            )
            == "sent"
        )
        release.set()
        assert await stale_task == "stale_claim"
        assert [message.idempotency_key for message in stale_adapter.messages] == [
            str(notice_id)
        ]
        assert [message.idempotency_key for message in winning_adapter.messages] == [
            str(notice_id)
        ]

        async with postgis_db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == NotificationStatus.SENT.value
            assert stored.provider_message_id == f"provider-{notice_id}"
            assert stored.attempt_count == 2
            assert stored.delivery_claim_token is None
            assert stored.delivery_claim_expires_at is None

    asyncio.run(run())


def test_email_service_stale_claim_token_fences_terminal_write(db_sessionmaker) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        async with db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:stale-token-fence:1",
            )
            await session.commit()
            notice_id = notice.id
        replacement_token = uuid4()

        class ReplacingClaimAdapter:
            async def send(self, message: EmailMessage) -> EmailSubmission:
                async with db_sessionmaker() as session:
                    stored = await session.get(Notification, notice_id)
                    assert stored is not None and stored.delivery_claim_token is not None
                    stored.delivery_claim_token = replacement_token
                    await session.commit()
                return EmailSubmission(
                    provider_message_id=f"provider-{message.idempotency_key}"
                )

        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=_settings(),
                email_adapter=ReplacingClaimAdapter(),
                now=datetime.now(UTC),
            )
            == "stale_claim"
        )
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == NotificationStatus.PENDING.value
            assert stored.delivery_claim_token == replacement_token
            assert stored.provider_message_id is None
            assert stored.sent_at is None

    asyncio.run(run())


def test_email_service_claim_time_eligibility_is_not_revoked_in_flight(
    postgis_db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(postgis_db_sessionmaker)
        async with postgis_db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:claim-time-eligibility:1",
            )
            await session.commit()
            notice_id = notice.id

        started = asyncio.Event()
        release = asyncio.Event()

        class BlockingEmailAdapter:
            async def send(self, message: EmailMessage) -> EmailSubmission:
                started.set()
                await release.wait()
                return EmailSubmission(provider_message_id=f"provider-{message.idempotency_key}")

        task = asyncio.create_task(
            process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=_settings(),
                email_adapter=BlockingEmailAdapter(),
                now=datetime.now(UTC),
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        async with postgis_db_sessionmaker() as session:
            user = await session.get(User, user_id)
            preference = await session.scalar(
                select(AdvertiserOrganizationNotificationPreference).where(
                    AdvertiserOrganizationNotificationPreference.advertiser_organization_id
                    == organization_id
                )
            )
            assert user is not None and preference is not None
            user.status = UserStatus.SUSPENDED.value
            preference.transactional_email_enabled = False
            await session.commit()
        release.set()

        assert await task == "sent"
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == NotificationStatus.SENT.value

    asyncio.run(run())


def test_email_service_expired_claim_remains_reclaimable_above_attempt_cap(
    postgis_db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(postgis_db_sessionmaker)
        settings = _settings()
        now = datetime.now(UTC)
        async with postgis_db_sessionmaker() as session:
            notice = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:max-attempt-reclaim:1",
            )
            notice.attempt_count = settings.email_delivery_max_attempts
            notice.delivery_claim_token = uuid4()
            notice.delivery_claim_expires_at = now
            await session.commit()
            notice_id = notice.id

        assert (
            await process_email_notification(
                postgis_db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=RecordingEmailAdapter(),
                now=now,
            )
            == "sent"
        )
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == NotificationStatus.SENT.value
            assert stored.attempt_count == settings.email_delivery_max_attempts + 1

    asyncio.run(run())


def test_email_service_adapter_failures_clear_claim_and_respect_attempt_cap(
    db_sessionmaker,
) -> None:
    async def run() -> None:
        user_id, organization_id = await _seed_advertiser(db_sessionmaker)
        settings = _settings()
        async with db_sessionmaker() as session:
            permanent = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:permanent-failure:1",
            )
            capped = await create_advertiser_email_notification(
                session,
                advertiser_organization_id=organization_id,
                recipient_user_id=user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={},
                dedupe_key="email:capped-failure:1",
            )
            capped.attempt_count = settings.email_delivery_max_attempts - 1
            await session.commit()
            permanent_id = permanent.id
            capped_id = capped.id

        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=permanent_id,
                settings=settings,
                email_adapter=RecordingEmailAdapter(
                    [EmailSendError("email_recipient_rejected", retryable=False)]
                ),
                now=datetime.now(UTC),
            )
            == "failed"
        )
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=capped_id,
                settings=settings,
                email_adapter=RecordingEmailAdapter(
                    [EmailSendError("email_provider_unavailable", retryable=True)]
                ),
                now=datetime.now(UTC),
            )
            == "failed"
        )
        async with db_sessionmaker() as session:
            permanent = await session.get(Notification, permanent_id)
            capped = await session.get(Notification, capped_id)
            assert permanent is not None and capped is not None
            assert permanent.last_error_code == "email_recipient_rejected"
            assert capped.last_error_code == "email_provider_unavailable"
            assert capped.attempt_count == settings.email_delivery_max_attempts
            for stored in (permanent, capped):
                assert stored.status == NotificationStatus.FAILED.value
                assert stored.next_attempt_at is None
                assert stored.delivery_claim_token is None
                assert stored.delivery_claim_expires_at is None

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
