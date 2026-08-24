import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import auth_headers, create_test_trip_session
from sqlalchemy import func, select
from test_mny03a_earnings_release import NOW, build_graph, create_flag
from test_payout_batches import _seed_authority
from test_payout_corrections import (
    approved_order,
    correction_entries,
    execute,
    raise_rule_rate,
    set_trip_payout_status,
)
from test_payout_reconciliation import _admins, _submitted_batch
from test_payouts_v2 import build_v2_graph, pipeline_to_v2

from app.adapters.disbursement import FakeDisbursementAdapter
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
from app.models.trip import TripSessionStatus
from app.services import disbursements
from app.services.disbursements import (
    create_payout_batch_draft,
    reconcile_payout_webhook,
    reserve_payout_batch,
)
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
from app.services.payout_debt import (
    allocate_available_credit_to_debt,
    driver_money_balance,
    record_reversal_obligation,
)
from app.services.payouts import (
    _posted_amount_for_trip,
    advertiser_campaign_cost_summary,
    driver_earnings_summary,
    driver_trip_earnings_breakdown,
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
    # The available source stays whole-entry blocked until allocation, but the
    # driver-facing settlement projection is its debt-aware net amount.
    assert before.batch_payable == Decimal("90.00")
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


def test_debt_projection_keeps_economic_provenance_separate_from_settlement(
    db_sessionmaker, settings
) -> None:
    """Two trips agree through debt allocation, cash payment and a no-op correction basis."""
    graph = build_graph(db_sessionmaker, f"debt-projection-{uuid4().hex[:8]}")
    trip_two = create_test_trip_session(
        db_sessionmaker,
        assignment_id=graph.assignment.id,
        campaign_id=graph.campaign.id,
        driver_profile_id=graph.profile.id,
        vehicle_id=graph.vehicle.id,
        started_by_user_id=graph.driver.id,
        trip_status=TripSessionStatus.SEALED,
        started_at=NOW + timedelta(days=1),
        ended_at=NOW + timedelta(days=1, hours=1),
    )

    async def exercise():
        async with db_sessionmaker() as session:
            paid = _ledger(graph, amount="100.00", status="paid")
            reversal = _ledger(
                graph, amount="60.00", status="available", entry_type="reversal"
            )
            credit = _ledger(graph, amount="150.00", status="available")
            credit.trip_session_id = trip_two.id
            credit.occurred_at = trip_two.ended_at
            session.add_all([paid, reversal, credit])
            await session.flush()
            await record_reversal_obligation(session, reversal_entry=reversal)

            before_balance = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            before_summary = await driver_earnings_summary(
                session, user_id=graph.driver.id, currency="NGN", settings=settings
            )
            before_first_trip = await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=graph.trip.id
            )
            before_second_trip = await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=trip_two.id
            )
            before_cost = await advertiser_campaign_cost_summary(
                session,
                user_id=graph.advertiser.id,
                campaign_id=graph.campaign.id,
                start_at=None,
                end_at=None,
                currency="NGN",
                settings=settings,
            )
            allocation = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            remainder = await session.get(EarningsLedgerEntry, allocation.remainder_entry_ids[0])
            after_summary = await driver_earnings_summary(
                session, user_id=graph.driver.id, currency="NGN", settings=settings
            )
            after_second_trip = await driver_trip_earnings_breakdown(
                session, user_id=graph.driver.id, trip_id=trip_two.id
            )
            after_cost = await advertiser_campaign_cost_summary(
                session,
                user_id=graph.advertiser.id,
                campaign_id=graph.campaign.id,
                start_at=None,
                end_at=None,
                currency="NGN",
                settings=settings,
            )
            posted = await _posted_amount_for_trip(
                session,
                trip_session_id=trip_two.id,
                driver_profile_id=graph.profile.id,
                currency="NGN",
            )
            remainder.status = "paid"
            paid_summary = await driver_earnings_summary(
                session, user_id=graph.driver.id, currency="NGN", settings=settings
            )
            await session.commit()
            return (
                before_balance,
                before_summary.totals_by_currency[0],
                before_first_trip,
                before_second_trip,
                before_cost.totals_by_currency[0],
                allocation.balance,
                remainder,
                after_summary.totals_by_currency[0],
                after_second_trip,
                after_cost.totals_by_currency[0],
                posted,
                paid_summary.totals_by_currency[0],
            )

    (
        before_balance,
        before_summary,
        before_first_trip,
        before_second_trip,
        before_cost,
        after_balance,
        remainder,
        after_summary,
        after_second_trip,
        after_cost,
        posted,
        paid_summary,
    ) = asyncio.run(exercise())
    assert before_balance.earned_net == Decimal("190.00")
    assert before_balance.released_available == Decimal("150.00")
    assert before_balance.cash_paid == Decimal("100.00")
    assert before_balance.carry_forward_debt == Decimal("60.00")
    assert before_balance.batch_payable == Decimal("90.00")
    assert before_summary.lifetime_earned_amount == Decimal("190.00")
    assert before_summary.released_available_amount == Decimal("150.00")
    assert before_summary.cash_paid_amount == Decimal("100.00")
    assert before_summary.carry_forward_debt_amount == Decimal("60.00")
    assert before_summary.batch_payable_amount == Decimal("90.00")
    assert before_first_trip.amount == Decimal("40.00")
    assert before_second_trip.amount == Decimal("150.00")
    assert before_cost.ledger_net_total == Decimal("190.00")
    assert after_balance.batch_payable == Decimal("90.00")
    assert remainder.amount == Decimal("90.00")
    assert after_summary.lifetime_earned_amount == Decimal("190.00")
    assert after_summary.released_available_amount == Decimal("90.00")
    assert after_summary.carry_forward_debt_amount == Decimal("0.00")
    assert after_summary.batch_payable_amount == Decimal("90.00")
    assert after_second_trip.amount == Decimal("150.00")
    assert after_cost.ledger_net_total == Decimal("190.00")
    assert posted == Decimal("150.00")
    assert paid_summary.lifetime_earned_amount == Decimal("190.00")
    assert paid_summary.cash_paid_amount == Decimal("190.00")
    assert paid_summary.batch_payable_amount == Decimal("0.00")


