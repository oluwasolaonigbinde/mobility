import asyncio
from types import SimpleNamespace

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_fraud_assessments import build_graph, create_flag

from app.models.audit import AuditEvent
from app.models.fraud_dispute import FraudDispute
from app.models.notification import Notification
from app.models.trip_analytics import FraudFlag
from app.services.fraud_disputes import create_driver_dispute, reply_to_dispute
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
from app.services.notifications import create_fraud_hold_raised_notice
from app.services.route_replay import _remove_open_replay_flag, _write_replay_flag
from app.services.trip_analytics import AnalyticsMetrics, replace_open_fraud_flags

PASSWORD = "long-secure-password"


def seed_hold(db_sessionmaker, tag: str):
    graph = build_graph(db_sessionmaker, tag)
    flag = create_flag(db_sessionmaker, graph)

    async def notice() -> None:
        async with db_sessionmaker() as session:
            attached = await session.get(FraudFlag, flag.id)
            await create_fraud_hold_raised_notice(session, attached)
            await session.commit()

    asyncio.run(notice())
    return graph, flag


def counts(db_sessionmaker) -> tuple[int, int, int]:
    async def fetch() -> tuple[int, int, int]:
        async with db_sessionmaker() as session:
            return (
                int(await session.scalar(select(func.count()).select_from(FraudDispute)) or 0),
                int(await session.scalar(select(func.count()).select_from(Notification)) or 0),
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(
                            AuditEvent.action.in_(
                                {
                                    "driver.fraud_dispute.created",
                                    "admin.fraud_dispute.replied",
                                }
                            )
                        )
                    )
                    or 0
                ),
            )

    return asyncio.run(fetch())


def test_driver_projection_is_sanitized_and_dispute_reply_is_exactly_idempotent(
    db_client, db_sessionmaker
) -> None:
    graph, flag = seed_hold(db_sessionmaker, "driver-dispute")
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    admin_headers = auth_headers(db_client, "admin-driver-dispute@example.com", PASSWORD)

    async def add_legacy_secret() -> None:
        async with db_sessionmaker() as session:
            notice = await session.scalar(select(Notification))
            notice.payload = {**notice.payload, "internal_secret": "must not escape"}
            await session.commit()

    asyncio.run(add_legacy_secret())

    listed = db_client.get("/api/v1/driver/fraud-holds", headers=driver_headers)
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["id"] == str(flag.id)
    assert item["public_status"] == "assessment_pending"
    assert item["reason"] == {
        "code": "route_pattern_review",
        "version": "v1",
        "title": "Route needs review",
        "body": "A route pattern for this trip needs a staff review.",
    }
    serialized = str(item)
    for secret in (
        "description",
        "evidence",
        "observed_mps",
        "severity",
        "campaign_id",
        "driver_profile_id",
        "reviewed_by_user_id",
        "resolution_note",
    ):
        assert secret not in serialized
    assert item["notices"][0]["fraud_flag_id"] == str(flag.id)
    assert "payload" not in item["notices"][0]
    assert "internal_secret" not in serialized

    url = f"/api/v1/driver/fraud-holds/{flag.id}/disputes"
    first = db_client.post(url, headers=driver_headers, json={"message": "  Please review.  "})
    retry = db_client.post(url, headers=driver_headers, json={"message": "Please review."})
    conflict = db_client.post(url, headers=driver_headers, json={"message": "Changed."})
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert conflict.status_code == 409
    assert counts(db_sessionmaker) == (1, 1, 1)

    reply_url = f"/api/v1/admin/fraud-disputes/{first.json()['id']}/reply"
    replied = db_client.post(reply_url, headers=admin_headers, json={"reply": "  Reviewed.  "})
    reply_retry = db_client.post(reply_url, headers=admin_headers, json={"reply": "Reviewed."})
    reply_conflict = db_client.post(reply_url, headers=admin_headers, json={"reply": "Different."})
    assert replied.status_code == reply_retry.status_code == 200
    assert replied.json() == reply_retry.json()
    assert reply_conflict.status_code == 409
    assert counts(db_sessionmaker) == (1, 2, 2)

    after = db_client.get("/api/v1/driver/fraud-holds", headers=driver_headers).json()
    assert after["items"][0]["dispute"]["reply"] == "Reviewed."
    assert any(
        notice["type_key"] == "fraud_dispute_replied" for notice in after["items"][0]["notices"]
    )


