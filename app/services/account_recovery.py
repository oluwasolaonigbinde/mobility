import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.contact import PasswordResetAttempt, PasswordResetToken
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event
from app.services.payout_rule_serialization import database_clock
from app.services.users import get_user_by_email, normalize_email, validate_password_length

PASSWORD_RESET_RESPONSE = "If the account can be recovered, reset instructions will be sent."
RECOVERY_ELIGIBLE_ROLES = frozenset({UserRole.ADVERTISER.value, UserRole.ADMIN.value})
RECOVERY_ELIGIBLE_STATUSES = frozenset({UserStatus.ACTIVE.value, UserStatus.INVITED.value})


def _digest(value: str, settings: Settings, *, purpose: str) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"{purpose}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _rate_lock_key(digest: str) -> int:
    return int.from_bytes(bytes.fromhex(digest)[:8], byteorder="big", signed=True)


async def _acquire_rate_limit_locks(
    session: AsyncSession, *, email_digest: str, ip_digest: str
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    for lock_key in sorted({_rate_lock_key(email_digest), _rate_lock_key(ip_digest)}):
        await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


def _reset_token_value(row: PasswordResetToken, user: User, settings: Settings) -> str:
    expires = int(_utc(row.expires_at).timestamp())
    payload = f"{row.id}:{user.id}:{row.session_version}:{expires}"
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
        f"password-reset:v1:{payload}".encode(),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{row.id}.{encoded}"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def password_reset_token_for_delivery(
    row: PasswordResetToken, user: User, settings: Settings
) -> str:
    token = _reset_token_value(row, user, settings)
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row.token_hash):
        raise RuntimeError("password reset token evidence mismatch")
    return token


def synthetic_password_reset_token(
    row: PasswordResetToken,
    user: User,
    settings: Settings,
    *,
    synthetic_test_authority: bool,
) -> str:
    if not synthetic_test_authority or settings.environment not in {"test", "testing"}:
        raise RuntimeError("synthetic password reset token authority is test-only")
    return password_reset_token_for_delivery(row, user, settings)


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
    client_ip: str,
    settings: Settings,
) -> PasswordResetToken | None:
    normalized_email = normalize_email(email)
    email_digest = _digest(normalized_email, settings, purpose="reset-email")
    ip_digest = _digest(client_ip, settings, purpose="reset-ip")
    await _acquire_rate_limit_locks(session, email_digest=email_digest, ip_digest=ip_digest)
    now = await database_clock(session)
    window_start = now - timedelta(seconds=settings.password_reset_rate_window_seconds)
    account_attempts = int(
        await session.scalar(
            select(func.count())
            .select_from(PasswordResetAttempt)
            .where(
                PasswordResetAttempt.email_digest == email_digest,
                PasswordResetAttempt.requested_at >= window_start,
            )
        )
        or 0
    )
    ip_attempts = int(
        await session.scalar(
            select(func.count())
            .select_from(PasswordResetAttempt)
            .where(
                PasswordResetAttempt.ip_digest == ip_digest,
                PasswordResetAttempt.requested_at >= window_start,
            )
        )
        or 0
    )
    if (
        account_attempts >= settings.password_reset_account_max_attempts
        or ip_attempts >= settings.password_reset_ip_max_attempts
    ):
        raise AppError(
            "PASSWORD_RESET_RATE_LIMITED",
            "Too many password reset requests",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    user = await get_user_by_email(session, normalized_email)
    eligible = (
        user is not None
        and user.role in RECOVERY_ELIGIBLE_ROLES
        and user.status in RECOVERY_ELIGIBLE_STATUSES
    )
    attempt = PasswordResetAttempt(
        email_digest=email_digest,
        ip_digest=ip_digest,
        issued_user_id=user.id if eligible else None,
        requested_at=now,
    )
    session.add(attempt)
    await session.flush()
    reset = None
    if eligible and user is not None:
        reset_id = uuid4()
        reset = PasswordResetToken(
            id=reset_id,
            attempt_id=attempt.id,
            user_id=user.id,
            token_hash="0" * 64,
            session_version=user.session_version,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.password_reset_ttl_seconds),
        )
        token = _reset_token_value(reset, user, settings)
        reset.token_hash = hashlib.sha256(token.encode()).hexdigest()
        session.add(reset)
        await session.flush()
        from app.services.notifications import create_password_reset_notification

        await create_password_reset_notification(session, user=user, reset=reset)
    await create_audit_event(
        session,
        actor_user_id=user.id if eligible and user is not None else None,
        action="auth.password_reset.requested",
        entity_type="password_reset_attempt",
        entity_id=str(attempt.id),
        metadata={
            "reset_issued": bool(reset),
            "rate_window_seconds": settings.password_reset_rate_window_seconds,
        },
    )
    return reset


def _token_id(token: str) -> UUID | None:
    try:
        raw_id, signature = token.split(".", 1)
        if not signature:
            return None
        return UUID(raw_id)
    except (ValueError, AttributeError):
        return None


async def complete_password_reset(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
    settings: Settings,
) -> User:
    validate_password_length(new_password, settings)
    reset_id = _token_id(token)
    reset = (
        await session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.id == reset_id).with_for_update()
        )
        if reset_id is not None
        else None
    )
    if reset is None:
        raise AppError(
            "PASSWORD_RESET_INVALID",
            "Password reset token is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    user = await session.scalar(
        select(User)
        .where(User.id == reset.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = await database_clock(session)
    supplied_hash = hashlib.sha256(token.encode()).hexdigest()
    if (
        user is None
        or reset.used_at is not None
        or now >= _utc(reset.expires_at)
        or reset.session_version != user.session_version
        or not hmac.compare_digest(supplied_hash, reset.token_hash)
        or user.role not in RECOVERY_ELIGIBLE_ROLES
        # Eligibility is re-read live under this lock, never trusted from
        # issuance: a bearer minted before suspension must not survive it. The
        # token is deliberately left unconsumed, so a later reactivation still
        # requires a fresh request rather than silently burning the old one.
        or user.status not in RECOVERY_ELIGIBLE_STATUSES
    ):
        raise AppError(
            "PASSWORD_RESET_INVALID",
            "Password reset token is invalid or expired",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    reset.used_at = now
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.session_version += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="auth.password_reset.completed",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"sessions_revoked": True},
    )
    return user