def test_paid_line_confirmed_fraud_creates_debt_then_nets_future_credit(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"debt-fraud-{uuid4().hex[:8]}")
    flag = create_flag(db_sessionmaker, graph)

    async def exercise():
        async with db_sessionmaker() as session:
            paid = _ledger(graph, amount="125.50", status="paid")
            session.add(paid)
            await session.flush()
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
                outcome="confirmed",
                resolution_note="Provider-paid fraud confirmed.",
                now=NOW + timedelta(seconds=1),
            )
            obligation = await session.scalar(
                select(PayoutDebtObligation).where(
                    PayoutDebtObligation.source_reversal_entry_id
                    == select(EarningsLedgerEntry.id)
                    .where(EarningsLedgerEntry.source_fraud_flag_id == flag.id)
                    .scalar_subquery()
                )
            )
            future_credit = await _seed_authority(session, graph, amount="200.00")
            allocation = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            remainder = await session.get(EarningsLedgerEntry, allocation.remainder_entry_ids[0])
            return paid, obligation, future_credit, allocation, remainder

    paid, obligation, future_credit, allocation, remainder = asyncio.run(exercise())
    assert paid.status == "paid"
    assert obligation is not None
    assert obligation.original_amount == Decimal("125.50")
    assert future_credit.status == "reversed"
    assert allocation.balance.carry_forward_debt == Decimal("0.00")
    assert allocation.balance.batch_payable == Decimal("74.50")
    assert remainder.amount == Decimal("74.50")


