import asyncio
import html
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select
from test_driver_person_payee_onboarding import _register
from test_driver_vehicle_approval import _approved_applicant
from test_email_delivery import RecordingEmailAdapter

from app.core.observability import redact_log_message, scrub_observability_value
from app.models.driver_application import DriverApplication, DriverApplicationAccessToken
from app.models.notification import Notification
from app.services import driver_applications
from app.services.email_delivery import process_email_notification


@pytest.mark.parametrize("approved", [False, True])
def test_continuation_email_resolves_current_step_and_body_capability(
    db_client, db_sessionmaker, settings, approved, monkeypatch
):
    if approved:
        token, _, _ = _approved_applicant(
            db_client, db_sessionmaker, settings, suffix="continue-approved"
        )
    else:
        token, response = _register(db_client, db_sessionmaker, settings, suffix="continue-new")
        assert token not in response.text
    expected = "car" if approved else "details"

    async def deliver():
        async with db_sessionmaker() as session:
            access = await session.get(
                DriverApplicationAccessToken, driver_applications._access_token_id(token)
            )
            notice = await session.scalar(
                select(Notification).where(
                    Notification.payload["driver_application_access_id"].as_string()
                    == str(access.id)
                )
            )
            assert set(notice.payload) == {"driver_application_access_id"}
        adapter = RecordingEmailAdapter()
        assert (
            await process_email_notification(
                db_sessionmaker,
                notification_id=notice.id,
                settings=settings,
                email_adapter=adapter,
                now=datetime.now(UTC),
            )
            == "sent"
        )
        return access, adapter.messages[0]

    access, message = asyncio.run(deliver())
    assert (
        timedelta(hours=23, minutes=59)
        < access.expires_at - datetime.now(UTC)
        <= timedelta(hours=24)
    )
    url = html.unescape(re.search(r'href="([^"]+)"', message.html_body).group(1))
    parts = urlsplit(url)
    assert parse_qs(parts.query) == {"step": [expected]}
    assert parse_qs(parts.fragment) == {"application_access_token": [token]}
    assert "24 hours" in message.text_body and "enter this code" not in message.text_body
    continuation = db_client.post(
        "/api/v1/auth/driver-onboarding/continue?step=wrong",
        json={"application_access_token": token},
    )
    assert continuation.status_code == 200 and continuation.json()["step"] == expected
    assert set(continuation.json()) == {"step", "state", "changes_reason", "expires_at"}
    assert continuation.json()["state"] == ("car_needed" if approved else "details_needed")
    assert continuation.json()["changes_reason"] is None and token not in continuation.text
    assert token not in redact_log_message("action " + url)
    assert parts.netloc not in redact_log_message("action " + url)
    assert token not in str(scrub_observability_value({"application_access_token": token}))
    assert redact_log_message(token) == "[REDACTED]"

    class Clock(datetime):
        moment = access.expires_at - timedelta(microseconds=1)

        @classmethod
        def now(cls, tz=None):
            return cls.moment

    monkeypatch.setattr(driver_applications, "datetime", Clock)
    assert (
        db_client.post(
            "/api/v1/auth/driver-onboarding/continue", json={"application_access_token": token}
        ).status_code
        == 200
    )
    Clock.moment = access.expires_at
    expired = db_client.post(
        "/api/v1/auth/driver-onboarding/continue", json={"application_access_token": token}
    )
    invalid = db_client.post(
        "/api/v1/auth/driver-onboarding/continue",
        json={"application_access_token": token[:-1] + "!"},
    )
    assert expired.status_code == invalid.status_code == 404
    assert (
        expired.json()["error"]["code"]
        == invalid.json()["error"]["code"]
        == "ONBOARDING_ACCESS_INVALID"
    )


def test_renewal_preserves_old_expiry_and_revoked_terminal_access_is_generic(
    db_client,
    db_sessionmaker,
    settings,
):
    token, _ = _register(db_client, db_sessionmaker, settings, suffix="continue-renew")

    async def renew():
        async with db_sessionmaker() as session:
            old = await session.get(
                DriverApplicationAccessToken, driver_applications._access_token_id(token)
            )
            application = await session.get(DriverApplication, old.application_id)
            expiry = old.expires_at
            fresh = await driver_applications.renew_driver_application_access(
                session, email=application.email, settings=settings
            )
            fresh_token = driver_applications.synthetic_driver_application_access_token(
                fresh, settings, synthetic_test_authority=True
            )
            assert old.expires_at == expiry and old.invalidated_at is None
            await session.commit()
            return fresh_token, application.id

    fresh, application_id = asyncio.run(renew())
    path = "/api/v1/auth/driver-onboarding/continue"
    for capability in (token, fresh):
        assert (
            db_client.post(path, json={"application_access_token": capability}).status_code == 200
        )

    async def invalidate(terminal=False):
        async with db_sessionmaker() as session:
            if terminal:
                application = await session.get(DriverApplication, application_id)
                application.status = "rejected"
            else:
                access = await session.get(
                    DriverApplicationAccessToken, driver_applications._access_token_id(token)
                )
                access.invalidated_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(invalidate())
    revoked = db_client.post(path, json={"application_access_token": token})
    assert revoked.status_code == 404
    assert db_client.post(path, json={"application_access_token": fresh}).status_code == 200
    asyncio.run(invalidate(terminal=True))
    terminal = db_client.post(path, json={"application_access_token": fresh})
    assert terminal.status_code == 404
    assert revoked.json()["error"]["code"] == terminal.json()["error"]["code"]


def test_continuation_waits_for_application_before_locking_access(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
):
    from sqlalchemy import text

    from app.core.errors import AppError

    token, _ = _register(db_client, db_sessionmaker, settings, suffix="continue-race")

    async def exercise():
        async with db_sessionmaker() as writer, db_sessionmaker() as reader:
            access_id = driver_applications._access_token_id(token)
            access = await writer.get(DriverApplicationAccessToken, access_id)
            application = await writer.scalar(
                select(DriverApplication)
                .where(DriverApplication.id == access.application_id)
                .with_for_update()
            )
            waiting = asyncio.Event()
            original = reader.scalar

            async def observe(statement, *args, **kwargs):
                if statement.column_descriptions[0].get("entity") is DriverApplication:
                    waiting.set()
                return await original(statement, *args, **kwargs)

            monkeypatch.setattr(reader, "scalar", observe)

            async def continuation():
                with pytest.raises(AppError) as denied:
                    await driver_applications.continue_driver_application(
                        reader, token=token, settings=settings
                    )
                assert denied.value.code == "ONBOARDING_ACCESS_INVALID"
                await reader.rollback()

            task = asyncio.create_task(continuation())
            try:
                await asyncio.wait_for(waiting.wait(), 5)
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                # Same application -> access order as account setup invalidation.
                locked = await writer.scalar(
                    select(DriverApplicationAccessToken)
                    .where(DriverApplicationAccessToken.id == access_id)
                    .with_for_update()
                )
                locked.invalidated_at = datetime.now(UTC)
                application.status = "rejected"
                await writer.commit()
                await asyncio.wait_for(task, 5)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
