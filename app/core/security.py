from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from jwt import InvalidTokenError

from app.core.config import Settings

_password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


@dataclass(frozen=True, slots=True)
class ValidatedAccessTokenClaims:
    subject: UUID
    expires_at: int
    issued_at: int
    authenticated_at: int
    session_version: int


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except Argon2Error:
        return False


def create_access_token(
    user_id: UUID,
    settings: Settings,
    *,
    session_version: int,
    auth_time: datetime | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, int]:
    now = datetime.now(UTC)
    auth_time = auth_time or now
    expires_at = expires_at or now + timedelta(minutes=settings.access_token_expire_minutes)
    expires_in = max(0, int((expires_at - now).total_seconds()))
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "auth_time": int(auth_time.timestamp()),
            "sv": session_version,
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def _integer_claim(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if type(value) is not int:
        raise ValueError
    return value


def _epoch_claim(payload: dict[str, object], name: str) -> int:
    value = _integer_claim(payload, name)
    try:
        datetime.fromtimestamp(value, UTC)
    except (OSError, OverflowError, ValueError):
        raise ValueError from None
    return value


def _validated_claims(payload: dict[str, object]) -> ValidatedAccessTokenClaims:
    subject_value = payload.get("sub")
    if type(subject_value) is not str:
        raise ValueError
    try:
        subject = UUID(subject_value)
    except ValueError:
        raise ValueError from None
    if str(subject) != subject_value:
        raise ValueError

    expires_at = _epoch_claim(payload, "exp")
    issued_at = _epoch_claim(payload, "iat")
    authenticated_at = _epoch_claim(payload, "auth_time")
    session_version = _integer_claim(payload, "sv")
    now = datetime.now(UTC).timestamp()
    if (
        session_version < 1
        or expires_at <= now
        or issued_at > now
        or authenticated_at > issued_at
        or issued_at >= expires_at
    ):
        raise ValueError

    return ValidatedAccessTokenClaims(
        subject=subject,
        expires_at=expires_at,
        issued_at=issued_at,
        authenticated_at=authenticated_at,
        session_version=session_version,
    )


def decode_token_claims(token: str, settings: Settings) -> ValidatedAccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False, "verify_iat": False},
        )
    except (InvalidTokenError, TypeError):
        raise ValueError("Invalid token") from None
    if not isinstance(payload, dict):
        raise ValueError("Invalid token")
    try:
        return _validated_claims(payload)
    except ValueError:
        raise ValueError("Invalid token") from None
