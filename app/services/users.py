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


async def _lock_users(session: AsyncSession, user_ids: set[UUID]) -> dict[UUID, User]:
    # All administrative actor/target commands take the same UUID order.
    users = await session.scalars(
        select(User)
        .where(User.id.in_(user_ids))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {user.id: user for user in users}


def _require_admin_actor(actor: User | None, actor_session_version: int | None) -> User:
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
    return actor


async def _reauthenticate_admin(
    actor: User,
    current_password: str | None,
    *,
    rate_limiter: LoginRateLimiter | None,
    client_ip: str | None,
) -> None:
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
    if current_password is None or not verify_password(current_password, actor.password_hash):
        raise AppError(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    await rate_limiter.release_success(client_ip, actor.email)


async def create_user(
    session: AsyncSession,
    payload: UserCreate,
    settings: Settings,
    *,
    actor_user_id: UUID,
    actor_session_version: int,
    rate_limiter: LoginRateLimiter | None = None,
    client_ip: str | None = None,
) -> User:
    actor = _require_admin_actor(
        (await _lock_users(session, {actor_user_id})).get(actor_user_id), actor_session_version
    )
    if payload.role == UserRole.ADMIN:
        await _reauthenticate_admin(
            actor, payload.current_password, rate_limiter=rate_limiter, client_ip=client_ip
        )
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
    """Serialize current actor authority and one global target revocation per transition."""
    user_ids = {user_id}
    if actor_user_id is not None:
        user_ids.add(actor_user_id)
    locked = await _lock_users(session, user_ids)
    user = locked.get(user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)
    actor = None
    if actor_user_id is not None:
        actor = _require_admin_actor(locked.get(actor_user_id), actor_session_version)

    update_values = payload.model_dump(exclude_unset=True, exclude={"current_password"})
    changed_fields = list(update_values)
    status_changed = "status" in update_values and update_values["status"] != user.status
    role_changed = "role" in update_values and update_values["role"] != user.role
    enters_admin_role = role_changed and update_values["role"] == UserRole.ADMIN
    activates_admin = (
        status_changed
        and update_values["status"] == UserStatus.ACTIVE
        and update_values.get("role", user.role) == UserRole.ADMIN
    )
    if enters_admin_role and user.status != UserStatus.ACTIVE:
        raise AppError(
            "USER_NOT_ACTIVE",
            "Only an active user can be elevated to administrator",
            status_code=status.HTTP_409_CONFLICT,
        )
    if enters_admin_role or activates_admin:
        actor = _require_admin_actor(actor, actor_session_version)
        await _reauthenticate_admin(
            actor, payload.current_password, rate_limiter=rate_limiter, client_ip=client_ip
        )
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
