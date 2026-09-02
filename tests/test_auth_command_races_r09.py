"""R09 (GOV-007, AUT-001, AUT-002) auth command authority and containment races.

Every test here runs against real PostgreSQL because the guarantees under test are
row-lock guarantees: `SELECT ... FOR UPDATE` is a no-op on SQLite, so a SQLite run
would pass while the production database still lost the update.

Lock order is fixed for the whole authentication surface and every test below
depends on it: password reset takes `password_reset_tokens` then `users`; login,
change-password and admin status updates take `users` only. No path takes them in
the opposite order, so no pair of these commands can deadlock.
"""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import create_test_organization, create_test_user
from sqlalchemy import select

from app.core.errors import AppError
from app.core.rate_limit import NoopLoginRateLimiter
from app.core.security import create_access_token, verify_password
from app.models.audit import AuditEvent
from app.models.contact import PasswordResetToken
from app.models.user import User, UserRole, UserStatus
from app.services.account_recovery import (
    complete_password_reset,
    request_password_reset,
    synthetic_password_reset_token,
)
from app.services.auth import (
    AuthCommandError,
    change_user_password,
    issue_session,
    login_with_password,
    refresh_user_session,
)

PASSWORD = "long-secure-password"
RESET_PASSWORD = "victim-recovered-password-1"
ATTACKER_PASSWORD = "attacker-chosen-password-1"
NOOP_LOGIN_LIMITER = NoopLoginRateLimiter()


def _issue_reset(sessionmaker, settings, user_id) -> str:
    """Issue a real reset token for `user_id` and return the delivered bearer."""

    async def issue() -> str:
        async with sessionmaker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            reset = await request_password_reset(
                session,
                email=user.email,
                client_ip="203.0.113.10",
                settings=settings,
            )
            assert reset is not None
            await session.commit()
            return synthetic_password_reset_token(
                reset,
                user,
                settings,
                synthetic_test_authority=True,
            )

    return asyncio.run(issue())


def _user_state(sessionmaker, user_id) -> tuple[int, str, str]:
    async def read() -> tuple[int, str, str]:
        async with sessionmaker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            return user.session_version, user.password_hash, user.status

    return asyncio.run(read())


