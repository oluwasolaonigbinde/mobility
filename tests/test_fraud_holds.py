import asyncio
from datetime import UTC, datetime

import pytest
from conftest import auth_headers, create_test_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_fraud_assessments import build_graph, create_flag

from app.core.errors import AppError
from app.models.trip_analytics import FraudFlag, FraudFlagStatus
from app.models.user import User
from app.services.fraud_holds import (
    HOLD_ACTIVE_STATUSES,
    acknowledge_fraud_flag,
    fraud_hold_counts,
    hold_active,
    resolve_fraud_flag,
)

PASSWORD = "long-secure-password"
NOW = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)


def build_review_graph(db_sessionmaker, tag: str):
    graph = build_graph(db_sessionmaker, tag)

    async def fetch_admin():
        async with db_sessionmaker() as session:
            return await session.scalar(
                select(User).where(User.email == f"admin-{tag}@example.com")
            )

    graph.admin = asyncio.run(fetch_admin())
    return graph


def test_hold_predicate_has_one_explicit_fail_closed_status_set() -> None:
    assert HOLD_ACTIVE_STATUSES == {"open", "acknowledged", "confirmed"}
    for status in FraudFlagStatus:
        assert hold_active(status.value) is (status.value != "dismissed")


def test_review_lifecycle_and_exact_retries_are_idempotent(
    db_client,
    db_sessionmaker,
) -> None:
    graph = build_review_graph(db_sessionmaker, "review-lifecycle")
    flag = create_flag(db_sessionmaker, graph)
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)

    first_ack = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=headers,
    )
    retry_ack = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=headers,
    )
    resolved = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "confirmed", "note": "  Route evidence verified.  "},
    )
    retry_resolved = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "confirmed", "note": "Route evidence verified."},
    )

    assert first_ack.status_code == 200
    assert first_ack.json()["status"] == "acknowledged"
    assert first_ack.json()["reviewed_by_user_id"] == str(graph.admin.id)
    assert retry_ack.status_code == 200
    assert retry_ack.json()["reviewed_at"] == first_ack.json()["reviewed_at"]
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "confirmed"
    assert resolved.json()["resolution_note"] == "Route evidence verified."
    assert retry_resolved.status_code == 200
    assert retry_resolved.json()["reviewed_at"] == resolved.json()["reviewed_at"]


def test_review_rejects_illegal_transitions_and_non_exact_replays(
    db_client,
    db_sessionmaker,
) -> None:
    graph = build_review_graph(db_sessionmaker, "review-errors")
    flag = create_flag(db_sessionmaker, graph)
    other_admin = create_test_user(db_sessionmaker, email="other-reviewer@example.com")
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    other_headers = auth_headers(db_client, other_admin.email, PASSWORD)

    resolve_open = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "dismissed", "note": "No anomaly."},
    )
    assert resolve_open.status_code == 409
    assert resolve_open.json()["error"]["code"] == "FRAUD_FLAG_INVALID_TRANSITION"

    assert db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=headers,
    ).status_code == 200
    other_actor_retry = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=other_headers,
    )
    assert other_actor_retry.status_code == 409
    assert other_actor_retry.json()["error"]["code"] == "FRAUD_FLAG_REVIEW_REPLAY_CONFLICT"

    assert db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "dismissed", "note": "Distinct route confirmed."},
    ).status_code == 200
    changed_note_retry = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "dismissed", "note": "Different note."},
    )
    cross_outcome = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "confirmed", "note": "Different outcome."},
    )
    assert changed_note_retry.status_code == 409
    assert changed_note_retry.json()["error"]["code"] == "FRAUD_FLAG_REVIEW_REPLAY_CONFLICT"
    assert cross_outcome.status_code == 409
    assert cross_outcome.json()["error"]["code"] == "FRAUD_FLAG_INVALID_TRANSITION"


