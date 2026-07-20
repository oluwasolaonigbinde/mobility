from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from jwt import InvalidTokenError

from app.core.config import Settings

_password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


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


def decode_token_claims(token: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (InvalidTokenError, ValueError):
        raise ValueError("Invalid token") from None
