import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.driver_application import (
    DriverApplication,
    DriverApplicationAccessToken,
    DriverApplicationStatus,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.driver_applications import DriverApplicationCreate
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.users import get_user_by_email

PUBLIC_APPLICATION_MESSAGE = "Application received for review."
PUBLIC_STATUS_MESSAGE = "Application status is pending review."
PUBLIC_NOT_FOUND_MESSAGE = "Application status is unavailable."


@dataclass(frozen=True)
class DriverApplicationSubmission:
    application: DriverApplication | None
    reference: str | None
    access_application: DriverApplication | None


def status_reference_hash(reference: str) -> str:
    return hashlib.sha256(reference.encode("utf-8")).hexdigest()


def _unreachable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(96))


def _access_token_value(access: DriverApplicationAccessToken, settings: Settings) -> str:
    expires_at = (
        access.expires_at.replace(tzinfo=UTC)
        if access.expires_at.tzinfo is None
        else access.expires_at.astimezone(UTC)
    )
    expires = int(expires_at.timestamp())
    payload = f"{access.id}:{access.application_id}:{expires}"
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
        f"driver-onboarding-access:v1:{payload}".encode(),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{access.id}.{encoded}"


def driver_application_access_token_for_delivery(
    access: DriverApplicationAccessToken, settings: Settings
) -> str:
    token = _access_token_value(access, settings)
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), access.token_sha256):
        raise RuntimeError("driver onboarding access-token evidence mismatch")
    return token


def synthetic_driver_application_access_token(
    access: DriverApplicationAccessToken,
    settings: Settings,
    *,
    synthetic_test_authority: bool,
) -> str:
    if not synthetic_test_authority or settings.environment not in {"test", "testing"}:
        raise RuntimeError("synthetic driver onboarding access authority is test-only")
    return driver_application_access_token_for_delivery(access, settings)


async def issue_driver_application_access(
    session: AsyncSession,
    *,
    application: DriverApplication,
    settings: Settings,
) -> DriverApplicationAccessToken | None:
    locked_application = await session.scalar(
        select(DriverApplication)
        .where(DriverApplication.id == application.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked_application is None
        or locked_application.status != DriverApplicationStatus.PENDING.value
    ):
        return None
    access = DriverApplicationAccessToken(
        id=uuid4(),
        application_id=locked_application.id,
        token_sha256="0" * 64,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.driver_onboarding_access_ttl_seconds),
    )
    token = _access_token_value(access, settings)
    access.token_sha256 = hashlib.sha256(token.encode()).hexdigest()
    session.add(access)
    await session.flush()
    user = await session.get(User, locked_application.user_id)
    if user is None:  # pragma: no cover - protected by FK
        raise RuntimeError("driver onboarding access recipient disappeared")
    from app.services.notifications import create_driver_onboarding_access_notification

    await create_driver_onboarding_access_notification(session, user=user, access=access)
    return access


