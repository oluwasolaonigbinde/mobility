import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_driver_profile, create_test_user
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_file_scanning import advertiser_with_org, confirm_png
from test_file_scanning import file_boundaries as scanning_boundaries

from app.core.errors import AppError
from app.db import outbox_session
from app.db.outbox_session import OutboxSession
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.models.stored_file import StoredFile
from app.models.user import UserRole
from app.schemas.driver_applications import DriverApplicationCreate
from app.schemas.payees import BankAccountPayoutVerificationCreate
from app.services.email_templates import render_email_template
from app.services.notifications import create_notification
from app.services.payees import verification_reference_hash

file_boundaries = scanning_boundaries


@pytest.mark.parametrize("reference", ["1", "AB 12-34", "₦50 / bank ref", "BANK-\ue000", "x" * 512])
def test_bank_transfer_reference_accepts_real_bank_formats(reference):
    assert (
        verification_reference_hash(f"  {reference}  ")
        == hashlib.sha256(reference.encode()).hexdigest()
    )
    assert BankAccountPayoutVerificationCreate(verification_reference=reference)


@pytest.mark.parametrize("reference", ["", "  ", "x" * 513, "bank\nref", "x\x00y", "x\u200by"])
def test_bank_transfer_reference_rejects_unusable_input(reference):
    with pytest.raises(AppError) as error:
        verification_reference_hash(reference)
    assert error.value.code == "VERIFICATION_REFERENCE_INVALID"
    assert reference not in str(error.value) if reference else True


@pytest.mark.parametrize("city", [None, "", "   "])
def test_new_application_requires_city(city):
    with pytest.raises(ValidationError):
        DriverApplicationCreate(email="new@example.test", full_name="New Driver", service_city=city)


def test_new_application_trims_city_and_requires_field():
    assert (
        DriverApplicationCreate(
            email="new@example.test", full_name="New Driver", service_city=" Abuja "
        ).service_city
        == "Abuja"
    )
    with pytest.raises(ValidationError):
        DriverApplicationCreate(email="new@example.test", full_name="New Driver")


def test_transactional_jobs_escape_only_outer_commit_and_survive_session_reuse(
    db_sessionmaker,
    settings,
    monkeypatch,
):
    deliveries = []

    async def record(_settings, jobs):
        for kind, identity in jobs:
            async with db_sessionmaker() as read:
                assert await read.get(Notification, identity) is not None
            deliveries.append((kind, identity))

    monkeypatch.setattr(outbox_session, "enqueue_outbox_jobs", record)
    factory = async_sessionmaker(
        db_sessionmaker.kw["bind"],
        class_=OutboxSession,
        expire_on_commit=False,
        info={"enqueue_settings": settings},
    )
    user = create_test_user(db_sessionmaker, email="outbox@example.test", password="test-password")

    async def notice(session, key):
        return await create_notification(
            session,
            recipient_user_id=user.id,
            type_key=NotificationType.CAMPAIGN_APPROVED,
            payload={},
            dedupe_key=key,
            channel=NotificationChannel.TRANSACTIONAL_EMAIL,
        )

    async def run():
        async with factory() as session:
            await notice(session, "outer-rollback")
            assert not deliveries  # create_notification committed a nested savepoint
            await session.rollback()
            await session.commit()
            assert not deliveries
            kept = await notice(session, "kept")
            with pytest.raises(RuntimeError):
                async with session.begin_nested():
                    await notice(session, "inner-rollback")
                    raise RuntimeError("rollback inner only")
            assert not deliveries
            await session.commit()
            assert deliveries == [("deliver_email", kept.id)]
            await session.commit()
            assert len(deliveries) == 1
            await notice(session, "dedupe")
            await notice(session, "dedupe")
            with pytest.raises(AppError):
                await create_notification(
                    session,
                    recipient_user_id=user.id,
                    type_key=NotificationType.CAMPAIGN_APPROVED,
                    payload={"changed": True},
                    dedupe_key="dedupe",
                    channel=NotificationChannel.TRANSACTIONAL_EMAIL,
                )
            await session.commit()
            assert len(deliveries) == 2

    asyncio.run(run())


