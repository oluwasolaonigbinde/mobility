import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority
from test_payout_corrections import (
    approved_order,
    correction_entries,
    execute,
    raise_rule_rate,
    set_trip_payout_status,
)
from test_payouts_v2 import build_v2_graph, pipeline_to_v2

from app.core.errors import AppError
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatchLine,
    PayoutDebtAllocation,
    PayoutDebtObligation,
    PayoutDebtPaidSource,
    PayoutDebtSettlement,
)
from app.models.payout import EarningsLedgerEntry
from app.services.disbursements import create_payout_batch_draft, reserve_payout_batch
from app.services.payout_debt import (
    allocate_available_credit_to_debt,
    driver_money_balance,
    record_reversal_obligation,
)


def _ledger(
    graph,
    *,
    amount: str,
    status: str,
    currency: str = "NGN",
    entry_type: str = "adjustment",
    occurred_at: datetime | None = None,
):
    return EarningsLedgerEntry(
        payout_calculation_id=None,
        driver_profile_id=graph.profile.id,
        driver_user_id=graph.driver.id,
        campaign_id=graph.campaign.id,
        trip_session_id=graph.trip.id,
        vehicle_id=graph.vehicle.id,
        entry_type=entry_type,
        status=status,
        amount=Decimal(amount),
        currency=currency,
        occurred_at=occurred_at or graph.trip.ended_at,
        ledger_metadata={},
    )


async def _debt(session, graph, amount: str, *, currency: str = "NGN"):
    paid = _ledger(graph, amount="500.00", status="paid", currency=currency)
    reversal = _ledger(
        graph,
        amount=amount,
        status="available",
        currency=currency,
        entry_type="reversal",
    )
    session.add_all([paid, reversal])
    await session.flush()
    obligation = await record_reversal_obligation(session, reversal_entry=reversal)
    assert obligation is not None
    return paid, reversal, obligation


