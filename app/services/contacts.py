import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
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
from app.models.user import User, UserRole, UserStatus
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
        f"phone-verification:v2:{challenge_id}".encode(),
        hashlib.sha256,
    ).digest()
    return f"{int.from_bytes(digest[:8], 'big') % 1_000_000:06d}"


def _challenge_code_hash(code: str, settings: Settings) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"phone-verification-code:v2:{code}".encode(),
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
    from app.services.users import _lock_users

    user = (await _lock_users(session, {user_id})).get(user_id)
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        profile is None
        or user is None
        or user.role != UserRole.DRIVER
        or user.status != UserStatus.ACTIVE
    ):
        raise AppError(
            "DRIVER_PROFILE_NOT_FOUND",
            "Driver profile was not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return profile, user


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
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def set_driver_phone(
    session: AsyncSession, *, user_id: UUID, phone: str, settings: Settings
) -> DriverPhoneVersion:
    profile, user = await _locked_driver_context(session, user_id=user_id)
    normalized = normalize_phone(phone)
    fingerprint = phone_fingerprint(normalized, settings)
    latest = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    try:
        saved_phone_matches = bool(user.phone) and normalize_phone(user.phone) == normalized
    except AppError:
        saved_phone_matches = False
    if latest is not None and latest.phone_fingerprint == fingerprint and saved_phone_matches:
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
    require_phone_verification_available(settings)
    profile, user = await _locked_driver_context(session, user_id=user_id)
    if not user.phone:
        raise AppError(
            "PHONE_VERSION_REQUIRED",
            "Record a phone number before requesting verification",
            status_code=status.HTTP_409_CONFLICT,
        )
    phone = await set_driver_phone(session, user_id=user_id, phone=user.phone, settings=settings)
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
                    PhoneChallengeStatus.PENDING.value,
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
            .join(
                DriverPhoneVersion,
                DriverPhoneVersion.id == PhoneVerificationChallenge.phone_version_id,
            )
            .where(
                DriverPhoneVersion.driver_profile_id == profile.id,
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
        status=PhoneChallengeStatus.PENDING.value,
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


def phone_verification_available(settings: Settings) -> bool:
    number = settings.phone_verification_terrax_number.strip()
    if not PHONE_PATTERN.fullmatch(number):
        return False
    if settings.environment in {"local", "dev", "development", "test", "testing", "preview"}:
        # Owner-approved temporary destination; no provider or send operation.
        return number == "+2347068369842"
    return bool(
        settings.phone_operator_external_approved
        and settings.phone_operator_name.strip()
        and settings.phone_whatsapp_notice_approval_reference.strip()
        and not re.fullmatch(r"\+447700900[0-9]{3}", number)
        and not number.startswith("+2340")
    )


def require_phone_verification_available(settings: Settings) -> None:
    if not phone_verification_available(settings):
        raise AppError(
            "PHONE_VERIFICATION_UNAVAILABLE",
            "Phone verification is not available yet",
            status_code=503,
        )


def driver_phone_challenge_code(challenge: PhoneVerificationChallenge, settings: Settings) -> str:
    # Called only by the authenticated owner response, never staff serializers.
    return _challenge_code(challenge.id, settings)


async def current_phone_challenge(
    session: AsyncSession, phone: DriverPhoneVersion | None
) -> PhoneVerificationChallenge | None:
    if phone is None:
        return None
    return await session.scalar(
        select(PhoneVerificationChallenge)
        .where(PhoneVerificationChallenge.phone_version_id == phone.id)
        .order_by(
            PhoneVerificationChallenge.created_at.desc(), PhoneVerificationChallenge.id.desc()
        )
        .limit(1)
    )


async def list_phone_verification_work(
    session: AsyncSession, *, limit: int, offset: int, driver_profile_id: UUID | None = None
) -> tuple[list[tuple[PhoneVerificationChallenge, DriverPhoneVersion]], int]:
    now = await database_clock(session)
    newer_phone = aliased(DriverPhoneVersion)
    newer_exists = (
        select(newer_phone.id)
        .where(
            newer_phone.driver_profile_id == DriverPhoneVersion.driver_profile_id,
            newer_phone.version > DriverPhoneVersion.version,
        )
        .correlate(DriverPhoneVersion)
        .exists()
    )
    base = (
        select(PhoneVerificationChallenge, DriverPhoneVersion)
        .join(
            DriverPhoneVersion, DriverPhoneVersion.id == PhoneVerificationChallenge.phone_version_id
        )
        .join(DriverProfile, DriverProfile.id == DriverPhoneVersion.driver_profile_id)
        .join(User, User.id == DriverProfile.user_id)
        .where(
            PhoneVerificationChallenge.status == PhoneChallengeStatus.PENDING.value,
            PhoneVerificationChallenge.expires_at > now,
            DriverPhoneVersion.verified_at.is_(None),
            ~newer_exists,
            User.status == UserStatus.ACTIVE.value,
        )
    )
    if driver_profile_id is not None:
        base = base.where(DriverPhoneVersion.driver_profile_id == driver_profile_id)
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await session.execute(
            base.order_by(PhoneVerificationChallenge.created_at, PhoneVerificationChallenge.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(row[0], row[1]) for row in rows], total


async def record_phone_verification(
    session: AsyncSession,
    *,
    driver_profile_id: UUID,
    actor_user_id: UUID,
    challenge_id: UUID,
    code: str,
    sender_phone: str,
    settings: Settings,
) -> DriverPhoneVersion:
    require_phone_verification_available(settings)
    user_id = await session.scalar(
        select(DriverProfile.user_id).where(DriverProfile.id == driver_profile_id)
    )
    if user_id is None:
        raise AppError("DRIVER_PROFILE_NOT_FOUND", "Driver profile was not found", status_code=404)
    from app.services.users import _lock_users

    await _lock_users(session, {actor_user_id, user_id})
    await require_active_admin(session, actor_user_id)
    profile, user = await _locked_driver_context(session, user_id=user_id)
    phone = await _latest_phone_version(session, driver_profile_id=profile.id, lock=True)
    challenge = await session.scalar(
        select(PhoneVerificationChallenge)
        .where(PhoneVerificationChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if challenge is None or phone is None or challenge.phone_version_id != phone.id:
        raise AppError(
            "PHONE_CHALLENGE_INVALID",
            "This verification request is no longer available",
            status_code=409,
        )
    now = await database_clock(session)
    if challenge.status != PhoneChallengeStatus.PENDING.value or phone.verified_at is not None:
        raise AppError(
            "PHONE_CHALLENGE_USED",
            "Request a new code if this phone still needs verification",
            status_code=409,
        )
    if now >= _utc(challenge.expires_at):
        challenge.status = PhoneChallengeStatus.EXPIRED.value
        await session.commit()
        raise AppError(
            "PHONE_CHALLENGE_EXPIRED",
            "The code expired. Ask the driver to request another code",
            status_code=409,
        )
    try:
        sender = normalize_phone(sender_phone)
        matches_phone = (
            bool(user.phone)
            and sender == normalize_phone(user.phone)
            and phone_fingerprint(sender, settings) == phone.phone_fingerprint
        )
    except AppError:
        matches_phone = False
    challenge.attempt_count += 1
    if not matches_phone or not hmac.compare_digest(
        _challenge_code_hash(code, settings), challenge.code_hash
    ):
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.status = PhoneChallengeStatus.EXHAUSTED.value
        await create_audit_event(
            session,
            actor_user_id=actor_user_id,
            action="admin.phone_verification.failed",
            entity_type="phone_verification_challenge",
            entity_id=str(challenge.id),
            metadata={"attempt_count": challenge.attempt_count},
        )
        await session.commit()
        raise AppError(
            "PHONE_VERIFICATION_MISMATCH",
            "The code or sender number does not match. Check the message received",
            status_code=400,
        )
    challenge.status = PhoneChallengeStatus.VERIFIED.value
    challenge.verified_at = now
    challenge.verified_by_user_id = actor_user_id
    phone.verified_at = now
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.phone_verification.recorded",
        entity_type="driver_phone_version",
        entity_id=str(phone.id),
        metadata={"version": phone.version, "challenge_id": str(challenge.id)},
    )
    await session.flush()
    return phone


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
    authority = await _manual_contact_authority(
        session, driver_profile_id=driver_profile_id, purpose=purpose
    )
    if authority is None:
        return None
    phone, consent = authority
    existing = await session.scalar(
        select(ManualDriverContactTask)
        .where(
            ManualDriverContactTask.driver_profile_id == driver_profile_id,
            ManualDriverContactTask.event_key == event_key,
        )
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        return existing if _task_matches_authority(existing, phone, consent, purpose) else None
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
            select(ManualDriverContactTask)
            .where(
                ManualDriverContactTask.driver_profile_id == driver_profile_id,
                ManualDriverContactTask.event_key == event_key,
            )
            .execution_options(populate_existing=True)
        )
        if concurrent is None:
            raise
        return concurrent if _task_matches_authority(concurrent, phone, consent, purpose) else None
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


def _task_matches_authority(
    task: ManualDriverContactTask,
    phone: DriverPhoneVersion,
    consent: WhatsappConsent,
    purpose: str,
) -> bool:
    return (
        task.phone_version_id == phone.id
        and task.consent_id == consent.id
        and task.purpose == purpose == consent.purpose
    )


async def _manual_contact_authority(
    session: AsyncSession, *, driver_profile_id: UUID, purpose: str
) -> tuple[DriverPhoneVersion, WhatsappConsent] | None:
    # Phone replacement and withdrawal already hold this profile lock. Keep
    # profile -> phone -> consent -> task order across contact mutations.
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == driver_profile_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if profile is None:
        return None
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
        .execution_options(populate_existing=True)
    )
    if (
        phone is None
        or phone.verified_at is None
        or consent is None
        or consent.phone_version_id != phone.id
        or consent.purpose != purpose
    ):
        return None
    return phone, consent


async def current_driver_contact_state(
    session: AsyncSession, *, user_id: UUID, settings: Settings
) -> tuple[DriverPhoneVersion | None, WhatsappConsent | None]:
    profile, user = await _locked_driver_context(session, user_id=user_id)
    phone = await _latest_phone_version(session, driver_profile_id=profile.id)
    if phone is not None:
        try:
            current_fingerprint = phone_fingerprint(normalize_phone(user.phone or ""), settings)
        except AppError:
            return None, None
        if phone.phone_fingerprint != current_fingerprint:
            return None, None
    consent = await session.scalar(
        select(WhatsappConsent)
        .where(WhatsappConsent.driver_profile_id == profile.id)
        .order_by(WhatsappConsent.version.desc())
        .limit(1)
    )
    return phone, consent


async def list_manual_driver_contact_tasks(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    history: bool = False,
    driver_profile_id: UUID | None = None,
    oldest_first: bool = False,
    open_only: bool = False,
) -> tuple[list[tuple[ManualDriverContactTask, DriverPhoneVersion]], int]:
    newer_phone = aliased(DriverPhoneVersion)
    has_newer_phone = (
        select(newer_phone.id)
        .where(
            newer_phone.driver_profile_id == ManualDriverContactTask.driver_profile_id,
            newer_phone.version > DriverPhoneVersion.version,
        )
        .correlate(ManualDriverContactTask, DriverPhoneVersion)
        .exists()
    )
    current_authority = (
        select(WhatsappConsent.id)
        .where(
            WhatsappConsent.id == ManualDriverContactTask.consent_id,
            WhatsappConsent.driver_profile_id == ManualDriverContactTask.driver_profile_id,
            WhatsappConsent.phone_version_id == ManualDriverContactTask.phone_version_id,
            WhatsappConsent.purpose == ManualDriverContactTask.purpose,
            WhatsappConsent.withdrawn_at.is_(None),
        )
        .correlate(ManualDriverContactTask)
        .exists()
    )
    visible = or_(
        ManualDriverContactTask.status == ManualContactTaskStatus.COMPLETED.value,
        and_(current_authority, ~has_newer_phone, DriverPhoneVersion.verified_at.is_not(None)),
    )
    base = select(ManualDriverContactTask, DriverPhoneVersion).join(
        DriverPhoneVersion,
        DriverPhoneVersion.id == ManualDriverContactTask.phone_version_id,
    )
    if driver_profile_id is not None:
        base = base.where(ManualDriverContactTask.driver_profile_id == driver_profile_id)
    if open_only:
        base = base.where(
            ManualDriverContactTask.status == "open", ManualDriverContactTask.completed_at.is_(None)
        )
    if not history:
        base = base.where(visible)
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        (
            await session.execute(
                base.order_by(
                    ManualDriverContactTask.created_at.asc()
                    if oldest_first
                    else ManualDriverContactTask.created_at.desc(),
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
    settings: Settings,
) -> ManualDriverContactTask:
    if (
        await session.scalar(
            select(User.id).where(
                User.id == actor_user_id,
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
        )
        is None
    ):
        raise AppError("FORBIDDEN_ROLE", "Admin role is required", status_code=403)
    normalized_note = note.strip()
    if outcome not in {"attempted", "reached", "failed"} or not normalized_note:
        raise AppError(
            "INVALID_CONTACT_COMPLETION",
            "A valid outcome and nonblank operator note are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    identity = (
        await session.execute(
            select(
                ManualDriverContactTask.driver_profile_id,
                ManualDriverContactTask.purpose,
                DriverProfile.user_id,
            )
            .join(DriverProfile, DriverProfile.id == ManualDriverContactTask.driver_profile_id)
            .where(ManualDriverContactTask.id == task_id)
        )
    ).first()
    if identity is None:
        raise AppError("CONTACT_TASK_NOT_FOUND", "Contact task was not found", status_code=404)
    from app.services.users import _lock_users

    users = await _lock_users(session, {actor_user_id, identity.user_id})
    await require_active_admin(session, actor_user_id)
    driver = users.get(identity.user_id)
    authority = await _manual_contact_authority(
        session, driver_profile_id=identity.driver_profile_id, purpose=identity.purpose
    )
    task = await session.scalar(
        select(ManualDriverContactTask)
        .where(ManualDriverContactTask.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise AppError("CONTACT_TASK_NOT_FOUND", "Contact task was not found", status_code=404)
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
    current_fingerprint = None
    if driver is not None and driver.role == UserRole.DRIVER and driver.status == UserStatus.ACTIVE:
        try:
            current_fingerprint = phone_fingerprint(driver.phone or "", settings)
        except AppError:
            pass
    if (
        authority is None
        or authority[0].phone_fingerprint != current_fingerprint
        or not _task_matches_authority(task, *authority, task.purpose)
    ):
        raise AppError(
            "CONTACT_TASK_AUTHORITY_INACTIVE",
            "The task no longer has current consent for its purpose and phone",
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