def test_owner_mismatch_is_404_and_dismissed_resolution_remains_visible(
    db_client, db_sessionmaker
) -> None:
    graph, flag = seed_hold(db_sessionmaker, "resolved-visible")
    other_graph = build_graph(db_sessionmaker, "other-driver")
    owner_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    other_headers = auth_headers(db_client, other_graph.driver.email, PASSWORD)
    admin_headers = auth_headers(db_client, "admin-resolved-visible@example.com", PASSWORD)

    mismatch = db_client.post(
        f"/api/v1/driver/fraud-holds/{flag.id}/disputes",
        headers=other_headers,
        json={"message": "Not mine."},
    )
    assert mismatch.status_code == 404
    trip_mismatch = db_client.get(
        f"/api/v1/driver/fraud-holds?trip_session_id={flag.trip_session_id}",
        headers=other_headers,
    )
    assert trip_mismatch.status_code == 404

    assert (
        db_client.post(
            f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
            headers=admin_headers,
        ).status_code
        == 200
    )
    resolved = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=admin_headers,
        json={"outcome": "dismissed", "note": "Internal explanation must stay private."},
    )
    assert resolved.status_code == 200
    listed = db_client.get("/api/v1/driver/fraud-holds", headers=owner_headers).json()
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["public_status"] == "review_cleared"
    resolved_notice = next(
        notice for notice in item["notices"] if notice["type_key"] == "fraud_review_resolved"
    )
    assert resolved_notice["outcome"] == "dismissed"
    assert "Internal explanation" not in str(item)


def test_confirmed_resolution_is_visible_but_flag_stays_hold_active(
    db_client, db_sessionmaker
) -> None:
    graph, flag = seed_hold(db_sessionmaker, "confirmed-visible")
    driver_headers = auth_headers(db_client, graph.driver.email, PASSWORD)
    admin_headers = auth_headers(db_client, "admin-confirmed-visible@example.com", PASSWORD)
    db_client.post(f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge", headers=admin_headers)
    db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=admin_headers,
        json={"outcome": "confirmed", "note": "Internal."},
    )
    item = db_client.get("/api/v1/driver/fraud-holds", headers=driver_headers).json()["items"][0]
    assert item["public_status"] == "issue_confirmed"
    resolved_notice = next(
        notice for notice in item["notices"] if notice["type_key"] == "fraud_review_resolved"
    )
    assert resolved_notice["outcome"] == "confirmed"


def test_disputed_base_flag_identity_and_evidence_survive_detector_reconciliation(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "base-preservation")
    flag = create_flag(db_sessionmaker, graph)
    original_evidence = dict(flag.evidence)

    async def run() -> tuple[object, dict]:
        async with db_sessionmaker() as session:
            session.add(
                FraudDispute(
                    fraud_flag_id=flag.id,
                    driver_profile_id=graph.profile.id,
                    submitted_by_user_id=graph.driver.id,
                    message="Please review.",
                    status="open",
                )
            )
            await session.flush()
            trip = await session.get(type(graph.trip), graph.trip.id)
            analytics = await session.get(type(graph.analytics), graph.analytics.id)
            metrics = AnalyticsMetrics(
                poor_accuracy_ratio=0,
                stationary_ratio=0,
                excessive_gap_count=0,
                max_ping_gap_seconds=0,
                impossible_speed_count=0,
                ignored_segment_count=0,
                segment_count=0,
                future_ping_count=0,
                start_end_distance_m=None,
            )
            await replace_open_fraud_flags(
                session,
                trip=trip,
                analytics=analytics,
                metrics=metrics,
                settings=settings,
                detected_at=graph.analytics.computed_at,
            )
            await session.commit()
            preserved = await session.get(FraudFlag, flag.id)
            return preserved.id, preserved.evidence

    preserved_id, evidence = asyncio.run(run())
    assert preserved_id == flag.id
    assert evidence == original_evidence