def _recoverable_user(sessionmaker):
    user = create_test_user(
        sessionmaker,
        email="r09-advertiser@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(sessionmaker, owner_user_id=user.id)
    return user


# --- GOV-007: the commands are the authority, not the router --------------------


def test_login_command_outside_http_matches_route_decisions_and_audit(
    postgis_db_sessionmaker, settings
) -> None:
    user = _recoverable_user(postgis_db_sessionmaker)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            authenticated = await login_with_password(
                session, email=user.email.upper(), password=PASSWORD
            )
            assert authenticated.id == user.id
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as wrong:
                await login_with_password(session, email=user.email, password="wrong-password")
            assert wrong.value.error.code == "INVALID_CREDENTIALS"
            assert wrong.value.error.status_code == 401
            assert wrong.value.audited is True
            # The router commits audited failures; a direct caller must too.
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as unknown:
                await login_with_password(
                    session, email="nobody-r09@example.com", password=PASSWORD
                )
            assert unknown.value.error.code == "INVALID_CREDENTIALS"
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            actions = list(
                (await session.execute(select(AuditEvent.action).order_by(AuditEvent.created_at)))
                .scalars()
                .all()
            )
            assert actions.count("auth.login.succeeded") == 1
            assert actions.count("auth.login.failed") == 2

    asyncio.run(scenario())


def test_login_command_verifies_credentials_before_revealing_status(
    postgis_db_sessionmaker, settings
) -> None:
    """A wrong password on a suspended account must not disclose the suspension."""
    user = create_test_user(
        postgis_db_sessionmaker,
        email="r09-suspended@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
        user_status=UserStatus.SUSPENDED,
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as wrong:
                await login_with_password(session, email=user.email, password="wrong-password")
            assert wrong.value.error.code == "INVALID_CREDENTIALS"
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as contained:
                await login_with_password(session, email=user.email, password=PASSWORD)
            assert contained.value.error.code == "USER_NOT_ACTIVE"
            assert contained.value.error.status_code == 403
            await session.commit()

    asyncio.run(scenario())


def test_change_password_command_outside_http_rotates_and_audits(
    postgis_db_sessionmaker, settings
) -> None:
    user = _recoverable_user(postgis_db_sessionmaker)
    before_version, before_hash, _ = _user_state(postgis_db_sessionmaker, user.id)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as wrong:
                await change_user_password(
                    session,
                    user_id=user.id,
                    expected_session_version=before_version,
                    current_password="not-the-password",
                    new_password=ATTACKER_PASSWORD,
                    settings=settings,
                )
            assert wrong.value.error.code == "CURRENT_PASSWORD_INCORRECT"
            assert wrong.value.audited is True
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            changed = await change_user_password(
                session,
                user_id=user.id,
                expected_session_version=before_version,
                current_password=PASSWORD,
                new_password=ATTACKER_PASSWORD,
                settings=settings,
            )
            assert changed.session_version == before_version + 1
            await session.commit()

    asyncio.run(scenario())

    version, password_hash, _ = _user_state(postgis_db_sessionmaker, user.id)
    assert version == before_version + 1
    assert password_hash != before_hash
    assert verify_password(ATTACKER_PASSWORD, password_hash)


def test_change_password_command_rejects_a_stale_session_version(
    postgis_db_sessionmaker, settings
) -> None:
    user = _recoverable_user(postgis_db_sessionmaker)
    before_version, before_hash, _ = _user_state(postgis_db_sessionmaker, user.id)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AuthCommandError) as stale:
                await change_user_password(
                    session,
                    user_id=user.id,
                    expected_session_version=before_version - 1,
                    current_password=PASSWORD,
                    new_password=ATTACKER_PASSWORD,
                    settings=settings,
                )
            assert stale.value.error.code == "SESSION_REVOKED"
            assert stale.value.error.status_code == 401
            await session.rollback()

    asyncio.run(scenario())
    assert _user_state(postgis_db_sessionmaker, user.id) == (
        before_version,
        before_hash,
        UserStatus.ACTIVE.value,
    )


# --- AUT-001: change-password must not overwrite a completed recovery -----------


def test_change_password_refuses_a_user_loaded_before_the_recovery_committed(
    postgis_db_sessionmaker, settings
) -> None:
    """The stale-object case: recovery commits after the request read the user.

    A request loads its user through the authentication dependency, and only
    afterwards does the credential command take the row lock. If the recovery
    commits inside that gap, the locking read returns a row the session already
    has in its identity map — so without `populate_existing` the command would
    decide on the pre-recovery session version and password hash, pass its own
    fence, and overwrite the recovered credential. This is the interleaving the
    lock alone cannot close.
    """
    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            # What get_current_user does: load the user into this session.
            loaded = await session.get(User, user.id)
            assert loaded is not None
            expected_version = loaded.session_version

            # The victim's recovery commits in another transaction, in the gap
            # between that read and the credential command's lock.
            assert await _complete_reset(postgis_db_sessionmaker, token, settings) == "reset"

            with pytest.raises(AuthCommandError) as lost:
                await change_user_password(
                    session,
                    user_id=user.id,
                    expected_session_version=expected_version,
                    current_password=PASSWORD,
                    new_password=ATTACKER_PASSWORD,
                    settings=settings,
                )
            assert lost.value.error.code == "SESSION_REVOKED"
            await session.rollback()

    asyncio.run(scenario())

    _, password_hash, _ = _user_state(postgis_db_sessionmaker, user.id)
    assert verify_password(RESET_PASSWORD, password_hash)
    assert not verify_password(ATTACKER_PASSWORD, password_hash)


@pytest.mark.parametrize("reset_first", [True, False])
def test_change_password_and_reset_completion_never_both_win(
    postgis_db_sessionmaker, settings, reset_first: bool
) -> None:
    """Both orders: exactly one credential transition may commit."""
    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)
    start_version, _, _ = _user_state(postgis_db_sessionmaker, user.id)

    async def run_reset() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await complete_password_reset(
                    session,
                    token=token,
                    new_password=RESET_PASSWORD,
                    settings=settings,
                )
                await session.commit()
                return "reset"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def run_change() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await change_user_password(
                    session,
                    user_id=user.id,
                    expected_session_version=start_version,
                    current_password=PASSWORD,
                    new_password=ATTACKER_PASSWORD,
                    settings=settings,
                )
                await session.commit()
                return "change"
            except AuthCommandError as exc:
                await session.rollback()
                return exc.error.code

    async def scenario() -> None:
        first, second = (run_reset, run_change) if reset_first else (run_change, run_reset)
        outcomes = await asyncio.wait_for(asyncio.gather(first(), second()), timeout=30)
        winners = [outcome for outcome in outcomes if outcome in {"reset", "change"}]
        assert len(winners) == 1, f"two credential transitions committed: {outcomes}"
        losers = [outcome for outcome in outcomes if outcome not in {"reset", "change"}]
        assert losers[0] in {"SESSION_REVOKED", "PASSWORD_RESET_INVALID"}, outcomes

        async with postgis_db_sessionmaker() as session:
            final = await session.get(User, user.id)
            assert final is not None
            version, password_hash = final.session_version, final.password_hash
        assert version == start_version + 1
        expected = RESET_PASSWORD if winners[0] == "reset" else ATTACKER_PASSWORD
        assert verify_password(expected, password_hash)
        assert not verify_password(PASSWORD, password_hash)

    asyncio.run(scenario())


