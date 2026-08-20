"""MNY-06C: maker-checker payout correction orders (Q22, PR6/PR7/PR12/PR13).

Covers the campaign/Lagos-day projection (the PR6 core in dry-run), the full
state machine with its illegal transitions, creator-approves-own rejection at
the service AND database layers, stale-projection blocking at approve and
execute, idempotent execution under a PostGIS double-execute race, Q22
positive-delta pending entries carrying their own release_at, negative-delta
reversal semantics (carry-forward debt is MNY-11A and deliberately absent),
v2/v3/mixed-day recompute correctness through the order flow, the retired
direct endpoint, and value-complete audit events.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from conftest import (
    auth_headers,
    create_test_user,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from starlette import status as http_status
from test_payouts_v2 import (
    build_v2_graph,
    driver_totals,
    lagos_day_for,
    moving_points,
    pipeline_to_v2,
)
from test_payouts_v3 import bind_v2_graph, build_mixed_engine_day
from test_trip_processing import PASSWORD, add_pings, run_pipeline

from app.core.errors import AppError
from app.models.payout import (
    CampaignPayoutRule,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.services import payout_corrections
from app.services.payout_corrections import (
    approve_correction_order,
    create_correction_order,
    execute_correction_order,
    project_campaign_day,
    reject_correction_order,
    submit_correction_order,
)
from app.services.payouts import PAYOUT_V3, driver_trip_earnings_breakdown

RELEASE_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


# --- Helpers -----------------------------------------------------------------


def service(db_sessionmaker, coro_factory):
    async def run():
        async with db_sessionmaker() as session:
            result = await coro_factory(session)
            await session.commit()
            return result

    return asyncio.run(run())


def create_order(db_sessionmaker, settings, graph, *, reason="test correction"):
    return service(
        db_sessionmaker,
        lambda session: create_correction_order(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            reason=reason,
            created_by_user_id=graph.admin.id,
            settings=settings,
        ),
    )


def submit(db_sessionmaker, order_id, actor_id):
    return service(
        db_sessionmaker,
        lambda session: submit_correction_order(session, order_id=order_id, actor_user_id=actor_id),
    )


def approve(db_sessionmaker, settings, order_id, actor_id):
    return service(
        db_sessionmaker,
        lambda session: approve_correction_order(
            session, order_id=order_id, actor_user_id=actor_id, settings=settings
        ),
    )


def execute(db_sessionmaker, settings, order_id, actor_id, *, release_at=RELEASE_AT):
    return service(
        db_sessionmaker,
        lambda session: execute_correction_order(
            session,
            order_id=order_id,
            actor_user_id=actor_id,
            release_at=release_at,
            request_metadata={"source": "test"},
            settings=settings,
        ),
    )


def second_admin(db_sessionmaker, tag):
    return create_test_user(db_sessionmaker, email=f"approver-{tag}@example.com")


def submitted_order(db_sessionmaker, settings, graph, tag):
    """create -> submit, plus a second admin to approve (maker-checker)."""
    approver = second_admin(db_sessionmaker, tag)
    order = create_order(db_sessionmaker, settings, graph)
    submit(db_sessionmaker, order.id, graph.admin.id)
    return order, approver


def approved_order(db_sessionmaker, settings, graph, tag):
    order, approver = submitted_order(db_sessionmaker, settings, graph, tag)
    approve(db_sessionmaker, settings, order.id, approver.id)
    return order, approver


def reload_order(db_sessionmaker, order_id) -> PayoutCorrectionOrder:
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.get(PayoutCorrectionOrder, order_id)

    return asyncio.run(fetch())


def raise_rule_rate(db_sessionmaker, rule_id, rate: str) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, rule_id)
            rule.hourly_rate_naira = Decimal(rate)
            await session.commit()

    asyncio.run(run())


def void_trip_payout(db_sessionmaker, trip_id) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(run())


def set_trip_payout_status(db_sessionmaker, trip_id, status_value: str) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.status = status_value
            await session.commit()

    asyncio.run(run())


def drift_inputs(db_sessionmaker, graph) -> None:
    """Cheapest real input drift (PR12): a new ping batch on the day's trip
    changes the trip's current ping-set fingerprint."""
    add_pings(
        db_sessionmaker,
        trip_id=graph.trip.id,
        points=moving_points(graph.trip.started_at + timedelta(minutes=5), minutes=5),
        idempotency_key=f"drift-{uuid4()}",
    )


