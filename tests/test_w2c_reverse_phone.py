import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_driver_profile, create_test_user
from sqlalchemy import event, func, select

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.contact import PhoneVerificationChallenge
from app.models.driver import DriverProfile
from app.models.user import User, UserRole


def setup_phone(db_client, db_sessionmaker, settings):
    driver = create_test_user(
        db_sessionmaker, email="reverse-driver@example.com", role=UserRole.DRIVER
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    headers = auth_headers(db_client, driver.email, "long-secure-password")
    saved = db_client.put(
        "/api/v1/driver/contact/phone", headers=headers, json={"phone": "+447700900101"}
    )
    assert saved.status_code == 200
    settings.phone_verification_terrax_number = "+2347068369842"
    return driver, headers


def test_driver_can_request_a_code_that_staff_cannot_read(
    db_client, db_sessionmaker, settings, caplog
):
    driver, headers = setup_phone(db_client, db_sessionmaker, settings)
    response = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["code"]) == 6
    assert response.headers["cache-control"] == "no-store"
    challenge = response.json()
    admin = create_test_user(db_sessionmaker, email="reverse-admin@example.com")
    staff = auth_headers(db_client, admin.email, "long-secure-password")
    profile = db_client.get("/api/v1/driver/profile", headers=headers).json()
    path = f"/api/v1/admin/drivers/{profile['id']}/phone-verification"
    work = db_client.get("/api/v1/admin/phone-verification-challenges", headers=staff)
    assert work.status_code == 200
    assert challenge["code"] not in work.text
    assert "code_hash" not in work.text
    assert work.json()["total"] == 1
    malformed = db_client.post(
        path,
        headers=staff,
        json={"challenge_id": challenge["id"], "code": challenge["code"], "sender_phone": "x"},
    )
    assert malformed.status_code == 422
    assert challenge["code"] not in malformed.text
    forbidden = db_client.post(
        path,
        headers=headers,
        json={
            "challenge_id": challenge["id"],
            "code": challenge["code"],
            "sender_phone": "+447700900101",
        },
    )
    assert forbidden.status_code == 403
    assert challenge["code"] not in forbidden.text
    failed = db_client.post(
        path,
        headers=staff,
        json={
            "challenge_id": challenge["id"],
            "code": challenge["code"],
            "sender_phone": "+447700900102",
        },
    )
    assert failed.status_code == 400
    assert challenge["code"] not in failed.text
    success = db_client.post(
        path,
        headers=staff,
        json={
            "challenge_id": challenge["id"],
            "code": challenge["code"],
            "sender_phone": "+44 7700 900101",
        },
    )
    assert success.status_code == 200
    assert success.json()["verified"] is True
    assert challenge["code"] not in success.text
    replay = db_client.post(
        path,
        headers=staff,
        json={
            "challenge_id": challenge["id"],
            "code": challenge["code"],
            "sender_phone": "+447700900101",
        },
    )
    assert replay.status_code == 409
    assert challenge["code"] not in replay.text
    assert challenge["code"] not in caplog.text
    assert (
        db_client.get("/api/v1/admin/phone-verification-challenges", headers=staff).json()["total"]
        == 0
    )

    async def stored():
        async with db_sessionmaker() as session:
            row = await session.get(
                PhoneVerificationChallenge, __import__("uuid").UUID(challenge["id"])
            )
            assert row.code_hash != challenge["code"] and len(row.code_hash) == 64
            assert row.verified_by_user_id == admin.id
            audits = list(await session.scalars(select(AuditEvent)))
            payload = json.dumps([event.event_metadata for event in audits])
            assert challenge["code"] not in payload
            assert "+447700900101" not in payload
            assert row.attempt_count == 2

    asyncio.run(stored())
    reissue = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers)
    assert reissue.status_code == 409
    assert reissue.json()["error"]["code"] == "PHONE_ALREADY_VERIFIED"
    assert challenge["code"] not in reissue.text


