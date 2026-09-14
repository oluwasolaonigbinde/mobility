import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.driver_application import (
    DriverAccountSetupToken,
    DriverApplication,
    DriverApplicationAccessToken,
    DriverApplicationStatus,
)
from app.models.kyc import DriverKycReviewDecision, DriverKycSubmission, KycSubmissionStatus
from app.models.payee import PayeeBankAccountPayoutVerification
from app.models.user import User, UserRole, UserStatus
from app.models.vehicle import Vehicle, VehicleStatus
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.payout_rule_serialization import database_clock
from app.services.users import validate_password_length


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _token_id(token: str) -> UUID | None:
    try:
        raw_id, signature = token.split(".", 1)
        return UUID(raw_id) if signature else None
    except (AttributeError, ValueError):
        return None


def _token_value(row: DriverAccountSetupToken, settings: Settings) -> str:
    expires = int(_utc(row.expires_at).timestamp())
    payload = f"{row.id}:{row.application_id}:{row.user_id}:{row.session_version}:{expires}"
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
        f"driver-account-setup:v1:{payload}".encode(),
        hashlib.sha256,
    ).digest()
    return f"{row.id}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def driver_account_setup_token_for_delivery(
    row: DriverAccountSetupToken, settings: Settings
) -> str:
    token = _token_value(row, settings)
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row.token_sha256):
        raise RuntimeError("driver account setup token evidence mismatch")
    return token


def synthetic_driver_account_setup_token(
    row: DriverAccountSetupToken,
    settings: Settings,
    *,
    synthetic_test_authority: bool,
) -> str:
    if not synthetic_test_authority or settings.environment not in {"test", "testing"}:
        raise RuntimeError("synthetic driver account setup authority is test-only")
    return driver_account_setup_token_for_delivery(row, settings)


async def _current_evidence_digest(
    session: AsyncSession, *, application: DriverApplication
) -> str:
    from app.models.kyc import VehicleEvidenceReviewDecision, VehicleEvidenceSubmission
    from app.services.vehicle_onboarding import reconcile_driver_work_eligibility

    eligible = await reconcile_driver_work_eligibility(
        session, driver_profile_id=application.driver_profile_id
    )
    profile = await session.scalar(
        select(DriverProfile)
        .where(DriverProfile.id == application.driver_profile_id)
        .with_for_update()
    )
    if (
        not eligible
        or profile is None
        or profile.user_id != application.user_id
        or profile.onboarding_status != DriverOnboardingStatus.ACTIVE.value
    ):
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_NOT_READY",
            "Current approved person, payee and vehicle evidence is required",
            status_code=status.HTTP_409_CONFLICT,
        )
    person = await session.scalar(
        select(DriverKycSubmission)
        .where(DriverKycSubmission.driver_profile_id == profile.id)
        .order_by(DriverKycSubmission.version.desc())
        .limit(1)
        .with_for_update()
    )
    person_decision = (
        await session.scalar(
            select(DriverKycReviewDecision).where(
                DriverKycReviewDecision.submission_id == person.id,
                DriverKycReviewDecision.decision == KycSubmissionStatus.APPROVED.value,
            )
        )
        if person is not None
        else None
    )
    payee_verification = (
        await session.scalar(
            select(PayeeBankAccountPayoutVerification).where(
                PayeeBankAccountPayoutVerification.bank_account_version_id
                == person.bank_account_version_id
            )
        )
        if person is not None
        else None
    )
    vehicles = list(
        (
            await session.scalars(
                select(Vehicle)
                .where(
                    Vehicle.driver_profile_id == profile.id,
                    Vehicle.status == VehicleStatus.ACTIVE.value,
                )
                .order_by(Vehicle.id)
                .with_for_update()
            )
        ).all()
    )
    vehicle_facts: list[dict[str, object]] = []
    for vehicle in vehicles:
        submission = await session.scalar(
            select(VehicleEvidenceSubmission)
            .where(VehicleEvidenceSubmission.vehicle_id == vehicle.id)
            .order_by(VehicleEvidenceSubmission.version.desc())
            .limit(1)
            .with_for_update()
        )
        decision = (
            await session.scalar(
                select(VehicleEvidenceReviewDecision)
                .where(VehicleEvidenceReviewDecision.submission_id == submission.id)
                .order_by(VehicleEvidenceReviewDecision.sequence.desc())
                .limit(1)
                .with_for_update()
            )
            if submission is not None
            else None
        )
        if (
            submission is not None
            and decision is not None
            and submission.status == KycSubmissionStatus.APPROVED.value
            and decision.decision == KycSubmissionStatus.APPROVED.value
        ):
            vehicle_facts.append(
                {
                    "vehicle_id": str(vehicle.id),
                    "submission_id": str(submission.id),
                    "version": submission.version,
                    "decision_id": str(decision.id),
                    "sequence": decision.sequence,
                    "valid_until": (
                        _utc(decision.valid_until).isoformat() if decision.valid_until else None
                    ),
                }
            )
    if (
        person is None
        or person.status != KycSubmissionStatus.APPROVED.value
        or person_decision is None
        or payee_verification is None
        or not vehicle_facts
    ):
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_NOT_READY",
            "Current approved person, payee and vehicle evidence is required",
            status_code=status.HTTP_409_CONFLICT,
        )
    facts = {
        "application_id": str(application.id),
        "user_id": str(application.user_id),
        "profile_id": str(profile.id),
        "person_submission_id": str(person.id),
        "person_version": person.version,
        "person_decision_id": str(person_decision.id),
        "payee_verification_id": str(payee_verification.id),
        "vehicles": vehicle_facts,
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _request_fingerprint(application_id: UUID, actor_user_id: UUID) -> str:
    return hashlib.sha256(
        f"driver-account-setup:v1:{application_id}:{actor_user_id}".encode()
    ).hexdigest()


async def _acquire_client_request_lock(session: AsyncSession, client_request_id: UUID) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"driver-account-setup:{client_request_id}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def initiate_driver_account_setup(
    session: AsyncSession,
    *,
    application_id: UUID,
    actor_user_id: UUID,
    client_request_id: UUID,
    settings: Settings,
) -> DriverAccountSetupToken:
    await require_active_admin(session, actor_user_id)
    await _acquire_client_request_lock(session, client_request_id)
    fingerprint = _request_fingerprint(application_id, actor_user_id)
    retry = await session.scalar(
        select(DriverAccountSetupToken)
        .where(DriverAccountSetupToken.client_request_id == client_request_id)
        .with_for_update()
    )
    if retry is not None:
        if retry.application_id != application_id or retry.request_fingerprint != fingerprint:
            raise AppError(
                "DRIVER_ACCOUNT_SETUP_RETRY_CONFLICT",
                "The setup retry does not match its original request",
                status_code=status.HTTP_409_CONFLICT,
            )
        return retry
    application = await session.scalar(
        select(DriverApplication)
        .where(DriverApplication.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = (
        await session.scalar(select(User).where(User.id == application.user_id).with_for_update())
        if application is not None
        else None
    )
    if (
        application is None
        or application.status != DriverApplicationStatus.APPROVED.value
        or user is None
        or user.role != UserRole.DRIVER.value
        or user.status != UserStatus.INVITED.value
    ):
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_NOT_READY",
            "The approved invited driver is not eligible for setup",
            status_code=status.HTTP_409_CONFLICT,
        )
    evidence_sha256 = await _current_evidence_digest(session, application=application)
    now = await database_clock(session)
    previous = list(
        (
            await session.scalars(
                select(DriverAccountSetupToken)
                .where(
                    DriverAccountSetupToken.application_id == application.id,
                    DriverAccountSetupToken.used_at.is_(None),
                    DriverAccountSetupToken.superseded_at.is_(None),
                )
                .with_for_update()
            )
        ).all()
    )
    for row in previous:
        row.superseded_at = now
    setup = DriverAccountSetupToken(
        id=uuid4(),
        application_id=application.id,
        user_id=user.id,
        issued_by_user_id=actor_user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
        token_sha256="0" * 64,
        evidence_sha256=evidence_sha256,
        session_version=user.session_version,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.driver_account_setup_ttl_seconds),
    )
    setup.token_sha256 = hashlib.sha256(_token_value(setup, settings).encode()).hexdigest()
    session.add(setup)
    await session.flush()
    from app.services.notifications import create_driver_account_setup_notification

    await create_driver_account_setup_notification(session, user=user, setup=setup)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.driver_account_setup.initiated",
        entity_type="driver_account_setup_token",
        entity_id=str(setup.id),
        metadata={"application_id": str(application.id), "superseded_count": len(previous)},
    )
    return setup