def correction_entries(db_sessionmaker) -> list[EarningsLedgerEntry]:
    return [
        entry
        for entry in fetch_earnings_ledger_entries(db_sessionmaker)
        if (entry.ledger_metadata or {}).get("correction_order_id")
    ]


# --- Projection + create (C1) ------------------------------------------------


def test_create_projects_value_complete_draft_and_matches_dry_run_endpoint(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-create")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")

    admin_headers = auth_headers(postgis_db_client, graph.admin.email, PASSWORD)
    day = lagos_day_for(graph.trip.started_at).isoformat()

    # Read-only dry-run first: same PR6 core, no state created.
    projection = postgis_db_client.get(
        "/api/v1/admin/payouts/day-projection",
        headers=admin_headers,
        params={"campaign_id": str(graph.campaign.id), "lagos_day": day},
    )
    assert projection.status_code == http_status.HTTP_200_OK
    projected = projection.json()
    assert projected["projected_delta"]["day_totals"]["delta_amount"] == "150.00"

    response = postgis_db_client.post(
        "/api/v1/admin/payouts/correction-orders",
        headers=admin_headers,
        json={
            "campaign_id": str(graph.campaign.id),
            "lagos_day": day,
            "reason": "rate was corrected upward after the fact",
        },
    )
    assert response.status_code == http_status.HTTP_201_CREATED
    body = response.json()
    assert body["status"] == "draft"
    assert body["projection_fingerprint"] == projected["projection_fingerprint"]
    assert body["projected_at"] is not None
    trips = body["projected_delta"]["trips"]
    assert len(trips) == 1
    # Per-trip old vs new amounts, Decimal strings on the wire (§6.4.4).
    assert trips[0]["previous_posted_amount"] == "600.00"
    assert trips[0]["target_amount"] == "750.00"
    assert trips[0]["delta_amount"] == "150.00"
    assert body["projected_delta"]["day_totals"]["projected_adjustment_count"] == 1

    detail = postgis_db_client.get(
        f"/api/v1/admin/payouts/correction-orders/{body['id']}",
        headers=admin_headers,
    )
    assert detail.status_code == http_status.HTTP_200_OK
    assert detail.json() == body

    listed = postgis_db_client.get(
        "/api/v1/admin/payouts/correction-orders",
        headers=admin_headers,
        params={"campaign_id": str(graph.campaign.id)},
    )
    assert listed.status_code == http_status.HTTP_200_OK
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == body["id"]

    # Nothing was written by projecting: the day's money is untouched.
    assert correction_entries(postgis_db_sessionmaker) == []


