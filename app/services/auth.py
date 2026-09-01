from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services.users import get_user_by_email


@lru_cache(maxsize=1)
def _timing_equalizer_hash() -> str:
    return hash_password("cardvert-timing-equalizer-not-a-real-password")


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None:
        verify_password(password, _timing_equalizer_hash())
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
