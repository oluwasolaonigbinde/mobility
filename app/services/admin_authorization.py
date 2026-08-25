"""Transactional service-boundary authorization for administrative writes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.user import User, UserRole, UserStatus


async def require_active_admin(session: AsyncSession, actor_user_id: UUID) -> None:
    """Require and lock an active admin before reading or mutating a domain row.

    The row lock keeps the authorization decision in the caller's transaction;
    a concurrent disable cannot slip between this check and the protected
    operation on PostgreSQL.
    """
    admin_id = await session.scalar(
        select(User.id)
        .where(
            User.id == actor_user_id,
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
        )
        .with_for_update()
    )
    if admin_id is None:
        raise AppError(
            "FORBIDDEN_ROLE",
            "Admin role is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