def test_correction_endpoints_require_admin(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-perm")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    day = lagos_day_for(graph.trip.started_at).isoformat()
    body = {
        "campaign_id": str(graph.campaign.id),
        "lagos_day": day,
        "reason": "perm probe",
    }
    assert (
        postgis_db_client.post("/api/v1/admin/payouts/correction-orders", json=body).status_code
        == http_status.HTTP_401_UNAUTHORIZED
    )
    driver_headers = auth_headers(postgis_db_client, graph.driver.email, PASSWORD)
    assert (
        postgis_db_client.post(
            "/api/v1/admin/payouts/correction-orders",
            json=body,
            headers=driver_headers,
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )
    assert (
        postgis_db_client.get(
            "/api/v1/admin/payouts/day-projection",
            headers=driver_headers,
            params={"campaign_id": str(graph.campaign.id), "lagos_day": day},
        ).status_code
        == http_status.HTTP_403_FORBIDDEN
    )


# --- State machine (C1) ------------------------------------------------------


def test_full_lifecycle_via_api_with_maker_checker_actors(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-life")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")
    approver = second_admin(postgis_db_sessionmaker, "co-life")

    creator_headers = auth_headers(postgis_db_client, graph.admin.email, PASSWORD)
    approver_headers = auth_headers(postgis_db_client, approver.email, PASSWORD)
    day = lagos_day_for(graph.trip.started_at).isoformat()

    created = postgis_db_client.post(
        "/api/v1/admin/payouts/correction-orders",
        headers=creator_headers,
        json={
            "campaign_id": str(graph.campaign.id),
            "lagos_day": day,
            "reason": "upward rate correction",
        },
    )
    order_id = created.json()["id"]

    submitted = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/submit",
        headers=creator_headers,
    )
    assert submitted.status_code == http_status.HTTP_200_OK
    assert submitted.json()["status"] == "pending_approval"

    # Creator approving own order: 403 at the service boundary (C1).
    self_approval = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/approve",
        headers=creator_headers,
    )
    assert self_approval.status_code == http_status.HTTP_403_FORBIDDEN
    assert self_approval.json()["error"]["code"] == "CORRECTION_ORDER_SELF_APPROVAL"

    approved = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/approve",
        headers=approver_headers,
    )
    assert approved.status_code == http_status.HTTP_200_OK
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by_user_id"] == str(approver.id)
    assert approved.json()["decided_at"] is not None

    # Positive delta without release_at -> 400, no state change (Q22).
    missing_release = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/execute",
        headers=creator_headers,
    )
    assert missing_release.status_code == http_status.HTTP_400_BAD_REQUEST
    assert missing_release.json()["error"]["code"] == "CORRECTION_RELEASE_AT_REQUIRED"
    assert reload_order(postgis_db_sessionmaker, order_id).status == "approved"

    # The creator MAY execute: independent approval already happened — Q22
    # forbids only creator-approves-own.
    executed = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/execute",
        headers=creator_headers,
        json={"release_at": RELEASE_AT.isoformat()},
    )
    assert executed.status_code == http_status.HTTP_200_OK
    executed_body = executed.json()
    assert executed_body["status"] == "executed"
    assert executed_body["executed_by_user_id"] == str(graph.admin.id)
    result = executed_body["execution_result"]
    assert result["adjustment_count"] == 1
    assert result["reversal_count"] == 0
    assert result["release_at"] == RELEASE_AT.isoformat()
    trip_result = result["drivers"][0]["trips"][0]
    assert trip_result["delta_amount"] == "150.00"
    assert trip_result["entry_type"] == "adjustment"
    assert trip_result["entry_status"] == "pending"

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("150.00")
    assert entries[0].status == EarningsLedgerEntryStatus.PENDING.value
    assert entries[0].release_at == RELEASE_AT
    assert entries[0].ledger_metadata["correction_order_id"] == order_id

    # Idempotent replay: same recorded result, no second money effect (C3).
    replay = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{order_id}/execute",
        headers=approver_headers,
        json={"release_at": RELEASE_AT.isoformat()},
    )
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json()["execution_result"] == result
    assert len(correction_entries(postgis_db_sessionmaker)) == 1

    # Value-complete audit trail (C4): both actors, reason, old/new status,
    # money values.
    events = {
        event.action: event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action.startswith("admin.payout_correction_order.")
    }
    assert set(events) == {
        "admin.payout_correction_order.created",
        "admin.payout_correction_order.submitted",
        "admin.payout_correction_order.approved",
        "admin.payout_correction_order.executed",
    }
    created_meta = events["admin.payout_correction_order.created"].event_metadata
    assert created_meta["status_before"] is None
    assert created_meta["status_after"] == "draft"
    assert created_meta["reason"] == "upward rate correction"
    assert created_meta["projected_delta"]["trips"][0]["previous_posted_amount"] == "600.00"
    approved_meta = events["admin.payout_correction_order.approved"].event_metadata
    assert approved_meta["status_before"] == "pending_approval"
    assert approved_meta["status_after"] == "approved"
    assert approved_meta["created_by_user_id"] == str(graph.admin.id)
    assert approved_meta["approved_by_user_id"] == str(approver.id)
    executed_meta = events["admin.payout_correction_order.executed"].event_metadata
    assert executed_meta["status_before"] == "approved"
    assert executed_meta["status_after"] == "executed"
    assert executed_meta["executed_by_user_id"] == str(graph.admin.id)
    assert executed_meta["execution_result"]["drivers"][0]["trips"][0]["delta_amount"] == "150.00"
    assert executed_meta["decided_at"] is not None
    assert executed_meta["executed_at"] is not None

    # One executed order audits exactly once (the replay mutated nothing).
    executed_events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.payout_correction_order.executed"
    ]
    assert len(executed_events) == 1

    # Reject path over the API: a fresh order for the (now settled) day is
    # rejected by the approver, with a value-complete audit event.
    second = postgis_db_client.post(
        "/api/v1/admin/payouts/correction-orders",
        headers=creator_headers,
        json={
            "campaign_id": str(graph.campaign.id),
            "lagos_day": day,
            "reason": "second thoughts",
        },
    )
    second_id = second.json()["id"]
    postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{second_id}/submit",
        headers=creator_headers,
    )
    rejected = postgis_db_client.post(
        f"/api/v1/admin/payouts/correction-orders/{second_id}/reject",
        headers=approver_headers,
    )
    assert rejected.status_code == http_status.HTTP_200_OK
    assert rejected.json()["status"] == "rejected"
    reject_events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.payout_correction_order.rejected"
    ]
    assert len(reject_events) == 1
    reject_meta = reject_events[0].event_metadata
    assert reject_meta["status_before"] == "pending_approval"
    assert reject_meta["status_after"] == "rejected"
    assert reject_meta["rejected_by_user_id"] == str(approver.id)
    assert reject_meta["reason"] == "second thoughts"
    assert reject_events[0].actor_user_id == approver.id


