import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_organization,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
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
    "blocked", ["unknown_type", "account_type", "inactive_user", "wrong_recipient"]
)
def test_non_campaign_or_inactive_context_never_queries_private_facts(blocked):
    from app.models.user import User
    from app.services.notifications import notification_campaign_context

    user = User(id=uuid4(), role="advertiser", status="active")
    notice = Notification(
        recipient_user_id=user.id,
        type_key="campaign_approved",
        payload={"campaign_id": str(uuid4())},
    )
    if blocked == "unknown_type":
        notice.type_key = "unrecognized_future_type"
    elif blocked == "account_type":
        notice.type_key = NotificationType.PASSWORD_RESET_REQUESTED
    elif blocked == "inactive_user":
        user.status = "disabled"
    else:
        notice.recipient_user_id = uuid4()
    # Any private-fact read would fail because there is deliberately no session.
    assert asyncio.run(notification_campaign_context(None, notice=notice, user=user)) is None


@pytest.mark.parametrize("reference", ["activity_flag_id", "fraud_flag_id"])
def test_typed_review_reference_resolves_its_canonical_campaign(reference):
    from unittest.mock import AsyncMock

    from app.models.assignment_activity import AssignmentActivityFlag
    from app.models.trip import TripSession
    from app.models.trip_analytics import FraudFlag
    from app.services.notifications import _notification_reference_scope

    campaign_id, assignment_id, reference_id, trip_id = (uuid4() for _ in range(4))
    row = (
        AssignmentActivityFlag(
            id=reference_id, campaign_id=campaign_id, assignment_id=assignment_id
        )
        if reference == "activity_flag_id"
        else FraudFlag(id=reference_id, trip_session_id=trip_id)
    )
    trip = TripSession(id=trip_id, campaign_id=campaign_id, assignment_id=assignment_id)
    session = AsyncMock()
    session.get.side_effect = [row, trip] if reference == "fraud_flag_id" else [row]
    assert asyncio.run(_notification_reference_scope(session, {reference: str(reference_id)})) == (
        {campaign_id},
        {assignment_id},
    )
    if reference == "fraud_flag_id":
        session.get.side_effect = [row, None]
        assert (
            asyncio.run(_notification_reference_scope(session, {reference: str(reference_id)}))
            is None
        )


def _campaign_notice(
    db_sessionmaker, recipient, payload, type_key=NotificationType.CAMPAIGN_APPROVED
):
    async def insert():
        async with db_sessionmaker() as session:
            notice = await create_notification(
                session,
                recipient_user_id=recipient.id,
                type_key=type_key,
                payload=payload,
                dedupe_key=None,
            )
            await session.commit()
            return notice.id

    return asyncio.run(insert())


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.ADVERTISER, UserRole.DRIVER])
def test_campaign_context_is_projected_for_each_role_and_mark_read(
    db_client, db_sessionmaker, role
):
    owner = create_test_user(
        db_sessionmaker,
        email="context-owner@example.com",
        role=UserRole.ADVERTISER,
        password=PASSWORD,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="PalmPay Wuse Blitz",
    )
    actor = (
        owner
        if role == UserRole.ADVERTISER
        else create_test_user(
            db_sessionmaker, email="context-actor@example.com", role=role, password=PASSWORD
        )
    )
    payload = {
        "campaign_id": str(campaign.id),
        "campaign_name": "UNTRUSTED",
        "action_url": "https://attacker.invalid",
    }
    if role == UserRole.DRIVER:
        profile = create_test_driver_profile(db_sessionmaker, user_id=actor.id)
        vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
        assignment = create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=campaign.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=owner.id,
        )
        payload["assignment_id"] = str(assignment.id)
        expected_url = f"/driver/assignments?assignment_id={assignment.id}"
    else:
        expected_url = f"/{role.value}/campaigns/{campaign.id}"
    notice_id = _campaign_notice(db_sessionmaker, actor, payload)
    headers = auth_headers(db_client, actor.email, PASSWORD)
    feed = db_client.get("/api/v1/notifications", headers=headers).json()["items"][0]
    read = db_client.post(f"/api/v1/notifications/{notice_id}/read", headers=headers)
    assert read.status_code == 200, read.text
    for item in (feed, read.json()):
        assert item["campaign_name"] == campaign.name
        assert item["action_url"] == expected_url
        assert campaign.name in item["title"]
        assert "UNTRUSTED" not in str(item)
        assert "attacker" not in str(item)