@pytest.mark.parametrize("mode", ["expired", "exhausted", "changed_phone", "foreign_challenge"])
def test_reverse_verification_fails_closed(
    postgis_db_client, postgis_db_sessionmaker, settings, mode
):
    db_client, db_sessionmaker = postgis_db_client, postgis_db_sessionmaker
    driver, headers = setup_phone(db_client, db_sessionmaker, settings)
    challenge = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).json()
    admin = create_test_user(db_sessionmaker, email="reverse-negative-admin@example.com")
    staff = auth_headers(db_client, admin.email, "long-secure-password")
    profile = db_client.get("/api/v1/driver/profile", headers=headers).json()
    path = f"/api/v1/admin/drivers/{profile['id']}/phone-verification"
    if mode == "expired":

        async def expire():
            async with db_sessionmaker() as session:
                row = await session.get(
                    PhoneVerificationChallenge, __import__("uuid").UUID(challenge["id"])
                )
                row.created_at = datetime.now(UTC) - timedelta(hours=1)
                row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
                await session.commit()

        asyncio.run(expire())
        if mode == "expired":
            reloaded = db_client.get("/api/v1/driver/contact", headers=headers)
            assert reloaded.status_code == 200
            assert reloaded.json()["challenge"]["status"] == "expired"
            assert challenge["code"] not in reloaded.text
    if mode == "changed_phone":
        assert (
            db_client.put(
                "/api/v1/driver/contact/phone", headers=headers, json={"phone": "+447700900103"}
            ).status_code
            == 200
        )
        assert (
            db_client.get("/api/v1/admin/phone-verification-challenges", headers=staff).json()[
                "total"
            ]
            == 0
        )
    if mode == "foreign_challenge":
        challenge["id"] = str(uuid4())
    payload = {
        "challenge_id": challenge["id"],
        "code": challenge["code"],
        "sender_phone": "+447700900101",
    }
    if mode == "exhausted":

        async def persisted_attempts(count):
            from app.models.contact import DriverPhoneVersion

            async with db_sessionmaker() as session:
                row = await session.get(PhoneVerificationChallenge, UUID(challenge["id"]))
                assert row.max_attempts == settings.phone_verification_max_code_attempts
                assert row.attempt_count == count
                assert row.status == ("exhausted" if count == row.max_attempts else "pending")
                assert row.verified_at is None and row.verified_by_user_id is None
                assert (
                    await session.get(DriverPhoneVersion, row.phone_version_id)
                ).verified_at is None
                failures = list(
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action == "admin.phone_verification.failed"
                        )
                    )
                )
                assert len(failures) == count
                assert sorted(a.event_metadata["attempt_count"] for a in failures) == list(
                    range(1, count + 1)
                )
                assert all(
                    a.event_metadata == {"attempt_count": a.event_metadata["attempt_count"]}
                    and a.actor_user_id == admin.id
                    and a.entity_id == challenge["id"]
                    and a.entity_type == "phone_verification_challenge"
                    for a in failures
                )
                assert (
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.action == "admin.phone_verification.recorded"
                        )
                    )
                    == 0
                )

        malformed = db_client.post(path, headers=staff, json={**payload, "sender_phone": "x"})
        assert malformed.status_code == 422 and challenge["code"] not in malformed.text
        missing = db_client.post(
            f"/api/v1/admin/drivers/{uuid4()}/phone-verification", headers=staff, json=payload
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "DRIVER_PROFILE_NOT_FOUND"
        asyncio.run(persisted_attempts(0))
        wrong_code = "000000" if challenge["code"] != "000000" else "111111"
        for count in range(1, settings.phone_verification_max_code_attempts + 1):
            bad = (
                {**payload, "sender_phone": "abcdefgh"}
                if count == 1
                else {**payload, "sender_phone": "+447700900102"}
                if count == 2
                else {**payload, "code": wrong_code}
            )
            failure = db_client.post(path, headers=staff, json=bad)
            assert failure.status_code == 400
            assert failure.json()["error"]["code"] == "PHONE_VERIFICATION_MISMATCH"
            assert challenge["code"] not in failure.text and bad["sender_phone"] not in failure.text
            asyncio.run(persisted_attempts(count))
    denied = db_client.post(path, headers=staff, json=payload)
    assert denied.status_code == 409
    if mode == "exhausted":
        assert denied.json()["error"]["code"] == "PHONE_CHALLENGE_USED"
        asyncio.run(persisted_attempts(settings.phone_verification_max_code_attempts))
    assert challenge["code"] not in denied.text
    state = db_client.get("/api/v1/driver/contact", headers=headers).json()
    assert state["phone"]["verified"] is False


def test_request_limit_survives_number_changes_and_live_retry_converges(
    db_client, db_sessionmaker, settings
):
    _, headers = setup_phone(db_client, db_sessionmaker, settings)
    settings.phone_verification_request_max_attempts = 2
    first = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).json()
    retry = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).json()
    assert first == retry
    for suffix, expected in [("102", 200), ("103", 429)]:
        assert (
            db_client.put(
                "/api/v1/driver/contact/phone",
                headers=headers,
                json={"phone": f"+447700900{suffix}"},
            ).status_code
            == 200
        )
        result = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers)
        assert result.status_code == expected