def test_reject_path_and_illegal_transitions(postgis_db_sessionmaker, settings) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-illegal")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    approver = second_admin(postgis_db_sessionmaker, "co-illegal")

    def expect_invalid(coro_factory, action):
        try:
            service(postgis_db_sessionmaker, coro_factory)
            raise AssertionError(f"expected CORRECTION_ORDER_INVALID_STATE for {action}")
        except AppError as exc:
            assert exc.code == "CORRECTION_ORDER_INVALID_STATE"
            assert exc.status_code == http_status.HTTP_409_CONFLICT

    order = create_order(postgis_db_sessionmaker, settings, graph)

    # draft: approve/reject/execute are illegal.
    expect_invalid(
        lambda session: approve_correction_order(
            session, order_id=order.id, actor_user_id=approver.id, settings=settings
        ),
        "approve draft",
    )
    expect_invalid(
        lambda session: reject_correction_order(
            session, order_id=order.id, actor_user_id=approver.id
        ),
        "reject draft",
    )
    expect_invalid(
        lambda session: execute_correction_order(
            session,
            order_id=order.id,
            actor_user_id=approver.id,
            release_at=RELEASE_AT,
            request_metadata={},
            settings=settings,
        ),
        "execute draft",
    )

    submit(postgis_db_sessionmaker, order.id, graph.admin.id)
    # pending_approval: submit again / execute are illegal.
    expect_invalid(
        lambda session: submit_correction_order(
            session, order_id=order.id, actor_user_id=graph.admin.id
        ),
        "submit pending",
    )
    expect_invalid(
        lambda session: execute_correction_order(
            session,
            order_id=order.id,
            actor_user_id=approver.id,
            release_at=RELEASE_AT,
            request_metadata={},
            settings=settings,
        ),
        "execute pending",
    )

    rejected = service(
        postgis_db_sessionmaker,
        lambda session: reject_correction_order(
            session, order_id=order.id, actor_user_id=approver.id
        ),
    )
    assert rejected.status == PayoutCorrectionOrderStatus.REJECTED.value
    assert rejected.decided_at is not None
    # rejected is terminal.
    expect_invalid(
        lambda session: submit_correction_order(
            session, order_id=order.id, actor_user_id=graph.admin.id
        ),
        "submit rejected",
    )
    expect_invalid(
        lambda session: execute_correction_order(
            session,
            order_id=order.id,
            actor_user_id=approver.id,
            release_at=RELEASE_AT,
            request_metadata={},
            settings=settings,
        ),
        "execute rejected",
    )
    assert correction_entries(postgis_db_sessionmaker) == []

    # Unknown order -> 404.
    try:
        service(
            postgis_db_sessionmaker,
            lambda session: submit_correction_order(
                session, order_id=uuid4(), actor_user_id=graph.admin.id
            ),
        )
        raise AssertionError("expected CORRECTION_ORDER_NOT_FOUND")
    except AppError as exc:
        assert exc.code == "CORRECTION_ORDER_NOT_FOUND"


def test_creator_approval_is_blocked_by_the_database_check_too(
    postgis_db_sessionmaker, settings
) -> None:
    """C1: the maker-checker rule holds below the service layer — a direct
    UPDATE writing approved_by = created_by violates the CHECK constraint."""
    graph = build_v2_graph(postgis_db_sessionmaker, "co-dbcheck")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    order = create_order(postgis_db_sessionmaker, settings, graph)

    async def direct_update() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(PayoutCorrectionOrder)
                .where(PayoutCorrectionOrder.id == order.id)
                .values(approved_by_user_id=graph.admin.id)
            )
            await session.commit()

    try:
        asyncio.run(direct_update())
        raise AssertionError("expected IntegrityError")
    except IntegrityError as exc:
        assert "ck_payout_correction_orders_approver_not_creator" in str(exc.orig)


