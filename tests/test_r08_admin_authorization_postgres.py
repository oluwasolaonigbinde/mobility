from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError
from app.models.user import User, UserRole, UserStatus
from app.services import billing
from app.services.admin_authorization import require_active_admin
from tests.test_r08_admin_authorization import (
    MIGRATED_CALL_SITES,
    _module,
    _required_argument,
)

CALL_SITE_IDS = tuple(
    f"{service_name}.{function_name}"
    for service_name, function_names in MIGRATED_CALL_SITES.items()
    for function_name in function_names
)


async def _seed_admin(sessionmaker, call_site: str, mode: str) -> User:
    async with sessionmaker() as session:
        admin = User(
            email=f"r08-{mode}-{call_site.replace('.', '-').replace('_', '-')}@example.com",
            password_hash="unused",
            full_name=f"Original {call_site}",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


async def _load_user(sessionmaker, user_id: UUID) -> User:
    async with sessionmaker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user


async def _backend_pid(session) -> int:
    backend_pid = await session.scalar(select(func.pg_backend_pid()))
    assert backend_pid is not None
    return backend_pid


async def _assert_blocked_by(
    sessionmaker, *, blocked_backend_pid: int, blocker_backend_pid: int
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2
    blocking_pids: tuple[int, ...] = ()
    while loop.time() < deadline:
        async with sessionmaker() as observer:
            observed = await observer.scalar(select(func.pg_blocking_pids(blocked_backend_pid)))
        blocking_pids = tuple(observed or ())
        if blocker_backend_pid in blocking_pids:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"PostgreSQL backend {blocked_backend_pid} was not blocked by "
        f"{blocker_backend_pid}; observed blockers: {blocking_pids}"
    )


async def _invoke_call_site(session, call_site: str, *, actor_user_id: UUID, settings) -> None:
    service_name, function_name = call_site.split(".", maxsplit=1)
    function = getattr(_module(service_name), function_name)
    kwargs = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.name == "session":
            continue
        if parameter.default is not inspect.Parameter.empty and parameter.name not in {
            "admin",
            "require_admin",
        }:
            continue
        kwargs[parameter.name] = _required_argument(
            function,
            parameter.name,
            denied_user_id=actor_user_id,
            active_admin_id=actor_user_id,
            settings=settings,
        )
    await function(session, **kwargs)


class _StopAfterAuthorization(Exception):
    pass


async def _disable_first(
    sessionmaker, *, admin: User, call_site: str, settings, monkeypatch
) -> None:
    disable_locked = asyncio.Event()
    release_disable = asyncio.Event()
    writer_started = asyncio.Event()
    backend_pids: dict[str, int] = {}
    timeline: list[str] = []

    async def disable() -> None:
        async with sessionmaker() as session, session.begin():
            backend_pids["disable"] = await _backend_pid(session)
            user = await session.scalar(select(User).where(User.id == admin.id).with_for_update())
            assert user is not None
            user.status = UserStatus.DISABLED
            await session.flush()
            disable_locked.set()
            await release_disable.wait()
        timeline.append("disable_committed")

    async def write() -> None:
        async with sessionmaker() as session, session.begin():
            backend_pids["write"] = await _backend_pid(session)
            writer_started.set()
            with pytest.raises(AppError) as caught:
                await _invoke_call_site(
                    session,
                    call_site,
                    actor_user_id=admin.id,
                    settings=settings,
                )
            assert caught.value.code == "FORBIDDEN_ROLE"
        timeline.append("write_denied")

    service_name, _ = call_site.split(".", maxsplit=1)
    with monkeypatch.context() as patch:
        patch.setattr(_module(service_name), "require_active_admin", require_active_admin)
        disable_task = asyncio.create_task(disable())
        await asyncio.wait_for(disable_locked.wait(), timeout=2)
        write_task = asyncio.create_task(write())
        await asyncio.wait_for(writer_started.wait(), timeout=2)
        await _assert_blocked_by(
            sessionmaker,
            blocked_backend_pid=backend_pids["write"],
            blocker_backend_pid=backend_pids["disable"],
        )
        release_disable.set()
        await asyncio.wait_for(asyncio.gather(disable_task, write_task), timeout=2)

    persisted = await _load_user(sessionmaker, admin.id)
    assert persisted.status == UserStatus.DISABLED
    assert persisted.full_name == f"Original {call_site}"
    assert timeline == ["disable_committed", "write_denied"]


async def _write_first(sessionmaker, *, admin: User, call_site: str, settings, monkeypatch) -> None:
    write_locked = asyncio.Event()
    release_write = asyncio.Event()
    disable_started = asyncio.Event()
    backend_pids: dict[str, int] = {}
    timeline: list[str] = []

    async def probed_authority(session, actor_user_id: UUID) -> None:
        await require_active_admin(session, actor_user_id)
        write_locked.set()
        await release_write.wait()
        raise _StopAfterAuthorization

    async def write() -> None:
        async with sessionmaker() as session, session.begin():
            backend_pids["write"] = await _backend_pid(session)
            with pytest.raises(_StopAfterAuthorization):
                await _invoke_call_site(
                    session,
                    call_site,
                    actor_user_id=admin.id,
                    settings=settings,
                )
        timeline.append("write_committed")

    async def disable() -> None:
        async with sessionmaker() as session, session.begin():
            backend_pids["disable"] = await _backend_pid(session)
            disable_started.set()
            user = await session.scalar(select(User).where(User.id == admin.id).with_for_update())
            assert user is not None
            user.status = UserStatus.DISABLED
        timeline.append("disable_committed")

    service_name, _ = call_site.split(".", maxsplit=1)
    with monkeypatch.context() as patch:
        patch.setattr(_module(service_name), "require_active_admin", probed_authority)
        write_task = asyncio.create_task(write())
        await asyncio.wait_for(write_locked.wait(), timeout=2)
        disable_task = asyncio.create_task(disable())
        await asyncio.wait_for(disable_started.wait(), timeout=2)
        await _assert_blocked_by(
            sessionmaker,
            blocked_backend_pid=backend_pids["disable"],
            blocker_backend_pid=backend_pids["write"],
        )
        release_write.set()
        await asyncio.wait_for(asyncio.gather(write_task, disable_task), timeout=2)

    persisted = await _load_user(sessionmaker, admin.id)
    assert persisted.full_name == f"Original {call_site}"
    assert persisted.status == UserStatus.DISABLED
    assert timeline == ["write_committed", "disable_committed"]


async def _rollback_releases_lock(
    sessionmaker, *, admin: User, call_site: str, settings, monkeypatch
) -> None:
    write_locked = asyncio.Event()
    release_write = asyncio.Event()
    disable_started = asyncio.Event()
    backend_pids: dict[str, int] = {}
    timeline: list[str] = []

    async def probed_authority(session, actor_user_id: UUID) -> None:
        await require_active_admin(session, actor_user_id)
        write_locked.set()
        await release_write.wait()
        raise RuntimeError("forced protected-write failure")

    async def write() -> None:
        try:
            async with sessionmaker() as session, session.begin():
                backend_pids["write"] = await _backend_pid(session)
                await _invoke_call_site(
                    session,
                    call_site,
                    actor_user_id=admin.id,
                    settings=settings,
                )
        except RuntimeError as exc:
            assert str(exc) == "forced protected-write failure"
        timeline.append("write_rolled_back")

    async def disable() -> None:
        async with sessionmaker() as session, session.begin():
            backend_pids["disable"] = await _backend_pid(session)
            disable_started.set()
            user = await session.scalar(select(User).where(User.id == admin.id).with_for_update())
            assert user is not None
            user.status = UserStatus.DISABLED
        timeline.append("disable_committed")

    service_name, _ = call_site.split(".", maxsplit=1)
    with monkeypatch.context() as patch:
        patch.setattr(_module(service_name), "require_active_admin", probed_authority)
        write_task = asyncio.create_task(write())
        await asyncio.wait_for(write_locked.wait(), timeout=2)
        disable_task = asyncio.create_task(disable())
        await asyncio.wait_for(disable_started.wait(), timeout=2)
        await _assert_blocked_by(
            sessionmaker,
            blocked_backend_pid=backend_pids["disable"],
            blocker_backend_pid=backend_pids["write"],
        )
        release_write.set()
        await asyncio.wait_for(asyncio.gather(write_task, disable_task), timeout=2)

    persisted = await _load_user(sessionmaker, admin.id)
    assert persisted.full_name == f"Original {call_site}"
    assert persisted.status == UserStatus.DISABLED
    assert timeline == ["write_rolled_back", "disable_committed"]


RACE_CLASSES: dict[str, Callable[..., Awaitable[None]]] = {
    "disable_first": _disable_first,
    "write_first": _write_first,
    "rollback_error": _rollback_releases_lock,
}


@pytest.mark.parametrize("race_class", tuple(RACE_CLASSES))
def test_every_migrated_call_site_has_bounded_disable_write_serialization(
    postgis_db_sessionmaker, race_class: str, settings, monkeypatch
) -> None:
    async def scenario() -> None:
        for call_site in CALL_SITE_IDS:
            admin = await _seed_admin(postgis_db_sessionmaker, call_site, race_class)
            await RACE_CLASSES[race_class](
                postgis_db_sessionmaker,
                admin=admin,
                call_site=call_site,
                settings=settings,
                monkeypatch=monkeypatch,
            )

    assert len(CALL_SITE_IDS) == 44
    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_approved_credit_locks_equal_and_swapped_admins_sorted_unique(
    postgis_db_sessionmaker, monkeypatch
) -> None:
    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            first = User(
                id=UUID(int=100),
                email="r08-credit-first@example.com",
                password_hash="unused",
                full_name="First Billing Admin",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            second = User(
                id=UUID(int=200),
                email="r08-credit-second@example.com",
                password_hash="unused",
                full_name="Second Billing Admin",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add_all((first, second))
            await session.commit()

        calls: dict[str, list[UUID]] = {}
        real_authority = require_active_admin

        async def tracked_authority(session, actor_user_id: UUID) -> None:
            task = asyncio.current_task()
            assert task is not None
            calls.setdefault(task.get_name(), []).append(actor_user_id)
            await real_authority(session, actor_user_id)

        monkeypatch.setattr(billing, "require_active_admin", tracked_authority)

        async def attempt(name: str, actor_user_id: UUID, approver_user_id: UUID) -> str:
            task = asyncio.current_task()
            assert task is not None
            task.set_name(name)
            async with postgis_db_sessionmaker() as session:
                with pytest.raises(AppError) as caught:
                    async with session.begin():
                        await billing.record_approved_credit_authorization(
                            session,
                            campaign_id=uuid4(),
                            actor_user_id=actor_user_id,
                            credit_limit="100.00",
                            max_driver_liability="100.00",
                            due_at=datetime.now(UTC) + timedelta(days=1),
                            approved_by_user_id=approver_user_id,
                            credit_terms={"synthetic": True},
                            reason="R08 lock-order evidence",
                        )
                assert caught.value.code == "APPROVED_CREDIT_TERMS_REQUIRED"
                return caught.value.code

        results = await asyncio.wait_for(
            asyncio.gather(
                attempt("forward", first.id, second.id),
                attempt("reverse", second.id, first.id),
            ),
            timeout=2,
        )
        assert results == [
            "APPROVED_CREDIT_TERMS_REQUIRED",
            "APPROVED_CREDIT_TERMS_REQUIRED",
        ]
        expected = [first.id, second.id]
        assert calls["forward"] == expected
        assert calls["reverse"] == expected

        assert await asyncio.wait_for(attempt("equal", first.id, first.id), timeout=2)
        assert calls["equal"] == [first.id]

    asyncio.run(scenario())