@pytest.mark.parametrize("terminal", ["expired", "superseded", "verified"])
def test_phone_queue_filters_current_driver_and_paginates_without_secrets(
    db_client, db_sessionmaker, settings, monkeypatch, terminal
):
    _, headers = setup_phone(db_client, db_sessionmaker, settings)
    first = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).json()
    profile_id = db_client.get("/api/v1/driver/profile", headers=headers).json()["id"]
    other = create_test_user(db_sessionmaker, email="queue-other@example.com", role=UserRole.DRIVER)
    create_test_driver_profile(db_sessionmaker, user_id=other.id)
    other_headers = auth_headers(db_client, other.email, "long-secure-password")
    saved = db_client.put(
        "/api/v1/driver/contact/phone", headers=other_headers, json={"phone": "+447700900104"}
    )
    assert saved.status_code == 200
    # Stagger issuance so expiring the first request leaves the second current.
    expires = datetime.fromisoformat(first["expires_at"].replace("Z", "+00:00"))
    now = expires - timedelta(seconds=1)

    async def clock(_):
        return now

    monkeypatch.setattr("app.services.contacts.database_clock", clock)
    second_response = db_client.post(
        "/api/v1/driver/contact/phone-verification", headers=other_headers
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    admin = create_test_user(db_sessionmaker, email="queue-admin@example.com")
    staff = auth_headers(db_client, admin.email, "long-secure-password")
    scoped = f"/api/v1/admin/phone-verification-challenges?driver_profile_id={profile_id}&limit=1"
    page = db_client.get(scoped, headers=staff)
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert [row["id"] for row in page.json()["items"]] == [first["id"]]
    beyond = db_client.get(scoped + "&offset=1", headers=staff).json()
    assert beyond["total"] == 1 and beyond["items"] == []
    assert first["code"] not in page.text and second["code"] not in page.text
    assert "code_hash" not in page.text
    if terminal == "expired":
        now = expires
    elif terminal == "superseded":
        changed = db_client.put(
            "/api/v1/driver/contact/phone", headers=headers, json={"phone": "+447700900105"}
        )
        assert changed.status_code == 200
    else:
        verified = db_client.post(
            f"/api/v1/admin/drivers/{profile_id}/phone-verification",
            headers=staff,
            json={
                "challenge_id": first["id"],
                "code": first["code"],
                "sender_phone": "+447700900101",
            },
        )
        assert verified.status_code == 200
    hidden = db_client.get(scoped, headers=staff).json()
    assert hidden["total"] == 0 and hidden["items"] == []
    remaining = db_client.get("/api/v1/admin/phone-verification-challenges", headers=staff)
    assert remaining.status_code == 200
    assert remaining.json()["total"] == 1
    assert [row["id"] for row in remaining.json()["items"]] == [second["id"]]
    assert first["code"] not in remaining.text and second["code"] not in remaining.text


@pytest.mark.parametrize(
    "environment,number,operator,name,notice,available",
    [
        ("test", "", False, "", "", False),
        ("test", "+2347068369842", False, "", "", True),
        ("development", "+2347074200080", True, "Somto", "approved-reference", False),
        ("production", "+2347074200080", False, "Somto", "approved-reference", False),
        ("production", "+2347074200080", True, "", "approved-reference", False),
        ("production", "+2347074200080", True, "Somto", "", False),
        ("production", "+447700900999", True, "Somto", "approved-reference", False),
        ("production", "+2347074200080", True, "Somto", "approved-reference", True),
    ],
)
def test_configuration_gates(environment, number, operator, name, notice, available, settings):
    from app.services.contacts import phone_verification_available

    configured = settings.model_copy(
        update={
            "environment": environment,
            "phone_verification_terrax_number": number,
            "phone_operator_external_approved": operator,
            "phone_operator_name": name,
            "phone_whatsapp_notice_approval_reference": notice,
        }
    )
    assert phone_verification_available(configured) is available


def test_missing_config_denies_issuance_and_removes_availability(
    db_client, db_sessionmaker, settings
):
    _, headers = setup_phone(db_client, db_sessionmaker, settings)
    settings.phone_verification_terrax_number = ""
    assert (
        db_client.get("/api/v1/driver/contact", headers=headers).json()["verification_available"]
        is False
    )
    assert (
        db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).status_code
        == 503
    )


