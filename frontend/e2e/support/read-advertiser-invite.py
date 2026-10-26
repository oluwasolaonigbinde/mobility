"""Read one synthetic issued invite inside the isolated E2E process; never send email."""

import asyncio
import json
import re
import runpy
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import get_settings
from app.models.contact import PasswordResetToken
from app.models.user import User
from app.services.account_recovery import _reset_token_value


async def main() -> None:
    guard = runpy.run_path(str(Path(__file__).with_name("prepare-account-setup-application.py")))
    settings = guard["validate_isolated_e2e_settings"](get_settings())
    email = sys.argv[1] if len(sys.argv) == 2 else ""
    if not re.fullmatch(r"f7e2e-advertiser-\d+@example\.com", email):
        raise RuntimeError("Invite fixture requires a synthetic E2E email")
    assert settings.database_url is not None
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None or user.status != "invited" or user.role != "advertiser":
                raise RuntimeError("Expected one pending synthetic advertiser")
            reset = await session.scalar(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.purpose == "advertiser_invite",
                    PasswordResetToken.used_at.is_(None),
                )
            )
            if reset is None:
                raise RuntimeError("Synthetic advertiser has no issued invite")
            # stdout is captured privately by execFileSync, never forwarded to a test report.
            print(json.dumps({"token": _reset_token_value(reset, user, settings)}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