def test_http_change_password_cannot_overwrite_a_completed_reset(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    """End-to-end AUT-001: the real route racing a real recovery over real HTTP."""
    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)
    login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    start_version, _, _ = _user_state(postgis_db_sessionmaker, user.id)

    outcome: dict[str, object] = {}

    def call_change() -> None:
        response = postgis_db_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": ATTACKER_PASSWORD},
            headers=headers,
        )
        outcome["status"] = response.status_code
        outcome["body"] = response.json()

    # Land the recovery inside the change request's argon2 work rather than
    # guessing a fixed delay; the assertions below hold for every interleaving.
    probe = time.monotonic()
    verify_password(PASSWORD, user.password_hash)
    argon2_seconds = time.monotonic() - probe

    changer = threading.Thread(target=call_change)
    changer.start()
    time.sleep(max(argon2_seconds * 0.5, 0.005))
    reset_outcome = asyncio.run(_complete_reset(postgis_db_sessionmaker, token, settings))
    changer.join(timeout=30)
    assert not changer.is_alive()

    version, password_hash, _ = _user_state(postgis_db_sessionmaker, user.id)
    assert version == start_version + 1
    if reset_outcome == "reset":
        assert outcome["status"] != 200, (
            f"change-password overwrote a completed recovery: {outcome['status']} {outcome['body']}"
        )
        assert verify_password(RESET_PASSWORD, password_hash)
    else:
        assert outcome["status"] == 200
        assert verify_password(ATTACKER_PASSWORD, password_hash)


async def _complete_reset(sessionmaker, token: str, settings) -> str:
    async with sessionmaker() as session:
        try:
            await complete_password_reset(
                session,
                token=token,
                new_password=RESET_PASSWORD,
                settings=settings,
            )
            await session.commit()
            return "reset"
        except AppError as exc:
            await session.rollback()
            return exc.code


# --- AUT-002: containment kills outstanding reset capabilities ------------------


