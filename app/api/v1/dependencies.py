from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User, UserRole, UserStatus
from app.services.users import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDependency,
    settings: SettingsDependency,
) -> User:
    if token is None:
        raise AppError(
            "AUTHENTICATION_REQUIRED",
            "Authentication credentials were not provided",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user_id = decode_access_token(token, settings)
    except ValueError as exc:
        raise AppError(
            "INVALID_TOKEN",
            "Invalid authentication token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AppError(
            "INVALID_TOKEN",
            "Invalid authentication token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.status in {UserStatus.SUSPENDED.value, UserStatus.DISABLED.value}:
        raise AppError(
            "USER_NOT_ACTIVE",
            "User account is not active",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


CurrentUserDependency = Annotated[User, Depends(get_current_user)]


def require_admin_user(user: CurrentUserDependency) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Admin role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


def require_advertiser_user(user: CurrentUserDependency) -> User:
    if user.role != UserRole.ADVERTISER:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Advertiser role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


def require_driver_user(user: CurrentUserDependency) -> User:
    if user.role != UserRole.DRIVER:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Driver role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


AdminUserDependency = Annotated[User, Depends(require_admin_user)]
AdvertiserUserDependency = Annotated[User, Depends(require_advertiser_user)]
DriverUserDependency = Annotated[User, Depends(require_driver_user)]
