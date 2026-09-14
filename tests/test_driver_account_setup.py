import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import create_test_user
from sqlalchemy import func, select
from test_driver_applications import PASSWORD
from test_email_delivery import RecordingEmailAdapter
from test_onboarding_approval_convergence import prepare

from app.core.errors import AppError
from app.core.security import create_access_token, verify_password
from app.models.audit import AuditEvent
from app.models.contact import PasswordResetToken
from app.models.driver_application import (
    DriverAccountSetupToken,
    DriverApplication,
    DriverApplicationAccessToken,
)
from app.models.notification import Notification, NotificationType
from app.models.user import User, UserRole, UserStatus
from app.services.account_recovery import (
    complete_password_reset,
    request_password_reset,
    synthetic_password_reset_token,
)
from app.services.driver_account_setup import (
    complete_driver_account_setup,
    initiate_driver_account_setup,
    synthetic_driver_account_setup_token,
)
from app.services.email_delivery import process_email_notification


def _approve(client, maker, settings):
    application, headers, requests = prepare(client, maker, settings)
    for stage in ("person", "vehicle"):
        path, body = requests[stage]
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
    return application, headers


def test_driver_account_setup_supersedes_replays_and_activates_atomically(
    db_client, db_sessionmaker, settings
) -> None:
    application, admin_headers = _approve(db_client, db_sessionmaker, settings)
    first_request = str(uuid4())
    first = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": first_request},
    )
    exact_retry = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": first_request},
    )
    second = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": str(uuid4())},
    )
    assert first.status_code == exact_retry.status_code == second.status_code == 201
    assert first.json()["id"] == exact_retry.json()["id"]
    assert second.json()["id"] != first.json()["id"]

    async def authorities():
        async with db_sessionmaker() as session:
            setups = list(
                (
                    await session.scalars(
                        select(DriverAccountSetupToken)
                        .where(DriverAccountSetupToken.application_id == application.id)
                        .order_by(DriverAccountSetupToken.created_at, DriverAccountSetupToken.id)
                    )
                ).all()
            )
            user = await session.get(User, application.user_id)
            assert len(setups) == 2 and user is not None
            tokens = [
                synthetic_driver_account_setup_token(
                    row, settings, synthetic_test_authority=True
                )
                for row in setups
            ]
            old_session, _ = create_access_token(
                user.id, settings, session_version=user.session_version
            )
            notices = list(
                (
                    await session.scalars(
                        select(Notification).where(
                            Notification.type_key
                            == NotificationType.DRIVER_ACCOUNT_SETUP_REQUESTED.value
                        )
                    )
                ).all()
            )
            return setups, tokens, user.session_version, old_session, notices

    setups, tokens, old_version, old_session, notices = asyncio.run(authorities())
    assert setups[0].superseded_at is not None
    assert setups[1].superseded_at is None
    assert len(notices) == 2
    assert {notice.recipient_user_id for notice in notices} == {application.user_id}
    assert all(set(notice.payload) == {"driver_account_setup_id"} for notice in notices)
    assert all(token not in str([notice.payload for notice in notices]) for token in tokens)

    async def deliver():
        by_setup = {
            notice.payload["driver_account_setup_id"]: notice for notice in notices
        }
        adapter = RecordingEmailAdapter()
        superseded_result = await process_email_notification(
            db_sessionmaker,
            notification_id=by_setup[str(setups[0].id)].id,
            settings=settings,
            email_adapter=adapter,
            now=datetime.now(UTC),
        )
        active_result = await process_email_notification(
            db_sessionmaker,
            notification_id=by_setup[str(setups[1].id)].id,
            settings=settings,
            email_adapter=adapter,
            now=datetime.now(UTC),
        )
        return superseded_result, active_result, adapter.messages

    superseded_delivery, active_delivery, messages = asyncio.run(deliver())
    assert (superseded_delivery, active_delivery) == ("failed", "sent")
    assert len(messages) == 1
    assert messages[0].recipient == application.email
    assert messages[0].subject == "Set up your Cardvert driver account"
    assert tokens[1] in messages[0].text_body
    assert tokens[0] not in messages[0].text_body

    superseded = db_client.post(
        "/api/v1/auth/driver-account-setup/complete",
        json={"token": tokens[0], "new_password": "replacement-driver-password"},
    )
    completed = db_client.post(
        "/api/v1/auth/driver-account-setup/complete",
        json={"token": tokens[1], "new_password": "replacement-driver-password"},
    )
    replay = db_client.post(
        "/api/v1/auth/driver-account-setup/complete",
        json={"token": tokens[1], "new_password": "another-driver-password"},
    )
    assert superseded.status_code == 400
    assert completed.status_code == 200, completed.text
    assert replay.status_code == 400
    assert superseded.json()["error"]["code"] == "DRIVER_ACCOUNT_SETUP_INVALID"
    assert replay.json()["error"]["code"] == "DRIVER_ACCOUNT_SETUP_INVALID"

    async def completed_state():
        async with db_sessionmaker() as session:
            user = await session.get(User, application.user_id)
            accesses = list(
                (
                    await session.scalars(
                        select(DriverApplicationAccessToken).where(
                            DriverApplicationAccessToken.application_id == application.id
                        )
                    )
                ).all()
            )
            initiation_audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.driver_account_setup.initiated"
                    )
                )
                or 0
            )
            completion_audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "auth.driver_account_setup.completed"
                    )
                )
                or 0
            )
            return user, accesses, initiation_audits, completion_audits

    user, accesses, initiation_audits, completion_audits = asyncio.run(completed_state())
    assert user is not None
    assert user.status == UserStatus.ACTIVE.value
    assert user.must_change_password is False
    assert user.session_version == old_version + 1
    assert verify_password("replacement-driver-password", user.password_hash)
    assert accesses and all(access.invalidated_at is not None for access in accesses)
    assert initiation_audits == 2
    assert completion_audits == 1
    assert db_client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {old_session}"}
    ).status_code == 401
    assert db_client.post(
        "/api/v1/auth/login",
        json={"email": application.email, "password": "replacement-driver-password"},
    ).status_code == 200


