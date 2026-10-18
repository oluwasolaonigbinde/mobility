import asyncio
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import select
from test_driver_person_payee_onboarding import (
    PASSWORD,
    _application,
    _complete_admin_review,
    _current_submission_id,
    _person_payee_payload,
    _register,
    _seed_clean_kyc_files,
)
from test_driver_vehicle_approval import (
    _approved_applicant,
    _decision_path,
    _review_files,
    _seed_vehicle_files,
    _vehicle_payload,
)
from test_email_delivery import RecordingEmailAdapter

from app.models.notification import Notification
from app.models.user import User
from app.services.email_delivery import process_email_notification


@pytest.mark.parametrize(
    "stage,approved,expired",
    [
        ("id", True, False),
        ("id", False, False),
        ("car", True, False),
        ("car", False, False),
        ("id", True, True),
        ("car", True, True),
    ],
)
def test_review_outcomes_queue_deduplicated_actionable_email(
    db_client,
    db_sessionmaker,
    settings,
    stage,
    approved,
    expired,
    monkeypatch,
):
    suffix = f"notice-{stage}-{str(approved).lower()}"
    if stage == "car":
        token, application, admin = _approved_applicant(
            db_client, db_sessionmaker, settings, suffix=suffix
        )
        files = _seed_vehicle_files(db_sessionmaker, application=application, suffix=suffix)
        submitted = db_client.post(
            "/api/v1/auth/driver-onboarding/vehicle", json=_vehicle_payload(token, files)
        ).json()
        path = _decision_path(application.id, submitted["vehicle_id"], submitted["submission_id"])
        decision = {
            "client_request_id": str(uuid4()),
            "decision": "approved" if approved else "rejected",
            "reason_code": "complete_current_evidence" if approved else "not_roadworthy",
        }
        if approved:
            _review_files(
                db_client,
                db_sessionmaker,
                admin=admin,
                submission_id=submitted["submission_id"],
                files=files,
            )
            decision.update(
                owner_match_confirmed=True,
                vehicle_identity_confirmed=True,
                roadworthy_confirmed=True,
                pilot_car_confirmed=True,
                documents_readable_confirmed=True,
                document_reviews={
                    kind: {"status": "accepted", "expires_on": "2030-01-01"} for kind in files
                },
                valid_until="2029-01-01T00:00:00Z",
            )
    else:
        token, _ = _register(db_client, db_sessionmaker, settings, suffix=suffix)
        application = _application(db_sessionmaker, email=f"person-payee-{suffix}@example.com")
        files = _seed_clean_kyc_files(db_sessionmaker, email=application.email)
        submitted = db_client.post(
            "/api/v1/auth/driver-onboarding/person-payee",
            json=_person_payee_payload(token, files, db_client),
        )
        assert submitted.status_code == 201
        admin = create_test_user(
            db_sessionmaker, email=f"{suffix}-admin@example.test", password=PASSWORD
        )
        if approved:
            # D9: the bank's short reference authorizes only the exact reviewed version.
            _complete_admin_review(
                db_client,
                db_sessionmaker,
                admin=admin,
                application=application,
                files=files,
                verification_reference="TX 1",
            )
        path = f"/api/v1/admin/driver-applications/{application.id}/person-payee-decision"
        decision = {
            "submission_id": _current_submission_id(db_sessionmaker, application.driver_profile_id),
            "client_request_id": str(uuid4()),
            "decision": "approved" if approved else "rejected",
            "reason_code": "complete_current_evidence" if approved else "unreadable_evidence",
        }
        if approved:
            decision.update(
                identity_match_confirmed=True,
                bank_account_match_confirmed=True,
                documents_readable_confirmed=True,
                document_reviews={
                    kind: {"status": "accepted", "expires_on": "2030-01-01"} for kind in files
                },
            )
    headers = auth_headers(db_client, admin.email, PASSWORD)
    response = db_client.post(path, headers=headers, json=decision)
    assert response.status_code == 200, response.text
    assert db_client.post(path, headers=headers, json=decision).status_code == 200
    type_key = f"driver_{stage}_{'approved' if approved else 'rejected'}"
    adapter = RecordingEmailAdapter()

    async def inspect_and_deliver():
        from datetime import UTC, datetime

        if expired:
            from app.services import payout_rule_serialization

            async def future_clock(_session):
                # Car validity ends before its documents; isolate that guard.
                return datetime(2029 if stage == "car" else 2100, 6, 1, tzinfo=UTC)

            monkeypatch.setattr(payout_rule_serialization, "database_clock", future_clock)

        async with db_sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(Notification).where(
                        Notification.recipient_user_id == application.user_id,
                        Notification.type_key == type_key,
                    )
                )
            )
            assert len(rows) == 2
            assert {row.channel for row in rows} == {"in_app", "transactional_email"}
            assert all(set(row.payload) == {"review_decision_id"} for row in rows)
            email = next(row for row in rows if row.channel == "transactional_email")
        result = await process_email_notification(
            db_sessionmaker,
            notification_id=email.id,
            settings=settings,
            email_adapter=adapter,
            now=datetime.now(UTC),
        )
        if expired:
            assert result == "skipped"
            assert adapter.messages == []
            from app.core.errors import AppError
            from app.services.notifications import (
                list_current_user_notifications,
                mark_notification_read,
                unread_notification_count,
            )

            async with db_sessionmaker() as session:
                notices, total = await list_current_user_notifications(
                    session, recipient_user_id=application.user_id, limit=100, offset=0
                )
                assert total == len(notices)
                assert (
                    await unread_notification_count(session, recipient_user_id=application.user_id)
                    == total
                )
                in_app = next(row for row in rows if row.channel == "in_app")
                assert all(row.id != in_app.id for row in notices)
                with pytest.raises(AppError) as error:
                    await mark_notification_read(
                        session, recipient_user_id=application.user_id, notification_id=in_app.id
                    )
                assert error.value.status_code == 404
            return
        assert result == "sent"
        assert len(adapter.messages) == 1
        message = adapter.messages[0]
        assert message.recipient == application.email
        assert '<a href="http://localhost:3000/apply?step=' in message.html_body
        assert "review_decision_id" not in message.text_body
        if not approved:
            assert (
                "roadworthiness" in message.text_body
                if stage == "car"
                else "clearer copy" in message.text_body
            )
        async with db_sessionmaker() as session:
            from app.services.notifications import mark_notification_read

            in_app = next(row for row in rows if row.channel == "in_app")
            first_read = await mark_notification_read(
                session, recipient_user_id=application.user_id, notification_id=in_app.id
            )
            read_at = first_read.read_at
            second_read = await mark_notification_read(
                session, recipient_user_id=application.user_id, notification_id=in_app.id
            )
            assert second_read.read_at == read_at
            user = await session.get(User, application.user_id)
            if approved:
                from app.api.v1.notifications import current_feed_item
                from app.models.notification import NotificationChannel, NotificationType
                from app.services.notifications import create_notification

                user.status = "active"
                active_copy = await current_feed_item(session, in_app, user)
                assert active_copy.action_url == "/driver/profile"
                assert "updated" in active_copy.body
                assert "setup" not in active_copy.body and "add your car" not in active_copy.body
                renewal = await create_notification(
                    session,
                    recipient_user_id=user.id,
                    type_key=NotificationType(type_key),
                    channel=NotificationChannel.TRANSACTIONAL_EMAIL,
                    payload=email.payload,
                    dedupe_key="active-renewal-copy",
                )
                await session.commit()
                active_adapter = RecordingEmailAdapter()
                assert (
                    await process_email_notification(
                        db_sessionmaker,
                        notification_id=renewal.id,
                        settings=settings,
                        email_adapter=active_adapter,
                        now=datetime.now(UTC),
                    )
                    == "sent"
                )
                assert "updated" in active_adapter.messages[0].text_body
                assert "/driver/profile" in active_adapter.messages[0].html_body
                assert "setup" not in active_adapter.messages[0].text_body
            user.status = "suspended"
            from app.services.driver_review_notifications import review_notice_context

            assert await review_notice_context(session, email, user) is None

    asyncio.run(inspect_and_deliver())
    if not approved:
        if stage == "id":
            replacement = db_client.post(
                "/api/v1/auth/driver-onboarding/person-payee",
                json=_person_payee_payload(token, files, db_client),
            )
            assert replacement.status_code == 201, replacement.text
        else:

            async def purge_rejected_payload():
                from datetime import UTC, datetime
                from uuid import UUID

                from sqlalchemy import update

                from app.models.kyc import VehicleEvidenceSubmission

                async with db_sessionmaker() as session:
                    # Materialize a lawful retained-metadata/purged-payload state.
                    values = {
                        column.name: None
                        for column in VehicleEvidenceSubmission.__table__.columns
                        if column.name.endswith("_snapshot")
                    }
                    await session.execute(
                        update(VehicleEvidenceSubmission)
                        .where(VehicleEvidenceSubmission.id == UUID(submitted["submission_id"]))
                        .values(purged_at=datetime.now(UTC), **values)
                    )
                    await session.commit()

            asyncio.run(purge_rejected_payload())

        async def assert_stale_hidden():
            from app.core.errors import AppError
            from app.models.notification import NotificationType
            from app.services.notifications import (
                create_notification,
                list_current_user_notifications,
                mark_all_notifications_read,
                mark_notification_read,
                unread_notification_count,
            )

            async with db_sessionmaker() as session:
                target = await session.scalar(
                    select(Notification).where(
                        Notification.recipient_user_id == application.user_id,
                        Notification.type_key == type_key,
                        Notification.channel == "in_app",
                    )
                )
                for index in range(2):
                    await create_notification(
                        session,
                        recipient_user_id=application.user_id,
                        type_key=NotificationType.ASSIGNMENT_OFFERED,
                        payload={},
                        dedupe_key=f"visible:{index}",
                    )
                notices, total = await list_current_user_notifications(
                    session, recipient_user_id=application.user_id, limit=100, offset=0
                )
                assert total == len(notices)
                assert (
                    await unread_notification_count(session, recipient_user_id=application.user_id)
                    == total
                )
                assert all(row.id != target.id for row in notices)
                page, page_total = await list_current_user_notifications(
                    session, recipient_user_id=application.user_id, limit=1, offset=1
                )
                assert page_total == total and [row.id for row in page] == [notices[1].id]
                with pytest.raises(AppError) as error:
                    await mark_notification_read(
                        session, recipient_user_id=application.user_id, notification_id=target.id
                    )
                assert error.value.status_code == 404
                assert (
                    await mark_all_notifications_read(
                        session, recipient_user_id=application.user_id
                    )
                    == total
                )
                await session.refresh(target)
                assert target.read_at is None

        asyncio.run(assert_stale_hidden())