@pytest.mark.parametrize(
    "invalid",
    [
        "other_tenant",
        "disabled_member",
        "inactive_org",
        "malformed",
        "missing",
        "absent",
        "account_type",
        "conflict",
    ],
)
def test_campaign_context_fails_closed_in_feed_and_mark_read(db_client, db_sessionmaker, invalid):
    actor = create_test_user(
        db_sessionmaker,
        email="scope-actor@example.com",
        role=UserRole.ADVERTISER,
        password=PASSWORD,
    )
    owner = create_test_user(
        db_sessionmaker,
        email="scope-owner@example.com",
        role=UserRole.ADVERTISER,
        password=PASSWORD,
    )
    organization, membership = create_test_organization(db_sessionmaker, owner_user_id=actor.id)
    other_org, _ = create_test_organization(
        db_sessionmaker, owner_user_id=owner.id, name="Other company"
    )
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=actor.id,
        name="PRIVATE campaign",
    )
    other = create_test_campaign(
        db_sessionmaker,
        organization_id=other_org.id,
        created_by_user_id=owner.id,
        name="OTHER PRIVATE",
    )
    payload = {"campaign_id": str(campaign.id)}
    notice_type = NotificationType.CAMPAIGN_APPROVED
    if invalid == "other_tenant":
        payload["campaign_id"] = str(other.id)
    elif invalid == "malformed":
        payload["campaign_id"] = "not-a-uuid"
    elif invalid == "missing":
        payload["campaign_id"] = str(uuid4())
    elif invalid == "absent":
        payload = {}
    elif invalid == "account_type":
        notice_type = NotificationType.COMPLAINT_REPLIED
    elif invalid == "conflict":
        driver = create_test_user(
            db_sessionmaker, email="scope-driver@example.com", role=UserRole.DRIVER
        )
        profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
        vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
        assignment = create_test_campaign_assignment(
            db_sessionmaker,
            campaign_id=other.id,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            assigned_by_user_id=owner.id,
        )
        payload["assignment_id"] = str(assignment.id)
    notice_id = _campaign_notice(db_sessionmaker, actor, payload, notice_type)

    async def stored_facts():
        async with db_sessionmaker() as session:
            notice = await session.get(Notification, notice_id)
            return notice.payload, notice.dedupe_fingerprint

    original_facts = asyncio.run(stored_facts())
    headers = auth_headers(db_client, actor.email, PASSWORD)
    if invalid in {"disabled_member", "inactive_org"}:
        before = db_client.get("/api/v1/notifications", headers=headers)
        assert before.status_code == 200
        visible = next(item for item in before.json()["items"] if item["id"] == str(notice_id))
        assert visible["campaign_name"] == campaign.name
        assert visible["action_url"] == f"/advertiser/campaigns/{campaign.id}"

        async def revoke():
            async with db_sessionmaker() as session:
                if invalid == "disabled_member":
                    row = await session.get(OrganizationMembership, membership.id)
                    row.status = "disabled"
                else:
                    from app.models.organization import AdvertiserOrganization

                    row = await session.get(AdvertiserOrganization, organization.id)
                    row.status = "suspended"
                await session.commit()

        asyncio.run(revoke())
    feed = db_client.get("/api/v1/notifications", headers=headers)
    read = db_client.post(f"/api/v1/notifications/{notice_id}/read", headers=headers)
    assert feed.status_code == read.status_code == 200
    for item in (feed.json()["items"][0], read.json()):
        assert item["campaign_name"] is None
        assert item["action_url"] is None
        assert "PRIVATE" not in str(item)

    async def inspect_immutable_notice():
        async with db_sessionmaker() as session:
            notice = await session.get(Notification, notice_id)
            assert notice.payload == payload
            assert (notice.payload, notice.dedupe_fingerprint) == original_facts
            assert notice.read_at is not None

    asyncio.run(inspect_immutable_notice())


