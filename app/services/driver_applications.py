import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.driver_application import DriverApplication, DriverApplicationStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.driver_applications import DriverApplicationCreate
from app.services.users import get_user_by_email

PUBLIC_APPLICATION_MESSAGE = "Application received for review."
PUBLIC_STATUS_MESSAGE = "Application status is pending review."
PUBLIC_NOT_FOUND_MESSAGE = "Application status is unavailable."


@dataclass(frozen=True)
class DriverApplicationSubmission:
    application: DriverApplication | None
    reference: str | None


def status_reference_hash(reference: str) -> str:
    return hashlib.sha256(reference.encode("utf-8")).hexdigest()


def _unreachable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(96))


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
        return DriverApplicationSubmission(application=None, reference=reference)

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
            return DriverApplicationSubmission(application=None, reference=reference)
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
    return DriverApplicationSubmission(application=application, reference=reference)


async def _require_active_admin(session: AsyncSession, admin_user_id: UUID) -> User:
    actor = await session.scalar(select(User).where(User.id == admin_user_id).with_for_update())
    if actor is None:
        raise AppError(
            "AUTHENTICATION_REQUIRED",
            "Authentication credentials were not provided",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if actor.status != UserStatus.ACTIVE.value:
        raise AppError(
            "USER_NOT_ACTIVE",
            "User account is not active",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if actor.role != UserRole.ADMIN.value:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Admin role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return actor


async def list_driver_applications(
    session: AsyncSession,
    *,
    admin_user_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[DriverApplication], int]:
    """Read the pending queue only after locking and validating the admin."""

    await _require_active_admin(session, admin_user_id)
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
