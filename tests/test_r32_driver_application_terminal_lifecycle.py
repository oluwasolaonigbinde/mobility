"""R32 terminal driver-application lifecycle migration and lock evidence."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_driver_vehicle_approval import (
    _approved_applicant,
    _review_files,
    _seed_vehicle_files,
    _vehicle_payload,
)
from test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

from app.core.errors import AppError
from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.driver_application import (
    DriverApplication,
    DriverApplicationAccessToken,
    DriverApplicationStatus,
)
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole, UserStatus
from app.schemas.driver_applications import DriverApplicationCreate
from app.schemas.driver_onboarding import VehicleReviewDecisionCreate
from app.schemas.drivers import DriverProfileAdminUpdate
from app.services import drivers as drivers_service
from app.services import vehicle_onboarding as vehicle_onboarding_service
from app.services.driver_applications import (
    application_from_access_token,
    issue_driver_application_access,
    submit_driver_application,
    synthetic_driver_application_access_token,
    terminalize_driver_application,
)
from app.services.drivers import update_driver_profile
from app.services.vehicle_onboarding import review_application_vehicle

PRE_TERMINAL_REVISION = "0071_report_issuances"
TERMINAL_REVISION = "0072_driver_application_terminal_status"


async def _seed_application(sessionmaker, settings, *, suffix: str):
    async with sessionmaker() as session:
        submission = await submit_driver_application(
            session,
            DriverApplicationCreate(
                email=f"r32-{suffix}@example.test",
                full_name="R32 Applicant",
            ),
        )
        assert submission.application is not None
        access = await issue_driver_application_access(
            session,
            application=submission.application,
            settings=settings,
        )
        assert access is not None
        admin = User(
            email=f"r32-admin-{suffix}@example.test",
            password_hash="unused",
            full_name="R32 Admin",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(admin)
        await session.commit()
        token = synthetic_driver_application_access_token(
            access,
            settings,
            synthetic_test_authority=True,
        )
        return submission.application.id, access.id, admin.id, token


async def _race_authority(
    sessionmaker,
    settings,
    *,
    application_id,
    token,
    operation,
    terminal_locked,
    authority_started,
):
    await terminal_locked.wait()
    async with sessionmaker() as session:
        authority_started.set()
        if operation == "issue":
            application = await session.get(DriverApplication, application_id)
            assert application is not None
            result = await issue_driver_application_access(
                session,
                application=application,
                settings=settings,
            )
            await session.commit()
            return result
        try:
            await application_from_access_token(
                session,
                token=token,
                settings=settings,
                lock=True,
            )
        except AppError as exc:
            return exc.code
        return "unexpected-authority"


async def _assert_terminal_evidence(
    sessionmaker,
    *,
    application_id,
    terminal_status,
) -> None:
    async with sessionmaker() as session:
        application = await session.get(DriverApplication, application_id)
        assert application is not None
        assert application.status == terminal_status.value
        assert (
            await session.scalar(
                select(func.count(DriverApplicationAccessToken.id)).where(
                    DriverApplicationAccessToken.application_id == application_id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.entity_id == str(application_id),
                    AuditEvent.action == f"admin.driver_application.{terminal_status.value}",
                )
            )
            == 1
        )


@pytest.mark.parametrize("operation", ["issue", "mutate"])
def test_r32_profile_rejection_entry_point_fences_racing_authority(
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
    operation,
) -> None:
    async def run() -> None:
        application_id, _access_id, admin_id, token = await _seed_application(
            postgis_db_sessionmaker,
            settings,
            suffix=f"entry-rejected-{operation}",
        )
        async with postgis_db_sessionmaker() as session:
            application = await session.get(DriverApplication, application_id)
            assert application is not None
            driver_profile_id = application.driver_profile_id

        terminal_locked = asyncio.Event()
        authority_started = asyncio.Event()
        release_terminal = asyncio.Event()
        original_terminalize = drivers_service.terminalize_driver_application

        async def pause_terminalize(*args, **kwargs):
            terminal_locked.set()
            await release_terminal.wait()
            return await original_terminalize(*args, **kwargs)

        monkeypatch.setattr(
            drivers_service,
            "terminalize_driver_application",
            pause_terminalize,
        )

        async def reject() -> None:
            async with postgis_db_sessionmaker() as session:
                await update_driver_profile(
                    session,
                    driver_profile_id,
                    DriverProfileAdminUpdate(onboarding_status="rejected"),
                    actor_user_id=admin_id,
                )
                await session.commit()

        rejection_task = asyncio.create_task(reject())
        authority_task = asyncio.create_task(
            _race_authority(
                postgis_db_sessionmaker,
                settings,
                application_id=application_id,
                token=token,
                operation=operation,
                terminal_locked=terminal_locked,
                authority_started=authority_started,
            )
        )
        await asyncio.wait_for(authority_started.wait(), timeout=5)
        await asyncio.sleep(0.05)
        assert not authority_task.done()
        release_terminal.set()
        _, authority_result = await asyncio.wait_for(
            asyncio.gather(rejection_task, authority_task),
            timeout=10,
        )
        assert (
            authority_result is None
            if operation == "issue"
            else (authority_result == "ONBOARDING_ACCESS_INVALID")
        )
        await _assert_terminal_evidence(
            postgis_db_sessionmaker,
            application_id=application_id,
            terminal_status=DriverApplicationStatus.REJECTED,
        )

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["issue", "mutate"])
def test_r32_full_approval_entry_point_fences_racing_authority(
    postgis_db_client,
    postgis_db_sessionmaker,
    settings,
    monkeypatch,
    operation,
) -> None:
    token, application, admin = _approved_applicant(
        postgis_db_client,
        postgis_db_sessionmaker,
        settings,
        suffix=f"entry-approved-{operation}",
    )
    files = _seed_vehicle_files(
        postgis_db_sessionmaker,
        application=application,
        suffix=f"entry-approved-{operation}",
    )
    submitted = postgis_db_client.post(
        "/api/v1/auth/driver-onboarding/vehicle",
        json=_vehicle_payload(token, files),
    )
    assert submitted.status_code == 201
    _review_files(
        postgis_db_client,
        postgis_db_sessionmaker,
        admin=admin,
        submission_id=submitted.json()["submission_id"],
        files=files,
    )
    terminal_locked = asyncio.Event()
    authority_started = asyncio.Event()
    release_terminal = asyncio.Event()
    original_terminalize = vehicle_onboarding_service.terminalize_driver_application

    async def pause_terminalize(*args, **kwargs):
        terminal_locked.set()
        await release_terminal.wait()
        return await original_terminalize(*args, **kwargs)

    monkeypatch.setattr(
        vehicle_onboarding_service,
        "terminalize_driver_application",
        pause_terminalize,
    )
    decision = VehicleReviewDecisionCreate.model_validate(
        {
            "client_request_id": str(uuid4()),
            "decision": "approved",
            "reason_code": "complete_current_evidence",
            "owner_match_confirmed": True,
            "vehicle_identity_confirmed": True,
            "roadworthy_confirmed": True,
            "pilot_car_confirmed": True,
            "documents_readable_confirmed": True,
            "valid_until": datetime(2099, 1, 1, tzinfo=UTC),
        }
    )

    async def run() -> None:
        async def approve() -> None:
            async with postgis_db_sessionmaker() as session:
                await review_application_vehicle(
                    session,
                    application_id=application.id,
                    vehicle_id=UUID(submitted.json()["vehicle_id"]),
                    submission_id=UUID(submitted.json()["submission_id"]),
                    actor_user_id=admin.id,
                    payload=decision,
                )
                await session.commit()

        approval_task = asyncio.create_task(approve())
        authority_task = asyncio.create_task(
            _race_authority(
                postgis_db_sessionmaker,
                settings,
                application_id=application.id,
                token=token,
                operation=operation,
                terminal_locked=terminal_locked,
                authority_started=authority_started,
            )
        )
        await asyncio.wait_for(authority_started.wait(), timeout=5)
        await asyncio.sleep(0.05)
        assert not authority_task.done()
        release_terminal.set()
        _, authority_result = await asyncio.wait_for(
            asyncio.gather(approval_task, authority_task),
            timeout=10,
        )
        assert (
            authority_result is None
            if operation == "issue"
            else (authority_result == "ONBOARDING_ACCESS_INVALID")
        )
        await _assert_terminal_evidence(
            postgis_db_sessionmaker,
            application_id=application.id,
            terminal_status=DriverApplicationStatus.APPROVED,
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    ("terminal_status", "operation"),
    [
        (DriverApplicationStatus.APPROVED, "issue"),
        (DriverApplicationStatus.APPROVED, "mutate"),
        (DriverApplicationStatus.REJECTED, "issue"),
        (DriverApplicationStatus.REJECTED, "mutate"),
    ],
)
def test_r32_terminal_transition_fences_racing_authority(
    postgis_db_sessionmaker,
    settings,
    terminal_status,
    operation,
) -> None:
    async def run() -> None:
        application_id, access_id, admin_id, token = await _seed_application(
            postgis_db_sessionmaker,
            settings,
            suffix=f"{terminal_status.value}-{operation}",
        )
        terminal_locked = asyncio.Event()
        authority_started = asyncio.Event()
        release_terminal = asyncio.Event()

        async def win_terminal_transition() -> bool:
            async with postgis_db_sessionmaker() as session:
                application = await session.scalar(
                    select(DriverApplication)
                    .where(DriverApplication.id == application_id)
                    .with_for_update()
                )
                assert application is not None
                terminal_locked.set()
                await release_terminal.wait()
                changed = await terminalize_driver_application(
                    session,
                    application=application,
                    terminal_status=terminal_status,
                    actor_user_id=admin_id,
                    source_entity_type="driver_profile",
                    source_entity_id=application.driver_profile_id,
                )
                await session.commit()
                return changed

        async def race_authority():
            await terminal_locked.wait()
            async with postgis_db_sessionmaker() as session:
                authority_started.set()
                if operation == "issue":
                    application = await session.get(DriverApplication, application_id)
                    assert application is not None
                    result = await issue_driver_application_access(
                        session,
                        application=application,
                        settings=settings,
                    )
                    await session.commit()
                    return result
                try:
                    await application_from_access_token(
                        session,
                        token=token,
                        settings=settings,
                        lock=True,
                    )
                except AppError as exc:
                    return exc.code
                return "unexpected-authority"

        terminal_task = asyncio.create_task(win_terminal_transition())
        authority_task = asyncio.create_task(race_authority())
        await asyncio.wait_for(authority_started.wait(), timeout=5)
        release_terminal.set()
        terminal_changed, authority_result = await asyncio.wait_for(
            asyncio.gather(terminal_task, authority_task),
            timeout=10,
        )

        assert terminal_changed is True
        if operation == "issue":
            assert authority_result is None
        else:
            assert authority_result == "ONBOARDING_ACCESS_INVALID"
        async with postgis_db_sessionmaker() as session:
            application = await session.get(DriverApplication, application_id)
            assert application is not None
            assert application.status == terminal_status.value
            assert (
                await session.scalar(
                    select(func.count(DriverApplicationAccessToken.id)).where(
                        DriverApplicationAccessToken.application_id == application_id
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.type_key
                        == NotificationType.DRIVER_ONBOARDING_ACCESS_REQUESTED.value,
                        Notification.payload["driver_application_access_id"].as_string()
                        == str(access_id),
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.entity_id == str(application_id),
                        AuditEvent.action == f"admin.driver_application.{terminal_status.value}",
                    )
                )
                == 1
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "winning_status",
    [DriverApplicationStatus.APPROVED, DriverApplicationStatus.REJECTED],
)
def test_r32_only_terminal_race_winner_emits_audit(
    postgis_db_sessionmaker,
    settings,
    winning_status,
) -> None:
    async def run() -> None:
        application_id, _access_id, admin_id, _token = await _seed_application(
            postgis_db_sessionmaker,
            settings,
            suffix=f"winner-{winning_status.value}",
        )
        winner_locked = asyncio.Event()
        loser_started = asyncio.Event()
        release_winner = asyncio.Event()
        losing_status = (
            DriverApplicationStatus.REJECTED
            if winning_status == DriverApplicationStatus.APPROVED
            else DriverApplicationStatus.APPROVED
        )

        async def attempt(status, *, winner: bool) -> bool:
            async with postgis_db_sessionmaker() as session:
                if not winner:
                    await winner_locked.wait()
                    loser_started.set()
                application = await session.scalar(
                    select(DriverApplication)
                    .where(DriverApplication.id == application_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                assert application is not None
                if winner:
                    winner_locked.set()
                    await release_winner.wait()
                changed = await terminalize_driver_application(
                    session,
                    application=application,
                    terminal_status=status,
                    actor_user_id=admin_id,
                    source_entity_type="driver_profile",
                    source_entity_id=application.driver_profile_id,
                )
                await session.commit()
                return changed

        winner = asyncio.create_task(attempt(winning_status, winner=True))
        loser = asyncio.create_task(attempt(losing_status, winner=False))
        await asyncio.wait_for(loser_started.wait(), timeout=5)
        release_winner.set()
        assert await asyncio.wait_for(asyncio.gather(winner, loser), timeout=10) == [True, False]

        async with postgis_db_sessionmaker() as session:
            application = await session.get(DriverApplication, application_id)
            assert application is not None
            assert application.status == winning_status.value
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.entity_id == str(application_id),
                        AuditEvent.action.like("admin.driver_application.%"),
                    )
                )
                == 1
            )

    asyncio.run(run())


def test_r32_terminal_status_migration_matrix(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def seed_pending() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, full_name, role, status) "
                        "VALUES ('72000000-0000-0000-0000-000000000001', "
                        "'r32-migration@example.test', 'unused', 'R32 Migration', "
                        "'driver', 'invited')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO driver_profiles (id, user_id, onboarding_status, metadata) "
                        "VALUES ('72000000-0000-0000-0000-000000000002', "
                        "'72000000-0000-0000-0000-000000000001', 'pending', '{}')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO driver_applications "
                        "(id, user_id, driver_profile_id, status, status_reference_sha256, "
                        "email, full_name) VALUES "
                        "('72000000-0000-0000-0000-000000000003', "
                        "'72000000-0000-0000-0000-000000000001', "
                        "'72000000-0000-0000-0000-000000000002', 'pending', "
                        "repeat('a', 64), 'r32-migration@example.test', 'R32 Migration')"
                    )
                )
        finally:
            await engine.dispose()

    async def read_state() -> tuple[str, str]:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                revision = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                status = (
                    await connection.execute(
                        text(
                            "SELECT status FROM driver_applications WHERE id = "
                            "'72000000-0000-0000-0000-000000000003'"
                        )
                    )
                ).scalar_one()
                return revision, status
        finally:
            await engine.dispose()

    async def assert_invalid_and_set_terminal() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            with pytest.raises(DBAPIError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE driver_applications SET status = 'invalid' WHERE id = "
                            "'72000000-0000-0000-0000-000000000003'"
                        )
                    )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE driver_applications SET status = 'approved' WHERE id = "
                        "'72000000-0000-0000-0000-000000000003'"
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, PRE_TERMINAL_REVISION, monkeypatch)
        upgrade_to(migration_url, TERMINAL_REVISION, monkeypatch)
        downgrade_to(migration_url, PRE_TERMINAL_REVISION, monkeypatch)
        asyncio.run(seed_pending())
        upgrade_to(migration_url, TERMINAL_REVISION, monkeypatch)
        downgrade_to(migration_url, PRE_TERMINAL_REVISION, monkeypatch)
        upgrade_to(migration_url, TERMINAL_REVISION, monkeypatch)
        assert asyncio.run(read_state()) == (
            TERMINAL_REVISION,
            "pending",
        )
        asyncio.run(assert_invalid_and_set_terminal())
        with pytest.raises(RuntimeError, match="0072 downgrade blocked"):
            downgrade_to(migration_url, PRE_TERMINAL_REVISION, monkeypatch)
        assert asyncio.run(read_state()) == (
            TERMINAL_REVISION,
            "approved",
        )
    finally:
        asyncio.run(drop_database(migration_url))


def test_r32_driver_application_model_has_no_owned_autogenerate_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def compare() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={"compare_type": False, "compare_server_default": False},
                        ),
                        Base.metadata,
                    )
                )
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)

        async def version_rows() -> list:
            engine = create_async_engine(migration_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    return list(
                        (
                            await connection.execute(
                                text("SELECT version_num FROM alembic_version ORDER BY version_num")
                            )
                        ).all()
                    )
            finally:
                await engine.dispose()

        assert asyncio.run(version_rows()) == [
            (revision,)
            for revision in sorted(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
        ]
        diffs = asyncio.run(compare())
        owned_diffs = []
        for diff in diffs:
            candidate = diff[1] if len(diff) > 1 else None
            table = getattr(candidate, "table", None)
            table_name = getattr(table, "name", None) or getattr(candidate, "name", None)
            if table_name == "driver_applications":
                owned_diffs.append(diff)
        assert owned_diffs == []
    finally:
        asyncio.run(drop_database(migration_url))
