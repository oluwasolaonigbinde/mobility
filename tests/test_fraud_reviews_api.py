import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from conftest import auth_headers, create_test_trip_analytics
from sqlalchemy import select
from starlette import status as http_status
from test_trip_analytics import PASSWORD, create_analytics_graph

from app.models.audit import AuditEvent
from app.models.trip_analytics import FraudFlag


def create_review_flag(db_sessionmaker) -> tuple[object, FraudFlag]:
    admin, _, _, campaign, profile, vehicle, assignment, trip = create_analytics_graph(
        db_sessionmaker
    )
    analytics = create_test_trip_analytics(
        db_sessionmaker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
    )

    async def create() -> FraudFlag:
        async with db_sessionmaker() as session:
            flag = FraudFlag(
                trip_session_id=trip.id,
                trip_analytics_id=analytics.id,
                assignment_id=assignment.id,
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                flag_type="impossible_speed",
                severity="high",
                status="open",
                description="Synthetic review evidence.",
                evidence={"observed_mps": 90},
                detected_at=datetime.now(UTC),
            )
            session.add(flag)
            await session.commit()
            await session.refresh(flag)
            return flag

    return admin, asyncio.run(create())


def review_audits(db_sessionmaker, flag_id) -> list[AuditEvent]:
    async def fetch() -> list[AuditEvent]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.entity_type == "fraud_flag",
                    AuditEvent.entity_id == str(flag_id),
                )
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
            return list(result.scalars().all())

    return asyncio.run(fetch())


def test_admin_can_acknowledge_then_confirm_and_list_enriched_flag(
    db_client,
    db_sessionmaker,
) -> None:
    admin, flag = create_review_flag(db_sessionmaker)
    headers = auth_headers(db_client, admin.email, PASSWORD)

    acknowledged = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=headers,
    )
    assert acknowledged.status_code == http_status.HTTP_200_OK
    acknowledged_body = acknowledged.json()
    assert acknowledged_body["status"] == "acknowledged"
    assert acknowledged_body["reviewed_by_user_id"] == str(admin.id)
    assert acknowledged_body["reviewed_at"] is not None
    assert acknowledged_body["resolution_note"] is None

    confirmed = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "confirmed", "note": "  Evidence verified.  "},
    )
    assert confirmed.status_code == http_status.HTTP_200_OK
    confirmed_body = confirmed.json()
    assert confirmed_body["status"] == "confirmed"
    assert confirmed_body["reviewed_by_user_id"] == str(admin.id)
    assert confirmed_body["reviewed_at"] is not None
    assert confirmed_body["resolution_note"] == "Evidence verified."

    listed = db_client.get(
        "/api/v1/admin/fraud-flags?status=confirmed",
        headers=headers,
    )
    assert listed.status_code == http_status.HTTP_200_OK
    assert listed.json()["total"] == 1
    assert listed.json()["items"] == [confirmed_body]

    audits = review_audits(db_sessionmaker, flag.id)
    assert {row.action for row in audits} == {
        "admin.fraud_flag.acknowledged",
        "admin.fraud_flag.resolved",
    }
    assert {row.actor_user_id for row in audits} == {admin.id}


def test_direct_resolve_and_terminal_cross_transition_conflict_but_retry_is_idempotent(
    db_client,
    db_sessionmaker,
) -> None:
    admin, flag = create_review_flag(db_sessionmaker)
    headers = auth_headers(db_client, admin.email, PASSWORD)
    payload = {"outcome": "dismissed", "note": "Not supported by route evidence."}

    direct = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json=payload,
    )
    acknowledge = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge",
        headers=headers,
    )
    first = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json=payload,
    )
    retry = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json=payload,
    )
    conflict = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=headers,
        json={"outcome": "confirmed", "note": "Changed decision."},
    )

    assert direct.status_code == http_status.HTTP_409_CONFLICT
    assert direct.json()["error"]["code"] == "FRAUD_FLAG_INVALID_TRANSITION"
    assert acknowledge.status_code == http_status.HTTP_200_OK
    assert first.status_code == http_status.HTTP_200_OK
    assert first.json()["status"] == "dismissed"
    assert retry.status_code == http_status.HTTP_200_OK
    assert retry.json() == first.json()
    assert conflict.status_code == http_status.HTTP_409_CONFLICT
    assert conflict.json()["error"]["code"] == "FRAUD_FLAG_INVALID_TRANSITION"
    audits = review_audits(db_sessionmaker, flag.id)
    assert len(audits) == 2
    assert [row.action for row in audits].count("admin.fraud_flag.resolved") == 1


def test_review_routes_require_admin_and_return_not_found(
    db_client,
    db_sessionmaker,
) -> None:
    _, flag = create_review_flag(db_sessionmaker)
    advertiser_headers = auth_headers(db_client, "advertiser@example.com", PASSWORD)

    for path, payload in (
        (f"/api/v1/admin/fraud-flags/{flag.id}/review/acknowledge", None),
        (
            f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
            {"outcome": "confirmed", "note": "Verified."},
        ),
    ):
        assert db_client.post(path, json=payload).status_code == http_status.HTTP_401_UNAUTHORIZED
        assert (
            db_client.post(path, headers=advertiser_headers, json=payload).status_code
            == http_status.HTTP_403_FORBIDDEN
        )

    missing = db_client.post(
        f"/api/v1/admin/fraud-flags/{uuid4()}/review/acknowledge",
        headers=auth_headers(db_client, "admin@example.com", PASSWORD),
    )
    assert missing.status_code == http_status.HTTP_404_NOT_FOUND


def test_resolve_request_rejects_invalid_or_ambiguous_payloads(
    db_client,
    db_sessionmaker,
) -> None:
    admin, flag = create_review_flag(db_sessionmaker)
    headers = auth_headers(db_client, admin.email, PASSWORD)
    url = f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve"

    invalid_payloads = [
        {},
        {"outcome": "open", "note": "Invalid outcome."},
        {"outcome": "confirmed", "note": "   "},
        {"outcome": "confirmed", "note": "x" * 2001},
        {"outcome": "confirmed", "note": "Valid.", "unexpected": True},
    ]
    for payload in invalid_payloads:
        response = db_client.post(url, headers=headers, json=payload)
        assert response.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT

    assert review_audits(db_sessionmaker, flag.id) == []
