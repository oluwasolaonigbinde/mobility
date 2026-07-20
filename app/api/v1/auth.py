from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette import status

from app.api.v1.dependencies import (
    CurrentUserDependency,
    RateLimiterDependency,
    SessionDependency,
    SettingsDependency,
    oauth2_scheme,
)
from app.core.errors import AppError
from app.core.rate_limit import login_client_ip
from app.core.security import (
    create_access_token,
    decode_token_claims,
    hash_password,
    verify_password,
)
from app.models.user import UserStatus
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, LoginUser
from app.services.audit import create_audit_event
from app.services.auth import authenticate_user
from app.services.users import validate_password_length

router = APIRouter(prefix="/auth", tags=["Auth"])


def login_response(user, settings, *, auth_time: datetime | None = None, expires_at=None):
    token, expires_in = create_access_token(
        user.id,
        settings,
        session_version=user.session_version,
        auth_time=auth_time,
        expires_at=expires_at,
    )
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=LoginUser.model_validate(user, from_attributes=True),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    description="Exchange local demo or application credentials for a bearer access token.",
)
async def login(
    payload: LoginRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
    rate_limiter: RateLimiterDependency,
) -> LoginResponse:
    client_ip = login_client_ip(request, settings)
    decision = await rate_limiter.reserve(client_ip, payload.email)
    if not decision.allowed:
        if decision.newly_blocked:
            await create_audit_event(
                session,
                actor_user_id=None,
                action="auth.login.rate_limited",
                entity_type="authentication",
                entity_id=None,
                metadata={
                    "bucket": decision.bucket,
                    "retry_after_seconds": decision.retry_after_seconds,
                    "ip": client_ip,
                    "email": payload.email.lower() if decision.bucket == "account" else None,
                },
            )
            await session.commit()
        raise AppError(
            "RATE_LIMITED",
            "Too many login attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    user = await authenticate_user(session, payload.email, payload.password)
    if user is None:
        await create_audit_event(
            session,
            actor_user_id=None,
            action="auth.login.failed",
            entity_type="authentication",
            entity_id=None,
            metadata={"email": payload.email.lower(), "reason": "invalid_credentials"},
        )
        await session.commit()
        raise AppError(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.status in {UserStatus.SUSPENDED.value, UserStatus.DISABLED.value}:
        await create_audit_event(
            session,
            actor_user_id=user.id,
            action="auth.login.failed",
            entity_type="authentication",
            entity_id=str(user.id),
            metadata={"email": user.email, "reason": "not_active"},
        )
        await session.commit()
        raise AppError(
            "USER_NOT_ACTIVE",
            "User account is not active",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    await rate_limiter.release_success(client_ip, payload.email)
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="auth.login.succeeded",
        entity_type="authentication",
        entity_id=str(user.id),
        metadata={"email": user.email},
    )
    await session.commit()
    return login_response(user, settings)


@router.post(
    "/change-password",
    response_model=LoginResponse,
    summary="Change the current user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
    rate_limiter: RateLimiterDependency,
) -> LoginResponse:
    # A stolen session cookie must not be convertible into the account password
    # by brute force: current-password guesses share the login failure buckets.
    client_ip = login_client_ip(request, settings)
    decision = await rate_limiter.reserve(client_ip, current_user.email)
    if not decision.allowed:
        if decision.newly_blocked:
            await create_audit_event(
                session,
                actor_user_id=current_user.id,
                action="auth.password.change_rate_limited",
                entity_type="user",
                entity_id=str(current_user.id),
                metadata={
                    "bucket": decision.bucket,
                    "retry_after_seconds": decision.retry_after_seconds,
                    "ip": client_ip,
                },
            )
            await session.commit()
        raise AppError(
            "RATE_LIMITED",
            "Too many password change attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    if not verify_password(payload.current_password, current_user.password_hash):
        await create_audit_event(
            session,
            actor_user_id=current_user.id,
            action="auth.password.change_failed",
            entity_type="user",
            entity_id=str(current_user.id),
            metadata={"reason": "current_password_incorrect", "ip": client_ip},
        )
        await session.commit()
        raise AppError(
            "CURRENT_PASSWORD_INCORRECT",
            "Current password is incorrect",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # The current password is proven; refund the reservation so validation
    # mistakes below never count toward the credential-guessing buckets.
    await rate_limiter.release_success(client_ip, current_user.email)
    validate_password_length(payload.new_password, settings)
    if payload.new_password == payload.current_password:
        raise AppError(
            "PASSWORD_REUSE",
            "New password must be different from the current password",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    current_user.session_version += 1
    await create_audit_event(
        session,
        actor_user_id=current_user.id,
        action="auth.password.changed",
        entity_type="user",
        entity_id=str(current_user.id),
    )
    await session.commit()
    return login_response(current_user, settings)


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Refresh an active session",
)
async def refresh_session(
    current_user: CurrentUserDependency,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: SettingsDependency,
) -> LoginResponse:
    claims = decode_token_claims(token, settings)
    auth_time_value = claims.get("auth_time")
    if not isinstance(auth_time_value, (int, float)):
        raise AppError(
            "REFRESH_NOT_ALLOWED",
            "This session cannot be refreshed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    auth_time = datetime.fromtimestamp(auth_time_value, UTC)
    now = datetime.now(UTC)
    cap_at = auth_time + timedelta(minutes=settings.session_absolute_lifetime_minutes)
    expires_at = min(
        now + timedelta(minutes=settings.access_token_expire_minutes),
        cap_at,
    )
    if expires_at <= now:
        raise AppError(
            "SESSION_EXPIRED",
            "Session has reached its maximum lifetime",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return login_response(current_user, settings, auth_time=auth_time, expires_at=expires_at)
