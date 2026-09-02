"""Authentication commands.

These commands, not the HTTP router, own who may sign in, whose credential may
change, and how a bearer is minted or refreshed (GOV-007). A direct caller gets the
same decision, the same stable error and the same audit evidence as a request; the
router only maps them onto a transaction and an envelope.

Every credential transition runs against a `SELECT ... FOR UPDATE` row that is
re-read with `populate_existing`, because an already-loaded ORM user would
otherwise be reconciled from the identity map and the command would decide on
stale state (AUT-001). Only `users` rows are locked here; password reset takes
`password_reset_tokens` before `users`, and no path takes them in the other order.

The lock spans the argon2 work, so concurrent attempts against one account are
serialised for the duration of a verification. That is per-account only and is
already bounded by the login rate limiter; it is the price of deciding status and
session version against the same row the transition writes.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    ValidatedAccessTokenClaims,
    create_access_token,
    decode_token_claims,
    hash_password,
    verify_password,
)
from app.models.user import User, UserStatus
from app.services.audit import create_audit_event
from app.services.users import normalize_email, validate_password_length

CONTAINED_USER_STATUSES = frozenset({UserStatus.SUSPENDED.value, UserStatus.DISABLED.value})


class AuthCommandError(Exception):
    """A business failure of an authentication command.

    ``audited`` marks a failure whose audit event is already written in the
    caller's transaction. The caller must commit before surfacing ``error``, or
    the evidence of the failure rolls back with it.
    """

    def __init__(self, error: AppError, *, audited: bool = False) -> None:
        super().__init__(error.message)
        self.error = error
        self.audited = audited


@dataclass(frozen=True)
class IssuedSession:
    """A minted bearer and the user it authenticates."""

    user: User
    access_token: str
    expires_in: int


def issue_session(
    user: User,
    settings: Settings,
    *,
    auth_time: datetime | None = None,
    expires_at: datetime | None = None,
) -> IssuedSession:
    """Mint the bearer for an already-decided session.

    Issuance is a command so that every caller — login, credential change and
    refresh alike — stamps `sv` from the same user row the decision was made on.
    """
    token, expires_in = create_access_token(
        user.id,
        settings,
        session_version=user.session_version,
        auth_time=auth_time,
        expires_at=expires_at,
    )
    return IssuedSession(user=user, access_token=token, expires_in=expires_in)


async def refresh_user_session(
    session: AsyncSession,
    *,
    user: User,
    token: str,
    settings: Settings,
) -> IssuedSession:
    """Re-issue a bearer without extending the session's absolute lifetime.

    The presented token is decoded again here, under the same strict claim
    contract the authenticating dependency applied, so a session whose expiry is
    crossed between the two decodes fails with the stable invalid-token envelope
    rather than being refreshed. `auth_time` is carried forward from the original
    sign-in and the new expiry is clamped to the cap measured from it, so
    refreshing can shorten a session but never lengthen it.

    The user row is locked and re-read before a bearer is minted. This closes the
    gap between the route dependency's authentication read and this command: a
    concurrent logout either waits for this refresh and then invalidates its new
    bearer, or commits first and makes this refresh fail as revoked.
    """
    claims, locked_user = await _lock_authenticated_session(
        session,
        user=user,
        token=token,
        settings=settings,
    )
    auth_time = datetime.fromtimestamp(claims.authenticated_at, UTC)
    now = datetime.now(UTC)
    cap_at = auth_time + timedelta(minutes=settings.session_absolute_lifetime_minutes)
    expires_at = min(now + timedelta(minutes=settings.access_token_expire_minutes), cap_at)
    if expires_at <= now:
        raise AuthCommandError(
            AppError(
                "SESSION_EXPIRED",
                "Session has reached its maximum lifetime",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        )
    await create_audit_event(
        session,
        actor_user_id=locked_user.id,
        action="auth.session.refreshed",
        entity_type="user",
        entity_id=str(locked_user.id),
    )
    return issue_session(
        locked_user,
        settings,
        auth_time=auth_time,
        expires_at=expires_at,
    )


@lru_cache(maxsize=1)
def _timing_equalizer_hash() -> str:
    return hash_password("cardvert-timing-equalizer-not-a-real-password")


def warm_password_timing_equalizer() -> None:
    """Pay the dummy-hash setup cost before a production request can observe it."""
    _timing_equalizer_hash()


def _locked(statement):
    return statement.with_for_update().execution_options(populate_existing=True)


async def _lock_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(_locked(select(User).where(User.email == normalize_email(email))))


async def _lock_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.scalar(_locked(select(User).where(User.id == user_id)))


def _invalid_token() -> AuthCommandError:
    return AuthCommandError(
        AppError(
            "INVALID_TOKEN",
            "Invalid authentication token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    )


async def _lock_authenticated_session(
    session: AsyncSession,
    *,
    user: User,
    token: str,
    settings: Settings,
) -> tuple[ValidatedAccessTokenClaims, User]:
    """Lock the bearer subject and re-prove its live session authority."""
    try:
        initial_claims = decode_token_claims(token, settings)
    except ValueError as exc:
        raise _invalid_token() from exc
    if initial_claims.subject != user.id:
        raise _invalid_token()

    locked_user = await _lock_user_by_id(session, initial_claims.subject)
    if locked_user is None:
        raise _invalid_token()

    try:
        claims = decode_token_claims(token, settings)
    except ValueError as exc:
        raise _invalid_token() from exc
    if claims.subject != locked_user.id:
        raise _invalid_token()
    if locked_user.status in CONTAINED_USER_STATUSES:
        raise AuthCommandError(
            AppError(
                "USER_NOT_ACTIVE",
                "User account is not active",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        )
    if claims.session_version != locked_user.session_version:
        raise AuthCommandError(
            AppError(
                "SESSION_REVOKED",
                "Session is no longer valid",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        )
    return claims, locked_user


async def revoke_user_sessions(
    session: AsyncSession,
    *,
    user: User,
    token: str,
    settings: Settings,
) -> None:
    """Revoke every bearer issued under the user's current session version."""
    _, locked_user = await _lock_authenticated_session(
        session,
        user=user,
        token=token,
        settings=settings,
    )
    locked_user.session_version += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=locked_user.id,
        action="auth.session.revoked",
        entity_type="user",
        entity_id=str(locked_user.id),
        metadata={"scope": "all_devices"},
    )


