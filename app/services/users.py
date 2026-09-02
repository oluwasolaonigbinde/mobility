from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.schemas.users import UserCreate, UserUpdate

if TYPE_CHECKING:
    from app.core.rate_limit import LoginRateLimiter


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password_length(password: str, settings: Settings) -> None:
    if len(password) < settings.password_min_length:
        raise AppError(
            "PASSWORD_TOO_SHORT",
            f"Password must be at least {settings.password_min_length} characters long",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, payload: UserCreate, settings: Settings) -> User:
    validate_password_length(payload.password, settings)
    normalized_email = normalize_email(payload.email)
    if await get_user_by_email(session, normalized_email):
        raise AppError(
            "DUPLICATE_EMAIL",
            "A user with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        status=payload.status,
        must_change_password=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "DUPLICATE_EMAIL",
            "A user with this email already exists",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    return user


async def list_users(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    role: str | None,
    user_status: str | None,
) -> tuple[list[User], int]:
    statement: Select[tuple[User]] = select(User)
    count_statement = select(func.count()).select_from(User)
    if role is not None:
        statement = statement.where(User.role == role)
        count_statement = count_statement.where(User.role == role)
    if user_status is not None:
        statement = statement.where(User.status == user_status)
        count_statement = count_statement.where(User.status == user_status)

    total = await session.scalar(count_statement)
    result = await session.execute(
        statement.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


@dataclass(frozen=True)
class UserUpdateResult:
    user: User
    changed_fields: list[str]
    sessions_revoked: bool


async def update_user(
    session: AsyncSession,
    user_id: UUID,
    payload: UserUpdate,
    *,
    actor_user_id: UUID | None = None,
    actor_session_version: int | None = None,
    rate_limiter: LoginRateLimiter | None = None,
    client_ip: str | None = None,
) -> UserUpdateResult:
    """Apply an administrative user update under the user row lock.

    Any real status transition rotates ``session_version``. An active
    non-admin-to-admin transition also rotates after the acting administrator's
    current authority and password are rechecked under locks and through the
    shared authentication failure buckets. Either transition ends capabilities
    issued under the previous authority: live bearers stop verifying, and an
    unused password reset fails its captured-version fence. Restating the current
    status or role is not a transition and rotates nothing.
    """
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)

    update_values = payload.model_dump(exclude_unset=True, exclude={"current_password"})
    changed_fields = list(update_values)
    status_changed = "status" in update_values and update_values["status"] != user.status
    role_changed = "role" in update_values and update_values["role"] != user.role
    enters_admin_role = role_changed and update_values["role"] == UserRole.ADMIN
    if enters_admin_role:
        if user.status != UserStatus.ACTIVE:
            raise AppError(
                "USER_NOT_ACTIVE",
                "Only an active user can be elevated to administrator",
                status_code=status.HTTP_409_CONFLICT,
            )
        actor = await session.scalar(
            select(User)
            .where(User.id == actor_user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if actor is None:
            raise AppError(
                "INVALID_TOKEN",
                "Invalid authentication token",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if actor.status != UserStatus.ACTIVE:
            raise AppError(
                "USER_NOT_ACTIVE",
                "User account is not active",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if actor.role != UserRole.ADMIN:
            raise AppError(
                "FORBIDDEN_ROLE",
                "Admin role is required",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if actor.session_version != actor_session_version:
            raise AppError(
                "SESSION_REVOKED",
                "Session is no longer valid",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if rate_limiter is None or client_ip is None:
            raise AppError(
                "RATE_LIMIT_UNAVAILABLE",
                "Authentication service is temporarily unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "60"},
            )
        decision = await rate_limiter.reserve(client_ip, actor.email)
        if decision.storage_available is False:
            raise AppError(
                "RATE_LIMIT_UNAVAILABLE",
                "Authentication service is temporarily unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": str(max(decision.retry_after_seconds, 1))},
            )
        if not decision.allowed:
            raise AppError(
                "RATE_LIMITED",
                "Too many administrator elevation attempts",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"retry_after_seconds": decision.retry_after_seconds},
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        if payload.current_password is None or not verify_password(
            payload.current_password, actor.password_hash
        ):
            raise AppError(
                "INVALID_CREDENTIALS",
                "Invalid email or password",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        await rate_limiter.release_success(client_ip, actor.email)
    for field, value in update_values.items():
        setattr(user, field, value)
    sessions_revoked = status_changed or enters_admin_role
    if sessions_revoked:
        user.session_version += 1
    await session.flush()
    return UserUpdateResult(
        user=user,
        changed_fields=changed_fields,
        sessions_revoked=sessions_revoked,
    )