def test_dismissed_flag_clears_hold_and_permits_one_new_open_flag(
    db_sessionmaker,
) -> None:
    graph = build_review_graph(db_sessionmaker, "dismiss-redetect")
    flag = create_flag(db_sessionmaker, graph)

    async def run() -> tuple[dict[str, int], dict[str, int], int]:
        async with db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                now=NOW,
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="dismissed",
                resolution_note="Legitimate route variation.",
                now=NOW,
            )
            await session.commit()

        async with db_sessionmaker() as session:
            before = await fraud_hold_counts(session, graph.trip.id)
            original = await session.get(FraudFlag, flag.id)
            replacement = FraudFlag(
                trip_session_id=original.trip_session_id,
                trip_analytics_id=original.trip_analytics_id,
                assignment_id=original.assignment_id,
                campaign_id=original.campaign_id,
                driver_profile_id=original.driver_profile_id,
                vehicle_id=original.vehicle_id,
                flag_type=original.flag_type,
                severity=original.severity,
                status="open",
                description="Fresh detector evidence",
                evidence={"fixture": "redetected"},
                detected_at=NOW,
            )
            session.add(replacement)
            await session.commit()

        async with db_sessionmaker() as session:
            after = await fraud_hold_counts(session, graph.trip.id)
            row_count = await session.scalar(
                select(func.count(FraudFlag.id)).where(
                    FraudFlag.trip_session_id == graph.trip.id,
                    FraudFlag.flag_type == flag.flag_type,
                )
            )
            return before, after, int(row_count or 0)

    before, after, row_count = asyncio.run(run())
    assert before == {"low": 0, "medium": 0, "high": 0}
    assert after == {"low": 0, "medium": 0, "high": 1}
    assert row_count == 2


@pytest.mark.parametrize("status", ["open", "acknowledged", "confirmed"])
def test_nonterminal_unique_index_rejects_duplicate_trip_type(
    db_sessionmaker,
    status: str,
) -> None:
    graph = build_review_graph(db_sessionmaker, f"dedup-{status}")
    first = create_flag(db_sessionmaker, graph)

    async def run() -> None:
        async with db_sessionmaker() as session:
            stored = await session.get(FraudFlag, first.id)
            stored.status = status
            if status != "open":
                stored.reviewed_by_user_id = graph.admin.id
                stored.reviewed_at = NOW
            if status == "confirmed":
                stored.resolution_note = "Confirmed fraud."
            await session.flush()
            session.add(
                FraudFlag(
                    trip_session_id=stored.trip_session_id,
                    trip_analytics_id=stored.trip_analytics_id,
                    assignment_id=stored.assignment_id,
                    campaign_id=stored.campaign_id,
                    driver_profile_id=stored.driver_profile_id,
                    vehicle_id=stored.vehicle_id,
                    flag_type=stored.flag_type,
                    severity=stored.severity,
                    status="open",
                    description="duplicate",
                    evidence={},
                    detected_at=NOW,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()

    asyncio.run(run())


def test_postgres_two_reviewers_serialize_on_one_flag(postgis_db_sessionmaker) -> None:
    graph = build_review_graph(postgis_db_sessionmaker, "review-race")
    flag = create_flag(postgis_db_sessionmaker, graph)
    other_admin = create_test_user(
        postgis_db_sessionmaker,
        email="other-race-reviewer@example.com",
    )

    async def review(actor_id):
        async with postgis_db_sessionmaker() as session:
            try:
                result = await acknowledge_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=actor_id,
                    now=NOW,
                )
                await session.commit()
                return ("ok", result.changed)
            except AppError as exc:
                await session.rollback()
                return (exc.code, None)

    async def run():
        return await asyncio.gather(review(graph.admin.id), review(other_admin.id))

    results = asyncio.run(run())
    assert sorted(results) == [
        ("FRAUD_FLAG_REVIEW_REPLAY_CONFLICT", None),
        ("ok", True),
    ]
