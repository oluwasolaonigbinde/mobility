from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.users import UserCreate, UserUpdate


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
) -> UserUpdateResult:
    """Apply an administrative user update under the user row lock.

    Any real status transition rotates ``session_version``. That covers entering
    containment, leaving it, and reactivation, and it is what ends capabilities
    issued under the previous status: live bearers stop verifying, and an unused
    password reset fails its captured-version fence. Restating the current status
    is not a transition and rotates nothing.
    """
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)

    update_values = payload.model_dump(exclude_unset=True)
    changed_fields = list(update_values)
    status_changed = "status" in update_values and update_values["status"] != user.status
    for field, value in update_values.items():
        setattr(user, field, value)
    if status_changed:
        user.session_version += 1
    await session.flush()
    return UserUpdateResult(
        user=user,
        changed_fields=changed_fields,
        sessions_revoked=status_changed,
    )