def test_postgres_paid_finality_and_fraud_confirmation_share_lock_order(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"debt-fraud-race-{uuid4().hex[:8]}")
    checker, _reconciler = _admins(postgis_db_sessionmaker, "debt-fraud-race")
    fake = FakeDisbursementAdapter()

    async def setup():
        async with postgis_db_sessionmaker() as session:
            _batch, lines, entries = await _submitted_batch(
                session,
                graph,
                checker,
                fake,
            )
            await session.commit()
            return (
                lines[0].provider_transfer_reference,
                entries[0].id,
                entries[0].amount,
            )

    provider_reference, paid_entry_id, paid_amount = asyncio.run(setup())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def acknowledge():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                now=NOW,
            )
            await session.commit()

    asyncio.run(acknowledge())

    async def exercise_race():
        provider_has_scope = asyncio.Event()
        release_provider = asyncio.Event()
        original_lock = disbursements.lock_driver_currency_debt_scope

        async def held_provider_lock(session, *, driver_profile_id, currency):
            result = await original_lock(
                session,
                driver_profile_id=driver_profile_id,
                currency=currency,
            )
            provider_has_scope.set()
            await release_provider.wait()
            return result

        monkeypatch.setattr(
            disbursements,
            "lock_driver_currency_debt_scope",
            held_provider_lock,
        )
        payload = json.dumps(
            {
                "provider_transfer_reference": provider_reference,
                "provider_event_id": "paid-fraud-race-success",
                "outcome": "succeeded",
                "occurred_at": (NOW + timedelta(seconds=1)).isoformat(),
            },
            sort_keys=True,
        ).encode()

        async def reconcile():
            async with postgis_db_sessionmaker() as session:
                await reconcile_payout_webhook(
                    session,
                    payload=payload,
                    signature=fake.sign_webhook(payload),
                    adapter=fake,
                )
                await session.commit()

        async def confirm():
            await provider_has_scope.wait()
            async with postgis_db_sessionmaker() as session:
                await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    outcome="confirmed",
                    resolution_note="Provider-paid fraud confirmed concurrently.",
                    now=NOW + timedelta(seconds=2),
                )
                await session.commit()

        provider_task = asyncio.create_task(reconcile())
        confirmation_task = asyncio.create_task(confirm())
        await provider_has_scope.wait()
        await asyncio.sleep(0.05)
        release_provider.set()
        await asyncio.wait_for(
            asyncio.gather(provider_task, confirmation_task),
            timeout=5,
        )

        async with postgis_db_sessionmaker() as session:
            paid = await session.get(EarningsLedgerEntry, paid_entry_id)
            obligations = tuple((await session.scalars(select(PayoutDebtObligation))).all())
            sources = tuple((await session.scalars(select(PayoutDebtPaidSource))).all())
            return paid, obligations, sources

    paid, obligations, sources = asyncio.run(exercise_race())
    assert paid is not None
    assert paid.status == "paid"
    assert paid.amount == paid_amount
    assert len(obligations) == 1
    assert obligations[0].original_amount == paid_amount
    assert [source.paid_ledger_entry_id for source in sources] == [paid_entry_id]


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
    driver_summary = db_client.get(
        "/api/v1/driver/earnings/summary?currency=ngn",
        headers=auth_headers(db_client, graph.driver.email),
    )
    allocated = db_client.post(
        f"/api/v1/admin/payout-batches/debt-balances/{graph.profile.id}/allocate",
        headers=headers,
        json={"currency": "ngn"},
    )
    assert before.status_code == 200
    assert before.json()["carry_forward_debt"] == "25.00"
    assert before.json()["batch_payable"] == "15.00"
    assert driver_summary.status_code == 200
    driver_total = driver_summary.json()["totals_by_currency"][0]
    assert driver_total["carry_forward_debt_amount"] == "25.00"
    assert driver_total["batch_payable_amount"] == "15.00"
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