def test_available_pre_payment_reversal_is_netted_before_batching(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"debt-prepaid-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            credit = await _seed_authority(session, graph, amount="150.00")
            reversal = _ledger(
                graph,
                amount="60.00",
                status="available",
                entry_type="reversal",
            )
            session.add(reversal)
            await session.flush()
            obligation = await record_reversal_obligation(session, reversal_entry=reversal)
            result = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            remainder = await session.get(EarningsLedgerEntry, result.remainder_entry_ids[0])
            return credit, reversal, obligation, result, remainder

    credit, reversal, obligation, result, remainder = asyncio.run(exercise())
    assert obligation is not None
    assert obligation.original_amount == Decimal("60.00")
    assert credit.status == "reversed"
    assert reversal.status == "available"
    assert result.balance.carry_forward_debt == Decimal("0.00")
    assert result.balance.batch_payable == Decimal("90.00")
    assert remainder.amount == Decimal("90.00")


@pytest.mark.parametrize("paid_type", ["adjustment", "debt_remainder"])
def test_actual_paid_credit_type_defines_post_payment_boundary(
    db_sessionmaker, paid_type: str
) -> None:
    graph = build_graph(db_sessionmaker, f"debt-paid-kind-{paid_type}-{uuid4().hex[:6]}")

    async def exercise():
        async with db_sessionmaker() as session:
            paid = _ledger(
                graph,
                amount="80.00",
                status="paid",
                entry_type=paid_type,
            )
            reversal = _ledger(
                graph,
                amount="25.00",
                status="pending",
                entry_type="reversal",
            )
            session.add_all([paid, reversal])
            await session.flush()
            obligation = await record_reversal_obligation(session, reversal_entry=reversal)
            sources = tuple(
                (
                    await session.scalars(
                        select(PayoutDebtPaidSource).where(
                            PayoutDebtPaidSource.debt_obligation_id == obligation.id
                        )
                    )
                ).all()
            )
            return paid, reversal, obligation, sources

    paid, reversal, obligation, sources = asyncio.run(exercise())
    assert reversal.status == "available"
    assert obligation.original_amount == Decimal("25.00")
    assert [source.paid_ledger_entry_id for source in sources] == [paid.id]


def test_paid_reversal_debt_future_credit_and_whole_entry_batch_e2e(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"debt-e2e-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            future_credit = await _seed_authority(session, graph, amount="150.00")
            paid, reversal, obligation = await _debt(session, graph, "60.00")
            before = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            with pytest.raises(AppError) as blocked:
                await reserve_payout_batch(
                    session,
                    batch_id=draft.id,
                    ledger_entry_ids=(future_credit.id,),
                    actor_user_id=graph.admin.id,
                )
            assert blocked.value.code == "PAYOUT_DEBT_ALLOCATION_REQUIRED"
            result = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            replay = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            remainder = await session.get(EarningsLedgerEntry, result.remainder_entry_ids[0])
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(remainder.id,),
                actor_user_id=graph.admin.id,
            )
            paid_sources = tuple(
                (
                    await session.scalars(
                        select(PayoutDebtPaidSource).where(
                            PayoutDebtPaidSource.debt_obligation_id == obligation.id
                        )
                    )
                ).all()
            )
            allocations = tuple((await session.scalars(select(PayoutDebtAllocation))).all())
            settlements = tuple((await session.scalars(select(PayoutDebtSettlement))).all())
            await session.commit()
            return (
                before,
                result,
                replay,
                paid,
                reversal,
                future_credit,
                remainder,
                batch,
                lines,
                paid_sources,
                allocations,
                settlements,
            )

    (
        before,
        result,
        replay,
        paid,
        reversal,
        future_credit,
        remainder,
        batch,
        lines,
        paid_sources,
        allocations,
        settlements,
    ) = asyncio.run(exercise())
    assert before.earned_net == Decimal("590.00")
    assert before.released_available == Decimal("150.00")
    assert before.cash_paid == Decimal("500.00")
    assert before.carry_forward_debt == Decimal("60.00")
    assert before.batch_payable == Decimal("0.00")
    assert result.balance.earned_net == before.earned_net
    assert result.balance.carry_forward_debt == Decimal("0.00")
    assert result.balance.batch_payable == Decimal("90.00")
    assert replay.settlement_ids == ()
    assert paid.status == "paid"
    assert reversal.status == "available"
    assert future_credit.status == "reversed"
    assert remainder.entry_type == "debt_remainder"
    assert remainder.amount == Decimal("90.00")
    assert batch.total_amount == Decimal("90.00")
    assert len(lines) == 1 and lines[0].ledger_entry_id == remainder.id
    assert [source.paid_ledger_entry_id for source in paid_sources] == [paid.id]
    assert sum(item.amount for item in allocations) == Decimal("60.00")
    assert len(settlements) == 1


def test_multi_period_allocation_is_monotone_idempotent_and_currency_isolated(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"debt-periods-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            _, reversal, _ = await _debt(session, graph, "100.00")
            usd_credit = _ledger(graph, amount="55.00", status="available", currency="USD")
            session.add(usd_credit)
            balances = []
            for index, amount in enumerate(("30.00", "50.00", "35.00")):
                session.add(
                    _ledger(
                        graph,
                        amount=amount,
                        status="available",
                        occurred_at=datetime(2026, 8, 20, tzinfo=UTC) + timedelta(days=index),
                    )
                )
                await session.flush()
                result = await allocate_available_credit_to_debt(
                    session,
                    driver_profile_id=graph.profile.id,
                    currency="NGN",
                    actor_user_id=graph.admin.id,
                )
                balances.append(result.balance)
            replay = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            usd = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="USD"
            )
            allocations = Decimal(
                await session.scalar(
                    select(func.coalesce(func.sum(PayoutDebtAllocation.amount), 0))
                )
            )
            await session.commit()
            return reversal, balances, replay, usd, allocations

    reversal, balances, replay, usd, allocations = asyncio.run(exercise())
    assert [balance.carry_forward_debt for balance in balances] == [
        Decimal("70.00"),
        Decimal("20.00"),
        Decimal("0.00"),
    ]
    assert [balance.batch_payable for balance in balances] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("15.00"),
    ]
    assert replay.settlement_ids == ()
    assert allocations == Decimal("100.00")
    assert reversal.amount == Decimal("100.00")
    assert usd.carry_forward_debt == Decimal("0.00")
    assert usd.batch_payable == Decimal("55.00")