async def login_with_password(session: AsyncSession, *, email: str, password: str) -> User:
    """Admit a sign-in against the locked live user row.

    Credentials are proven before status is consulted, so a wrong password on a
    contained account is indistinguishable from a wrong password on an unknown
    one and suspension stays undisclosed.
    """
    user = await _lock_user_by_email(session, email)
    if user is None:
        verify_password(password, _timing_equalizer_hash())
        raise await _login_rejected(session, email=email)
    if not verify_password(password, user.password_hash):
        raise await _login_rejected(session, email=email)
    if user.status in CONTAINED_USER_STATUSES:
        await create_audit_event(
            session,
            actor_user_id=user.id,
            action="auth.login.failed",
            entity_type="authentication",
            entity_id=str(user.id),
            metadata={"email": user.email, "reason": "not_active"},
        )
        raise AuthCommandError(
            AppError(
                "USER_NOT_ACTIVE",
                "User account is not active",
                status_code=status.HTTP_403_FORBIDDEN,
            ),
            audited=True,
        )
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="auth.login.succeeded",
        entity_type="authentication",
        entity_id=str(user.id),
        metadata={"email": user.email},
    )
    return user


async def _login_rejected(session: AsyncSession, *, email: str) -> AuthCommandError:
    await create_audit_event(
        session,
        actor_user_id=None,
        action="auth.login.failed",
        entity_type="authentication",
        entity_id=None,
        metadata={"email": email.lower(), "reason": "invalid_credentials"},
    )
    return AuthCommandError(
        AppError(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ),
        audited=True,
    )


async def change_user_password(
    session: AsyncSession,
    *,
    user_id: UUID,
    expected_session_version: int,
    current_password: str,
    new_password: str,
    settings: Settings,
    client_ip: str | None = None,
) -> User:
    """Replace a credential inside one locked transition.

    The lock is taken first, then the session version is snapshotted, then status
    is re-checked, and only then is the current password verified against the
    locked hash. A caller whose ``expected_session_version`` no longer matches the
    locked row lost a race to another credential transition and is refused rather
    than allowed to overwrite it.
    """
    user = await _lock_user_by_id(session, user_id)
    if user is None:
        raise AuthCommandError(
            AppError("USER_NOT_FOUND", "User not found", status_code=status.HTTP_404_NOT_FOUND)
        )
    session_version = user.session_version
    if session_version != expected_session_version:
        raise AuthCommandError(
            AppError(
                "SESSION_REVOKED",
                "Session is no longer valid",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        )
    if user.status in CONTAINED_USER_STATUSES:
        raise AuthCommandError(
            AppError(
                "USER_NOT_ACTIVE",
                "User account is not active",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        )
    if not verify_password(current_password, user.password_hash):
        await create_audit_event(
            session,
            actor_user_id=user.id,
            action="auth.password.change_failed",
            entity_type="user",
            entity_id=str(user.id),
            metadata={"reason": "current_password_incorrect", "ip": client_ip},
        )
        raise AuthCommandError(
            AppError(
                "CURRENT_PASSWORD_INCORRECT",
                "Current password is incorrect",
                status_code=status.HTTP_400_BAD_REQUEST,
            ),
            audited=True,
        )
    try:
        validate_password_length(new_password, settings)
    except AppError as exc:
        raise AuthCommandError(exc) from exc
    if new_password == current_password:
        raise AuthCommandError(
            AppError(
                "PASSWORD_REUSE",
                "New password must be different from the current password",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.session_version = session_version + 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="auth.password.changed",
        entity_type="user",
        entity_id=str(user.id),
    )
    return user