def test_postgres_concurrent_exact_dispute_retry_creates_one_authority_row(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "concurrent-dispute")
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def run() -> tuple[list[object], int, int]:
        async def submit():
            async with postgis_db_sessionmaker() as session:
                result = await create_driver_dispute(
                    session,
                    flag_id=flag.id,
                    user_id=graph.driver.id,
                    message="Please review.",
                )
                await session.commit()
                return result.dispute.id

        ids = await asyncio.gather(submit(), submit())
        async with postgis_db_sessionmaker() as session:
            dispute_count = int(
                await session.scalar(select(func.count()).select_from(FraudDispute)) or 0
            )
            audit_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "driver.fraud_dispute.created")
                )
                or 0
            )
        return ids, dispute_count, audit_count

    ids, dispute_count, audit_count = asyncio.run(run())
    assert ids[0] == ids[1]
    assert dispute_count == audit_count == 1


def test_postgres_concurrent_exact_resolution_retry_creates_one_notice_and_audit(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, "concurrent-resolution-notice")
    flag = create_flag(postgis_db_sessionmaker, graph)
    actor_id = graph.campaign.created_by_user_id

    async def run() -> tuple[list[bool], int, int, str]:
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=actor_id,
            )
            await session.commit()

        async def resolve() -> bool:
            async with postgis_db_sessionmaker() as session:
                result = await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=actor_id,
                    outcome="dismissed",
                    resolution_note="Exact concurrent review outcome.",
                )
                await session.commit()
                return result.changed

        changed = await asyncio.gather(resolve(), resolve())
        async with postgis_db_sessionmaker() as session:
            notice_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == "fraud_review_resolved")
                )
                or 0
            )
            audit_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "admin.fraud_flag.resolved")
                )
                or 0
            )
            stored = await session.get(FraudFlag, flag.id)
            return changed, notice_count, audit_count, stored.status

    changed, notice_count, audit_count, stored_status = asyncio.run(run())
    assert sorted(changed) == [False, True]
    assert notice_count == audit_count == 1
    assert stored_status == "dismissed"


def test_reply_failure_rolls_back_reply_audit_and_notice(db_sessionmaker, monkeypatch) -> None:
    graph = build_graph(db_sessionmaker, "reply-rollback")
    flag = create_flag(db_sessionmaker, graph)

    async def fail_notice(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic notice failure")

    monkeypatch.setattr(
        "app.services.fraud_disputes.create_fraud_dispute_replied_notice",
        fail_notice,
    )

    async def run() -> tuple[str, int, int]:
        async with db_sessionmaker() as session:
            created = await create_driver_dispute(
                session,
                flag_id=flag.id,
                user_id=graph.driver.id,
                message="Please review.",
            )
            await session.commit()
            dispute_id = created.dispute.id
        async with db_sessionmaker() as session:
            with pytest.raises(RuntimeError, match="synthetic notice failure"):
                await reply_to_dispute(
                    session,
                    dispute_id=dispute_id,
                    actor_user_id=graph.campaign.created_by_user_id,
                    reply="Reviewed.",
                )
                await session.commit()
            await session.rollback()
        async with db_sessionmaker() as session:
            dispute = await session.get(FraudDispute, dispute_id)
            reply_audits = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.action == "admin.fraud_dispute.replied")
                )
                or 0
            )
            reply_notices = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.type_key == "fraud_dispute_replied")
                )
                or 0
            )
            return dispute.status, reply_audits, reply_notices

    assert asyncio.run(run()) == ("open", 0, 0)


def test_disputed_route_replay_flag_cannot_be_removed_or_rewritten(
    db_sessionmaker, settings
) -> None:
    graph = build_graph(db_sessionmaker, "replay-preservation")
    flag = create_flag(db_sessionmaker, graph, flag_type="route_replay")
    original_evidence = dict(flag.evidence)

    async def run() -> tuple[bool, bool, dict]:
        async with db_sessionmaker() as session:
            session.add(
                FraudDispute(
                    fraud_flag_id=flag.id,
                    driver_profile_id=graph.profile.id,
                    submitted_by_user_id=graph.driver.id,
                    message="Please review.",
                    status="open",
                )
            )
            await session.flush()
            removed = await _remove_open_replay_flag(session, graph.trip.id)
            preserved, changed = await _write_replay_flag(
                session,
                target=SimpleNamespace(
                    trip_id=graph.trip.id,
                    analytics_id=graph.analytics.id,
                ),
                match_kind="time_shifted",
                total_match_count=99,
                cross_account_match_count=99,
                sampled_trip_ids=[],
                settings=settings,
            )
            await session.commit()
            return removed, changed, preserved.evidence

    removed, changed, evidence = asyncio.run(run())
    assert removed is False
    assert changed is False
    assert evidence == original_evidence
