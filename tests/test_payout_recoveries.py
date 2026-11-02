"""REQ-262: an offset settles debt once, independently of bank transfers."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.core.errors import AppError
from app.models.disbursement import PayoutBatch, PayoutBatchLine, PayoutRecoveryOffset
from app.models.payee import Payee
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.trip import TripSession
from app.services.disbursements import (
    _frozen_payee_authority,
    build_frozen_payout_line,
    create_payout_batch_draft,
    freeze_batch_instruction_set,
    reserve_payout_batch,
    void_payout_batch,
)
from app.services.payout_balances import (
    allocate_payout_recovery,
    lock_driver_money_scope,
    trip_money_position,
)


async def seed_debt(
    session, graph, *, payable="10000.00", cash="10000.00", deduction="100.00", funding=None
):
    funding = funding or await _seed_authority(session, graph, amount=payable)
    original = await session.get(TripSession, graph.trip.id)
    source_trip = TripSession(
        **{
            column.name: getattr(original, column.name)
            for column in TripSession.__table__.columns
            if column.name != "id"
        }
    )
    source_trip.id = uuid4()
    source_trip.started_at -= timedelta(days=2)
    source_trip.ended_at -= timedelta(days=2)
    session.add(source_trip)
    await session.flush()
    source_calculation = None
    if funding.payout_calculation_id:
        calculation = await session.get(PayoutCalculation, funding.payout_calculation_id)
        source_calculation = PayoutCalculation(
            **{
                attribute.key: getattr(calculation, attribute.key)
                for attribute in PayoutCalculation.__mapper__.column_attrs
                if attribute.key not in {"id", "trip_session_id"}
            }
        )
        source_calculation.trip_session_id = source_trip.id
        day = source_trip.started_at.date().isoformat()
        source_calculation.amount_by_day = {day: "10000.00"}
        source_calculation.distance_m_by_day = {day: 10000}
        source_calculation.final_payout = Decimal("10000.00")
        source_calculation.gross_payout = Decimal("10000.00")
        session.add(source_calculation)
        await session.flush()
    credit = EarningsLedgerEntry(
        driver_profile_id=funding.driver_profile_id,
        driver_user_id=funding.driver_user_id,
        campaign_id=funding.campaign_id,
        trip_session_id=source_trip.id,
        vehicle_id=funding.vehicle_id,
        entry_type="trip_payout" if source_calculation else "adjustment",
        status="paid",
        payout_calculation_id=source_calculation.id if source_calculation else None,
        amount=Decimal("10000.00"),
        currency="NGN",
        occurred_at=source_trip.ended_at,
        ledger_metadata={"lagos_day": source_trip.started_at.date().isoformat()},
    )
    session.add(credit)
    await session.flush()
    if Decimal(deduction):
        session.add(
            EarningsLedgerEntry(
                driver_profile_id=credit.driver_profile_id,
                driver_user_id=credit.driver_user_id,
                campaign_id=credit.campaign_id,
                trip_session_id=source_trip.id,
                vehicle_id=credit.vehicle_id,
                entry_type="reversal",
                status="available",
                amount=Decimal(deduction),
                currency="NGN",
                occurred_at=funding.occurred_at,
                ledger_metadata={"source_entry_id": str(credit.id), "lagos_day": "2026-08-21"},
            )
        )
    payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.profile.id))
    version, account = await _frozen_payee_authority(session, credit, payee)
    batch = await create_payout_batch_draft(
        session, currency="NGN", actor_user_id=graph.admin.id, reason="Original paid trip"
    )
    line = build_frozen_payout_line(
        batch_id=batch.id,
        entry=credit,
        payee_version=version,
        account_version=account,
        amount=min(credit.amount, Decimal(cash)),
    )
    line.amount = Decimal(cash)  # Also model a duplicate cash total without another deduction.
    line.status = "succeeded"
    line.reservation_active = False
    line.provider_transfer_reference = f"paid-{uuid4()}"
    line.reconciled_at = funding.occurred_at
    freeze_batch_instruction_set(batch, [line])
    batch.status = "completed"
    session.add(line)
    await session.flush()
    return funding, credit


@pytest.mark.parametrize(
    "payable,expected_cash,remaining",
    [
        ("10000.00", "9900.00", "0.00"),
        ("40.00", "0.00", "60.00"),
    ],
)
def test_next_payout_offsets_debt_once_without_zero_cash_batches(
    db_sessionmaker,
    payable,
    expected_cash,
    remaining,
):
    graph = build_graph(db_sessionmaker, f"recovery-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, source = await seed_debt(session, graph, payable=payable)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, reason="Next payout"
            )
            request_id = batch.id
            result, lines = await reserve_payout_batch(
                session,
                batch_id=request_id,
                ledger_entry_ids=(funding.id,),
                actor_user_id=graph.admin.id,
                reason="Next payout",
            )
            assert sum((line.amount for line in lines), Decimal(0)) == Decimal(expected_cash)
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            assert position.debt == Decimal(remaining)
            if not lines:
                assert result is None
                assert await session.get(PayoutBatch, request_id) is None
                assert funding.status == "paid"
            await session.commit()
        async with db_sessionmaker() as session:
            from app.models.disbursement import PayoutRecoveryOffset

            assert await session.scalar(select(func.sum(PayoutRecoveryOffset.amount))) == (
                Decimal("100.00") - Decimal(remaining)
            )
            if lines:
                _, replay = await reserve_payout_batch(
                    session,
                    batch_id=request_id,
                    ledger_entry_ids=(funding.id,),
                    actor_user_id=graph.admin.id,
                    reason="Next payout",
                )
                assert replay[0].id == lines[0].id

    asyncio.run(exercise())


def test_partial_offsets_carry_forward_and_funding_void_does_not_collect_twice(db_sessionmaker):
    graph = build_graph(db_sessionmaker, f"partial-offset-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, source = await seed_debt(session, graph, payable="40.00")
            first_request = uuid4()
            await lock_driver_money_scope(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            assert (
                await allocate_payout_recovery(
                    session,
                    entry=funding,
                    payable=Decimal("40.00"),
                    request_id=first_request,
                    actor_user_id=graph.admin.id,
                )
                == 0
            )
            next_credit = await _seed_authority(session, graph, amount="60.00")
            assert (
                await allocate_payout_recovery(
                    session,
                    entry=next_credit,
                    payable=Decimal("60.00"),
                    request_id=uuid4(),
                    actor_user_id=graph.admin.id,
                )
                == 0
            )
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            assert position.debt == 0
            funding.status = "voided"
            await session.flush()
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            assert position.debt == Decimal("40.00")
            assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == 2

    asyncio.run(exercise())


@pytest.mark.parametrize("cause", ["manual", "recompute"])
def test_funded_offsets_become_debt_if_funding_trip_worth_falls(db_sessionmaker, cause):
    graph = build_graph(db_sessionmaker, f"funded-debt-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, _ = await seed_debt(session, graph, deduction="10000.00")
            await lock_driver_money_scope(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            assert (
                await allocate_payout_recovery(
                    session,
                    entry=funding,
                    payable=funding.amount,
                    request_id=uuid4(),
                    actor_user_id=graph.admin.id,
                )
                == 0
            )
            session.add(
                EarningsLedgerEntry(
                    driver_profile_id=funding.driver_profile_id,
                    driver_user_id=funding.driver_user_id,
                    campaign_id=funding.campaign_id,
                    trip_session_id=funding.trip_session_id,
                    vehicle_id=funding.vehicle_id,
                    entry_type="reversal",
                    status="available",
                    amount=funding.amount,
                    currency="NGN",
                    occurred_at=funding.occurred_at,
                    ledger_metadata={"source_entry_id": str(funding.id)}
                    if cause == "manual"
                    else {"recompute_day": "2026-08-21"},
                )
            )
            await session.flush()
            position = await trip_money_position(
                session, trip_session_id=funding.trip_session_id, currency="NGN"
            )
            assert position.cash_paid == 0
            assert position.settled == Decimal("10000.00")
            assert position.debt == Decimal("10000.00")

    asyncio.run(exercise())


def test_original_transfer_reversal_restores_cash_authority_and_preview(db_sessionmaker):
    from app.services.automatic_payouts import automatic_final_clean_authority
    from app.services.payout_operations import preview_payment_selection

    graph = build_graph(db_sessionmaker, f"reverse-offset-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, source = await seed_debt(session, graph)
            await lock_driver_money_scope(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            await allocate_payout_recovery(
                session,
                entry=funding,
                payable=funding.amount,
                request_id=uuid4(),
                actor_user_id=graph.admin.id,
            )
            line = await session.scalar(
                select(PayoutBatchLine).where(PayoutBatchLine.ledger_entry_id == source.id)
            )
            line.status = "failed"
            source.status = "available"
            await session.flush()
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            compensation = await _seed_authority(session, graph, amount="100.00")
            preview = await preview_payment_selection(
                session, currency="NGN", ledger_entry_ids=(compensation.id,)
            )
            assert preview["total_amount"] == Decimal("100.00")
            assert position.settled == Decimal("-100.00")
            assert position.batch_payable == Decimal("10000.00")
            assert position.debt == 0
            await automatic_final_clean_authority(
                session,
                batch=await session.get(PayoutBatch, line.batch_id),
                trip_ids=(funding.trip_session_id,),
                driver_profile_ids=(graph.profile.id,),
            )
            await session.commit()
            draft = await create_payout_batch_draft(
                session,
                currency="NGN",
                actor_user_id=graph.admin.id,
                reason="Pay the checked positive correction",
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(compensation.id,),
                actor_user_id=graph.admin.id,
                reason="Pay the checked positive correction",
            )
            assert lines[0].amount == Decimal("100.00")
            assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == 1

    asyncio.run(exercise())


def test_driver_money_row_serializes_overlapping_allocations(postgis_db_sessionmaker):
    db = postgis_db_sessionmaker
    graph = build_graph(db, f"race-offset-{uuid4().hex[:8]}")

    async def exercise():
        async with db() as session:
            first, _ = await seed_debt(session, graph)
            second = await _seed_authority(session, graph)
            await session.commit()
            ids = first.id, second.id
        first_locked, second_started, second_acquired = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )

        async def allocate(index):
            async with db() as session:
                if index:
                    await first_locked.wait()
                    second_started.set()
                await lock_driver_money_scope(
                    session, driver_profile_id=graph.profile.id, currency="NGN"
                )
                if index:
                    second_acquired.set()
                if not index:
                    first_locked.set()
                    await second_started.wait()
                    await asyncio.sleep(0.05)
                    assert not second_acquired.is_set()
                entry = await session.get(EarningsLedgerEntry, ids[index])
                cash = await allocate_payout_recovery(
                    session,
                    entry=entry,
                    payable=entry.amount,
                    request_id=uuid4(),
                    actor_user_id=graph.admin.id,
                )
                await session.commit()
                return cash

        cash = await asyncio.wait_for(asyncio.gather(allocate(0), allocate(1)), timeout=15)
        assert sum(cash) == Decimal("10000.00")
        async with db() as session:
            assert await session.scalar(select(func.sum(PayoutRecoveryOffset.amount))) == Decimal(
                "100.00"
            )

    asyncio.run(exercise())


def test_offset_migration_rejects_database_mutation(postgis_db_sessionmaker):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text, update
    from sqlalchemy.exc import DBAPIError

    db = postgis_db_sessionmaker
    graph = build_graph(db, f"migration-offset-{uuid4().hex[:8]}")
    path = Path(__file__).parents[1] / "alembic/versions/0121_payout_recovery_offsets.py"
    spec = importlib.util.spec_from_file_location("recovery_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    async def exercise():
        async with db() as session:
            connection = await session.connection()

            def migrate(sync):
                sync.execute(text("DROP TABLE payout_recovery_offsets"))
                with Operations.context(MigrationContext.configure(sync)):
                    migration.upgrade()
                    migration.downgrade()
                    migration.upgrade()

            await connection.run_sync(migrate)
            funding, _ = await seed_debt(session, graph)
            await lock_driver_money_scope(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            await allocate_payout_recovery(
                session,
                entry=funding,
                payable=funding.amount,
                request_id=uuid4(),
                actor_user_id=graph.admin.id,
            )
            with pytest.raises(DBAPIError, match="immutable"):
                async with session.begin_nested():
                    await session.execute(
                        update(PayoutRecoveryOffset).values(amount=Decimal("1.00"))
                    )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "cause,expected",
    [
        ("deduction", "100.00"),
        ("correction", "100.00"),
        ("duplicate", "100.00"),
        ("void", "1000.00"),
    ],
)
def test_debt_is_cash_above_trip_worth_not_a_fine(db_sessionmaker, cause, expected):
    graph = build_graph(db_sessionmaker, f"worth-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            _, source = await seed_debt(
                session,
                graph,
                cash="1000.00" if cause == "void" else "10000.00",
                deduction="200.00" if cause == "void" else "100.00",
            )
            if cause == "void":
                source.status = "voided"
            elif cause == "duplicate":
                source.amount = Decimal("9900.00")
                deduction = await session.scalar(
                    select(EarningsLedgerEntry).where(
                        EarningsLedgerEntry.trip_session_id == source.trip_session_id,
                        EarningsLedgerEntry.entry_type == "reversal",
                    )
                )
                deduction.status = "voided"
            elif cause == "correction":
                deduction = await session.scalar(
                    select(EarningsLedgerEntry).where(
                        EarningsLedgerEntry.trip_session_id == source.trip_session_id,
                        EarningsLedgerEntry.entry_type == "reversal",
                    )
                )
                deduction.ledger_metadata = {"recompute_day": True}
            await session.flush()
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            assert position.debt == Decimal(expected)
            assert position.earned_net >= 0

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["void", "failed"])
def test_final_offset_survives_void_and_retry_of_cash(db_sessionmaker, outcome):
    graph = build_graph(db_sessionmaker, f"void-offset-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, source = await seed_debt(session, graph)
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, reason="Next payout"
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(funding.id,),
                actor_user_id=graph.admin.id,
                reason="Next payout",
            )
            assert lines[0].amount == Decimal("9900.00")
            if outcome == "void":
                await void_payout_batch(session, batch_id=batch.id, actor_user_id=graph.admin.id)
            else:
                lines[0].status = "failed"
                lines[0].reservation_active = False
                lines[0].provider_transfer_reference = f"failed-{uuid4()}"
                batch.status = "failed"
                await session.flush()
            position = await trip_money_position(
                session, trip_session_id=funding.trip_session_id, currency="NGN"
            )
            assert position.unpaid_authority == Decimal("9900.00")
            if outcome == "failed":
                assert position.terminal_failed == Decimal("9900.00")
                source_position = await trip_money_position(
                    session,
                    trip_session_id=source.trip_session_id,
                    currency="NGN",
                )
                assert source_position.debt == 0
                assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == 1
                return
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, reason="Retry net cash"
            )
            _, retry = await reserve_payout_batch(
                session,
                batch_id=draft.id,
                ledger_entry_ids=(funding.id,),
                actor_user_id=graph.admin.id,
                reason="Retry net cash",
            )
            assert retry[0].amount == Decimal("9900.00")
            position = await trip_money_position(
                session, trip_session_id=source.trip_session_id, currency="NGN"
            )
            assert position.debt == 0
            assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("refusal", ["wrong_actor", "different_selection"])
@pytest.mark.parametrize("recreated_draft", [False, True])
def test_settled_recovery_reference_refuses_changed_retries(
    db_sessionmaker, refusal, recreated_draft
):
    graph = build_graph(db_sessionmaker, f"retry-refusal-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            funding, _ = await seed_debt(session, graph, payable="40.00")
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, reason="Next payout"
            )
            request_id = batch.id
            result, lines = await reserve_payout_batch(
                session,
                batch_id=request_id,
                ledger_entry_ids=(funding.id,),
                actor_user_id=graph.admin.id,
                reason="Next payout",
            )
            assert result is None and not lines
            other = type(graph.admin)(
                email=f"retry-admin-{uuid4().hex}@example.com",
                password_hash=graph.admin.password_hash,
                full_name="Other admin",
                role="admin",
                status="active",
            )
            session.add(other)
            await session.flush()
            if recreated_draft:
                await create_payout_batch_draft(
                    session,
                    currency="NGN",
                    actor_user_id=graph.admin.id,
                    request_id=request_id,
                    reason="Next payout",
                )
            before = await session.scalar(select(func.count(PayoutRecoveryOffset.id)))
            actor = other.id if refusal == "wrong_actor" else graph.admin.id
            selection = (funding.id,) if refusal == "wrong_actor" else (uuid4(),)
            with pytest.raises(AppError) as caught:
                await reserve_payout_batch(
                    session,
                    batch_id=request_id,
                    ledger_entry_ids=selection,
                    actor_user_id=actor,
                    reason="Next payout",
                )
            assert caught.value.code == "PAYOUT_DRAFT_RETRY_CONFLICT"
            assert await session.scalar(select(func.count(PayoutRecoveryOffset.id))) == before
            assert bool(await session.get(PayoutBatch, request_id)) == recreated_draft

    asyncio.run(exercise())
