import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import (
    create_test_driver_profile,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import func, select

from app.adapters.messaging import EmailSubmission
from app.core.errors import AppError
from app.core.security import create_access_token, verify_password
from app.models.audit import AuditEvent
from app.models.contact import (
    ManualDriverContactTask,
    PasswordResetAttempt,
    PasswordResetToken,
    WhatsappConsent,
)
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole
from app.services.account_recovery import (
    complete_password_reset,
    request_password_reset,
    synthetic_password_reset_token,
)
from app.services.contacts import (
    complete_manual_driver_contact_task,
    create_manual_driver_contact_task,
    grant_whatsapp_consent,
    list_phone_verification_work,
    record_phone_challenge_sent,
    request_phone_verification,
    set_driver_phone,
    synthetic_phone_challenge_code,
    verify_phone_challenge,
)
from app.services.email_delivery import process_email_notification


def test_missing_manual_contact_task_returns_hidden_not_found(db_sessionmaker) -> None:
    admin = create_test_user(db_sessionmaker, email="contact-missing-admin@example.com")

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as missing:
                await complete_manual_driver_contact_task(
                    session,
                    task_id=uuid4(),
                    actor_user_id=admin.id,
                    outcome="reached",
                    note="No matching manual contact task.",
                )
            assert missing.value.code == "CONTACT_TASK_NOT_FOUND"
            assert missing.value.status_code == 404

    asyncio.run(scenario())


def test_missing_phone_challenge_returns_hidden_not_found(db_sessionmaker, settings) -> None:
    admin = create_test_user(db_sessionmaker, email="phone-missing-admin@example.com")
    settings.phone_operator_external_approved = True

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as missing:
                await record_phone_challenge_sent(
                    session,
                    challenge_id=uuid4(),
                    actor_user_id=admin.id,
                    channel="whatsapp",
                    operator_evidence_reference="operator-evidence",
                    provider_message_id="provider-message",
                    settings=settings,
                )
            assert missing.value.code == "PHONE_CHALLENGE_NOT_FOUND"
            assert missing.value.status_code == 404

    asyncio.run(scenario())


def test_missing_phone_challenge_verify_returns_hidden_not_found(db_sessionmaker, settings) -> None:
    driver = create_test_user(
        db_sessionmaker,
        email="phone-verify-missing-driver@example.com",
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as missing:
                await verify_phone_challenge(
                    session,
                    user_id=driver.id,
                    challenge_id=uuid4(),
                    code="123456",
                    settings=settings,
                )
            assert missing.value.code == "PHONE_CHALLENGE_NOT_FOUND"
            assert missing.value.status_code == 404

    asyncio.run(scenario())


def test_verified_phone_consent_and_manual_contact_are_versioned_and_secret_safe(
    db_sessionmaker, settings
) -> None:
    admin = create_test_user(db_sessionmaker, email="contact-admin@example.com")
    driver = create_test_user(
        db_sessionmaker,
        email="contact-driver@example.com",
        role=UserRole.DRIVER,
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)

    async def scenario():
        async with db_sessionmaker() as session:
            phone = await set_driver_phone(
                session,
                user_id=driver.id,
                phone="+234 803 123 4567",
                settings=settings,
            )
            challenge = await request_phone_verification(
                session, user_id=driver.id, settings=settings
            )
            code = synthetic_phone_challenge_code(
                challenge, settings, synthetic_test_authority=True
            )
            work, total = await list_phone_verification_work(session, limit=50, offset=0)
            assert total == 1
            assert work[0][0].id == challenge.id
            assert work[0][1].masked_phone == phone.masked_phone
            assert code not in challenge.code_hash
            assert hashlib.sha256(code.encode()).hexdigest() != challenge.code_hash
            assert hashlib.sha256(b"+2348031234567").hexdigest() != phone.phone_fingerprint
            with pytest.raises(AppError) as unavailable:
                await record_phone_challenge_sent(
                    session,
                    challenge_id=challenge.id,
                    actor_user_id=admin.id,
                    channel="whatsapp",
                    operator_evidence_reference="synthetic-test-evidence",
                    provider_message_id="synthetic-test-message",
                    settings=settings,
                )
            assert unavailable.value.code == "PHONE_OPERATOR_UNAVAILABLE"
            await record_phone_challenge_sent(
                session,
                challenge_id=challenge.id,
                actor_user_id=admin.id,
                channel="whatsapp",
                operator_evidence_reference="synthetic-test-evidence",
                provider_message_id="synthetic-test-message",
                settings=settings,
                synthetic_test_authority=True,
            )
            with pytest.raises(AppError) as wrong:
                await verify_phone_challenge(
                    session,
                    user_id=driver.id,
                    challenge_id=challenge.id,
                    code="000000" if code != "000000" else "000001",
                    settings=settings,
                )
            assert wrong.value.code == "PHONE_CHALLENGE_INVALID"
            verified = await verify_phone_challenge(
                session,
                user_id=driver.id,
                challenge_id=challenge.id,
                code=code,
                settings=settings,
            )
            assert verified.id == phone.id
            assert verified.verified_at is not None
            _, remaining_work = await list_phone_verification_work(session, limit=50, offset=0)
            assert remaining_work == 0
            consent = await grant_whatsapp_consent(
                session,
                user_id=driver.id,
                purpose="campaign operations updates",
                notice_version="synthetic-notice-v1",
            )
            task = await create_manual_driver_contact_task(
                session,
                driver_profile_id=profile.id,
                event_key="synthetic:event:v1:123",
                purpose="synthetic campaign operations",
            )
            retry = await create_manual_driver_contact_task(
                session,
                driver_profile_id=profile.id,
                event_key="synthetic:event:v1:123",
                purpose="synthetic campaign operations",
            )
            assert task is not None and retry is not None and task.id == retry.id
            completed = await complete_manual_driver_contact_task(
                session,
                task_id=task.id,
                actor_user_id=admin.id,
                outcome="reached",
                note="Operator reached the driver; no provider delivery evidence claimed.",
            )
            assert completed.status == "completed"
            assert completed.completion_outcome == "reached"
            assert not hasattr(completed, "provider_message_id")

            changed = await set_driver_phone(
                session,
                user_id=driver.id,
                phone="+2348039990000",
                settings=settings,
            )
            assert changed.version == 2 and changed.verified_at is None
            await session.refresh(consent)
            assert consent.withdrawn_at is not None
            blocked_task = await create_manual_driver_contact_task(
                session,
                driver_profile_id=profile.id,
                event_key="synthetic:event:v1:456",
                purpose="must remain blocked",
            )
            assert blocked_task is None
            serialized = json.dumps(
                {
                    "masked_phone": changed.masked_phone,
                    "challenge_id": str(challenge.id),
                    "consent_id": str(consent.id),
                }
            )
            assert "+2348039990000" not in serialized
            assert code not in serialized
            audit_payloads = json.dumps(
                list(await session.scalars(select(AuditEvent.event_metadata)))
            )
            assert "synthetic-test-evidence" not in audit_payloads
            assert "synthetic-test-message" not in audit_payloads
            assert (
                await session.scalar(select(func.count()).select_from(ManualDriverContactTask)) == 1
            )
            assert await session.scalar(select(func.count()).select_from(WhatsappConsent)) == 1
            await session.commit()

    asyncio.run(scenario())


def test_password_reset_delivery_hash_mismatch_leaves_expiring_reclaimable_claim(
    db_sessionmaker, db_client, settings
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="recover-delivery-mismatch@example.com",
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    assert (
        db_client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": advertiser.email},
        ).status_code
        == 202
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            notice = await session.scalar(
                select(Notification).where(
                    Notification.type_key == NotificationType.PASSWORD_RESET_REQUESTED.value
                )
            )
            assert notice is not None
            notice_id = notice.id

        class RecordingAdapter:
            def __init__(self) -> None:
                self.idempotency_keys: list[str] = []

            async def send(self, message) -> EmailSubmission:
                self.idempotency_keys.append(message.idempotency_key)
                return EmailSubmission(
                    provider_message_id=f"provider-{message.idempotency_key}"
                )

        now = datetime.now(UTC)
        with pytest.raises(RuntimeError, match="password reset token evidence mismatch"):
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=settings.model_copy(
                    update={"jwt_secret_key": "different-test-secret-key-at-least-32-bytes"}
                ),
                email_adapter=RecordingAdapter(),
                now=now,
            )

        async with db_sessionmaker() as session:
            claimed = await session.get(Notification, notice_id)
            assert claimed is not None
            assert claimed.status == "pending"
            assert claimed.attempt_count == 1
            assert claimed.delivery_claim_token is not None
            assert claimed.delivery_claim_expires_at is not None
            claim_expires_at = claimed.delivery_claim_expires_at
            if claim_expires_at.tzinfo is None:
                claim_expires_at = claim_expires_at.replace(tzinfo=UTC)

        adapter = RecordingAdapter()
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice_id,
                settings=settings,
                email_adapter=adapter,
                now=claim_expires_at,
            )
            == "sent"
        )
        assert adapter.idempotency_keys == [str(notice_id)]
        async with db_sessionmaker() as session:
            stored = await session.get(Notification, notice_id)
            assert stored is not None
            assert stored.status == "sent"
            assert stored.attempt_count == 2
            assert stored.delivery_claim_token is None

    asyncio.run(scenario())


