"""REQ-213: trip-local net pay, manual negatives and one-person controls."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_trip_session
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph, create_flag
from test_payout_batches import _seed_authority

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.payout import EarningsLedgerEntry
from app.models.trip import TripSessionStatus
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    reserve_payout_batch,
)
from app.services.payout_adjustments import _adjustment_day, record_negative_adjustment
from app.services.payout_balances import driver_money_balance, trip_cash_position


def credit(amount="100.00", status="available", kind="adjustment"):
    return SimpleNamespace(amount=Decimal(amount), status=status, entry_type=kind)


def line(amount="100.00", status="succeeded", active=False, predecessor=None):
    return SimpleNamespace(
        id=uuid4(),
        amount=Decimal(amount),
        status=status,
        reservation_active=active,
        predecessor_line_id=predecessor,
    )


def test_trip_net_is_cash_authority_without_mutating_the_original_credit():
    original = credit()
    net = trip_cash_position([original, credit("20.00", kind="reversal")], [])
    assert net.earned_net == net.batch_payable == Decimal("80.00")
    assert original.amount == Decimal("100.00")
    paid = trip_cash_position([original, credit("20.00", kind="reversal")], [(line("80.00"), None)])
    assert paid.cash_paid == Decimal("80.00") and paid.batch_payable == 0


def test_reservations_and_failed_replacements_are_not_double_counted():
    pending = line("80.00", status="reserved", active=True)
    reserved = trip_cash_position([credit(), credit("20.00", kind="reversal")], [(pending, None)])
    assert reserved.reserved == Decimal("80.00")
    assert reserved.released_available == reserved.batch_payable == 0
    pending.status = "failed"
    pending.reservation_active = False
    failed = trip_cash_position([credit(), credit("20.00", kind="reversal")], [(pending, None)])
    assert failed.terminal_failed == failed.batch_payable == Decimal("80.00")
    assert failed.released_available == 0
    replacement = line("80.00", status="submitted", active=True, predecessor=pending.id)
    exposed = trip_cash_position(
        [credit(), credit("20.00", kind="reversal")], [(pending, None), (replacement, None)]
    )
    assert exposed.terminal_failed == 0 and exposed.in_flight == Decimal("80.00")
    assert exposed.batch_payable == exposed.released_available == 0


def test_duplicate_real_cash_remains_counted_above_source_credit():
    result = trip_cash_position(
        [credit("999999999999.99")],
        [(line("999999999999.99"), None), (line("999999999999.99"), None)],
    )
    assert result.cash_paid == Decimal("1999999999999.98")
    assert result.batch_payable == 0


def test_manual_adjustment_requires_the_actual_nigeria_day_for_a_multi_day_trip():
    trip = SimpleNamespace(
        started_at=datetime(2026, 10, 9, 22, 30, tzinfo=UTC),
        ended_at=datetime(2026, 10, 9, 23, 30, tzinfo=UTC),
    )
    with pytest.raises(AppError) as exc:
        _adjustment_day(trip, None)
    assert exc.value.code == "PAYOUT_ADJUSTMENT_DAY_REQUIRED"
    assert _adjustment_day(trip, date(2026, 10, 10)) == date(2026, 10, 10)
    with pytest.raises(AppError) as exc:
        _adjustment_day(trip, date(2026, 10, 11))
    assert exc.value.code == "PAYOUT_ADJUSTMENT_DAY_INVALID"


def test_manual_negative_is_add_only_audited_idempotent_and_caps_the_next_payment(
    db_client, db_sessionmaker
):
    graph = build_graph(db_sessionmaker, "manual-negative-" + uuid4().hex[:8])

    async def exercise():
        async with db_sessionmaker() as session:
            original = await _seed_authority(session, graph)
            original.ledger_metadata = {"lagos_day": "2026-08-21"}
            request_id = uuid4()
            args = dict(
                source_entry_id=original.id,
                request_id=request_id,
                amount=Decimal("20.00"),
                currency="NGN",
                reason="Correct verified overpayment",
                actor_user_id=graph.admin.id,
            )
            negative = await record_negative_adjustment(session, **args)
            again = await record_negative_adjustment(session, **args)
            assert negative.id == again.id
            assert negative.ledger_metadata["lagos_day"] == "2026-08-21"
            assert original.amount == Decimal("100.00") and original.status == "available"
            batch = await create_payout_batch_draft(
                session,
                currency="NGN",
                actor_user_id=graph.admin.id,
                reason="Prepare corrected trip pay",
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(original.id,),
                actor_user_id=graph.admin.id,
                reason="Use the corrected net award",
            )
            await approve_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                reason="Checked net amount and destination",
            )
            assert lines[0].amount == Decimal("80.00")
            assert lines[0].instruction["amount"] == "80.00"
            assert batch.approved_by_user_id == batch.created_by_user_id == graph.admin.id
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.earnings.negative_adjustment"
                    )
                )
                == 1
            )
            with pytest.raises(AppError) as exc:
                await record_negative_adjustment(session, **{**args, "amount": Decimal("21.00")})
            assert exc.value.code == "PAYOUT_ADJUSTMENT_RETRY_CONFLICT"
            from app.adapters.disbursement import FakeDisbursementAdapter
            from app.models.disbursement import PayoutSubmissionIntent
            from app.services.disbursements import (
                poll_payout_line,
                process_payout_submission_intent,
                submit_payout_batch,
            )

            fake = FakeDisbursementAdapter()
            await submit_payout_batch(
                session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=fake
            )
            intent_id = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == lines[0].id
                )
            )
            line_id = lines[0].id
            await session.commit()
        assert (
            await process_payout_submission_intent(
                db_sessionmaker, intent_id=intent_id, adapter=fake
            )
            == "resolved"
        )
        async with db_sessionmaker() as session:
            from app.models.disbursement import PayoutBatchLine

            line = await session.get(PayoutBatchLine, line_id)
            assert line.amount == Decimal("80.00")
            fake.set_poll_result(
                provider_transfer_reference=line.provider_transfer_reference,
                provider_event_id="manual-net-success",
                outcome="succeeded",
                occurred_at=datetime.now(UTC),
            )
            await poll_payout_line(
                session,
                line_id=line.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
                reason="Verified net payment with bank",
            )
            position = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            original = await session.get(EarningsLedgerEntry, original.id)
            assert original.amount == Decimal("100.00") and original.status == "paid"
            assert position.earned_net == position.cash_paid == Decimal("80.00")
            assert position.batch_payable == position.released_available == 0
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "admin.payout_line.reconciled")
            )
            assert (
                audit.actor_user_id == graph.admin.id
                and audit.event_metadata["reason"] == "Verified net payment with bank"
            )
            await session.commit()

    asyncio.run(exercise())
    response = db_client.get(
        "/api/v1/driver/earnings/days",
        headers=auth_headers(db_client, graph.driver.email, "long-secure-password"),
    )
    assert response.status_code == 200, response.text
    [day] = response.json()["days"]
    assert day["amount"] == "80.00" and day["status"] == "paid" and day["paid_at"]


@pytest.mark.parametrize(
    "case,code,status_code",
    [
        ("driver", "FORBIDDEN_ROLE", 403),
        ("disabled", "FORBIDDEN_ROLE", 403),
        ("currency", "PAYOUT_ADJUSTMENT_CURRENCY_INVALID", 422),
        ("reason", "PAYOUT_REASON_INVALID", 422),
    ],
)
def test_negative_refusals_leave_ledger_audit_and_lines_unchanged(
    db_sessionmaker, case, code, status_code
):
    from app.models.disbursement import PayoutBatchLine
    from app.models.user import User

    graph = build_graph(db_sessionmaker, "negative-refusal-" + uuid4().hex[:8])

    async def exercise():
        async with db_sessionmaker() as session:
            original = await _seed_authority(session, graph)
            if case == "disabled":
                actor = await session.get(User, graph.admin.id)
                actor.status = "disabled"
                await session.flush()

            async def counts():
                return tuple(
                    [
                        await session.scalar(select(func.count(model.id)))
                        for model in (EarningsLedgerEntry, AuditEvent, PayoutBatchLine)
                    ]
                )

            before = await counts()
            with pytest.raises(AppError) as exc:
                await record_negative_adjustment(
                    session,
                    source_entry_id=original.id,
                    request_id=uuid4(),
                    amount=Decimal("20.00"),
                    currency="USD" if case == "currency" else "NGN",
                    reason="   " if case == "reason" else "Correct verified overpayment",
                    actor_user_id=graph.driver.id if case == "driver" else graph.admin.id,
                )
            assert exc.value.code == code
            assert exc.value.status_code == status_code
            assert await counts() == before
            await session.refresh(original)
            assert original.amount == Decimal("100.00") and original.status == "available"

    asyncio.run(exercise())


def test_negative_on_one_trip_never_reduces_a_later_trip(db_sessionmaker):
    graph = build_graph(db_sessionmaker, "trip-isolation-" + uuid4().hex[:8])
    other = create_test_trip_session(
        db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=graph.trip.started_at,
        ended_at=graph.trip.ended_at,
    )

    async def exercise():
        async with db_sessionmaker() as session:
            original = await _seed_authority(session, graph, amount="100.00")
            await record_negative_adjustment(
                session,
                source_entry_id=original.id,
                request_id=uuid4(),
                amount=Decimal("150.00"),
                currency="NGN",
                reason="Record earlier overpayment",
                actor_user_id=graph.admin.id,
            )
            later = EarningsLedgerEntry(
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=other.id,
                vehicle_id=graph.vehicle.id,
                entry_type="adjustment",
                status="available",
                amount=Decimal("70.00"),
                currency="NGN",
                occurred_at=graph.trip.ended_at,
                ledger_metadata={"lagos_day": "2026-08-21"},
            )
            session.add(later)
            await session.flush()
            balance = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            assert balance.earned_net == Decimal("20.00")
            assert balance.batch_payable == Decimal("70.00")

    asyncio.run(exercise())


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("1.001"), Decimal("NaN")])
def test_bad_negative_amount_never_changes_ledger(db_sessionmaker, amount):
    graph = build_graph(db_sessionmaker, "bad-negative-" + uuid4().hex[:8])

    async def exercise():
        async with db_sessionmaker() as session:
            source = await _seed_authority(session, graph)
            with pytest.raises(AppError) as exc:
                await record_negative_adjustment(
                    session,
                    source_entry_id=source.id,
                    request_id=uuid4(),
                    amount=amount,
                    currency="NGN",
                    reason="Correction checked",
                    actor_user_id=graph.admin.id,
                )
            assert exc.value.code == "PAYOUT_ADJUSTMENT_AMOUNT_INVALID"
            assert await session.scalar(select(func.count(EarningsLedgerEntry.id))) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("cross_midnight", [False, True])
def test_confirmed_flag_holds_without_money_rewrite_and_driver_earnings_stay_readable(
    db_client, db_sessionmaker, cross_midnight
):
    from app.models.trip import TripSession

    graph = build_graph(db_sessionmaker, "confirmed-readable-" + uuid4().hex[:8])

    async def seed():
        async with db_sessionmaker() as session:
            source = await _seed_authority(session, graph)
            source.ledger_metadata = {"lagos_day": "2026-08-21"}
            if cross_midnight:
                trip = await session.get(TripSession, graph.trip.id)
                trip.started_at = datetime(2026, 8, 21, 22, 30, tzinfo=UTC)
                trip.ended_at = datetime(2026, 8, 21, 23, 30, tzinfo=UTC)
            await session.commit()
            return source.id

    source_id = asyncio.run(seed())
    flag = create_flag(db_sessionmaker, graph)
    staff = auth_headers(db_client, graph.admin.email, "long-secure-password")
    response = db_client.post(
        f"/api/v1/admin/fraud-flags/{flag.id}/review/resolve",
        headers=staff,
        json={"outcome": "confirmed", "note": "Evidence verified"},
    )
    assert response.status_code == 200, response.text
    driver = auth_headers(db_client, graph.driver.email, "long-secure-password")
    earnings = db_client.get("/api/v1/driver/earnings/days", headers=driver)
    assert earnings.status_code == 200, earnings.text
    assert earnings.json()["days"][0]["amount"] == "100.00"
    assert earnings.json()["days"][0]["status"] == "on_hold"

    async def verify():
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(EarningsLedgerEntry.id))) == 1
            source = await session.get(EarningsLedgerEntry, source_id)
            assert source.amount == Decimal("100.00") and source.status == "available"
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, reason="Check confirmed hold"
            )
            with pytest.raises(AppError) as exc:
                await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(source_id,),
                    actor_user_id=graph.admin.id,
                    reason="Try held trip",
                )
            assert exc.value.code == "PAYOUT_ENTRY_HELD"

    asyncio.run(verify())


@pytest.mark.parametrize("negative_first", [False, True])
def test_negative_and_reservation_serialize_both_orders(
    postgis_db_sessionmaker, monkeypatch, negative_first
):
    from conftest import create_test_user

    from app.models.disbursement import PayoutBatchLine
    from app.services import disbursements, payout_adjustments, payout_balances

    db = postgis_db_sessionmaker
    graph = build_graph(db, "negative-reserve-race-" + uuid4().hex[:8])

    adjuster = create_test_user(db, email="negative-race-" + uuid4().hex + "@example.com")

    async def race():
        async with db() as session:
            source = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session,
                currency="NGN",
                actor_user_id=graph.admin.id,
                reason="Prepare before correction",
            )
            source_id, batch_id = source.id, batch.id
            await session.commit()
        entered = asyncio.Event()
        release = asyncio.Event()
        leader = None
        original = payout_balances.lock_driver_money_scope

        async def controlled(session, **kwargs):
            result = await original(session, **kwargs)
            if asyncio.current_task() is leader and not entered.is_set():
                entered.set()
                await release.wait()
            return result

        monkeypatch.setattr(disbursements, "lock_driver_money_scope", controlled)
        monkeypatch.setattr(payout_adjustments, "lock_driver_money_scope", controlled)

        async def adjust():
            async with db() as session:
                await record_negative_adjustment(
                    session,
                    source_entry_id=source_id,
                    request_id=uuid4(),
                    amount=Decimal("20.00"),
                    currency="NGN",
                    reason="Verified correction in race",
                    actor_user_id=adjuster.id,
                )
                await session.commit()

        async def reserve():
            async with db() as session:
                await reserve_payout_batch(
                    session,
                    batch_id=batch_id,
                    ledger_entry_ids=(source_id,),
                    actor_user_id=graph.admin.id,
                    reason="Reserve corrected entitlement",
                )
                await session.commit()

        first = asyncio.create_task(adjust() if negative_first else reserve())
        leader = first
        await asyncio.wait_for(entered.wait(), 10)
        second = asyncio.create_task(reserve() if negative_first else adjust())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(second), 0.1)
        finally:
            release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 15)
        async with db() as session:
            lines = list(await session.scalars(select(PayoutBatchLine)))
            if negative_first:
                assert (
                    len(lines) == 1
                    and lines[0].amount == Decimal("80.00")
                    and lines[0].reservation_active
                )
            else:
                assert (
                    len(lines) == 1
                    and lines[0].amount == Decimal("100.00")
                    and lines[0].status == "void"
                )
                replacement = await create_payout_batch_draft(
                    session,
                    currency="NGN",
                    actor_user_id=graph.admin.id,
                    reason="Prepare corrected net after cancellation",
                )
                _, fresh = await reserve_payout_batch(
                    session,
                    batch_id=replacement.id,
                    ledger_entry_ids=(source_id,),
                    actor_user_id=graph.admin.id,
                    reason="Reserve the reduced trip entitlement",
                )
                assert fresh[0].amount == Decimal("80.00")
            balance = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            assert (
                balance.earned_net == balance.reserved == Decimal("80.00")
                and balance.batch_payable == 0
            )

    asyncio.run(race())


def test_committed_submit_claim_still_queries_after_negative_but_cannot_send_again(
    postgis_db_sessionmaker,
):
    from datetime import timedelta

    from sqlalchemy import update
    from test_disbursement_worker import _prepare_batch

    from app.adapters.disbursement import FakeDisbursementAdapter
    from app.models.disbursement import PayoutBatchLine, PayoutSubmissionIntent
    from app.services.disbursements import (
        claim_payout_submission_intent,
        process_payout_submission_intent,
    )

    db = postgis_db_sessionmaker
    graph = build_graph(db, "negative-claimed-" + uuid4().hex[:8])

    class LookupProbe(FakeDisbursementAdapter):
        def __init__(self):
            super().__init__()
            self.lookups = 0

        async def lookup_line(self, **kwargs):
            self.lookups += 1
            return await super().lookup_line(**kwargs)

    adapter = LookupProbe()

    async def exercise():
        _, line_ids, intent_ids = await _prepare_batch(db, graph, adapter)
        claim = await claim_payout_submission_intent(db, intent_id=intent_ids[0], adapter=adapter)
        assert claim and claim.action == "submit"
        async with db() as session:
            line = await session.get(PayoutBatchLine, line_ids[0])
            await record_negative_adjustment(
                session,
                source_entry_id=line.ledger_entry_id,
                request_id=uuid4(),
                amount=Decimal("20.00"),
                currency="NGN",
                reason="Correction after committed call authority",
                actor_user_id=graph.admin.id,
            )
            intent = await session.get(PayoutSubmissionIntent, intent_ids[0])
            assert intent.state == "claimed" and line.reservation_active
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == intent.id)
                .values(claim_expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        assert (
            await process_payout_submission_intent(db, intent_id=intent_ids[0], adapter=adapter)
            == "pending"
        )
        assert adapter.lookups == 1 and adapter.calls == []
        with pytest.raises(AppError) as changed:
            await process_payout_submission_intent(db, intent_id=intent_ids[0], adapter=adapter)
        assert changed.value.code == "PAYOUT_TRIP_AMOUNT_CHANGED"
        assert adapter.calls == []

    asyncio.run(exercise())
