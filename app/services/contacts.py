import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.contact import (
    DriverPhoneVersion,
    ManualContactTaskStatus,
    ManualDriverContactTask,
    PhoneChallengeStatus,
    PhoneVerificationChallenge,
    WhatsappConsent,
)
from app.models.driver import DriverProfile
from app.models.user import User
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.payout_rule_serialization import database_clock

PHONE_PATTERN = re.compile(r"^\+[1-9][0-9]{7,14}$")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_phone(phone: str) -> str:
    normalized = "".join(character for character in phone.strip() if character not in " -()")
    if not PHONE_PATTERN.fullmatch(normalized):
        raise AppError(
            "INVALID_PHONE_NUMBER",
            "Phone number must use international E.164 format",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return normalized


def phone_fingerprint(phone: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"driver-phone:v1:{normalize_phone(phone)}".encode(),
        hashlib.sha256,
    ).hexdigest()


def mask_phone(phone: str) -> str:
    normalized = normalize_phone(phone)
    return f"{normalized[:3]}{'*' * max(len(normalized) - 7, 3)}{normalized[-4:]}"


def _challenge_code(challenge_id: UUID, settings: Settings) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode(),
        f"phone-verification:v1:{challenge_id}".encode(),
        hashlib.sha256,
    ).digest()
    return f"{int.from_bytes(digest[:8], 'big') % 1_000_000:06d}"


def _challenge_code_hash(code: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"phone-verification-code:v1:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def synthetic_phone_challenge_code(
    challenge: PhoneVerificationChallenge, settings: Settings, *, synthetic_test_authority: bool
) -> str:
    if not synthetic_test_authority or settings.environment not in {"test", "testing"}:
        raise RuntimeError("synthetic phone challenge authority is test-only")
    return _challenge_code(challenge.id, settings)