def test_password_reset_is_non_enumerating_single_use_expiring_and_revokes_sessions(
    db_sessionmaker, db_client, settings
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="recover-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    known = db_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": advertiser.email},
    )
    unknown = db_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown-recovery@example.com"},
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()

    async def scenario():
        async with db_sessionmaker() as session:
            reset = await session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == advertiser.id)
            )
            user = await session.get(User, advertiser.id)
            assert reset is not None and user is not None
            token = synthetic_password_reset_token(
                reset,
                user,
                settings,
                synthetic_test_authority=True,
            )
            notice = await session.scalar(
                select(Notification).where(
                    Notification.type_key == NotificationType.PASSWORD_RESET_REQUESTED.value
                )
            )
            assert notice is not None
            assert token not in json.dumps(notice.payload)
            assert set(notice.payload) == {"password_reset_request_id"}

            class UnexpectedEmailAdapter:
                async def send(self, _message):
                    raise AssertionError("production reset must fail before provider submission")

            production_settings = settings.model_copy(
                update={"environment": "production", "password_reset_public_url": ""}
            )
            assert (
                await process_email_notification(
                    db_sessionmaker,
                    notification_id=notice.id,
                    settings=production_settings,
                    email_adapter=UnexpectedEmailAdapter(),
                    now=datetime.now(UTC),
                )
                == "failed"
            )
            old_token, _ = create_access_token(
                user.id,
                settings,
                session_version=user.session_version,
            )
            old_session_version = user.session_version
            await complete_password_reset(
                session,
                token=token,
                new_password="replacement-password-123",
                settings=settings,
            )
            await session.commit()
            refreshed = await session.get(User, advertiser.id)
            assert refreshed is not None
            assert refreshed.session_version == old_session_version + 1
            assert verify_password("replacement-password-123", refreshed.password_hash)
            with pytest.raises(AppError) as replay:
                await complete_password_reset(
                    session,
                    token=token,
                    new_password="another-password-456",
                    settings=settings,
                )
            assert replay.value.code == "PASSWORD_RESET_INVALID"
            assert old_token

            expiring_settings = settings.model_copy(update={"password_reset_ttl_seconds": 1})
            second = await request_password_reset(
                session,
                email=advertiser.email,
                client_ip="127.0.0.2",
                settings=expiring_settings,
            )
            assert second is not None
            await session.commit()
            expired_token = synthetic_password_reset_token(
                second,
                refreshed,
                expiring_settings,
                synthetic_test_authority=True,
            )
            await asyncio.sleep(1.1)
            with pytest.raises(AppError) as expired:
                await complete_password_reset(
                    session,
                    token=expired_token,
                    new_password="expired-password-789",
                    settings=settings,
                )
            assert expired.value.code == "PASSWORD_RESET_INVALID"
            assert await session.scalar(select(func.count()).select_from(PasswordResetAttempt)) == 3

    asyncio.run(scenario())


def test_concurrent_password_reset_requests_obey_account_rate_limit(
    postgis_db_sessionmaker, settings
) -> None:
    advertiser = create_test_user(
        postgis_db_sessionmaker,
        email="recover-race-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    limited = settings.model_copy(update={"password_reset_account_max_attempts": 1})

    async def request(client_ip: str) -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                reset = await request_password_reset(
                    session,
                    email=advertiser.email,
                    client_ip=client_ip,
                    settings=limited,
                )
                await session.commit()
                return "issued" if reset is not None else "not_issued"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def scenario():
        outcomes = await asyncio.wait_for(
            asyncio.gather(request("127.0.0.11"), request("127.0.0.12")),
            timeout=10,
        )
        assert sorted(outcomes) == ["PASSWORD_RESET_RATE_LIMITED", "issued"]
        async with postgis_db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(PasswordResetAttempt)) == 1
            assert await session.scalar(select(func.count()).select_from(PasswordResetToken)) == 1

    asyncio.run(scenario())
