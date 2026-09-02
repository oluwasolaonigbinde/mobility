import asyncio

import pytest
from conftest import create_test_user
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditEvent
from app.models.user import User
from app.services.auth import (
    AuthCommandError,
    refresh_user_session,
    revoke_user_sessions,
)

PASSWORD = "long-secure-password"


def _user_state(sessionmaker, user_id) -> tuple[int, list[str]]:
    async def read() -> tuple[int, list[str]]:
        async with sessionmaker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            actions = list(
                (
                    await session.execute(
                        select(AuditEvent.action).where(AuditEvent.actor_user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
            return user.session_version, actions

    return asyncio.run(read())


def test_logout_revokes_copied_bearers_and_refresh_globally(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    user = create_test_user(
        postgis_db_sessionmaker,
        email="r11-global-logout@example.com",
        password=PASSWORD,
    )
    login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    copied_headers = {"Authorization": f"Bearer {token}"}

    logout = postgis_db_client.post("/api/v1/auth/logout", headers=copied_headers)

    assert logout.status_code == 204
    version, actions = _user_state(postgis_db_sessionmaker, user.id)
    assert version == user.session_version + 1
    assert actions.count("auth.session.revoked") == 1

    copied = postgis_db_client.get("/api/v1/me", headers=copied_headers)
    assert copied.status_code == 401
    assert copied.json()["error"]["code"] == "SESSION_REVOKED"
    refreshed = postgis_db_client.post("/api/v1/auth/refresh", headers=copied_headers)
    assert refreshed.status_code == 401
    assert refreshed.json()["error"]["code"] == "SESSION_REVOKED"

    duplicate = postgis_db_client.post("/api/v1/auth/logout", headers=copied_headers)
    assert duplicate.status_code == 401
    duplicate_version, duplicate_actions = _user_state(postgis_db_sessionmaker, user.id)
    assert duplicate_version == version
    assert duplicate_actions.count("auth.session.revoked") == 1


def test_forced_password_session_can_logout(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    user = create_test_user(
        postgis_db_sessionmaker,
        email="r11-forced-password@example.com",
        password=PASSWORD,
    )

    async def require_change() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            loaded.must_change_password = True
            await session.commit()

    asyncio.run(require_change())
    login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    token = login.json()["access_token"]

    logout = postgis_db_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert logout.status_code == 204


@pytest.mark.parametrize("first", ["refresh", "logout"])
def test_logout_and_inflight_refresh_are_serialized_in_both_orders(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
    first: str,
) -> None:
    user = create_test_user(
        postgis_db_sessionmaker,
        email=f"r11-{first}-first@example.com",
        password=PASSWORD,
    )
    presented, _ = create_access_token(
        user.id,
        settings,
        session_version=user.session_version,
    )

    async def refresh() -> tuple[str, str | None]:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            try:
                issued = await refresh_user_session(
                    session,
                    user=loaded,
                    token=presented,
                    settings=settings,
                )
            except AuthCommandError as exc:
                await session.rollback()
                return exc.error.code, None
            await session.commit()
            return "refreshed", issued.access_token

    async def logout() -> str:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            try:
                await revoke_user_sessions(
                    session,
                    user=loaded,
                    token=presented,
                    settings=settings,
                )
            except AuthCommandError as exc:
                await session.rollback()
                return exc.error.code
            await session.commit()
            return "logged_out"

    async def scenario() -> tuple[tuple[str, str | None], str]:
        if first == "refresh":
            async with postgis_db_sessionmaker() as first_session:
                loaded = await first_session.get(User, user.id)
                assert loaded is not None
                issued = await refresh_user_session(
                    first_session,
                    user=loaded,
                    token=presented,
                    settings=settings,
                )
                waiting_logout = asyncio.create_task(logout())
                await asyncio.sleep(0.05)
                assert not waiting_logout.done()
                await first_session.commit()
            return ("refreshed", issued.access_token), await waiting_logout

        async with postgis_db_sessionmaker() as first_session:
            loaded = await first_session.get(User, user.id)
            assert loaded is not None
            await revoke_user_sessions(
                first_session,
                user=loaded,
                token=presented,
                settings=settings,
            )
            waiting_refresh = asyncio.create_task(refresh())
            await asyncio.sleep(0.05)
            assert not waiting_refresh.done()
            await first_session.commit()
        return await waiting_refresh, "logged_out"

    refresh_outcome, logout_outcome = asyncio.run(scenario())
    assert logout_outcome == "logged_out"
    version, actions = _user_state(postgis_db_sessionmaker, user.id)
    assert version == user.session_version + 1
    assert actions.count("auth.session.revoked") == 1

    if first == "logout":
        assert refresh_outcome == ("SESSION_REVOKED", None)
        assert "auth.session.refreshed" not in actions
    else:
        assert refresh_outcome[0] == "refreshed"
        assert actions.count("auth.session.refreshed") == 1
        late_headers = {"Authorization": f"Bearer {refresh_outcome[1]}"}
        late = postgis_db_client.get("/api/v1/me", headers=late_headers)
        assert late.status_code == 401
        assert late.json()["error"]["code"] == "SESSION_REVOKED"