def test_setup_denies_nonapproved_and_expired_authority(
    db_client, db_sessionmaker, settings
) -> None:
    application, admin_headers = _approve(db_client, db_sessionmaker, settings)
    initiated = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": str(uuid4())},
    )
    assert initiated.status_code == 201

    async def expire():
        async with db_sessionmaker() as session:
            setup = await session.get(
                DriverAccountSetupToken, UUID(initiated.json()["id"])
            )
            user = await session.get(User, application.user_id)
            assert setup is not None and user is not None
            token = synthetic_driver_account_setup_token(
                setup, settings, synthetic_test_authority=True
            )
            setup.created_at = datetime.now(UTC) - timedelta(seconds=2)
            setup.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            return token

    expired_token = asyncio.run(expire())
    expired = db_client.post(
        "/api/v1/auth/driver-account-setup/complete",
        json={"token": expired_token, "new_password": "replacement-driver-password"},
    )
    reissue = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": str(uuid4())},
    )
    assert expired.status_code == 400
    assert reissue.status_code == 201

    async def reject():
        async with db_sessionmaker() as session:
            setup = await session.get(
                DriverAccountSetupToken, UUID(reissue.json()["id"])
            )
            app = await session.get(DriverApplication, application.id)
            assert setup is not None and app is not None
            token = synthetic_driver_account_setup_token(
                setup, settings, synthetic_test_authority=True
            )
            app.status = "rejected"
            await session.commit()
            return token

    rejected_token = asyncio.run(reject())
    rejected = db_client.post(
        "/api/v1/auth/driver-account-setup/complete",
        json={"token": rejected_token, "new_password": "replacement-driver-password"},
    )
    rejected_reissue = db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": str(uuid4())},
    )
    assert rejected.status_code == 400
    assert rejected_reissue.status_code == 409