def test_reset_issued_before_suspension_is_dead_after_containment(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r09-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)

    admin_login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    suspended = postgis_db_client.patch(
        f"/api/v1/admin/users/{user.id}",
        headers=admin_headers,
        json={"status": "suspended"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    assert asyncio.run(_complete_reset(postgis_db_sessionmaker, token, settings)) == (
        "PASSWORD_RESET_INVALID"
    )

    _, password_hash, user_status = _user_state(postgis_db_sessionmaker, user.id)
    assert user_status == UserStatus.SUSPENDED.value
    assert verify_password(PASSWORD, password_hash)
    assert not verify_password(RESET_PASSWORD, password_hash)

    async def unconsumed() -> None:
        async with postgis_db_sessionmaker() as session:
            reset = await session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
            )
            assert reset is not None
            assert reset.used_at is None

    asyncio.run(unconsumed())


def test_reset_completion_rechecks_live_status_under_its_lock(
    postgis_db_sessionmaker, settings
) -> None:
    """Status is re-read inside the completion transaction, not trusted from issuance."""
    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)

    async def contain_without_rotating() -> None:
        # Force the exact AUT-002 shape: containment that did not rotate the
        # session version, so only a live status check can reject the token.
        async with postgis_db_sessionmaker() as session:
            locked = await session.get(User, user.id)
            assert locked is not None
            locked.status = UserStatus.DISABLED.value
            await session.commit()

    asyncio.run(contain_without_rotating())
    assert asyncio.run(_complete_reset(postgis_db_sessionmaker, token, settings)) == (
        "PASSWORD_RESET_INVALID"
    )
    _, password_hash, _ = _user_state(postgis_db_sessionmaker, user.id)
    assert verify_password(PASSWORD, password_hash)


@pytest.mark.parametrize("suspend_first", [True, False])
def test_suspension_and_reset_completion_race_in_both_orders(
    postgis_db_sessionmaker, settings, suspend_first: bool
) -> None:
    from app.schemas.users import UserUpdate
    from app.services.users import update_user

    user = _recoverable_user(postgis_db_sessionmaker)
    token = _issue_reset(postgis_db_sessionmaker, settings, user.id)
    start_version, _, _ = _user_state(postgis_db_sessionmaker, user.id)

    async def run_suspend() -> str:
        async with postgis_db_sessionmaker() as session:
            await update_user(session, user.id, UserUpdate(status=UserStatus.SUSPENDED))
            await session.commit()
            return "suspended"

    async def scenario() -> None:
        first, second = (
            (run_suspend, lambda: _complete_reset(postgis_db_sessionmaker, token, settings))
            if suspend_first
            else (lambda: _complete_reset(postgis_db_sessionmaker, token, settings), run_suspend)
        )
        outcomes = await asyncio.wait_for(asyncio.gather(first(), second()), timeout=30)
        assert "suspended" in outcomes
        async with postgis_db_sessionmaker() as session:
            final = await session.get(User, user.id)
            assert final is not None
            version, password_hash, user_status = (
                final.session_version,
                final.password_hash,
                final.status,
            )
        # Whichever order the database grants, a suspended account must never end
        # up holding the reset bearer's password.
        assert user_status == UserStatus.SUSPENDED.value
        if "reset" in outcomes:
            # Legal only when recovery committed strictly before containment.
            assert verify_password(RESET_PASSWORD, password_hash)
        else:
            assert "PASSWORD_RESET_INVALID" in outcomes
            assert verify_password(PASSWORD, password_hash)
        assert version > start_version

    asyncio.run(scenario())


# --- AUT-002: every real status transition rotates the session version ----------


