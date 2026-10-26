import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import select
from test_req217_reports import PASSWORD, START, owner_graph
from test_stored_files import FakeStorageProvider

from app.adapters.messaging import EmailSubmission
from app.models.notification import Notification
from app.models.organization import (
    AdvertiserOrganization,
    AdvertiserOrganizationNotificationPreference,
    OrganizationMembership,
)
from app.models.user import User
from app.services.campaign_report_delivery import (
    _claim,
    _pair,
    _put_pair,
    _ready,
    publish_campaign_report,
)
from app.services.campaign_reports import create_report
from app.services.email_delivery import process_email_notification


async def request_report(session, *, owner, campaign, kind, settings, storage, previous=None):
    return await create_report(
        session,
        actor_user_id=owner.id,
        campaigns=[campaign],
        request_id=uuid4(),
        request_fingerprint=uuid4().hex * 2,
        start=START,
        end=START + timedelta(days=7),
        kind=kind,
        settings=settings,
        storage=storage,
        now=datetime.now(UTC),
        rerun_of=previous,
    )


class CaptureEmail:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        return EmailSubmission(provider_message_id=f"local-{message.idempotency_key}")


@pytest.mark.parametrize("kind", ["weekly", "final", "custom"])
@pytest.mark.parametrize("email_enabled", [True, False])
def test_report_ready_notice_is_small_preference_governed_and_once_per_window(
    db_client, db_sessionmaker, settings, kind, email_enabled
):
    owner, organization, campaign = owner_graph(db_sessionmaker, f"notice-{kind}-{email_enabled}")
    storage, mail = FakeStorageProvider(), CaptureEmail()

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(
                AdvertiserOrganizationNotificationPreference(
                    advertiser_organization_id=organization.id,
                    transactional_email_enabled=email_enabled,
                )
            )
            report = await request_report(
                session,
                owner=owner,
                campaign=campaign,
                kind=kind,
                settings=settings,
                storage=storage,
            )
            await session.commit()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=report.id, storage=storage)
            == "ready"
        )
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=report.id, storage=storage)
            == "skipped"
        )
        async with db_sessionmaker() as session:
            rerun = await request_report(
                session,
                owner=owner,
                campaign=campaign,
                kind=kind,
                settings=settings,
                storage=storage,
                previous=report,
            )
            await session.commit()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=rerun.id, storage=storage)
            == "ready"
        )
        async with db_sessionmaker() as session:
            notices = list(
                await session.scalars(
                    select(Notification).where(Notification.type_key == "report_ready")
                )
            )
        assert len(notices) == (0 if kind == "custom" else 1 + int(email_enabled))
        for notice in notices:
            assert notice.recipient_user_id == owner.id
            assert notice.payload["report_kind"] == kind
            assert set(notice.payload) <= {
                "campaign_id",
                "report_kind",
                "advertiser_organization_id",
            }
            assert notice.dedupe_key.startswith(f"report_ready:v1:{campaign.id}:{kind}:")
            if notice.channel == "transactional_email":
                assert (
                    await process_email_notification(
                        db_sessionmaker,
                        notification_id=notice.id,
                        settings=settings,
                        email_adapter=mail,
                        now=datetime.now(UTC),
                    )
                    == "sent"
                )
        return notices

    asyncio.run(exercise())
    if kind != "custom":
        feed = db_client.get(
            "/api/v1/notifications", headers=auth_headers(db_client, owner.email, PASSWORD)
        )
        assert feed.status_code == 200, feed.text
        item = next(row for row in feed.json()["items"] if row["type_key"] == "report_ready")
        assert item["body"] == f"Your {kind} report for {campaign.name} is ready"
        assert item["action_url"] == f"/advertiser/campaigns/{campaign.id}/report"
        if email_enabled:
            assert len(mail.messages) == 1
            assert mail.messages[0].text_body.startswith(item["body"])
            assert f"/advertiser/campaigns/{campaign.id}/report" in mail.messages[0].text_body
            assert "driver" not in mail.messages[0].text_body.lower()


@pytest.mark.parametrize("inactive", ["member", "user", "company"])
def test_report_notice_recipient_must_still_be_active(db_sessionmaker, settings, inactive):
    owner, organization, campaign = owner_graph(db_sessionmaker, f"inactive-{inactive}")
    storage = FakeStorageProvider()

    async def exercise():
        async with db_sessionmaker() as session:
            report = await request_report(
                session,
                owner=owner,
                campaign=campaign,
                kind="weekly",
                settings=settings,
                storage=storage,
            )
            await session.commit()
            if inactive == "member":
                row = await session.scalar(
                    select(OrganizationMembership).where(OrganizationMembership.user_id == owner.id)
                )
                row.status = "disabled"
            elif inactive == "user":
                row = await session.get(User, owner.id)
                row.status = "suspended"
            else:
                row = await session.get(AdvertiserOrganization, organization.id)
                row.status = "suspended"
            await session.commit()
        assert (
            await publish_campaign_report(db_sessionmaker, report_id=report.id, storage=storage)
            == "ready"
        )
        async with db_sessionmaker() as session:
            assert not list(
                await session.scalars(
                    select(Notification).where(Notification.type_key == "report_ready")
                )
            )

    asyncio.run(exercise())


def test_lease_expiry_rolls_back_report_notices(db_sessionmaker, settings, monkeypatch):
    owner, _, campaign = owner_graph(db_sessionmaker, "notice-rollback")
    storage = FakeStorageProvider()

    async def exercise():
        async with db_sessionmaker() as session:
            report = await request_report(
                session,
                owner=owner,
                campaign=campaign,
                kind="weekly",
                settings=settings,
                storage=storage,
            )
            await session.commit()
        claimed, token = await _claim(db_sessionmaker, report.id)
        artifacts = _pair(claimed)
        await _put_pair(storage, artifacts)
        now = datetime.now(UTC)
        clocks = iter([now, now, now + timedelta(minutes=5)])

        async def clock(_session):
            return next(clocks)

        monkeypatch.setattr("app.services.campaign_report_delivery.database_clock", clock)
        assert (
            await _ready(
                db_sessionmaker,
                report_id=report.id,
                token=token,
                artifacts=artifacts,
                storage=storage,
            )
            == "skipped"
        )
        async with db_sessionmaker() as session:
            assert not list(
                await session.scalars(
                    select(Notification).where(Notification.type_key == "report_ready")
                )
            )

    asyncio.run(exercise())