async def complete_driver_account_setup(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
    settings: Settings,
) -> User:
    validate_password_length(new_password, settings)
    setup_id = _token_id(token.strip())
    setup = (
        await session.scalar(
            select(DriverAccountSetupToken)
            .where(DriverAccountSetupToken.id == setup_id)
            .with_for_update()
        )
        if setup_id is not None
        else None
    )
    if setup is None:
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_INVALID",
            "Driver account setup is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    application = await session.scalar(
        select(DriverApplication)
        .where(DriverApplication.id == setup.application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = await session.scalar(
        select(User)
        .where(User.id == setup.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = await database_clock(session)
    supplied_hash = hashlib.sha256(token.strip().encode()).hexdigest()
    invalid = (
        application is None
        or user is None
        or setup.used_at is not None
        or setup.superseded_at is not None
        or now >= _utc(setup.expires_at)
        or not hmac.compare_digest(supplied_hash, setup.token_sha256)
        or application.user_id != user.id
        or application.status != DriverApplicationStatus.APPROVED.value
        or user.role != UserRole.DRIVER.value
        or user.status != UserStatus.INVITED.value
        or user.session_version != setup.session_version
    )
    if invalid:
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_INVALID",
            "Driver account setup is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    evidence_sha256 = await _current_evidence_digest(session, application=application)
    if not hmac.compare_digest(evidence_sha256, setup.evidence_sha256):
        raise AppError(
            "DRIVER_ACCOUNT_SETUP_INVALID",
            "Driver account setup is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    setup.used_at = now
    await session.execute(
        update(DriverApplicationAccessToken)
        .where(
            DriverApplicationAccessToken.application_id == application.id,
            DriverApplicationAccessToken.invalidated_at.is_(None),
        )
        .values(invalidated_at=now)
    )
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.status = UserStatus.ACTIVE.value
    user.session_version += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="auth.driver_account_setup.completed",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"application_id": str(application.id), "sessions_revoked": True},
    )
    return user


def setup_state(row: DriverAccountSetupToken) -> str:
    if row.used_at is not None:
        return "used"
    if row.superseded_at is not None:
        return "superseded"
    return "pending"