def test_every_real_status_transition_rotates_the_session_version(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r09-rotation-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    user = _recoverable_user(postgis_db_sessionmaker)
    login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": PASSWORD},
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    version = _user_state(postgis_db_sessionmaker, user.id)[0]
    for next_status in ("suspended", "disabled", "invited", "active", "suspended", "active"):
        response = postgis_db_client.patch(
            f"/api/v1/admin/users/{user.id}",
            headers=admin_headers,
            json={"status": next_status},
        )
        assert response.status_code == 200
        rotated = _user_state(postgis_db_sessionmaker, user.id)[0]
        assert rotated == version + 1, f"{next_status} did not rotate the session version"
        version = rotated

    # A no-op restatement of the current status is not a transition.
    noop = postgis_db_client.patch(
        f"/api/v1/admin/users/{user.id}",
        headers=admin_headers,
        json={"status": "active", "full_name": "Renamed Without Containment"},
    )
    assert noop.status_code == 200
    assert noop.json()["full_name"] == "Renamed Without Containment"
    assert _user_state(postgis_db_sessionmaker, user.id)[0] == version


def test_containment_revokes_the_live_bearer_and_reactivation_does_not_restore_it(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r09-revoke-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    user = _recoverable_user(postgis_db_sessionmaker)
    admin_login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": PASSWORD},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    victim_login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert victim_login.status_code == 200
    victim_headers = {"Authorization": f"Bearer {victim_login.json()['access_token']}"}
    assert postgis_db_client.get("/api/v1/me", headers=victim_headers).status_code == 200

    assert (
        postgis_db_client.patch(
            f"/api/v1/admin/users/{user.id}",
            headers=admin_headers,
            json={"status": "suspended"},
        ).status_code
        == 200
    )
    contained = postgis_db_client.get("/api/v1/me", headers=victim_headers)
    assert contained.status_code == 403
    assert contained.json()["error"]["code"] == "USER_NOT_ACTIVE"

    assert (
        postgis_db_client.patch(
            f"/api/v1/admin/users/{user.id}",
            headers=admin_headers,
            json={"status": "active"},
        ).status_code
        == 200
    )
    # Reactivation must not resurrect the pre-containment capability.
    restored = postgis_db_client.get("/api/v1/me", headers=victim_headers)
    assert restored.status_code == 401
    assert restored.json()["error"]["code"] == "SESSION_REVOKED"
    assert (
        postgis_db_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": PASSWORD},
        ).status_code
        == 200
    )


# --- AUT-006: administrator elevation reauthenticates and revokes globally -----


def test_admin_elevation_kills_old_bearer_refresh_and_reset_capabilities(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    target = _recoverable_user(postgis_db_sessionmaker)
    reset_token = _issue_reset(postgis_db_sessionmaker, settings, target.id)
    login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": target.email, "password": PASSWORD},
    )
    assert login.status_code == 200
    old_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    admin_login = postgis_db_client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": PASSWORD},
    )
    assert admin_login.status_code == 200

    elevated = postgis_db_client.patch(
        f"/api/v1/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        json={"role": "admin", "current_password": PASSWORD},
    )

    assert elevated.status_code == 200
    assert elevated.json()["role"] == "admin"
    for method, path in (
        (postgis_db_client.get, "/api/v1/me"),
        (postgis_db_client.post, "/api/v1/auth/refresh"),
    ):
        denied = method(path, headers=old_headers)
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "SESSION_REVOKED"
    assert (
        asyncio.run(_complete_reset(postgis_db_sessionmaker, reset_token, settings))
        == "PASSWORD_RESET_INVALID"
    )


@pytest.mark.parametrize("actor_update_first", [True, False])
def test_admin_elevation_and_actor_containment_serialize_in_both_orders(
    postgis_db_sessionmaker, actor_update_first: bool
) -> None:
    from app.schemas.users import UserUpdate
    from app.services.users import update_user

    admin = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-race-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    target = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-race-target@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    start_target_version = target.session_version

    async def elevate() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await update_user(
                    session,
                    target.id,
                    UserUpdate(role=UserRole.ADMIN, current_password=PASSWORD),
                    actor_user_id=admin.id,
                    actor_session_version=admin.session_version,
                    rate_limiter=NOOP_LOGIN_LIMITER,
                    client_ip="203.0.113.20",
                )
                await session.commit()
                return "elevated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as first_session:
            if actor_update_first:
                actor = await first_session.scalar(
                    select(User).where(User.id == admin.id).with_for_update()
                )
                assert actor is not None
                actor.status = UserStatus.SUSPENDED.value
                actor.session_version += 1
                contender = asyncio.create_task(elevate())
                await asyncio.sleep(0.1)
                assert not contender.done()
                await first_session.commit()
                assert await contender == "USER_NOT_ACTIVE"
            else:
                await update_user(
                    first_session,
                    target.id,
                    UserUpdate(role=UserRole.ADMIN, current_password=PASSWORD),
                    actor_user_id=admin.id,
                    actor_session_version=admin.session_version,
                    rate_limiter=NOOP_LOGIN_LIMITER,
                    client_ip="203.0.113.20",
                )

                async def contain_actor() -> None:
                    async with postgis_db_sessionmaker() as session:
                        await update_user(
                            session,
                            admin.id,
                            UserUpdate(status=UserStatus.SUSPENDED),
                        )
                        await session.commit()

                contender = asyncio.create_task(contain_actor())
                await asyncio.sleep(0.1)
                assert not contender.done()
                await first_session.commit()
                await contender

        async with postgis_db_sessionmaker() as session:
            stored_admin = await session.get(User, admin.id)
            stored_target = await session.get(User, target.id)
            assert stored_admin is not None and stored_target is not None
            assert stored_admin.status == UserStatus.SUSPENDED.value
            if actor_update_first:
                assert stored_target.role == UserRole.DRIVER.value
                assert stored_target.session_version == start_target_version
            else:
                assert stored_target.role == UserRole.ADMIN.value
                assert stored_target.session_version == start_target_version + 1

    asyncio.run(scenario())