@pytest.mark.parametrize("mode", ["request", "record", "edit_admin_first", "edit_driver_first"])
def test_postgres_phone_requests_records_and_account_edits_serialize(
    postgis_db_client, postgis_db_sessionmaker, settings, mode
):
    from app.schemas.users import UserUpdate
    from app.services.contacts import (
        driver_phone_challenge_code,
        record_phone_verification,
        request_phone_verification,
    )
    from app.services.users import update_user

    def assign_ids(_mapper, _connection, user):
        driver_first = mode == "edit_driver_first"
        user.id = UUID(int=1 if (user.role == UserRole.DRIVER) == driver_first else 2)

    event.listen(User, "before_insert", assign_ids)
    try:
        driver, _ = setup_phone(postgis_db_client, postgis_db_sessionmaker, settings)
        admin = create_test_user(postgis_db_sessionmaker, email="race-phone-admin@example.com")
    finally:
        event.remove(User, "before_insert", assign_ids)

    async def scenario():
        async with postgis_db_sessionmaker() as session:
            profile_id = await session.scalar(
                select(DriverProfile.id).where(DriverProfile.user_id == driver.id)
            )
            challenge = await request_phone_verification(
                session, user_id=driver.id, settings=settings
            )
            await session.commit()
            code = driver_phone_challenge_code(challenge, settings)
        barrier = asyncio.Barrier(2)

        async def worker(index):
            async with postgis_db_sessionmaker() as session:
                await barrier.wait()
                try:
                    if mode == "request":
                        result = str(
                            (
                                await request_phone_verification(
                                    session, user_id=driver.id, settings=settings
                                )
                            ).id
                        )
                    elif mode.startswith("edit") and index:
                        await update_user(
                            session,
                            driver.id,
                            UserUpdate(phone="+447700900102"),
                            actor_user_id=admin.id,
                            actor_session_version=admin.session_version,
                        )
                        result = "edited"
                    else:
                        await record_phone_verification(
                            session,
                            driver_profile_id=profile_id,
                            actor_user_id=admin.id,
                            challenge_id=challenge.id,
                            code=code,
                            sender_phone="+447700900101",
                            settings=settings,
                        )
                        result = "verified"
                    await session.commit()
                    return result
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        results = await asyncio.wait_for(asyncio.gather(worker(0), worker(1)), timeout=15)
        if mode == "request":
            assert results == [str(challenge.id)] * 2
        elif mode == "record":
            assert sorted(results) == ["PHONE_CHALLENGE_USED", "verified"]
        else:
            assert "edited" in results and any(
                result in {"verified", "PHONE_VERIFICATION_MISMATCH"} for result in results
            )
        async with postgis_db_sessionmaker() as session:
            assert await session.scalar(select(func.count(PhoneVerificationChallenge.id))) == 1

    asyncio.run(scenario())


