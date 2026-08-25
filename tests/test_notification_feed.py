import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
    fetch_audit_events,
)
from sqlalchemy import func, select
from starlette import status as http_status

from app.api.v1.notifications import notification_feed_response
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.notification import Notification, NotificationChannel, NotificationType
from app.models.organization import MembershipRole, MembershipStatus, OrganizationMembership
from app.models.user import UserRole
from app.services.notifications import create_notification, notification_dedupe_fingerprint
from app.services.organizations import get_notification_preference, update_notification_preference

PASSWORD = "long-secure-password"


@pytest.mark.parametrize(
    ("type_key", "title", "body"),
    [
        (
            NotificationType.ACTIVITY_FLOOR_BREACHED,
            "Verified activity below floor",
            "Your verified activity was below the configured weekly floor. "
            "Operations will review the assignment.",
        ),
        (
            NotificationType.ACTIVITY_FLOOR_RECOVERED,
            "Verified activity recovered",
            "Your verified activity has recovered to the configured weekly floor.",
        ),
        (
            NotificationType.ASSIGNMENT_INACTIVE,
            "Assignment inactive",
            "No verified activity was recorded for this assignment for seven "
            "consecutive days. Operations will review it.",
        ),
        (
            NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED,
            "Assignment activity resumed",
            "Verified activity resumed for this assignment. The operations flag "
            "has been recovered.",
        ),
    ],
)
def test_activity_notification_feed_copy_is_truthful(type_key, title, body) -> None:
    notice = Notification(
        id=uuid4(),
        recipient_user_id=uuid4(),
        type_key=type_key.value,
        channel=NotificationChannel.IN_APP.value,
        payload={"activity_flag_id": "private-flag", "analytics_source": "private"},
        dedupe_fingerprint="a" * 64,
        created_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
    )

    rendered = notification_feed_response(notice)

    assert rendered.title == title
    assert rendered.body == body
    assert "private" not in rendered.body


def _insert_notice(
    db_sessionmaker, *, recipient_user_id, key: str, created_at: datetime
) -> Notification:
    async def insert() -> Notification:
        payload = {"fraud_flag_id": "private-flag", "internal_token": "do-not-return"}
        async with db_sessionmaker() as session:
            notice = Notification(
                recipient_user_id=recipient_user_id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v1",
                channel=NotificationChannel.IN_APP.value,
                payload=payload,
                dedupe_key=key,
                dedupe_fingerprint=notification_dedupe_fingerprint(
                    recipient_user_id=recipient_user_id,
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    template_version="v1",
                    channel=NotificationChannel.IN_APP,
                    payload=payload,
                ),
                created_at=created_at,
                delivered_at=created_at,
            )
            session.add(notice)
            await session.commit()
            return notice

    return asyncio.run(insert())


def test_notification_creator_replays_exactly_rejects_changed_facts_and_freezes_evidence(
    db_sessionmaker,
) -> None:
    recipient = create_test_user(db_sessionmaker, email="notice@example.com", role=UserRole.DRIVER)

    async def run() -> None:
        async with db_sessionmaker() as session:
            first = await create_notification(
                session,
                recipient_user_id=recipient.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"trip_session_id": "trip", "fraud_flag_id": "flag"},
                dedupe_key="same-fact",
            )
            replay = await create_notification(
                session,
                recipient_user_id=recipient.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": "flag", "trip_session_id": "trip"},
                dedupe_key="same-fact",
            )
            assert first.id == replay.id
            assert first.status == "sent"
            assert first.sent_at is not None
            assert first.delivered_at is None
            assert first.provider_message_id is None
            with pytest.raises(AppError) as conflict:
                await create_notification(
                    session,
                    recipient_user_id=recipient.id,
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    payload={"fraud_flag_id": "changed", "trip_session_id": "trip"},
                    dedupe_key="same-fact",
                )
            assert conflict.value.code == "NOTIFICATION_DEDUPE_CONFLICT"
            await session.commit()

        async with db_sessionmaker() as session:
            notice = await session.scalar(select(Notification))
            assert notice is not None
            notice.payload["fraud_flag_id"] = "mutated"
            with pytest.raises(ValueError, match="immutable"):
                await session.commit()
            await session.rollback()

    asyncio.run(run())