def test_admin_elevation_refuses_stale_actor_session_authority(
    postgis_db_sessionmaker,
) -> None:
    from app.schemas.users import UserUpdate
    from app.services.users import update_user

    admin = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-stale-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    target = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-stale-target@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            actor = await session.get(User, admin.id)
            assert actor is not None
            actor.session_version += 1
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            with pytest.raises(AppError) as stale:
                await update_user(
                    session,
                    target.id,
                    UserUpdate(role=UserRole.ADMIN, current_password=PASSWORD),
                    actor_user_id=admin.id,
                    actor_session_version=admin.session_version,
                    rate_limiter=NOOP_LOGIN_LIMITER,
                    client_ip="203.0.113.20",
                )
            assert stale.value.code == "SESSION_REVOKED"
            await session.rollback()

        async with postgis_db_sessionmaker() as session:
            stored = await session.get(User, target.id)
            assert stored is not None
            assert stored.role == UserRole.DRIVER.value
            assert stored.session_version == target.session_version

    asyncio.run(scenario())


@pytest.mark.parametrize("target_update_first", [True, False])
def test_admin_elevation_and_target_disable_serialize_in_both_orders(
    postgis_db_sessionmaker, target_update_first: bool
) -> None:
    from app.schemas.users import UserUpdate
    from app.services.users import update_user

    admin = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-target-race-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    target = create_test_user(
        postgis_db_sessionmaker,
        email="aut006-target-race-user@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
    )
    start_version = target.session_version

    async def elevate() -> str:
        async with postgis_db_sessionmaker() as session:
            try:
                await update_user(
                    session,
                    target.id,
                    UserUpdate(role=UserRole.ADMIN, current_password=PASSWORD),
                    actor_user_id=admin.id,
                    actor_session_version=admin.session_version,
                    rate_limiter=NOOP_LOGIN_LIMITER,
                    client_ip="203.0.113.20",
                )
                await session.commit()
                return "elevated"
            except AppError as exc:
                await session.rollback()
                return exc.code

    async def disable() -> None:
        async with postgis_db_sessionmaker() as session:
            await update_user(
                session,
                target.id,
                UserUpdate(status=UserStatus.DISABLED),
            )
            await session.commit()

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as first_session:
            if target_update_first:
                locked = await first_session.scalar(
                    select(User).where(User.id == target.id).with_for_update()
                )
                assert locked is not None
                locked.status = UserStatus.DISABLED.value
                locked.session_version += 1
                contender = asyncio.create_task(elevate())
            else:
                await update_user(
                    first_session,
                    target.id,
                    UserUpdate(role=UserRole.ADMIN, current_password=PASSWORD),
                    actor_user_id=admin.id,
                    actor_session_version=admin.session_version,
                    rate_limiter=NOOP_LOGIN_LIMITER,
                    client_ip="203.0.113.20",
                )
                contender = asyncio.create_task(disable())
            await asyncio.sleep(0.1)
            assert not contender.done()
            await first_session.commit()
            outcome = await contender
            if target_update_first:
                assert outcome == "USER_NOT_ACTIVE"

        async with postgis_db_sessionmaker() as session:
            stored = await session.get(User, target.id)
            assert stored is not None
            assert stored.status == UserStatus.DISABLED.value
            if target_update_first:
                assert stored.role == UserRole.DRIVER.value
                assert stored.session_version == start_version + 1
            else:
                assert stored.role == UserRole.ADMIN.value
                assert stored.session_version == start_version + 2

    asyncio.run(scenario())