def test_admin_debt_balance_and_allocation_api(db_client, db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"debt-api-{uuid4().hex[:8]}")

    async def seed():
        async with db_sessionmaker() as session:
            await _debt(session, graph, "25.00")
            credit = _ledger(graph, amount="40.00", status="available")
            session.add(credit)
            await session.commit()

    asyncio.run(seed())
    headers = auth_headers(db_client, graph.admin.email)
    before = db_client.get(
        f"/api/v1/admin/payout-batches/debt-balances/{graph.profile.id}?currency=ngn",
        headers=headers,
    )
    allocated = db_client.post(
        f"/api/v1/admin/payout-batches/debt-balances/{graph.profile.id}/allocate",
        headers=headers,
        json={"currency": "ngn"},
    )
    assert before.status_code == 200
    assert before.json()["carry_forward_debt"] == "25.00"
    assert before.json()["batch_payable"] == "0.00"
    assert allocated.status_code == 200
    assert allocated.json()["balance"]["carry_forward_debt"] == "0.00"
    assert allocated.json()["balance"]["batch_payable"] == "15.00"
    assert len(allocated.json()["settlement_ids"]) == 1


def test_approved_post_payment_correction_posts_new_debt_authority(
    postgis_db_sessionmaker, settings
) -> None:
    graph = build_v2_graph(postgis_db_sessionmaker, "debt-correction")
    pipeline_to_v2(postgis_db_sessionmaker, settings, graph)
    set_trip_payout_status(postgis_db_sessionmaker, graph.trip.id, "paid")
    raise_rule_rate(postgis_db_sessionmaker, graph.rule.id, "900.00")
    order, approver = approved_order(postgis_db_sessionmaker, settings, graph, "debt-correction")
    executed, executed_now = execute(
        postgis_db_sessionmaker,
        settings,
        order.id,
        approver.id,
        release_at=None,
    )
    entries = correction_entries(postgis_db_sessionmaker)

    async def fetch():
        async with postgis_db_sessionmaker() as session:
            obligation = await session.scalar(
                select(PayoutDebtObligation).where(
                    PayoutDebtObligation.source_reversal_entry_id == entries[0].id
                )
            )
            sources = tuple(
                (
                    await session.scalars(
                        select(PayoutDebtPaidSource).where(
                            PayoutDebtPaidSource.debt_obligation_id == obligation.id
                        )
                    )
                ).all()
            )
            return obligation, sources

    obligation, sources = asyncio.run(fetch())
    assert executed_now is True
    assert executed.execution_result["reversal_count"] == 1
    assert entries[0].entry_type == "reversal"
    assert entries[0].status == "available"
    assert entries[0].amount == Decimal("150.00")
    assert obligation.correction_order_id == order.id
    assert obligation.original_amount == Decimal("150.00")
    assert obligation.outstanding_amount == Decimal("150.00")
    assert len(sources) == 1