@pytest.mark.parametrize("conflict_first", [False, True])
def test_driver_context_resolves_trip_and_denies_another_drivers_assignment(
    db_client, db_sessionmaker, conflict_first
):
    owner = create_test_user(db_sessionmaker, email="trip-owner@example.com")
    organization, _ = create_test_organization(db_sessionmaker)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=owner.id
    )
    driver = create_test_user(
        db_sessionmaker,
        email="trip-context-driver@example.com",
        role=UserRole.DRIVER,
        password=PASSWORD,
    )
    profile = create_test_driver_profile(db_sessionmaker, user_id=driver.id)
    vehicle = create_test_vehicle(db_sessionmaker, driver_profile_id=profile.id)
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=owner.id,
    )
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        campaign_id=campaign.id,
        started_by_user_id=driver.id,
    )
    first_created_at = datetime(2026, 10, 8, 12, tzinfo=UTC)
    trip_notice = _insert_notice(
        db_sessionmaker,
        recipient_user_id=driver.id,
        key="trip-context",
        created_at=first_created_at + timedelta(seconds=0 if conflict_first else 1),
        type_key=NotificationType.PAYOUT_RELEASED,
        payload={"trip_session_id": str(trip.id)},
    )
    headers = auth_headers(db_client, driver.email, PASSWORD)
    item = db_client.get("/api/v1/notifications", headers=headers).json()["items"][0]
    assert item["action_url"] == f"/driver/assignments?assignment_id={assignment.id}"
    stranger = create_test_user(
        db_sessionmaker, email="trip-stranger@example.com", role=UserRole.DRIVER, password=PASSWORD
    )
    stranger_notice_id = _campaign_notice(
        db_sessionmaker,
        stranger,
        {"assignment_id": str(assignment.id)},
        NotificationType.ASSIGNMENT_OFFERED,
    )
    other_item = db_client.get(
        "/api/v1/notifications", headers=auth_headers(db_client, stranger.email, PASSWORD)
    ).json()["items"][0]
    assert other_item["action_url"] is None
    assert other_item["campaign_name"] is None
    read = db_client.post(
        f"/api/v1/notifications/{stranger_notice_id}/read",
        headers=auth_headers(db_client, stranger.email, PASSWORD),
    )
    assert read.status_code == 200
    assert read.json()["campaign_name"] is None
    assert read.json()["action_url"] is None

    # The two references agree on campaign but disagree on the driver's job.
    other_profile = create_test_driver_profile(db_sessionmaker, user_id=stranger.id)
    other_vehicle = create_test_vehicle(
        db_sessionmaker, driver_profile_id=other_profile.id, plate_number="OTHER-123"
    )
    other_assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=other_profile.id,
        vehicle_id=other_vehicle.id,
        assigned_by_user_id=owner.id,
    )
    conflict_notice = _insert_notice(
        db_sessionmaker,
        recipient_user_id=driver.id,
        key="conflicting-trip-context",
        created_at=first_created_at + timedelta(seconds=1 if conflict_first else 0),
        type_key=NotificationType.PAYOUT_RELEASED,
        payload={"trip_session_id": str(trip.id), "assignment_id": str(other_assignment.id)},
    )
    conflict_id = conflict_notice.id
    feed = db_client.get("/api/v1/notifications", headers=headers)
    assert feed.status_code == 200
    items = feed.json()["items"]
    expected_ids = [str(conflict_id), str(trip_notice.id)]
    if not conflict_first:
        expected_ids.reverse()
    assert [item["id"] for item in items] == expected_ids
    conflict_item = next(item for item in items if item["id"] == str(conflict_id))
    assert conflict_item["campaign_name"] is None
    assert conflict_item["action_url"] is None
    conflict_read = db_client.post(f"/api/v1/notifications/{conflict_id}/read", headers=headers)
    assert conflict_read.status_code == 200
    assert conflict_read.json()["campaign_name"] is None
    assert conflict_read.json()["action_url"] is None