# --- GOV-007: refresh and token issuance are commands, not router policy -------

REQUIRED_ACCESS_TOKEN_CLAIMS = {"sub", "exp", "iat", "auth_time", "sv"}


def _decode(token: str, settings) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def _audit_actions(sessionmaker) -> list[str]:
    async def read() -> list[str]:
        async with sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent.action).order_by(AuditEvent.created_at, AuditEvent.id)
            )
            return [row[0] for row in result.all()]

    return asyncio.run(read())


def test_issue_session_command_mints_the_full_strict_claim_set(
    postgis_db_sessionmaker, settings
) -> None:
    """Issuance is a command: a direct caller gets the same R10 claim contract."""
    user = _recoverable_user(postgis_db_sessionmaker)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            issued = issue_session(loaded, settings)

        claims = _decode(issued.access_token, settings)
        assert set(claims) == REQUIRED_ACCESS_TOKEN_CLAIMS
        assert claims["sub"] == str(user.id)
        assert claims["sv"] == loaded.session_version
        for name in ("exp", "iat", "auth_time", "sv"):
            assert type(claims[name]) is int, name
        assert claims["auth_time"] <= claims["iat"] < claims["exp"]
        assert issued.user.id == user.id
        assert 0 < issued.expires_in <= settings.access_token_expire_minutes * 60

    asyncio.run(scenario())