# --- Stale projection (C2) ---------------------------------------------------


def test_input_drift_marks_order_stale_at_approve(postgis_db_sessionmaker, settings) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-stale-appr")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    order, approver = submitted_order(postgis_db_sessionmaker, settings, graph, "co-stale-appr")

    drift_inputs(postgis_db_sessionmaker, graph)

    try:
        approve(postgis_db_sessionmaker, settings, order.id, approver.id)
        raise AssertionError("expected CORRECTION_ORDER_STALE")
    except AppError as exc:
        assert exc.code == "CORRECTION_ORDER_STALE"
        assert exc.status_code == http_status.HTTP_409_CONFLICT

    reloaded = reload_order(postgis_db_sessionmaker, order.id)
    assert reloaded.status == PayoutCorrectionOrderStatus.STALE.value
    assert reloaded.approved_by_user_id is None

    # stale is terminal: re-projection means a NEW order.
    try:
        submit(postgis_db_sessionmaker, order.id, graph.admin.id)
        raise AssertionError("expected CORRECTION_ORDER_INVALID_STATE")
    except AppError as exc:
        assert exc.code == "CORRECTION_ORDER_INVALID_STATE"

    stale_events = [
        event
        for event in fetch_audit_events(postgis_db_sessionmaker)
        if event.action == "admin.payout_correction_order.stale"
    ]
    assert len(stale_events) == 1
    assert stale_events[0].event_metadata["detected_during"] == "approve"
    assert stale_events[0].event_metadata["status_after"] == "stale"


def test_input_drift_marks_order_stale_at_execute_with_no_money_effect(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-stale-exec")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-stale-exec")

    drift_inputs(postgis_db_sessionmaker, graph)

    try:
        execute(postgis_db_sessionmaker, settings, order.id, approver.id)
        raise AssertionError("expected CORRECTION_ORDER_STALE")
    except AppError as exc:
        assert exc.code == "CORRECTION_ORDER_STALE"

    reloaded = reload_order(postgis_db_sessionmaker, order.id)
    assert reloaded.status == PayoutCorrectionOrderStatus.STALE.value
    assert reloaded.executed_at is None
    assert reloaded.execution_result is None
    assert correction_entries(postgis_db_sessionmaker) == []


# --- Execution (C3) ----------------------------------------------------------


def test_concurrent_double_execute_has_exactly_one_money_effect(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-race")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-race")

    async def attempt():
        async with postgis_db_sessionmaker() as session:
            result_order, executed_now = await execute_correction_order(
                session,
                order_id=order.id,
                actor_user_id=approver.id,
                release_at=RELEASE_AT,
                request_metadata={"source": "race"},
                settings=settings,
            )
            await session.commit()
            return result_order.execution_result, executed_now

    async def race():
        return await asyncio.gather(attempt(), attempt())

    outcomes = asyncio.run(race())
    executed_flags = sorted(executed_now for _, executed_now in outcomes)
    assert executed_flags == [False, True]
    # The loser replays the winner's recorded result, never recomputing.
    assert outcomes[0][0] == outcomes[1][0]

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("150.00")


def test_execution_is_atomic_when_a_late_failure_rolls_back(
    postgis_db_sessionmaker, settings, monkeypatch
) -> None:
    """A crash after the ledger writes but before commit leaves NOTHING: no
    entries, no execution_result, order still approved — the retry re-runs
    under a fresh fingerprint check."""
    graph = build_v2_graph(postgis_db_sessionmaker, "co-atomic")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-atomic")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after ledger writes")

    monkeypatch.setattr(payout_corrections, "_execution_result_payload", boom)

    async def failing_execute():
        async with postgis_db_sessionmaker() as session:
            await execute_correction_order(
                session,
                order_id=order.id,
                actor_user_id=approver.id,
                release_at=RELEASE_AT,
                request_metadata={},
                settings=settings,
            )
            await session.commit()

    try:
        asyncio.run(failing_execute())
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    assert correction_entries(postgis_db_sessionmaker) == []
    reloaded = reload_order(postgis_db_sessionmaker, order.id)
    assert reloaded.status == PayoutCorrectionOrderStatus.APPROVED.value
    assert reloaded.execution_result is None

    monkeypatch.undo()
    _, executed_now = execute(postgis_db_sessionmaker, settings, order.id, approver.id)
    assert executed_now is True
    assert len(correction_entries(postgis_db_sessionmaker)) == 1