def test_notification_orm_defaults_are_channel_aware(db_sessionmaker) -> None:
    recipient = create_test_user(db_sessionmaker, email="orm-notice@example.com")

    async def run() -> None:
        async with db_sessionmaker() as session:
            in_app_payload = {"fraud_flag_id": "orm-in-app"}
            email_payload = {"fraud_flag_id": "orm-email"}
            in_app = Notification(
                recipient_user_id=recipient.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v1",
                channel=NotificationChannel.IN_APP,
                payload=in_app_payload,
                dedupe_key="orm-in-app",
                dedupe_fingerprint=notification_dedupe_fingerprint(
                    recipient_user_id=recipient.id,
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    template_version="v1",
                    channel=NotificationChannel.IN_APP,
                    payload=in_app_payload,
                ),
            )
            email = Notification(
                recipient_user_id=recipient.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED.value,
                template_version="v1",
                channel=NotificationChannel.TRANSACTIONAL_EMAIL,
                payload=email_payload,
                dedupe_key="orm-email",
                dedupe_fingerprint=notification_dedupe_fingerprint(
                    recipient_user_id=recipient.id,
                    type_key=NotificationType.FRAUD_HOLD_RAISED,
                    template_version="v1",
                    channel=NotificationChannel.TRANSACTIONAL_EMAIL,
                    payload=email_payload,
                ),
            )
            assert in_app.status == "sent"
            assert in_app.sent_at is not None
            assert email.status == "pending"
            assert email.sent_at is None
            session.add_all([in_app, email])
            await session.commit()

    asyncio.run(run())


def test_feed_is_recipient_scoped_ordered_sanitized_and_read_idempotent(
    db_client,
    db_sessionmaker,
) -> None:
    recipient = create_test_user(
        db_sessionmaker, email="feed@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    other = create_test_user(
        db_sessionmaker, email="other-feed@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    start = datetime(2026, 8, 24, 10, tzinfo=UTC)
    older = _insert_notice(
        db_sessionmaker, recipient_user_id=recipient.id, key="older", created_at=start
    )
    newer = _insert_notice(
        db_sessionmaker,
        recipient_user_id=recipient.id,
        key="newer",
        created_at=start + timedelta(seconds=1),
    )
    foreign = _insert_notice(
        db_sessionmaker,
        recipient_user_id=other.id,
        key="foreign",
        created_at=start + timedelta(seconds=2),
    )

    async def insert_email_delivery() -> Notification:
        async with db_sessionmaker() as session:
            notice = await create_notification(
                session,
                recipient_user_id=recipient.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={"fraud_flag_id": "email-only"},
                dedupe_key="email-only",
                channel=NotificationChannel.TRANSACTIONAL_EMAIL,
            )
            await session.commit()
            return notice

    email_delivery = asyncio.run(insert_email_delivery())
    assert email_delivery.status == "pending"
    assert email_delivery.sent_at is None
    headers = auth_headers(db_client, "feed@example.com", PASSWORD)

    response = db_client.get("/api/v1/notifications?limit=1", headers=headers)
    assert response.status_code == http_status.HTTP_200_OK
    assert response.json()["total"] == 2
    assert [item["id"] for item in response.json()["items"]] == [str(newer.id)]
    assert "payload" not in response.json()["items"][0]
    assert "internal_token" not in str(response.json())
    assert db_client.get("/api/v1/notifications?limit=101", headers=headers).status_code == 422
    assert db_client.get("/api/v1/notifications/unread-count", headers=headers).json() == {
        "unread_count": 2
    }
    assert (
        db_client.post(
            f"/api/v1/notifications/{email_delivery.id}/read", headers=headers
        ).status_code
        == http_status.HTTP_404_NOT_FOUND
    )

    foreign_read = db_client.post(f"/api/v1/notifications/{foreign.id}/read", headers=headers)
    assert foreign_read.status_code == http_status.HTTP_404_NOT_FOUND
    assert foreign_read.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"

    first_read = db_client.post(f"/api/v1/notifications/{older.id}/read", headers=headers)
    second_read = db_client.post(f"/api/v1/notifications/{older.id}/read", headers=headers)
    assert first_read.status_code == second_read.status_code == http_status.HTTP_200_OK
    first_read_at = datetime.fromisoformat(first_read.json()["read_at"].replace("Z", "+00:00"))
    second_read_at = datetime.fromisoformat(second_read.json()["read_at"].replace("Z", "+00:00"))
    assert first_read_at == second_read_at
    assert db_client.post("/api/v1/notifications/read-all", headers=headers).json() == {
        "unread_count": 0
    }
    assert db_client.get("/api/v1/notifications/unread-count", headers=headers).json() == {
        "unread_count": 0
    }
    assert db_client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(db_client, "other-feed@example.com", PASSWORD),
    ).json() == {"unread_count": 1}