def test_refresh_command_outside_http_reissues_under_the_original_cap(
    postgis_db_sessionmaker, settings
) -> None:
    """Refresh policy runs outside HTTP: cap measured from the original auth_time."""
    user = _recoverable_user(postgis_db_sessionmaker)
    auth_time = datetime.now(UTC) - timedelta(
        minutes=settings.session_absolute_lifetime_minutes - 1
    )
    presented, _ = create_access_token(
        user.id, settings, session_version=user.session_version, auth_time=auth_time
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            issued = await refresh_user_session(
                session, user=loaded, token=presented, settings=settings
            )
            await session.commit()

        claims = _decode(issued.access_token, settings)
        assert set(claims) == REQUIRED_ACCESS_TOKEN_CLAIMS
        # auth_time is carried forward, so refreshing never extends the cap.
        assert claims["auth_time"] == int(auth_time.timestamp())
        cap_at = int(
            (auth_time + timedelta(minutes=settings.session_absolute_lifetime_minutes)).timestamp()
        )
        assert claims["exp"] <= cap_at
        assert issued.access_token != presented

    asyncio.run(scenario())
    assert _audit_actions(postgis_db_sessionmaker).count("auth.session.refreshed") == 1


def test_refresh_command_refuses_a_session_past_its_absolute_cap(
    postgis_db_sessionmaker, settings
) -> None:
    user = _recoverable_user(postgis_db_sessionmaker)
    expired_auth_time = datetime.now(UTC) - timedelta(
        minutes=settings.session_absolute_lifetime_minutes + 1
    )
    presented, _ = create_access_token(
        user.id, settings, session_version=user.session_version, auth_time=expired_auth_time
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            with pytest.raises(AuthCommandError) as capped:
                await refresh_user_session(session, user=loaded, token=presented, settings=settings)
            assert capped.value.error.code == "SESSION_EXPIRED"
            assert capped.value.error.status_code == 401
            assert capped.value.audited is False
            await session.rollback()

    asyncio.run(scenario())
    # A refusal is not a refresh: it must leave no refresh evidence behind.
    assert "auth.session.refreshed" not in _audit_actions(postgis_db_sessionmaker)


@pytest.mark.parametrize(
    "claim_override",
    [
        pytest.param({"sv": None}, id="null-sv"),
        pytest.param({"sv": True}, id="boolean-sv"),
        pytest.param({"auth_time": 1.5}, id="float-auth-time"),
        pytest.param({"sub": "not-a-uuid"}, id="malformed-subject"),
    ],
)
def test_refresh_command_enforces_strict_token_claims(
    postgis_db_sessionmaker, settings, claim_override: dict
) -> None:
    """R10 strict-claim rejection is the command's, not the router's."""
    user = _recoverable_user(postgis_db_sessionmaker)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "sv": user.session_version,
        "auth_time": int(now.timestamp()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    payload.update(claim_override)
    presented = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            with pytest.raises(AuthCommandError) as invalid:
                await refresh_user_session(session, user=loaded, token=presented, settings=settings)
            assert invalid.value.error.code == "INVALID_TOKEN"
            assert invalid.value.error.status_code == 401
            await session.rollback()

    asyncio.run(scenario())
    assert "auth.session.refreshed" not in _audit_actions(postgis_db_sessionmaker)


def test_refresh_command_and_route_agree_on_the_same_session(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    """Direct-command parity: the route adds an envelope, not a different decision."""
    user = _recoverable_user(postgis_db_sessionmaker)
    auth_time = datetime.now(UTC) - timedelta(
        minutes=settings.session_absolute_lifetime_minutes - 5
    )
    presented, _ = create_access_token(
        user.id, settings, session_version=user.session_version, auth_time=auth_time
    )

    routed = postgis_db_client.post(
        "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {presented}"}
    )
    assert routed.status_code == 200
    routed_claims = _decode(routed.json()["access_token"], settings)

    async def direct() -> dict:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            issued = await refresh_user_session(
                session, user=loaded, token=presented, settings=settings
            )
            await session.commit()
            return _decode(issued.access_token, settings)

    direct_claims = asyncio.run(direct())

    assert set(routed_claims) == set(direct_claims) == REQUIRED_ACCESS_TOKEN_CLAIMS
    assert routed_claims["sub"] == direct_claims["sub"]
    assert routed_claims["sv"] == direct_claims["sv"]
    assert routed_claims["auth_time"] == direct_claims["auth_time"] == int(auth_time.timestamp())
    cap_at = int(
        (auth_time + timedelta(minutes=settings.session_absolute_lifetime_minutes)).timestamp()
    )
    assert routed_claims["exp"] <= cap_at and direct_claims["exp"] <= cap_at
    assert routed.json()["user"]["id"] == str(user.id)
    # Both paths recorded exactly one refresh each.
    assert _audit_actions(postgis_db_sessionmaker).count("auth.session.refreshed") == 2


def test_refresh_route_rejects_a_capped_session_with_the_stable_envelope(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    user = _recoverable_user(postgis_db_sessionmaker)
    expired_auth_time = datetime.now(UTC) - timedelta(
        minutes=settings.session_absolute_lifetime_minutes + 1
    )
    presented, _ = create_access_token(
        user.id, settings, session_version=user.session_version, auth_time=expired_auth_time
    )
    response = postgis_db_client.post(
        "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {presented}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_refresh_command_refuses_at_the_exact_absolute_cap_boundary(
    postgis_db_sessionmaker, settings
) -> None:
    """The boundary itself is closed: `expires_at <= now` refuses, not re-issues."""
    user = _recoverable_user(postgis_db_sessionmaker)
    at_cap_auth_time = datetime.now(UTC) - timedelta(
        minutes=settings.session_absolute_lifetime_minutes
    )
    presented, _ = create_access_token(
        user.id, settings, session_version=user.session_version, auth_time=at_cap_auth_time
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            loaded = await session.get(User, user.id)
            assert loaded is not None
            with pytest.raises(AuthCommandError) as at_cap:
                await refresh_user_session(session, user=loaded, token=presented, settings=settings)
            assert at_cap.value.error.code == "SESSION_EXPIRED"
            await session.rollback()

    asyncio.run(scenario())
    assert "auth.session.refreshed" not in _audit_actions(postgis_db_sessionmaker)
