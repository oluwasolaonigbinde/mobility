"""Bounded staff projections and explicit query-option denial matrix."""

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from authorization_matrix import _dependency_names, _routes
from conftest import auth_headers, create_test_driver_profile, create_test_user, fetch_audit_events
from test_fraud_assessments import create_flag
from test_fraud_holds import build_review_graph
from test_mny03a_earnings_release import create_ledger

from app.main import create_app
from app.models.driver import DriverOnboardingStatus
from app.models.trip_analytics import FraudFlag
from app.models.user import UserRole, UserStatus

PASSWORD = "long-secure-password"
# These entries complement the route-generated matrix with the approved read options.
READ_OPTIONS = {
    "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions": {
        "effective_before": "2026-10-02T00:00:00Z"
    },
    "/api/v1/admin/driver-applications": {"include_staff_added": "true", "oldest_first": "true"},
    "/api/v1/admin/vehicles": {"oldest_first": "true"},
    "/api/v1/admin/campaign-assignments": {"oldest_first": "true"},
    "/api/v1/admin/campaigns": {"oldest_first": "true"},
    "/api/v1/admin/campaigns/pending-review": {"oldest_first": "true"},
    "/api/v1/admin/installation-evidence/pending": {"limit": 1, "offset": 1},
    "/api/v1/admin/campaign-change-requests/pending": {"limit": 1, "status": "pending_admin"},
    "/api/v1/admin/evidence-verifications": {
        "oldest_first": "true",
        "verification_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
        "trip_session_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
    },
    "/api/v1/admin/fraud-flags": {"group_by_trip": "true", "unresolved_only": "true"},
    "/api/v1/admin/trips/quarantined-batches": {"status": "quarantined"},
    "/api/v1/admin/payout-batches/summaries": {"needs_attention": "true", "oldest_first": "true"},
    "/api/v1/admin/payouts/automatic/alerts": {"oldest_first": "true"},
    "/api/v1/admin/payouts/correction-orders": {"oldest_first": "true"},
    "/api/v1/admin/complaints": {"oldest_first": "true"},
    "/api/v1/admin/manual-driver-contact-tasks": {"open_only": "true", "oldest_first": "true"},
    "/api/v1/admin/fraud-disputes": {"oldest_first": "true"},
}


@pytest.fixture
def db_sessionmaker(postgis_db_sessionmaker):
    return postgis_db_sessionmaker


def test_read_options_inventory_keeps_staff_dependency():
    routes = {path: route for route, path in _routes(create_app().routes) if "GET" in route.methods}
    for path in READ_OPTIONS:
        assert "require_admin_user" in _dependency_names(routes[path]), path


def test_read_query_denials_leave_no_audit(db_client, db_sessionmaker, settings):
    users = [
        create_test_user(db_sessionmaker, email="reads-driver@example.com", role=UserRole.DRIVER),
        create_test_user(
            db_sessionmaker, email="reads-advertiser@example.com", role=UserRole.ADVERTISER
        ),
    ]
    headers = [{}] + [auth_headers(db_client, u.email, PASSWORD) for u in users]
    suspended = create_test_user(
        db_sessionmaker, email="reads-suspended@example.com", user_status=UserStatus.SUSPENDED
    )
    from test_admin_hub_reads import bearer

    headers.append(bearer(suspended, settings))
    before = len(fetch_audit_events(db_sessionmaker))
    for path, query in READ_OPTIONS.items():
        for principal in headers:
            response = db_client.get(path, params={"limit": 1, **query}, headers=principal)
            assert response.status_code in {401, 403}, (path, response.status_code)
    assert len(fetch_audit_events(db_sessionmaker)) == before


def test_group_before_count_and_limit_and_hold_once(db_client, db_sessionmaker):
    graph = build_review_graph(db_sessionmaker, "grouped")
    other = build_review_graph(db_sessionmaker, "grouped-other")
    first = create_flag(db_sessionmaker, graph)
    second = create_flag(db_sessionmaker, graph, flag_type="poor_accuracy")
    third = create_flag(db_sessionmaker, other)
    create_ledger(db_sessionmaker, graph, amount="3263.51")

    async def dates():
        async with db_sessionmaker() as session:
            f = await session.get(FraudFlag, first.id)
            f.detected_at -= timedelta(days=2)
            s = await session.get(FraudFlag, second.id)
            s.status = "acknowledged"
            s.reviewed_by_user_id = graph.admin.id
            s.reviewed_at = s.detected_at
            await session.commit()

    asyncio.run(dates())
    headers = auth_headers(db_client, graph.admin.email, PASSWORD)
    query = {"limit": 1, "unresolved_only": "true", "group_by_trip": "true", "oldest_first": "true"}
    page = db_client.get("/api/v1/admin/fraud-flags", params=query, headers=headers)
    assert page.status_code == 200, page.text
    data = page.json()
    assert data["total"] == 2 and len(data["items"]) == 1
    row = data["items"][0]
    assert row["id"] == str(first.id) and row["problem_count"] == 2
    assert row["driver_name"] and row["campaign_name"] and row["trip_started_at"]
    assert Decimal(row["money_effect"]["held_pending_net"]) == Decimal("3263.51")
    assert "latitude" not in row and "route" not in row
    next_page = db_client.get(
        "/api/v1/admin/fraud-flags", params={**query, "offset": 1}, headers=headers
    )
    assert next_page.json()["items"][0]["id"] == str(third.id)
    # Exact IDs are independent of visible page and still filtered by driver identity.
    selected = db_client.get(
        "/api/v1/admin/fraud-flags", params={"flag_id": str(third.id), "limit": 1}, headers=headers
    )
    assert selected.json()["total"] == 1
    wrong = db_client.get(
        "/api/v1/admin/fraud-flags",
        params={"flag_id": str(third.id), "driver_profile_id": str(graph.profile.id)},
        headers=headers,
    )
    assert wrong.json()["total"] == 0


def test_unified_applicants_has_one_filtered_total_and_staff_identity(db_client, db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="applicants-admin@example.com")
    driver = create_test_user(
        db_sessionmaker, email="pending-staff@example.com", role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(
        db_sessionmaker, user_id=driver.id, onboarding_status=DriverOnboardingStatus.PENDING
    )
    active = create_test_user(
        db_sessionmaker, email="active-staff@example.com", role=UserRole.DRIVER
    )
    create_test_driver_profile(
        db_sessionmaker, user_id=active.id, onboarding_status=DriverOnboardingStatus.ACTIVE
    )
    response = db_client.get(
        "/api/v1/admin/driver-applications",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        params={"include_staff_added": "true", "q": driver.email, "limit": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1 and data["items"] == []
    assert data["applicants"][0]["driver_profile_id"] == str(profile.id)
    assert data["applicants"][0]["application_id"] is None
    assert data["applicants"][0]["kind"] == "staff_added"