async def _locked_driver_context(
    session: AsyncSession, *, user_id: UUID
) -> tuple[DriverProfile, User]:
    row = (
        await session.execute(
            select(DriverProfile, User)
            .join(User, User.id == DriverProfile.user_id)
            .where(DriverProfile.user_id == user_id)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return row[0], row[1]


async def _latest_phone_version(
    session: AsyncSession, *, driver_profile_id: UUID, lock: bool = False
) -> DriverPhoneVersion | None:
    query = (
        select(DriverPhoneVersion)
        .where(DriverPhoneVersion.driver_profile_id == driver_profile_id)
        .order_by(DriverPhoneVersion.version.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def set_driver_phone(
    session: AsyncSession, *, user_id: UUID, phone: str, settings: Settings
) -> DriverPhoneVersion:
    profile, user = await _locked_driver_context(session, user_id=user_id)
    normalized = normalize_phone(phone)
    fingerprint = phone_fingerprint(normalized, settings)
    latest = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    if latest is not None and latest.phone_fingerprint == fingerprint:
        return latest
    now = await database_clock(session)
    active_consents = list(
        await session.scalars(
            select(WhatsappConsent)
            .where(
                WhatsappConsent.driver_profile_id == profile.id,
                WhatsappConsent.withdrawn_at.is_(None),
            )
            .with_for_update()
        )
    )
    for consent in active_consents:
        consent.withdrawn_by_user_id = user_id
        consent.withdrawn_at = now
    version = DriverPhoneVersion(
        driver_profile_id=profile.id,
        version=(latest.version + 1 if latest is not None else 1),
        phone_fingerprint=fingerprint,
        masked_phone=mask_phone(normalized),
        recorded_by_user_id=user_id,
        recorded_at=now,
        verified_at=None,
    )
    user.phone = normalized
    session.add(version)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.contact.phone_version.recorded",
        entity_type="driver_phone_version",
        entity_id=str(version.id),
        metadata={"version": version.version, "masked_phone": version.masked_phone},
    )
    return version


async def request_phone_verification(
    session: AsyncSession, *, user_id: UUID, settings: Settings
) -> PhoneVerificationChallenge:
    profile, _ = await _locked_driver_context(session, user_id=user_id)
    phone = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    if phone is None:
        raise AppError(
            "PHONE_VERSION_REQUIRED",
            "Record a phone number before requesting verification",
            status_code=status.HTTP_409_CONFLICT,
        )
    if phone.verified_at is not None:
        raise AppError(
            "PHONE_ALREADY_VERIFIED",
            "The current phone version is already verified",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    existing = await session.scalar(
        select(PhoneVerificationChallenge)
        .where(
            PhoneVerificationChallenge.phone_version_id == phone.id,
            PhoneVerificationChallenge.status.in_(
                [
                    PhoneChallengeStatus.PENDING_OPERATOR.value,
                    PhoneChallengeStatus.SENT.value,
                ]
            ),
            PhoneVerificationChallenge.expires_at > now,
        )
        .order_by(PhoneVerificationChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if existing is not None:
        return existing
    window_start = now - timedelta(seconds=settings.phone_verification_request_window_seconds)
    recent = int(
        await session.scalar(
            select(func.count())
            .select_from(PhoneVerificationChallenge)
            .where(
                PhoneVerificationChallenge.phone_version_id == phone.id,
                PhoneVerificationChallenge.created_at >= window_start,
            )
        )
        or 0
    )
    if recent >= settings.phone_verification_request_max_attempts:
        raise AppError(
            "PHONE_VERIFICATION_RATE_LIMITED",
            "Too many phone verification requests",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    challenge_id = uuid4()
    code = _challenge_code(challenge_id, settings)
    challenge = PhoneVerificationChallenge(
        id=challenge_id,
        phone_version_id=phone.id,
        code_hash=_challenge_code_hash(code, settings),
        status=PhoneChallengeStatus.PENDING_OPERATOR.value,
        attempt_count=0,
        max_attempts=settings.phone_verification_max_code_attempts,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.phone_verification_ttl_seconds),
    )
    session.add(challenge)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.contact.phone_verification.requested",
        entity_type="phone_verification_challenge",
        entity_id=str(challenge.id),
        metadata={
            "phone_version_id": str(phone.id),
            "phone_version": phone.version,
            "expires_at": challenge.expires_at.isoformat(),
            "external_gate": "EXT-PHONE-OPERATOR",
        },
    )
    return challenge


async def record_phone_challenge_sent(
    session: AsyncSession,
    *,
    challenge_id: UUID,
    actor_user_id: UUID,
    channel: str,
    operator_evidence_reference: str,
    provider_message_id: str,
    settings: Settings,
    synthetic_test_authority: bool = False,
) -> PhoneVerificationChallenge:
    await require_active_admin(session, actor_user_id)
    if not settings.phone_operator_external_approved and not (
        synthetic_test_authority and settings.environment in {"test", "testing"}
    ):
        raise AppError(
            "PHONE_OPERATOR_UNAVAILABLE",
            "EXT-PHONE-OPERATOR is missing; live phone sends are disabled",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if channel not in {"whatsapp", "voice"}:
        raise AppError(
            "INVALID_PHONE_VERIFICATION_CHANNEL",
            "Verification channel must be WhatsApp or voice",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    evidence_reference = operator_evidence_reference.strip()
    message_id = provider_message_id.strip()
    if not evidence_reference or not message_id:
        raise AppError(
            "PHONE_OPERATOR_EVIDENCE_REQUIRED",
            "Provider submission evidence is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    challenge = await session.scalar(
        select(PhoneVerificationChallenge)
        .where(PhoneVerificationChallenge.id == challenge_id)
        .with_for_update()
    )
    if challenge is None:
        raise AppError("PHONE_CHALLENGE_NOT_FOUND", "Phone challenge was not found", 404)
    if challenge.status == PhoneChallengeStatus.SENT.value:
        if (
            challenge.sent_by_user_id == actor_user_id
            and challenge.sent_channel == channel
            and challenge.operator_evidence_reference == evidence_reference
            and challenge.provider_message_id == message_id
        ):
            return challenge
        raise AppError(
            "PHONE_CHALLENGE_SEND_CONFLICT",
            "Phone challenge send evidence already exists",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if challenge.status != PhoneChallengeStatus.PENDING_OPERATOR.value or now >= _utc(
        challenge.expires_at
    ):
        challenge.status = PhoneChallengeStatus.EXPIRED.value
        raise AppError(
            "PHONE_CHALLENGE_EXPIRED",
            "Phone verification challenge has expired",
            status_code=status.HTTP_409_CONFLICT,
        )
    challenge.status = PhoneChallengeStatus.SENT.value
    challenge.sent_by_user_id = actor_user_id
    challenge.sent_channel = channel
    challenge.sent_at = now
    challenge.operator_evidence_reference = evidence_reference
    challenge.provider_message_id = message_id
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.phone_verification.sent",
        entity_type="phone_verification_challenge",
        entity_id=str(challenge.id),
        metadata={
            "channel": channel,
            "operator_evidence_fingerprint": hashlib.sha256(
                evidence_reference.encode()
            ).hexdigest(),
            "provider_message_fingerprint": hashlib.sha256(message_id.encode()).hexdigest(),
            "sent_at": now.isoformat(),
        },
    )
    return challenge


async def list_phone_verification_work(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[tuple[PhoneVerificationChallenge, DriverPhoneVersion]], int]:
    now = await database_clock(session)
    work_statuses = [
        PhoneChallengeStatus.PENDING_OPERATOR.value,
        PhoneChallengeStatus.SENT.value,
    ]
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(PhoneVerificationChallenge)
            .where(
                PhoneVerificationChallenge.status.in_(work_statuses),
                PhoneVerificationChallenge.expires_at > now,
            )
        )
        or 0
    )
    rows = list(
        (
            await session.execute(
                select(PhoneVerificationChallenge, DriverPhoneVersion)
                .join(
                    DriverPhoneVersion,
                    DriverPhoneVersion.id == PhoneVerificationChallenge.phone_version_id,
                )
                .where(
                    PhoneVerificationChallenge.status.in_(work_statuses),
                    PhoneVerificationChallenge.expires_at > now,
                )
                .order_by(
                    PhoneVerificationChallenge.created_at,
                    PhoneVerificationChallenge.id,
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return [(row[0], row[1]) for row in rows], total


async def verify_phone_challenge(
    session: AsyncSession,
    *,
    user_id: UUID,
    challenge_id: UUID,
    code: str,
    settings: Settings,
) -> DriverPhoneVersion:
    profile, user = await _locked_driver_context(session, user_id=user_id)
    current_phone = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    challenge = await session.scalar(
        select(PhoneVerificationChallenge)
        .where(PhoneVerificationChallenge.id == challenge_id)
        .with_for_update()
    )
    if challenge is None or current_phone is None or challenge.phone_version_id != current_phone.id:
        raise AppError(
            "PHONE_CHALLENGE_INVALID",
            "Phone verification challenge is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if challenge.status == PhoneChallengeStatus.VERIFIED.value:
        return current_phone
    now = await database_clock(session)
    if now >= _utc(challenge.expires_at):
        challenge.status = PhoneChallengeStatus.EXPIRED.value
        raise AppError(
            "PHONE_CHALLENGE_INVALID",
            "Phone verification challenge is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if challenge.status != PhoneChallengeStatus.SENT.value:
        raise AppError(
            "PHONE_CHALLENGE_NOT_SENT",
            "Phone verification challenge has not been sent",
            status_code=status.HTTP_409_CONFLICT,
        )
    supplied_hash = _challenge_code_hash(code, settings)
    if not hmac.compare_digest(supplied_hash, challenge.code_hash):
        challenge.attempt_count += 1
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.status = PhoneChallengeStatus.EXHAUSTED.value
        await create_audit_event(
            session,
            actor_user_id=user.id,
            action="driver.contact.phone_verification.failed",
            entity_type="phone_verification_challenge",
            entity_id=str(challenge.id),
            metadata={"attempt_count": challenge.attempt_count},
        )
        await session.commit()
        raise AppError(
            "PHONE_CHALLENGE_INVALID",
            "Phone verification challenge is invalid",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    challenge.attempt_count += 1
    challenge.status = PhoneChallengeStatus.VERIFIED.value
    challenge.verified_at = now
    current_phone.verified_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="driver.contact.phone_verified",
        entity_type="driver_phone_version",
        entity_id=str(current_phone.id),
        metadata={"version": current_phone.version, "verified_at": now.isoformat()},
    )
    return current_phone


async def grant_whatsapp_consent(
    session: AsyncSession,
    *,
    user_id: UUID,
    purpose: str,
    notice_version: str,
) -> WhatsappConsent:
    profile, _ = await _locked_driver_context(session, user_id=user_id)
    phone = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    if phone is None or phone.verified_at is None:
        raise AppError(
            "VERIFIED_PHONE_REQUIRED",
            "WhatsApp consent requires the current phone version to be verified",
            status_code=status.HTTP_409_CONFLICT,
        )
    normalized_purpose = purpose.strip()
    normalized_notice = notice_version.strip()
    if not normalized_purpose or not normalized_notice:
        raise AppError(
            "WHATSAPP_CONSENT_EVIDENCE_REQUIRED",
            "Consent purpose and notice version are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    active = await session.scalar(
        select(WhatsappConsent)
        .where(
            WhatsappConsent.driver_profile_id == profile.id,
            WhatsappConsent.withdrawn_at.is_(None),
        )
        .order_by(WhatsappConsent.version.desc())
        .limit(1)
        .with_for_update()
    )
    if active is not None:
        if (
            active.phone_version_id == phone.id
            and active.purpose == normalized_purpose
            and active.notice_version == normalized_notice
        ):
            return active
        raise AppError(
            "WHATSAPP_CONSENT_ALREADY_ACTIVE",
            "Withdraw the active WhatsApp consent before granting a new version",
            status_code=status.HTTP_409_CONFLICT,
        )
    latest_version = int(
        await session.scalar(
            select(func.coalesce(func.max(WhatsappConsent.version), 0)).where(
                WhatsappConsent.driver_profile_id == profile.id
            )
        )
        or 0
    )
    now = await database_clock(session)
    consent = WhatsappConsent(
        driver_profile_id=profile.id,
        phone_version_id=phone.id,
        version=latest_version + 1,
        purpose=normalized_purpose,
        notice_version=normalized_notice,
        granted_by_user_id=user_id,
        granted_at=now,
    )
    session.add(consent)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.contact.whatsapp_consent.granted",
        entity_type="whatsapp_consent",
        entity_id=str(consent.id),
        metadata={
            "version": consent.version,
            "purpose": consent.purpose,
            "notice_version": consent.notice_version,
            "phone_version": phone.version,
        },
    )
    return consent


async def withdraw_whatsapp_consent(session: AsyncSession, *, user_id: UUID) -> WhatsappConsent:
    profile, _ = await _locked_driver_context(session, user_id=user_id)
    consent = await session.scalar(
        select(WhatsappConsent)
        .where(
            WhatsappConsent.driver_profile_id == profile.id,
            WhatsappConsent.withdrawn_at.is_(None),
        )
        .order_by(WhatsappConsent.version.desc())
        .limit(1)
        .with_for_update()
    )
    if consent is None:
        raise AppError(
            "WHATSAPP_CONSENT_NOT_ACTIVE",
            "No active WhatsApp consent exists",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    consent.withdrawn_by_user_id = user_id
    consent.withdrawn_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user_id,
        action="driver.contact.whatsapp_consent.withdrawn",
        entity_type="whatsapp_consent",
        entity_id=str(consent.id),
        metadata={"version": consent.version, "withdrawn_at": now.isoformat()},
    )
    return consent


async def create_manual_driver_contact_task(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    event_key: str,
    purpose: str,
) -> ManualDriverContactTask | None:
    existing = await session.scalar(
        select(ManualDriverContactTask).where(
            ManualDriverContactTask.driver_profile_id == driver_profile_id,
            ManualDriverContactTask.event_key == event_key,
        )
    )
    if existing is not None:
        return existing
    phone = await _latest_phone_version(session, driver_profile_id=driver_profile_id, lock=True)
    consent = await session.scalar(
        select(WhatsappConsent)
        .where(
            WhatsappConsent.driver_profile_id == driver_profile_id,
            WhatsappConsent.withdrawn_at.is_(None),
        )
        .order_by(WhatsappConsent.version.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        phone is None
        or phone.verified_at is None
        or consent is None
        or consent.phone_version_id != phone.id
    ):
        return None
    now = await database_clock(session)
    task = ManualDriverContactTask(
        driver_profile_id=driver_profile_id,
        phone_version_id=phone.id,
        consent_id=consent.id,
        event_key=event_key,
        purpose=purpose,
        status=ManualContactTaskStatus.OPEN.value,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(task)
            await session.flush()
    except IntegrityError:
        concurrent = await session.scalar(
            select(ManualDriverContactTask).where(
                ManualDriverContactTask.driver_profile_id == driver_profile_id,
                ManualDriverContactTask.event_key == event_key,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    await create_audit_event(
        session,
        actor_user_id=None,
        action="operations.driver_contact_task.created",
        entity_type="manual_driver_contact_task",
        entity_id=str(task.id),
        metadata={
            "driver_profile_id": str(driver_profile_id),
            "event_key": event_key,
            "purpose": purpose,
            "phone_version": phone.version,
            "consent_version": consent.version,
        },
    )
    return task


async def current_driver_contact_state(
    session: AsyncSession, *, user_id: UUID
) -> tuple[DriverPhoneVersion | None, WhatsappConsent | None]:
    profile, _ = await _locked_driver_context(session, user_id=user_id)
    phone = await _latest_phone_version(session, driver_profile_id=profile.id)
    consent = await session.scalar(
        select(WhatsappConsent)
        .where(WhatsappConsent.driver_profile_id == profile.id)
        .order_by(WhatsappConsent.version.desc())
        .limit(1)
    )
    return phone, consent


async def list_manual_driver_contact_tasks(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[tuple[ManualDriverContactTask, DriverPhoneVersion]], int]:
    total = int(
        await session.scalar(select(func.count()).select_from(ManualDriverContactTask)) or 0
    )
    rows = list(
        (
            await session.execute(
                select(ManualDriverContactTask, DriverPhoneVersion)
                .join(
                    DriverPhoneVersion,
                    DriverPhoneVersion.id == ManualDriverContactTask.phone_version_id,
                )
                .order_by(
                    ManualDriverContactTask.created_at.desc(),
                    ManualDriverContactTask.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return [(row[0], row[1]) for row in rows], total


async def complete_manual_driver_contact_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    actor_user_id: UUID,
    outcome: str,
    note: str,
) -> ManualDriverContactTask:
    await require_active_admin(session, actor_user_id)
    normalized_note = note.strip()
    if outcome not in {"attempted", "reached", "failed"} or not normalized_note:
        raise AppError(
            "INVALID_CONTACT_COMPLETION",
            "A valid outcome and nonblank operator note are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    task = await session.scalar(
        select(ManualDriverContactTask)
        .where(ManualDriverContactTask.id == task_id)
        .with_for_update()
    )
    if task is None:
        raise AppError("CONTACT_TASK_NOT_FOUND", "Contact task was not found", 404)
    if task.status == ManualContactTaskStatus.COMPLETED.value:
        if (
            task.completed_by_user_id == actor_user_id
            and task.completion_outcome == outcome
            and task.completion_note == normalized_note
        ):
            return task
        raise AppError(
            "CONTACT_TASK_COMPLETION_CONFLICT",
            "Contact task already has different completion evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    task.status = ManualContactTaskStatus.COMPLETED.value
    task.completed_by_user_id = actor_user_id
    task.completed_at = now
    task.completion_outcome = outcome
    task.completion_note = normalized_note
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="operations.driver_contact_task.completed",
        entity_type="manual_driver_contact_task",
        entity_id=str(task.id),
        metadata={
            "outcome": outcome,
            "completed_at": now.isoformat(),
            "provider_delivery_claimed": False,
        },
    )
    return task
