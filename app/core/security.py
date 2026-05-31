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


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    expires_in = settings.access_token_expire_minutes * 60
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise ValueError
        return UUID(subject)
    except (InvalidTokenError, ValueError):
        raise ValueError("Invalid token") from None