def _access_token_id(token: str) -> UUID | None:
    try:
        raw_id, signature = token.split(".", 1)
        if not signature:
            return None
        return UUID(raw_id)
    except (ValueError, AttributeError):
        return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def application_from_access_token(
    session: AsyncSession,
    *,
    token: str,
    settings: Settings,
    lock: bool,
) -> DriverApplication:
    token_id = _access_token_id(token.strip())
    query = select(DriverApplicationAccessToken).where(DriverApplicationAccessToken.id == token_id)
    if lock:
        query = query.with_for_update()
    access = await session.scalar(query) if token_id is not None else None
    if access is None:
        application = None
    elif lock:
        application = await session.scalar(
            select(DriverApplication)
            .where(DriverApplication.id == access.application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        application = await session.get(DriverApplication, access.application_id)
    supplied_hash = hashlib.sha256(token.strip().encode()).hexdigest()
    if (
        access is None
        or application is None
        or application.status != DriverApplicationStatus.PENDING.value
        or datetime.now(UTC) >= _utc(access.expires_at)
        or not hmac.compare_digest(supplied_hash, access.token_sha256)
    ):
        raise AppError(
            "ONBOARDING_ACCESS_INVALID",
            "Driver onboarding access is unavailable",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return application


async def terminalize_driver_application(
    session: AsyncSession,
    *,
    application: DriverApplication,
    terminal_status: DriverApplicationStatus,
    actor_user_id: UUID,
    source_entity_type: str,
    source_entity_id: UUID,
) -> bool:
    """Move a locked pending application to one terminal state exactly once."""

    if terminal_status not in {
        DriverApplicationStatus.APPROVED,
        DriverApplicationStatus.REJECTED,
    }:
        raise ValueError("driver application terminal status is required")
    if application.status != DriverApplicationStatus.PENDING.value:
        return False
    application.status = terminal_status.value
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action=f"admin.driver_application.{terminal_status.value}",
        entity_type="driver_application",
        entity_id=str(application.id),
        metadata={
            "driver_profile_id": str(application.driver_profile_id),
            "from_status": DriverApplicationStatus.PENDING.value,
            "to_status": terminal_status.value,
            "source_entity_type": source_entity_type,
            "source_entity_id": str(source_entity_id),
        },
    )
    return True


async def _eligible_access_application(
    session: AsyncSession, user: User | None
) -> DriverApplication | None:
    if (
        user is None
        or user.role != UserRole.DRIVER.value
        or user.status != UserStatus.INVITED.value
    ):
        return None
    return await session.scalar(
        select(DriverApplication).where(
            DriverApplication.user_id == user.id,
            DriverApplication.status == DriverApplicationStatus.PENDING.value,
        )
    )


def _is_user_email_conflict(exc: IntegrityError) -> bool:
    candidates = (exc.orig, getattr(exc.orig, "__cause__", None))
    constraint_names = {
        str(name)
        for candidate in candidates
        if candidate is not None
        if (name := getattr(candidate, "constraint_name", None)) is not None
    }
    if constraint_names & {"uq_users_email", "ix_users_email"}:
        return True
    message = str(exc.orig).lower()
    return "unique constraint failed: users.email" in message


async def submit_driver_application(
    session: AsyncSession,
    payload: DriverApplicationCreate,
) -> DriverApplicationSubmission:
    """Create the user/profile/application graph or return a generic duplicate.

    The email uniqueness constraint is the race authority.  A lost insert race
    rolls back this transaction and returns the same public result as every
    existing-user path; no pre-existing graph is ever mutated.
    """

    # Always mint a one-time public reference so existing-user and lost-race
    # responses have the same observable shape as a newly created application.
    # Only a successful new application persists its digest.
    reference = secrets.token_urlsafe(32)
    existing_user = await get_user_by_email(session, payload.email)
    if existing_user is not None:
        return DriverApplicationSubmission(
            application=None,
            reference=reference,
            access_application=await _eligible_access_application(session, existing_user),
        )

    user = User(
        email=payload.email,
        password_hash=_unreachable_password_hash(),
        full_name=payload.full_name,
        phone=payload.phone,
        role=UserRole.DRIVER.value,
        status=UserStatus.INVITED.value,
        must_change_password=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if _is_user_email_conflict(exc):
            existing_user = await get_user_by_email(session, payload.email)
            return DriverApplicationSubmission(
                application=None,
                reference=reference,
                access_application=await _eligible_access_application(session, existing_user),
            )
        raise

    profile = DriverProfile(
        user_id=user.id,
        onboarding_status=DriverOnboardingStatus.PENDING.value,
        service_city=payload.service_city,
        country_code=payload.country_code,
        profile_metadata={},
    )
    session.add(profile)
    await session.flush()
    application = DriverApplication(
        user_id=user.id,
        driver_profile_id=profile.id,
        status=DriverApplicationStatus.PENDING.value,
        status_reference_sha256=status_reference_hash(reference),
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        service_city=payload.service_city,
        country_code=payload.country_code,
    )
    session.add(application)
    await session.flush()
    return DriverApplicationSubmission(
        application=application,
        reference=reference,
        access_application=application,
    )


async def list_driver_applications(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[DriverApplication], int]:
    """Read the pending queue only after locking and validating the admin."""

    await require_active_admin(session, admin_user_id)
    filters = [DriverApplication.status == DriverApplicationStatus.PENDING.value]
    total = await session.scalar(
        select(func.count()).select_from(DriverApplication).where(*filters)
    )
    result = await session.execute(
        select(DriverApplication)
        .where(*filters)
        .order_by(DriverApplication.created_at.desc(), DriverApplication.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def application_status_exists(session: AsyncSession, reference: str) -> bool:
    """Check the digest without changing the deliberately generic response."""

    digest = status_reference_hash(reference)
    return bool(
        await session.scalar(
            select(DriverApplication.id).where(
                DriverApplication.status_reference_sha256 == digest,
                DriverApplication.status == DriverApplicationStatus.PENDING.value,
            )
        )
    )