def test_positive_deltas_stay_pending_even_when_the_day_is_available(
    postgis_db_sessionmaker, settings
) -> None:
    """No API-reachable path creates a non-pending positive delta: even with
    the trip's payout already AVAILABLE, the correction adjustment posts as
    pending with its own release_at, and available money does not move."""
    graph = build_v2_graph(postgis_db_sessionmaker, "co-pending")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    set_trip_payout_status(
        postgis_db_sessionmaker,
        graph.trip.id,
        EarningsLedgerEntryStatus.AVAILABLE.value,
    )
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "1500.00")
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-pending")

    execute(postgis_db_sessionmaker, settings, order.id, approver.id)

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].entry_type == EarningsLedgerEntryType.ADJUSTMENT.value
    assert entries[0].status == EarningsLedgerEntryStatus.PENDING.value
    assert entries[0].release_at == RELEASE_AT

    totals_after = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    # Pending grew by the delta; available is untouched until MNY-03A's
    # release sweep consumes release_at.
    assert totals_after.pending_amount == totals_before.pending_amount + Decimal("150.00")
    assert totals_after.available_amount == totals_before.available_amount


def test_negative_delta_posts_reversal_without_debt_handling(
    postgis_db_sessionmaker, settings
) -> None:
    """MNY-11A boundary: a downward correction posts a positive-amount
    reversal (netted negative); no carry-forward debt is created here even if
    later reversals could exceed the day's balance."""
    graph = build_v2_graph(postgis_db_sessionmaker, "co-negative")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "900.00")
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-negative")

    # Negative-only corrections need no release_at (Q22 covers positives).
    executed, executed_now = execute(
        postgis_db_sessionmaker, settings, order.id, approver.id, release_at=None
    )
    assert executed_now is True
    assert executed.execution_result["reversal_count"] == 1
    assert executed.execution_result["adjustment_count"] == 0

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].entry_type == EarningsLedgerEntryType.REVERSAL.value
    assert entries[0].amount == Decimal("150.00")
    assert entries[0].release_at is None
    totals_after = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    assert totals_after.pending_amount == totals_before.pending_amount - Decimal("150.00")


# --- v3 and mixed-day recompute correctness (PR6) ----------------------------


def test_v3_day_reprices_from_frozen_binding_through_an_order(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "co-v3")  # rule row: 1200/h
    bind_v2_graph(
        postgis_db_sessionmaker,
        settings,
        graph,
        base="1000.00",
        premium="2000.00",
    )
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)  # v3 calc: 500.00

    void_trip_payout(postgis_db_sessionmaker, graph.trip.id)
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-v3")

    executed, _ = execute(postgis_db_sessionmaker, settings, order.id, approver.id, release_at=None)
    trip_result = executed.execution_result["drivers"][0]["trips"][0]
    # Void frees everything: posted(non-voided) was 0 after the void, so the
    # target is 0 and no differential is owed — the projection said so too.
    assert trip_result["previous_posted_amount"] == "0.00"
    assert trip_result["target_amount"] == "0.00"
    assert trip_result["delta_amount"] == "0.00"
    assert trip_result["voided"] is True

    # Now heal the void (admin re-instates the entry) and correct downward
    # from a later revision-independent drift: the recompute target must be
    # priced at the FROZEN binding rate (1000/h -> 500.00), never the rule
    # row's 1200/h.
    set_trip_payout_status(
        postgis_db_sessionmaker,
        graph.trip.id,
        EarningsLedgerEntryStatus.PENDING.value,
    )
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "9999.00")
    projection = service(
        postgis_db_sessionmaker,
        lambda session: project_campaign_day(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            settings=settings,
        ),
    )
    target = projection.computations[0].trips[0]
    assert target.formula_version == PAYOUT_V3
    assert target.target_amount == Decimal("500.00")
    assert target.previous_posted_amount == Decimal("500.00")
    assert target.delta_amount == Decimal("0.00")
    assert target.governing_values["binding_id"] == graph.binding.id
    assert target.governing_values["hourly_rate_naira"] == Decimal("1000.00")