def test_confirmation_registers_scan_and_immediate_job_preserves_backoff(
    db_client,
    db_sessionmaker,
    settings,
    file_boundaries,
    monkeypatch,
):
    from app.jobs import file_scanning
    from app.services.stored_files import scan_stored_file

    storage, scanner = file_boundaries
    user, _ = advertiser_with_org(db_sessionmaker, "immediate-scan@example.test")
    from app.db.session import get_session

    queued = []
    factory = async_sessionmaker(
        db_sessionmaker.kw["bind"],
        class_=OutboxSession,
        expire_on_commit=False,
        info={"enqueue_settings": settings},
    )

    async def committed_jobs(_settings, jobs):
        for kind, identity in jobs:
            async with db_sessionmaker() as read:
                assert await read.get(StoredFile, identity) is not None
            queued.append((kind, identity))

    async def session_dependency():
        async with factory() as session:
            yield session

    monkeypatch.setattr(outbox_session, "enqueue_outbox_jobs", committed_jobs)
    db_client.app.dependency_overrides[get_session] = session_dependency
    stored = confirm_png(db_client, storage, user.email)
    assert queued == [("scan_file", UUID(stored["id"]))]
    monkeypatch.setattr(file_scanning, "build_storage_provider", lambda _settings: storage)
    monkeypatch.setattr(file_scanning, "build_malware_scanner", lambda _settings: scanner)
    context = {"sessionmaker": db_sessionmaker, "settings": settings}

    async def run():
        async with db_sessionmaker() as locked:
            await locked.scalar(
                select(StoredFile).where(StoredFile.id == UUID(stored["id"])).with_for_update()
            )
            assert await file_scanning.scan_file(context, stored["id"]) is None
            assert scanner.calls == 0
        scanner.unavailable = True
        assert await file_scanning.scan_file(context, stored["id"]) == "error"
        assert scanner.calls == 1
        assert await file_scanning.scan_file(context, stored["id"]) == "error"
        assert scanner.calls == 1
        async with db_sessionmaker() as session:
            row = await session.get(StoredFile, UUID(stored["id"]))
            row.next_scan_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        scanner.unavailable = False
        assert await file_scanning.scan_file(context, stored["id"]) == "clean"
        assert scanner.calls == 2
        assert await file_scanning.scan_file(context, stored["id"]) == "clean"
        assert scanner.calls == 2
        async with db_sessionmaker() as session:
            assert (
                await scan_stored_file(session, file_id=uuid4(), storage=storage, scanner=scanner)
                is None
            )

    asyncio.run(run())


def test_broker_failure_is_bounded_and_durable_email_remains_pending(
    db_sessionmaker, settings, monkeypatch
):
    from app.core import outbox_enqueue

    class StalledPool:
        async def enqueue_job(self, *_args, **_kwargs):
            await asyncio.sleep(60)

    configured = settings.model_copy(update={"redis_url": "redis://outbox-test/0"})
    monkeypatch.setitem(outbox_enqueue._pools, configured.redis_url, StalledPool())
    monkeypatch.setattr(outbox_enqueue, "ENQUEUE_TIMEOUT_SECONDS", 0.01)
    user = create_test_user(
        db_sessionmaker, email="broker-down@example.test", password="test-password"
    )

    async def run():
        async with OutboxSession(
            bind=db_sessionmaker.kw["bind"],
            expire_on_commit=False,
            info={"enqueue_settings": configured},
        ) as session:
            row = await create_notification(
                session,
                recipient_user_id=user.id,
                type_key=NotificationType.CAMPAIGN_APPROVED,
                payload={},
                dedupe_key="broker-down",
                channel=NotificationChannel.TRANSACTIONAL_EMAIL,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            assert (await session.get(Notification, row.id)).status == "pending"

    asyncio.run(run())


def test_email_copy_has_escaped_clickable_links_and_no_bare_setup_token():
    rendered = render_email_template(
        "campaign_approved",
        "v1",
        {
            "campaign_name": "<script>hello</script>",
            "action_url": "https://example.test/campaign?a=1&b=2",
        },
    )
    assert "<script>" not in rendered.html_body
    assert 'href="https://example.test/campaign?a=1&amp;b=2"' in rendered.html_body
    setup = render_email_template("driver_account_setup_requested", "v1", {"setup_action": None})
    assert "Ask Terrax Media to resend" in setup.text_body
    assert "href=" not in setup.html_body


def test_summary_endpoints_enforce_roles_and_zero_counts(db_client, db_sessionmaker):
    admin = create_test_user(
        db_sessionmaker, email="badge-admin@example.test", password="test-password"
    )
    driver = create_test_user(
        db_sessionmaker,
        email="badge-driver@example.test",
        password="test-password",
        role=UserRole.DRIVER,
    )
    create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    ah = auth_headers(db_client, admin.email, "test-password")
    dh = auth_headers(db_client, driver.email, "test-password")
    badges = db_client.get("/api/v1/admin/badge-summary", headers=ah)
    assert badges.status_code == 200, badges.text
    assert badges.json()["total"] == 0
    # S16/D114 removes the late-data queue; S32/D109 removes pending spot checks.
    assert len(badges.json()["source_counts"]) == 16
    assert db_client.get("/api/v1/admin/badge-summary", headers=dh).status_code == 403
    assert db_client.get("/api/v1/driver/current-job", headers=ah).status_code == 403
    current = db_client.get("/api/v1/driver/current-job", headers=dh)
    assert current.status_code == 200, current.text
    assert current.json()["assignment"] is None
    # S22/D116 removes deactivated; S23/D118 replaces stored completed with read finished.
    assert current.json()["counts"] == {
        key: 0
        for key in [
            "offered",
            "accepted",
            "active",
            "declined",
            "expired",
            "cancelled",
            "finished",  # S23/D118: derived read status, never stored completed.
        ]
    }


def test_offer_without_driver_city_has_actionable_error(db_sessionmaker, settings):
    from payout_fixtures import build_offered_graph, materialize_offer

    from app.models.driver import DriverProfile

    graph = build_offered_graph(db_sessionmaker, "req180-city")

    async def remove_city():
        async with db_sessionmaker() as session:
            profile = await session.get(DriverProfile, graph.profile.id)
            profile.service_city = None
            await session.commit()

    asyncio.run(remove_city())
    with pytest.raises(AppError) as error:
        materialize_offer(db_sessionmaker, settings, graph)
    assert error.value.code == "DRIVER_SERVICE_AREA_REQUIRED"
    assert error.value.status_code == 409
    assert error.value.message == "Add the driver's city before sending a job offer"
