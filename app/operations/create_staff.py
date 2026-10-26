"""Create the first (or another) Terrax staff account from the server shell.

    python -m app.operations.create_staff --email ops@terrax.example --name "Ada Obi"

The account is an active admin with a one-time temporary password, printed once.
Cardvert asks for a new password at the first sign-in, the same as staff-created users.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import hash_password_async
from app.db.session import get_engine
from app.models.user import User, UserRole, UserStatus
from app.schemas.users import UserCreate
from app.services.audit import create_audit_event
from app.services.users import get_user_by_email, normalize_email, validate_password_length


class StaffAccountRefused(Exception):
    pass


async def create_staff_account(
    session: AsyncSession, *, email: str, full_name: str, settings: Settings
) -> str:
    """Create an active admin and return its temporary password; refuse a used email."""
    password = secrets.token_urlsafe(max(18, settings.password_min_length))
    validate_password_length(password, settings)
    try:
        payload = UserCreate(
            email=normalize_email(email),
            password=password,
            full_name=full_name.strip(),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
    except ValidationError as exc:
        raise StaffAccountRefused("Give a valid email and name.") from exc
    if "@" not in payload.email or await get_user_by_email(session, payload.email):
        raise StaffAccountRefused("That email is not valid or already has a Cardvert account.")
    user = User(
        email=payload.email,
        password_hash=await hash_password_async(password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        must_change_password=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise StaffAccountRefused("That email already has a Cardvert account.") from exc
    await create_audit_event(
        session,
        actor_user_id=None,
        action="admin.user.created",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"email": user.email, "role": user.role, "status": user.status, "source": "cli"},
    )
    await session.commit()
    return password


def main(
    argv: list[str] | None = None,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    settings: Settings | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Create an active Terrax staff (admin) account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    owns_engine = sessionmaker is None
    sessionmaker = sessionmaker or async_sessionmaker(get_engine(settings), expire_on_commit=False)

    async def run() -> str:
        try:
            async with sessionmaker() as session:
                return await create_staff_account(
                    session, email=args.email, full_name=args.name, settings=settings
                )
        finally:
            if owns_engine:
                await get_engine(settings).dispose()

    try:
        password = asyncio.run(run())
    except StaffAccountRefused as exc:
        print(f"Not created: {exc}", file=sys.stderr)
        return 1
    print(f"Created staff account {normalize_email(args.email)}.")
    print(f"Temporary password (shown once): {password}")
    print("They must choose a new password when they first sign in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