def test_restoring_a_phone_after_staff_edit_creates_unverified_version(
    db_client, db_sessionmaker, settings
):
    from app.models.contact import DriverPhoneVersion, WhatsappConsent
    from app.schemas.users import UserUpdate
    from app.services.users import update_user

    driver, headers = setup_phone(db_client, db_sessionmaker, settings)
    admin = create_test_user(db_sessionmaker, email="phone-restore-admin@example.com")

    async def change():
        async with db_sessionmaker() as session:
            original = await session.scalar(select(DriverPhoneVersion))
            original.verified_at = datetime.now(UTC)
            consent = WhatsappConsent(
                driver_profile_id=original.driver_profile_id,
                phone_version_id=original.id,
                version=1,
                purpose="campaign_assignment",
                notice_version="synthetic-approved-notice",
                granted_by_user_id=driver.id,
                granted_at=datetime.now(UTC),
            )
            session.add(consent)
            await session.commit()
        async with db_sessionmaker() as session:
            await update_user(
                session,
                driver.id,
                UserUpdate(phone="+447700900102"),
                actor_user_id=admin.id,
                actor_session_version=admin.session_version,
            )
            await session.commit()

    asyncio.run(change())
    restored = db_client.put(
        "/api/v1/driver/contact/phone", headers=headers, json={"phone": "+447700900101"}
    )
    assert restored.status_code == 200
    assert restored.json()["version"] == 2 and restored.json()["verified"] is False
    assert (
        db_client.get("/api/v1/driver/contact", headers=headers).json()["phone"]["verified"]
        is False
    )

    async def inspect():
        async with db_sessionmaker() as session:
            assert (await session.get(User, driver.id)).phone == "+447700900101"
            assert (await session.scalar(select(WhatsappConsent))).withdrawn_at is not None

    asyncio.run(inspect())

    async def clear_saved_phone():
        async with db_sessionmaker() as session:
            await update_user(
                session,
                driver.id,
                UserUpdate(phone=None),
                actor_user_id=admin.id,
                actor_session_version=admin.session_version,
            )
            await session.commit()

    asyncio.run(clear_saved_phone())
    denied = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "PHONE_VERSION_REQUIRED"
    assert db_client.get("/api/v1/driver/contact", headers=headers).json()["phone"] is None


def test_staff_cannot_verify_phone_for_inactive_driver(db_client, db_sessionmaker, settings):
    from app.models.contact import DriverPhoneVersion
    from app.models.user import UserStatus

    driver, headers = setup_phone(db_client, db_sessionmaker, settings)
    challenge = db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).json()
    profile = db_client.get("/api/v1/driver/profile", headers=headers).json()
    admin = create_test_user(db_sessionmaker, email="reverse-inactive-admin@example.com")
    staff = auth_headers(db_client, admin.email, "long-secure-password")

    async def disable():
        async with db_sessionmaker() as session:
            user = await session.get(User, driver.id)
            user.status = UserStatus.DISABLED
            await session.commit()

    asyncio.run(disable())
    denied = db_client.post(
        f"/api/v1/admin/drivers/{profile['id']}/phone-verification",
        headers=staff,
        json={
            "challenge_id": challenge["id"],
            "code": challenge["code"],
            "sender_phone": "+447700900101",
        },
    )
    assert denied.status_code == 404
    assert challenge["code"] not in denied.text
    assert (
        db_client.post("/api/v1/driver/contact/phone-verification", headers=headers).status_code
        == 403
    )

    async def inspect():
        async with db_sessionmaker() as session:
            phone = await session.scalar(select(DriverPhoneVersion))
            assert phone.verified_at is None
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.phone_verification.recorded"
                    )
                )
                == 0
            )

    asyncio.run(inspect())