def test_advertiser_notification_preference_is_shared_audited_and_cross_org_hidden(
    db_client,
    db_sessionmaker,
) -> None:
    owner = create_test_user(
        db_sessionmaker, email="owner@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    colleague = create_test_user(
        db_sessionmaker, email="colleague@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    other = create_test_user(
        db_sessionmaker, email="other@example.com", password=PASSWORD, role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    other_organization, _ = create_test_organization(db_sessionmaker, owner_user_id=other.id)

    async def add_colleague() -> None:
        async with db_sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=colleague.id,
                    role=MembershipRole.MANAGER,
                    status=MembershipStatus.ACTIVE,
                )
            )
            await session.commit()

    asyncio.run(add_colleague())
    owner_headers = auth_headers(db_client, "owner@example.com", PASSWORD)
    preference = db_client.get(
        "/api/v1/advertiser/notification-preferences", headers=owner_headers
    )
    assert preference.json() == {
        "transactional_email_enabled": True,
        "in_app_enabled": True,
    }
    changed = db_client.patch(
        "/api/v1/advertiser/notification-preferences",
        headers=owner_headers,
        json={"transactional_email_enabled": False},
    )
    assert changed.status_code == http_status.HTTP_200_OK
    assert changed.json()["transactional_email_enabled"] is False
    assert db_client.get(
        "/api/v1/advertiser/notification-preferences",
        headers=auth_headers(db_client, "colleague@example.com", PASSWORD),
    ).json()["transactional_email_enabled"] is False
    events = fetch_audit_events(db_sessionmaker)
    assert events[-1].action == "advertiser_notification_preferences.updated"
    assert events[-1].event_metadata["before"] == {"transactional_email_enabled": True}
    assert events[-1].event_metadata["after"] == {"transactional_email_enabled": False}

    async def cross_org() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as denied:
                await get_notification_preference(
                    session,
                    actor_user_id=owner.id,
                    organization_id=other_organization.id,
                )
            assert denied.value.status_code == http_status.HTTP_404_NOT_FOUND

    asyncio.run(cross_org())


def test_notification_preference_and_audit_share_the_same_transaction(db_sessionmaker) -> None:
    owner = create_test_user(
        db_sessionmaker,
        email="preference-rollback@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            preference = await update_notification_preference(
                session,
                actor_user_id=owner.id,
                organization_id=None,
                transactional_email_enabled=False,
            )
            assert preference.transactional_email_enabled is False
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "advertiser_notification_preferences.updated")
                )
                == 1
            )
            await session.rollback()

        async with db_sessionmaker() as session:
            persisted = await get_notification_preference(
                session,
                actor_user_id=owner.id,
                organization_id=organization.id,
            )
            assert persisted.transactional_email_enabled is True
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "advertiser_notification_preferences.updated")
                )
                == 0
            )

    asyncio.run(scenario())
