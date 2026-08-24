from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.payment_enqueue import PaymentEventEnqueuer, build_payment_event_enqueuer
from app.core.rate_limit import LoginRateLimiter, build_login_rate_limiter
from app.core.security import decode_token_claims
from app.core.trip_enqueue import TripProcessingEnqueuer, build_trip_enqueuer
from app.db.session import get_session
from app.models.user import User, UserRole, UserStatus
from app.services.users import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_login_rate_limiter(settings: SettingsDependency) -> LoginRateLimiter:
    return build_login_rate_limiter(settings)


RateLimiterDependency = Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)]


def get_trip_enqueuer(settings: SettingsDependency) -> TripProcessingEnqueuer:
    return build_trip_enqueuer(settings)


TripEnqueuerDependency = Annotated[TripProcessingEnqueuer, Depends(get_trip_enqueuer)]


def get_payment_event_enqueuer(settings: SettingsDependency) -> PaymentEventEnqueuer:
    return build_payment_event_enqueuer(settings)


PaymentEventEnqueuerDependency = Annotated[
    PaymentEventEnqueuer, Depends(get_payment_event_enqueuer)
]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
) -> User:
    if token is None:
        raise AppError(
            "AUTHENTICATION_REQUIRED",
            "Authentication credentials were not provided",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        claims = decode_token_claims(token, settings)
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise ValueError
        user_id = UUID(subject)
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
    token_session_version = claims.get("sv")
    if token_session_version is not None and token_session_version != user.session_version:
        raise AppError(
            "SESSION_REVOKED",
            "Session is no longer valid",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    auth_time = claims.get("auth_time")
    if isinstance(auth_time, (int, float)):
        cap_at = datetime.fromtimestamp(auth_time, UTC) + timedelta(
            minutes=settings.session_absolute_lifetime_minutes
        )
        if datetime.now(UTC) >= cap_at:
            raise AppError(
                "SESSION_EXPIRED",
                "Session has reached its maximum lifetime",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
    allowed_while_password_change_required = {
        f"{settings.api_v1_prefix}/me",
        f"{settings.api_v1_prefix}/auth/change-password",
        f"{settings.api_v1_prefix}/auth/refresh",
    }
    if user.must_change_password and request.url.path not in allowed_while_password_change_required:
        raise AppError(
            "PASSWORD_CHANGE_REQUIRED",
            "Password must be changed before continuing",
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