def test_mixed_v2_v3_day_shares_one_cap_pool_through_an_order(
    postgis_db_sessionmaker, settings
) -> None:
    """PR5/PR6: voiding the v2 trip frees shared cap; the order's execution
    re-fills it chronologically and pays the v3 trip at its FROZEN binding
    rate, with the positive delta pending on its own release_at (Q22)."""
    graph = build_mixed_engine_day(postgis_db_sessionmaker, settings, "co-mixed", cap="0.75")
    run_pipeline(postgis_db_sessionmaker, graph.trip.id, settings)
    run_pipeline(postgis_db_sessionmaker, graph.trip2.id, settings)
    # v2 trip: 1800 s at 1200/h = 600.00; v3 trip: remaining 900 s at the
    # binding's 1200/h = 300.00 (shared 2700 s pool).

    void_trip_payout(postgis_db_sessionmaker, graph.trip.id)
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "co-mixed")
    delta_by_trip = {
        trip["trip_session_id"]: trip["delta_amount"] for trip in order.projected_delta["trips"]
    }
    # Void zeroes the v2 trip (posted 0 after void); the v3 trip climbs from
    # 900 to its full 1800 eligible seconds inside the freed pool: +300.00 at
    # the frozen 1200/h.
    assert delta_by_trip[str(graph.trip.id)] == "0.00"
    assert delta_by_trip[str(graph.trip2.id)] == "300.00"

    executed, _ = execute(postgis_db_sessionmaker, settings, order.id, approver.id)
    result_trips = {
        trip["trip_session_id"]: trip
        for driver in executed.execution_result["drivers"]
        for trip in driver["trips"]
    }
    v3_result = result_trips[str(graph.trip2.id)]
    assert v3_result["entry_type"] == "adjustment"
    assert v3_result["entry_status"] == "pending"
    assert v3_result["target_amount"] == "600.00"  # 1800 s at frozen 1200/h

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.trip_session_id == graph.trip2.id
    assert entry.amount == Decimal("300.00")
    assert entry.status == EarningsLedgerEntryStatus.PENDING.value
    assert entry.release_at == RELEASE_AT
    breakdown = entry.ledger_metadata["breakdown"]
    day_key = lagos_day_for(graph.trip.started_at).isoformat()
    # v3 differentials store BOTH the day map (the shared pool reads this
    # exact key) and the tier split for later supersession.
    assert breakdown["payable_seconds_by_day"] == {day_key: 1800}
    assert breakdown["payable_seconds_by_day_tier"] == {day_key: {"base": 1800, "premium": 0}}
    assert entry.ledger_metadata["formula_version"] == PAYOUT_V3
    assert entry.ledger_metadata["binding_id"]

    async def driver_breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session,
                user_id=graph.driver.id,
                trip_id=graph.trip2.id,
            )

    corrected = asyncio.run(driver_breakdown())
    assert corrected.superseded_by_recompute is True
    assert corrected.base_payable_seconds == 1800
    assert corrected.premium_payable_seconds == 0
    assert corrected.base_amount == Decimal("600.00")
    assert corrected.premium_amount == Decimal("0.00")

    # While the correction remains authoritative, unchanged inputs project no
    # further money movement.
    projection = service(
        postgis_db_sessionmaker,
        lambda session: project_campaign_day(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            settings=settings,
        ),
    )
    assert all(
        target.delta_amount == Decimal("0.00")
        for computation in projection.computations
        for target in computation.trips
    )

    # A voided newest explanation is not durable authority. The driver view
    # falls back to the original calculation's stored v3 components.
    async def void_correction() -> None:
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(EarningsLedgerEntry, entry.id)
            stored.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_correction())
    fallback = asyncio.run(driver_breakdown())
    assert fallback.superseded_by_recompute is False
    assert fallback.base_payable_seconds == 900
    assert fallback.premium_payable_seconds == 0
    assert fallback.base_amount == Decimal("300.00")
    assert fallback.premium_amount == Decimal("0.00")

    # The day never exceeds the shared cap: 1800 (v3) + 0 (voided v2) <= 2700.
    total_day_seconds = sum(
        (entry.ledger_metadata["breakdown"]["payable_seconds_by_day"]).get(day_key, 0)
        for entry in entries
    )
    assert total_day_seconds <= 2700