def test_driver_password_reset_requires_active_status_and_revokes_old_session(
    db_client, db_sessionmaker, settings
) -> None:
    invited = create_test_user(
        db_sessionmaker,
        email="pending-reset-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
        user_status=UserStatus.INVITED,
    )
    active = create_test_user(
        db_sessionmaker,
        email="active-reset-driver@example.com",
        password=PASSWORD,
        role=UserRole.DRIVER,
        user_status=UserStatus.ACTIVE,
    )

    async def scenario():
        async with db_sessionmaker() as session:
            invited_reset = await request_password_reset(
                session, email=invited.email, client_ip="127.0.0.31", settings=settings
            )
            active_reset = await request_password_reset(
                session, email=active.email, client_ip="127.0.0.32", settings=settings
            )
            await session.commit()
            assert invited_reset is None
            assert active_reset is not None
            locked_active = await session.get(User, active.id)
            assert locked_active is not None
            old_token, _ = create_access_token(
                locked_active.id,
                settings,
                session_version=locked_active.session_version,
            )
            reset_token = synthetic_password_reset_token(
                active_reset,
                locked_active,
                settings,
                synthetic_test_authority=True,
            )
            await complete_password_reset(
                session,
                token=reset_token,
                new_password="active-driver-reset-password",
                settings=settings,
            )
            await session.commit()
            with pytest.raises(AppError) as replay:
                await complete_password_reset(
                    session,
                    token=reset_token,
                    new_password="active-driver-replay-password",
                    settings=settings,
                )
            assert replay.value.code == "PASSWORD_RESET_INVALID"
            resets = list(
                (
                    await session.scalars(
                        select(PasswordResetToken).where(
                            PasswordResetToken.user_id.in_([invited.id, active.id])
                        )
                    )
                ).all()
            )
            refreshed = await session.get(User, active.id)
            assert refreshed is not None
            assert verify_password("active-driver-reset-password", refreshed.password_hash)
            return old_token, resets

    old_token, resets = asyncio.run(scenario())
    assert len(resets) == 1
    assert resets[0].user_id == active.id
    assert db_client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401


def test_concurrent_setup_completion_has_one_winner(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    application, admin_headers = _approve(
        postgis_db_client, postgis_db_sessionmaker, settings
    )
    initiated = postgis_db_client.post(
        f"/api/v1/admin/driver-applications/{application.id}/account-setup",
        headers=admin_headers,
        json={"client_request_id": str(uuid4())},
    )
    assert initiated.status_code == 201

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            setup = await session.get(
                DriverAccountSetupToken, UUID(initiated.json()["id"])
            )
            assert setup is not None
            token = synthetic_driver_account_setup_token(
                setup, settings, synthetic_test_authority=True
            )

        async def complete_once():
            async with postgis_db_sessionmaker() as session:
                try:
                    await complete_driver_account_setup(
                        session,
                        token=token,
                        new_password="concurrent-driver-password",
                        settings=settings,
                    )
                    await session.commit()
                    return "completed"
                except AppError as error:
                    await session.rollback()
                    return error.code

        outcomes = await asyncio.gather(complete_once(), complete_once())
        async with postgis_db_sessionmaker() as session:
            completions = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "auth.driver_account_setup.completed"
                    )
                )
                or 0
            )
        return outcomes, completions

    outcomes, completions = asyncio.run(exercise())
    assert sorted(outcomes) == ["DRIVER_ACCOUNT_SETUP_INVALID", "completed"]
    assert completions == 1


def test_concurrent_identical_setup_initiation_converges(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    application, _ = _approve(postgis_db_client, postgis_db_sessionmaker, settings)
    client_request_id = uuid4()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            admin_id = await session.scalar(
                select(User.id).where(
                    User.role == UserRole.ADMIN.value,
                    User.status == UserStatus.ACTIVE.value,
                )
            )
            assert admin_id is not None

        async def initiate_once():
            async with postgis_db_sessionmaker() as session:
                setup = await initiate_driver_account_setup(
                    session,
                    application_id=application.id,
                    actor_user_id=admin_id,
                    client_request_id=client_request_id,
                    settings=settings,
                )
                await session.commit()
                return setup.id

        setup_ids = await asyncio.gather(initiate_once(), initiate_once())
        async with postgis_db_sessionmaker() as session:
            setup_count = int(
                await session.scalar(
                    select(func.count(DriverAccountSetupToken.id)).where(
                        DriverAccountSetupToken.client_request_id == client_request_id
                    )
                )
                or 0
            )
            audit_count = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.driver_account_setup.initiated"
                    )
                )
                or 0
            )
        return setup_ids, setup_count, audit_count

    setup_ids, setup_count, audit_count = asyncio.run(exercise())
    assert setup_ids[0] == setup_ids[1]
    assert setup_count == 1
    assert audit_count == 1