@pytest.mark.parametrize(
    ("type_key", "title", "body"),
    [
        (
            NotificationType.ACTIVITY_FLOOR_BREACHED,
            "Verified activity below floor",
            "Your verified activity was below the configured weekly floor. "
            "Terrax Media will review the assignment.",
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
            "consecutive days. Terrax Media will review it.",
        ),
        (
            NotificationType.ASSIGNMENT_ACTIVITY_RECOVERED,
            "Assignment activity resumed",
            "Verified activity resumed for this assignment, so the activity flag has been cleared.",
        ),
        (
            NotificationType.BUDGET_URGENT_ALERT,
            "Campaign budget nearly used",
            "A campaign has almost used its budget and will pause when it runs out.",
        ),
        (
            NotificationType.CAMPAIGN_BUDGET_RESUMED,
            "Campaign resumed",
            "Terrax Media resumed a campaign that was paused for budget.",
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
    db_sessionmaker,
    *,
    recipient_user_id,
    key: str,
    created_at: datetime,
    type_key=NotificationType.FRAUD_HOLD_RAISED,
    payload=None,
) -> Notification:
    if payload is None:
        payload = {"fraud_flag_id": "private-flag", "internal_token": "do-not-return"}

    async def insert() -> Notification:
        async with db_sessionmaker() as session:
            notice = Notification(
                recipient_user_id=recipient_user_id,
                type_key=type_key.value,
                template_version="v1",
                channel=NotificationChannel.IN_APP.value,
                payload=payload,
                dedupe_key=key,
                dedupe_fingerprint=notification_dedupe_fingerprint(
                    recipient_user_id=recipient_user_id,
                    type_key=type_key,
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
    remaining = db_client.get("/api/v1/notifications?limit=1", headers=headers).json()
    assert remaining["total"] == 1
    assert [item["id"] for item in remaining["items"]] == [str(newer.id)]
    assert db_client.post("/api/v1/notifications/read-all", headers=headers).json() == {
        "unread_count": 0
    }
    cleared = db_client.get("/api/v1/notifications", headers=headers).json()
    assert cleared["items"] == []
    assert cleared["total"] == 0
    assert db_client.get("/api/v1/notifications/unread-count", headers=headers).json() == {
        "unread_count": 0
    }
    assert db_client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(db_client, "other-feed@example.com", PASSWORD),
    ).json() == {"unread_count": 1}


def test_unread_feed_pages_skip_read_rows_and_read_all_preserves_later_notices(
    db_client,
    db_sessionmaker,
) -> None:
    user = create_test_user(
        db_sessionmaker, email="unread-pages@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    headers = auth_headers(db_client, "unread-pages@example.com", PASSWORD)
    start = datetime(2026, 8, 24, 10, tzinfo=UTC)
    notices = [
        _insert_notice(
            db_sessionmaker,
            recipient_user_id=user.id,
            key=f"page-{index}",
            created_at=start + timedelta(seconds=index),
        )
        for index in range(3)
    ]
    assert (
        db_client.post(f"/api/v1/notifications/{notices[2].id}/read", headers=headers).status_code
        == 200
    )
    for offset, expected in enumerate(reversed(notices[:2])):
        page = db_client.get(
            f"/api/v1/notifications?limit=1&offset={offset}", headers=headers
        ).json()
        assert page["total"] == 2
        assert [item["id"] for item in page["items"]] == [str(expected.id)]
    for _ in range(2):
        assert db_client.post("/api/v1/notifications/read-all", headers=headers).json() == {
            "unread_count": 0
        }
        assert db_client.get("/api/v1/notifications", headers=headers).json()["items"] == []

    async def retained() -> int:
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.recipient_user_id == user.id, Notification.read_at.is_not(None))
            )

    assert asyncio.run(retained()) == 3
    later = _insert_notice(
        db_sessionmaker,
        recipient_user_id=user.id,
        key="later",
        created_at=start + timedelta(seconds=4),
    )
    page = db_client.get("/api/v1/notifications", headers=headers).json()
    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [str(later.id)]
    assert db_client.get("/api/v1/notifications/unread-count", headers=headers).json() == {
        "unread_count": 1
    }


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
    preference = db_client.get("/api/v1/advertiser/notification-preferences", headers=owner_headers)
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
    assert (
        db_client.get(
            "/api/v1/advertiser/notification-preferences",
            headers=auth_headers(db_client, "colleague@example.com", PASSWORD),
        ).json()["transactional_email_enabled"]
        is False
    )
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