def test_postgres_concurrent_credit_allocation_has_one_deterministic_result(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"debt-race-{uuid4().hex[:8]}")

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            await _debt(session, graph, "100.00")
            session.add_all(
                [
                    _ledger(
                        graph,
                        amount="60.00",
                        status="available",
                        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
                    ),
                    _ledger(
                        graph,
                        amount="80.00",
                        status="available",
                        occurred_at=datetime(2026, 8, 21, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

        async def allocate():
            async with postgis_db_sessionmaker() as session:
                result = await allocate_available_credit_to_debt(
                    session,
                    driver_profile_id=graph.profile.id,
                    currency="NGN",
                    actor_user_id=graph.admin.id,
                )
                await session.commit()
                return len(result.settlement_ids)

        counts = await asyncio.gather(allocate(), allocate())
        async with postgis_db_sessionmaker() as session:
            account = await session.scalar(select(DriverCurrencyDebtAccount))
            settlements = int(
                await session.scalar(select(func.count(PayoutDebtSettlement.id))) or 0
            )
            allocations = Decimal(
                await session.scalar(
                    select(func.coalesce(func.sum(PayoutDebtAllocation.amount), 0))
                )
            )
            remainders = tuple(
                (
                    await session.scalars(
                        select(EarningsLedgerEntry).where(
                            EarningsLedgerEntry.entry_type == "debt_remainder"
                        )
                    )
                ).all()
            )
            return counts, account, settlements, allocations, remainders

    counts, account, settlements, allocations, remainders = asyncio.run(exercise())
    assert sorted(counts) == [0, 2]
    assert account.outstanding_amount == Decimal("0.00")
    assert account.lifetime_allocated_amount == Decimal("100.00")
    assert settlements == 2
    assert allocations == Decimal("100.00")
    assert len(remainders) == 1 and remainders[0].amount == Decimal("40.00")


def test_postgres_debt_creation_and_reservation_have_one_winner(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"debt-reserve-race-{uuid4().hex[:8]}")

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            credit = await _seed_authority(session, graph, amount="70.00")
            reversal = _ledger(
                graph,
                amount="20.00",
                status="available",
                entry_type="reversal",
            )
            session.add(reversal)
            draft = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await session.commit()
            credit_id, reversal_id, draft_id = credit.id, reversal.id, draft.id

        async def create_debt():
            async with postgis_db_sessionmaker() as session:
                reversal = await session.get(EarningsLedgerEntry, reversal_id)
                try:
                    await record_reversal_obligation(session, reversal_entry=reversal)
                    await session.commit()
                    return "debt"
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        async def reserve():
            async with postgis_db_sessionmaker() as session:
                try:
                    await reserve_payout_batch(
                        session,
                        batch_id=draft_id,
                        ledger_entry_ids=(credit_id,),
                        actor_user_id=graph.admin.id,
                    )
                    await session.commit()
                    return "reserved"
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        outcomes = await asyncio.gather(create_debt(), reserve())
        async with postgis_db_sessionmaker() as session:
            obligations = int(
                await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0
            )
            active_lines = int(
                await session.scalar(
                    select(func.count(PayoutBatchLine.id)).where(
                        PayoutBatchLine.reservation_active.is_(True)
                    )
                )
                or 0
            )
            return outcomes, obligations, active_lines

    outcomes, obligations, active_lines = asyncio.run(exercise())
    assert sum(result in {"debt", "reserved"} for result in outcomes) == 1
    assert (obligations, active_lines) in {(1, 0), (0, 1)}
    assert set(outcomes) & {
        "PAYOUT_DEBT_ACTIVE_RESERVATION",
        "PAYOUT_DEBT_ALLOCATION_REQUIRED",
    }


def test_postgres_duplicate_reversal_creation_is_idempotent(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"debt-duplicate-{uuid4().hex[:8]}")

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            reversal = _ledger(
                graph,
                amount="45.00",
                status="available",
                entry_type="reversal",
            )
            session.add(reversal)
            await session.commit()
            reversal_id = reversal.id

        async def create():
            async with postgis_db_sessionmaker() as session:
                reversal = await session.get(EarningsLedgerEntry, reversal_id)
                obligation = await record_reversal_obligation(session, reversal_entry=reversal)
                await session.commit()
                return obligation.id

        obligation_ids = await asyncio.gather(create(), create())
        async with postgis_db_sessionmaker() as session:
            account = await session.scalar(select(DriverCurrencyDebtAccount))
            count = int(await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0)
            return obligation_ids, account, count

    obligation_ids, account, count = asyncio.run(exercise())
    assert obligation_ids[0] == obligation_ids[1]
    assert count == 1
    assert account.outstanding_amount == Decimal("45.00")
    assert account.lifetime_incurred_amount == Decimal("45.00")
