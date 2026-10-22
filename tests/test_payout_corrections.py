"""REQ-213: single-admin payout correction orders with stale and cash safety.

Covers the campaign/Lagos-day projection (the PR6 core in dry-run), the full
state machine with its illegal transitions, creator-approves-own rejection at
the service AND database layers, stale-projection blocking at approve and
execute, idempotent execution under a PostGIS double-execute race, Q22
positive-delta pending entries carrying their own release_at, negative-delta
reversal semantics (carry-forward debt is MNY-11A and deliberately absent),
daily-rate recompute correctness through the order flow, the retired
direct endpoint, and value-complete audit events.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_user,
    fetch_audit_events,
    fetch_earnings_ledger_entries,
)
from payout_fixtures import build_v4_graph, drive, driver_totals, lagos_day_for, moving_points
from sqlalchemy import select, text, update
from starlette import status as http_status
from test_trip_processing import PASSWORD, add_pings

from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.payout import (
    AssignmentRuleBinding,
    CampaignPayoutRule,
    CampaignPayoutRuleRevision,
    EarningsLedgerEntry,
    EarningsLedgerEntryStatus,
    EarningsLedgerEntryType,
    PayoutCalculation,
    PayoutCorrectionOrder,
    PayoutCorrectionOrderStatus,
)
from app.services import payout_corrections
from app.services.payout_corrections import (
    approve_correction_order,
    create_correction_order,
    project_campaign_day,
)
from app.services.payouts.breakdown import driver_trip_earnings_breakdown
from app.services.payouts.common import PAYOUT_V4

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


def execute(db_sessionmaker, settings, order_id, actor_id, *, release_at=RELEASE_AT):
    return service(
        db_sessionmaker,
        lambda session: approve_correction_order(
            session,
            reason="Approve the checked correction",
            order_id=order_id,
            actor_user_id=actor_id,
            release_at=release_at,
            request_metadata={"source": "test"},
            settings=settings,
        ),
    )


def second_admin(db_sessionmaker, tag):
    return create_test_user(db_sessionmaker, email=f"approver-{tag}@example.com")


def reload_order(db_sessionmaker, order_id) -> PayoutCorrectionOrder:
    async def fetch():
        async with db_sessionmaker() as session:
            return await session.get(PayoutCorrectionOrder, order_id)

    return asyncio.run(fetch())


def build_correction_graph(db, settings, tag):
    return build_v4_graph(
        db,
        settings,
        tag,
        daily_rate_naira=Decimal("600.00"),
        daily_target_miles=Decimal("1.00"),
    )


def seed_misposted_amount(db, trip_id, amount):
    """Model a historical posting defect without changing accepted pay terms.

    These metadata-created test tables omit the production immutability trigger;
    direct fixture mutation is setup only, never an application correction path.
    """

    async def run():
        async with db() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == trip_id,
                    EarningsLedgerEntry.entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value,
                )
            )
            entry.amount = Decimal(amount)
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


def mark_binding_unresolved(db_sessionmaker, assignment_id) -> None:
    async def run() -> None:
        async with db_sessionmaker() as session:
            binding = await session.scalar(
                select(AssignmentRuleBinding).where(
                    AssignmentRuleBinding.assignment_id == assignment_id
                )
            )
            binding.stationary_policy_marker = "ext-rm2-fail-closed"
            await session.commit()

    asyncio.run(run())


# --- Projection + create (C1) ------------------------------------------------


def test_unresolved_binding_rejects_correction_projection_without_writes(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-rm2-old")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    original_entries = fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    original_entry_ids = [entry.id for entry in original_entries]
    mark_binding_unresolved(postgis_db_sessionmaker, graph.assignment.id)

    try:
        create_order(postgis_db_sessionmaker, settings, graph)
        raise AssertionError("expected unresolved binding to reject projection")
    except AppError as exc:
        assert exc.code == "PAYOUT_STATIONARY_POLICY_UNRESOLVED"

    assert [
        entry.id for entry in fetch_earnings_ledger_entries(postgis_db_sessionmaker)
    ] == original_entry_ids
    assert correction_entries(postgis_db_sessionmaker) == []
    breakdown = service(
        postgis_db_sessionmaker,
        lambda session: driver_trip_earnings_breakdown(
            session, user_id=graph.driver.id, trip_id=graph.trip.id
        ),
    )
    assert breakdown.amount == Decimal("600.00")


def test_unresolved_binding_rejects_approved_execution_atomically(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-rm2-exec")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-rm2-exec")
    mark_binding_unresolved(postgis_db_sessionmaker, graph.assignment.id)

    try:
        execute(postgis_db_sessionmaker, settings, order.id, approver.id)
        raise AssertionError("expected unresolved binding to reject execution")
    except AppError as exc:
        assert exc.code == "PAYOUT_STATIONARY_POLICY_UNRESOLVED"

    reloaded = reload_order(postgis_db_sessionmaker, order.id)
    assert reloaded.status == PayoutCorrectionOrderStatus.DRAFT.value
    assert reloaded.executed_at is None
    assert reloaded.execution_result is None
    assert correction_entries(postgis_db_sessionmaker) == []


def test_create_projects_value_complete_draft_and_matches_dry_run_endpoint(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-create")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")

    recompute = service(
        postgis_db_sessionmaker,
        lambda session: project_campaign_day(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            settings=settings,
        ),
    )
    assert set(recompute.computations[0].trips[0].governing_values["eligibility_params"]) == {
        "stationary_radius_m",
        "stationary_window_seconds",
        "stationary_grace_seconds",
        "max_accuracy_m",
        "teleport_kmh",
        "max_ping_gap_seconds",
    }

    assert (
        recompute.computations[0].trips[0].governing_values["resolved_eligibility_params"]
        == graph.binding.resolved_eligibility_params
    )

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
            "reason": "historical posting was too low",
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
    assert trips[0]["previous_posted_amount"] == "450.00"
    assert trips[0]["target_amount"] == "600.00"
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
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-perm")
    drive(postgis_db_sessionmaker, settings, graph.trip)
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


# --- Stale projection (C2) ---------------------------------------------------


def test_input_drift_marks_order_stale_at_execute_with_no_money_effect(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-stale-exec")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-stale-exec")

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
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-race")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-race")

    async def attempt():
        async with postgis_db_sessionmaker() as session:
            result_order, executed_now = await approve_correction_order(
                session,
                reason="Approve the checked correction",
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
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-atomic")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-atomic")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after ledger writes")

    monkeypatch.setattr(payout_corrections, "_execution_result_payload", boom)

    async def failing_execute():
        async with postgis_db_sessionmaker() as session:
            await approve_correction_order(
                session,
                reason="Approve the checked correction",
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
    assert reloaded.status == PayoutCorrectionOrderStatus.DRAFT.value
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
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-pending")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    set_trip_payout_status(
        postgis_db_sessionmaker,
        graph.trip.id,
        EarningsLedgerEntryStatus.AVAILABLE.value,
    )
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-pending")

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
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-negative")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "750.00")
    totals_before = driver_totals(postgis_db_sessionmaker, settings, graph.driver.id)
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-negative")

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


def test_paid_trip_correction_inserts_available_reversal_without_terminal_rewrite(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-paid-negative")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    set_trip_payout_status(
        postgis_db_sessionmaker,
        graph.trip.id,
        EarningsLedgerEntryStatus.PAID.value,
    )
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "750.00")
    order, approver = prepared_order(
        postgis_db_sessionmaker,
        settings,
        graph,
        "co-paid-negative",
    )

    async def install_paid_terminal_guard() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                text(
                    """
                    CREATE FUNCTION test_reject_paid_ledger_rewrite()
                    RETURNS trigger AS $$
                    BEGIN
                      IF OLD.status = 'paid' AND NEW.status <> OLD.status THEN
                        RAISE EXCEPTION 'paid ledger status is terminal';
                      END IF;
                      RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql
                    """
                )
            )
            await session.execute(
                text(
                    "CREATE TRIGGER test_paid_ledger_terminal "
                    "BEFORE UPDATE ON earnings_ledger_entries FOR EACH ROW "
                    "EXECUTE FUNCTION test_reject_paid_ledger_rewrite()"
                )
            )
            await session.commit()

    asyncio.run(install_paid_terminal_guard())
    execute(postgis_db_sessionmaker, settings, order.id, approver.id, release_at=None)

    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    assert entries[0].entry_type == EarningsLedgerEntryType.REVERSAL.value
    assert entries[0].status == EarningsLedgerEntryStatus.AVAILABLE.value


# --- Frozen daily-rate recompute correctness (PR6) ----------------------------


def test_daily_rate_day_recomputes_from_frozen_binding_through_an_order(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-v3")
    drive(postgis_db_sessionmaker, settings, graph.trip)

    void_trip_payout(postgis_db_sessionmaker, graph.trip.id)
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-v3")

    executed, _ = execute(postgis_db_sessionmaker, settings, order.id, approver.id, release_at=None)
    trip_result = executed.execution_result["drivers"][0]["trips"][0]
    # Void frees everything: posted(non-voided) was 0 after the void, so the
    # target is 0 and no differential is owed — the projection said so too.
    assert trip_result["previous_posted_amount"] == "0.00"
    assert trip_result["target_amount"] == "0.00"
    assert trip_result["delta_amount"] == "0.00"
    assert trip_result["voided"] is True

    # Restore the fixture entry; later live rule edits cannot reprice its binding.
    set_trip_payout_status(
        postgis_db_sessionmaker,
        graph.trip.id,
        EarningsLedgerEntryStatus.PENDING.value,
    )

    async def change_live_rule():
        async with postgis_db_sessionmaker() as session:
            rule = await session.get(CampaignPayoutRule, graph.rule.id)
            rule.currency = "USD"
            await session.commit()

    asyncio.run(change_live_rule())
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
    assert target.formula_version == PAYOUT_V4
    assert target.target_amount == Decimal("600.00")
    assert target.previous_posted_amount == Decimal("600.00")
    assert target.delta_amount == Decimal("0.00")
    assert target.governing_values["binding_id"] == graph.binding.id
    assert target.governing_values["daily_rate_naira"] == "600.00"
    assert target.currency == "NGN"
    assert target.governing_values["currency"] == "NGN"
    assert target.governing_values["campaign_window_start_at"] == graph.campaign.start_at
    assert target.governing_values["campaign_window_end_at"] == graph.campaign.end_at

    async def move_live_window() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                update(Campaign)
                .where(Campaign.id == graph.campaign.id)
                .values(
                    start_at=graph.trip.ended_at + timedelta(days=10),
                    end_at=graph.trip.ended_at + timedelta(days=20),
                )
            )
            await session.commit()

    asyncio.run(move_live_window())
    after_window_edit = service(
        postgis_db_sessionmaker,
        lambda session: project_campaign_day(
            session,
            campaign_id=graph.campaign.id,
            lagos_day=lagos_day_for(graph.trip.started_at),
            settings=settings,
        ),
    )
    # A daily-rate correction consumes the accepted window carried in the
    # binding. An unrelated later live campaign edit neither reprices nor
    # stales the order projection.
    assert after_window_edit.fingerprint == projection.fingerprint
    assert after_window_edit.computations[0].trips[0].target_amount == Decimal("600.00")


def test_daily_rate_day_refuses_revision_binding_and_ledger_currency_disagreement(
    postgis_db_sessionmaker,
    settings,
) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-v3-currency-chain")
    drive(postgis_db_sessionmaker, settings, graph.trip)

    async def set_revision_currency(currency: str) -> None:
        async with postgis_db_sessionmaker() as session:
            revision = await session.get(CampaignPayoutRuleRevision, graph.revision.id)
            revision.currency = currency
            await session.commit()

    asyncio.run(set_revision_currency("USD"))
    with pytest.raises(AppError) as revision_error:
        service(
            postgis_db_sessionmaker,
            lambda session: project_campaign_day(
                session,
                campaign_id=graph.campaign.id,
                lagos_day=lagos_day_for(graph.trip.started_at),
                settings=settings,
            ),
        )
    assert revision_error.value.code == "INVALID_PAYOUT_RULE"

    asyncio.run(set_revision_currency("NGN"))

    async def set_ledger_currency() -> None:
        async with postgis_db_sessionmaker() as session:
            entry = await session.scalar(
                select(EarningsLedgerEntry).where(
                    EarningsLedgerEntry.trip_session_id == graph.trip.id
                )
            )
            entry.currency = "USD"
            await session.commit()

    asyncio.run(set_ledger_currency())
    with pytest.raises(AppError) as ledger_error:
        service(
            postgis_db_sessionmaker,
            lambda session: project_campaign_day(
                session,
                campaign_id=graph.campaign.id,
                lagos_day=lagos_day_for(graph.trip.started_at),
                settings=settings,
            ),
        )
    assert ledger_error.value.code == "PAYOUT_DAY_CURRENCY_MISMATCH"


def test_daily_rate_correction_explanation_provenance(postgis_db_sessionmaker, settings) -> None:
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "co-provenance")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    graph.trip2 = graph.trip
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "300.00")
    order, approver = prepared_order(postgis_db_sessionmaker, settings, graph, "co-provenance")
    executed, _ = execute(postgis_db_sessionmaker, settings, order.id, approver.id)
    result = executed.execution_result["drivers"][0]["trips"][0]
    assert result["target_amount"] == "600.00"
    assert result["delta_amount"] == "300.00"
    entries = correction_entries(postgis_db_sessionmaker)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.amount == Decimal("300.00")
    assert entry.status == EarningsLedgerEntryStatus.PENDING.value
    assert entry.release_at == RELEASE_AT
    breakdown = entry.ledger_metadata["breakdown"]
    assert entry.ledger_metadata["formula_version"] == PAYOUT_V4
    assert entry.ledger_metadata["binding_id"] == str(graph.binding.id)

    async def driver_breakdown():
        async with postgis_db_sessionmaker() as session:
            return await driver_trip_earnings_breakdown(
                session,
                user_id=graph.driver.id,
                trip_id=graph.trip2.id,
            )

    corrected = asyncio.run(driver_breakdown())
    assert corrected.superseded_by_recompute is True
    assert corrected.excluded_seconds_by_reason == breakdown["excluded_seconds_by_reason"]

    async def replace_explanation(*, eligible: int, excluded: dict[str, int] | None) -> None:
        async with postgis_db_sessionmaker() as session:
            stored_entry = await session.get(EarningsLedgerEntry, entry.id)
            metadata = dict(stored_entry.ledger_metadata or {})
            stored_breakdown = dict(metadata["breakdown"])
            stored_breakdown["eligible_seconds"] = eligible
            if excluded is None:
                stored_breakdown.pop("excluded_seconds_by_reason", None)
            else:
                stored_breakdown["excluded_seconds_by_reason"] = excluded
            metadata["breakdown"] = stored_breakdown
            stored_entry.ledger_metadata = metadata

            calculation = await session.scalar(
                select(PayoutCalculation).where(PayoutCalculation.trip_session_id == graph.trip2.id)
            )
            calculation.excluded_seconds_by_reason = {"stale_original_reason": 77}
            await session.commit()

    # Both explanation fields come from the same newest recompute breakdown.
    asyncio.run(replace_explanation(eligible=123, excluded={"changed_reason": 45}))
    changed = asyncio.run(driver_breakdown())
    assert changed.eligible_seconds == 123
    assert changed.excluded_seconds_by_reason == {"changed_reason": 45}

    # A deliberately empty fresh map clears the superseded calculation's
    # reasons; a legacy recompute without the field reports unknown instead.
    asyncio.run(replace_explanation(eligible=124, excluded={}))
    cleared = asyncio.run(driver_breakdown())
    assert cleared.eligible_seconds == 124
    assert cleared.excluded_seconds_by_reason == {}
    asyncio.run(replace_explanation(eligible=125, excluded=None))
    legacy = asyncio.run(driver_breakdown())
    assert legacy.superseded_by_recompute is True
    assert legacy.eligible_seconds == 125
    assert legacy.excluded_seconds_by_reason is None

    async def append_malformed_newest_explanation() -> object:
        async with postgis_db_sessionmaker() as session:
            older = await session.get(EarningsLedgerEntry, entry.id)
            older_metadata = dict(older.ledger_metadata or {})
            older_breakdown = dict(older_metadata["breakdown"])
            older_breakdown["eligible_seconds"] = 126
            older_breakdown["excluded_seconds_by_reason"] = {"older_reason": 46}
            older_metadata["breakdown"] = older_breakdown
            older.ledger_metadata = older_metadata

            newest_metadata = dict(older_metadata)
            newest_breakdown = dict(older_breakdown)
            newest_breakdown["eligible_seconds"] = -1
            newest_breakdown["excluded_seconds_by_reason"] = ["malformed"]
            newest_metadata["breakdown"] = newest_breakdown
            newest = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=older.driver_profile_id,
                driver_user_id=older.driver_user_id,
                campaign_id=older.campaign_id,
                trip_session_id=older.trip_session_id,
                vehicle_id=older.vehicle_id,
                entry_type=EarningsLedgerEntryType.ADJUSTMENT.value,
                status=EarningsLedgerEntryStatus.PENDING.value,
                amount=Decimal("0.00"),
                currency=older.currency,
                description="Malformed explanation provenance regression",
                occurred_at=older.occurred_at + timedelta(seconds=1),
                release_at=older.release_at,
                ledger_metadata=newest_metadata,
            )
            session.add(newest)
            await session.commit()
            return newest.id

    malformed_entry_id = asyncio.run(append_malformed_newest_explanation())
    malformed_over_older = asyncio.run(driver_breakdown())
    assert malformed_over_older.superseded_by_recompute is True
    assert malformed_over_older.eligible_seconds is None
    assert malformed_over_older.excluded_seconds_by_reason is None

    async def void_older_correction() -> None:
        async with postgis_db_sessionmaker() as session:
            older = await session.get(EarningsLedgerEntry, entry.id)
            older.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_older_correction())
    malformed_over_original = asyncio.run(driver_breakdown())
    assert malformed_over_original.superseded_by_recompute is True
    assert malformed_over_original.eligible_seconds is None
    assert malformed_over_original.excluded_seconds_by_reason is None

    async def restore_older_correction() -> None:
        async with postgis_db_sessionmaker() as session:
            older = await session.get(EarningsLedgerEntry, entry.id)
            older.status = EarningsLedgerEntryStatus.PENDING.value
            await session.commit()

    asyncio.run(restore_older_correction())

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
    # falls back to the original calculation's stored daily-rate explanation.
    async def void_correction() -> None:
        async with postgis_db_sessionmaker() as session:
            stored = await session.get(EarningsLedgerEntry, entry.id)
            stored.status = EarningsLedgerEntryStatus.VOIDED.value
            malformed = await session.get(EarningsLedgerEntry, malformed_entry_id)
            malformed.status = EarningsLedgerEntryStatus.VOIDED.value
            await session.commit()

    asyncio.run(void_correction())
    fallback = asyncio.run(driver_breakdown())
    assert fallback.superseded_by_recompute is False
    assert fallback.excluded_seconds_by_reason == {"stale_original_reason": 77}


def prepared_order(db_sessionmaker, settings, graph, tag):
    """A saved draft is ready for its creator to approve and apply."""
    return create_order(db_sessionmaker, settings, graph), graph.admin


def test_same_admin_approves_applies_and_replays_with_required_reason(
    postgis_db_client, postgis_db_sessionmaker, settings
):
    graph = build_correction_graph(postgis_db_sessionmaker, settings, "one-admin-correction")
    drive(postgis_db_sessionmaker, settings, graph.trip)
    seed_misposted_amount(postgis_db_sessionmaker, graph.trip.id, "450.00")
    order = create_order(postgis_db_sessionmaker, settings, graph)
    headers = auth_headers(postgis_db_client, graph.admin.email, PASSWORD)
    url = f"/api/v1/admin/payouts/correction-orders/{order.id}/approve"
    assert postgis_db_client.post(url, headers=headers, json={"reason": "  "}).status_code == 422
    body = {"reason": "Checked the corrected distance", "release_at": RELEASE_AT.isoformat()}
    response = postgis_db_client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    stored = reload_order(postgis_db_sessionmaker, order.id)
    assert stored.status == "executed"
    assert stored.approved_by_user_id == stored.executed_by_user_id == graph.admin.id
    assert len(correction_entries(postgis_db_sessionmaker)) == 1
    replay = postgis_db_client.post(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert len(correction_entries(postgis_db_sessionmaker)) == 1
    audits = [
        e
        for e in fetch_audit_events(postgis_db_sessionmaker)
        if e.action == "admin.payout_correction_order.approved"
    ]
    assert len(audits) == 1 and audits[0].event_metadata["reason"] == body["reason"]
