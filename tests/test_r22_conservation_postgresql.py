import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_mny03a_earnings_release import build_graph, create_flag
from test_payout_batches import _seed_authority
from test_payout_reconciliation import _admins, _submitted_batch

import app.services.disbursements as disbursement_service
from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import FakeDisbursementAdapter
from app.db.base import Base
from app.models.disbursement import (
    DriverCurrencyDebtAccount,
    PayoutBatchLine,
    PayoutDebtObligation,
    PayoutRecoveryIncident,
    PayoutSubmissionIntent,
)
from app.models.payee import Payee
from app.models.payout import EarningsLedgerEntry
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    poll_payout_line,
    process_payout_submission_intent,
    reserve_payout_batch,
    retry_failed_payout_lines,
    submit_payout_batch,
)
from app.services.fraud_holds import acknowledge_fraud_flag, resolve_fraud_flag
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
)
from app.services.payout_debt import driver_money_balance
from tests.test_migration_0014_partitioning import (
    configured_postgres_url,
    create_database_from_url,
    downgrade_to,
    drop_database,
    upgrade_to,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


async def _poll(
    session,
    *,
    adapter: FakeDisbursementAdapter,
    line: PayoutBatchLine,
    reconciler_id,
    outcome: str,
    event: str,
    occurred_at: datetime,
):
    adapter.set_poll_result(
        provider_transfer_reference=line.provider_transfer_reference,
        provider_event_id=event,
        outcome=outcome,
        occurred_at=occurred_at,
    )
    return await poll_payout_line(
        session,
        line_id=line.id,
        actor_user_id=reconciler_id,
        adapter=adapter,
    )


async def _add_new_bank_version(session, graph) -> None:
    payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.profile.id))
    await add_verified_bank_account_version(
        session,
        payee_id=payee.id,
        details=VerifiedBankAccountDetails(
            account_name="Ada Replacement",
            account_number="9876543210",
            bank_code="058",
        ),
        verification_reference=f"r22-replacement-{uuid4().hex}",
        actor_user_id=graph.admin.id,
        crypto=EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1),
    )


def test_submitted_credit_is_exclusively_in_flight(postgis_db_sessionmaker) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-projection-{uuid4().hex[:8]}")
    checker, _ = _admins(postgis_db_sessionmaker, "r22-projection")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            _batch, _lines, _entries = await _submitted_batch(
                session,
                graph,
                checker,
                adapter,
            )
            return await driver_money_balance(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
            )

    balance = asyncio.run(exercise())

    assert balance.released_available == Decimal("0.00")
    assert balance.reserved == Decimal("0.00")
    assert balance.in_flight == Decimal("100.00")
    assert balance.terminal_failed == Decimal("0.00")
    assert balance.cash_paid == Decimal("0.00")
    assert balance.carry_forward_debt == Decimal("0.00")
    assert balance.batch_payable == Decimal("0.00")


def test_terminal_failure_releases_and_replacement_is_new_authority(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-replace-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-replace")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            original_batch, original_lines, _ = await _submitted_batch(
                session, graph, checker, adapter
            )
            original = original_lines[0]
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-failed-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            failed_balance = await driver_money_balance(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
            )
            await _add_new_bank_version(session, graph)
            replacement, replacement_lines = await retry_failed_payout_lines(
                session,
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            replay, replay_lines = await retry_failed_payout_lines(
                session,
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            replacement_balance = await driver_money_balance(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
            )
            return (
                original,
                failed_balance,
                replacement,
                replacement_lines[0],
                replay,
                replay_lines[0],
                replacement_balance,
            )

    original, failed, replacement, child, replay, replay_child, reserved = asyncio.run(exercise())
    assert original.status == "failed" and original.reservation_active is False
    assert failed.terminal_failed == failed.batch_payable == Decimal("100.00")
    assert replacement.id == replay.id
    assert child.id == replay_child.id
    assert child.predecessor_line_id == original.id
    assert child.bank_account_version_id != original.bank_account_version_id
    assert child.idempotency_key != original.idempotency_key
    assert replacement.approved_by_user_id is None
    assert reserved.reserved == Decimal("100.00")
    assert reserved.terminal_failed == reserved.batch_payable == Decimal("0.00")


def test_concurrent_replacement_requests_converge_to_one_child(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-replace-race-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-replace-race")
    adapter = FakeDisbursementAdapter()

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            batch, lines, _ = await _submitted_batch(session, graph, checker, adapter)
            await _poll(
                session,
                adapter=adapter,
                line=lines[0],
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-race-failed-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            await _add_new_bank_version(session, graph)
            await session.commit()
            return batch.id

    async def replace(batch_id):
        async with postgis_db_sessionmaker() as session:
            batch, lines = await retry_failed_payout_lines(
                session,
                batch_id=batch_id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            await session.commit()
            return batch.id, lines[0].id

    async def race():
        batch_id = await prepare()
        return await asyncio.wait_for(
            asyncio.gather(replace(batch_id), replace(batch_id)),
            timeout=10,
        )

    first, second = asyncio.run(race())
    assert first == second


@pytest.mark.parametrize("replacement_outcome", ["uncalled", "not_found", "failed"])
def test_late_old_success_with_safe_replacement_has_no_duplicate_debt(
    postgis_db_sessionmaker,
    monkeypatch,
    replacement_outcome,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-late-safe-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-late-safe")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            original_batch, lines, entries = await _submitted_batch(
                session, graph, checker, adapter
            )
            original = lines[0]
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-safe-failed-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            await _add_new_bank_version(session, graph)
            replacement, children = await retry_failed_payout_lines(
                session,
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            child = children[0]
            if replacement_outcome in {"not_found", "failed"}:
                await approve_payout_batch(
                    session, batch_id=replacement.id, actor_user_id=checker.id
                )
                await submit_payout_batch(
                    session,
                    batch_id=replacement.id,
                    actor_user_id=graph.admin.id,
                    adapter=adapter,
                )
                intent_id = await session.scalar(
                    select(PayoutSubmissionIntent.id).where(
                        PayoutSubmissionIntent.payout_batch_line_id == child.id
                    )
                )
                await session.commit()
                workers = async_sessionmaker(session.bind, expire_on_commit=False)
                if replacement_outcome == "not_found":
                    original_lease = disbursement_service.DISBURSEMENT_CLAIM_LEASE
                    monkeypatch.setattr(
                        disbursement_service,
                        "DISBURSEMENT_CLAIM_LEASE",
                        timedelta(microseconds=-1),
                    )
                    claim = await disbursement_service.claim_payout_submission_intent(
                        workers,
                        intent_id=intent_id,
                        adapter=adapter,
                    )
                    monkeypatch.setattr(
                        disbursement_service,
                        "DISBURSEMENT_CLAIM_LEASE",
                        original_lease,
                    )
                    assert claim is not None and claim.action == "submit"
                    assert (
                        await process_payout_submission_intent(
                            workers,
                            intent_id=intent_id,
                            adapter=adapter,
                        )
                        == "pending"
                    )
                else:
                    await process_payout_submission_intent(
                        workers, intent_id=intent_id, adapter=adapter
                    )
                child = await session.get(PayoutBatchLine, child.id)
                await session.refresh(child)
                if replacement_outcome == "failed":
                    await _poll(
                        session,
                        adapter=adapter,
                        line=child,
                        reconciler_id=reconciler.id,
                        outcome="failed",
                        event=f"r22-safe-child-failed-{uuid4().hex}",
                        occurred_at=NOW + timedelta(seconds=30),
                    )
            await session.commit()
            original = await session.get(PayoutBatchLine, original.id)
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"r22-safe-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=1),
            )
            await session.commit()
            return (
                await session.get(PayoutBatchLine, original.id),
                await session.get(PayoutBatchLine, child.id),
                await session.get(EarningsLedgerEntry, entries[0].id),
                await session.scalar(select(func.count(PayoutRecoveryIncident.id))),
                await session.scalar(select(func.count(PayoutDebtObligation.id))),
                replacement.id,
            )

    original, child, ledger, incidents, debts, _ = asyncio.run(exercise())
    assert original.status == "succeeded" and original.reservation_active is False
    assert child.status == ("failed" if replacement_outcome == "failed" else "void")
    assert child.reservation_active is False
    assert ledger.status == "paid"
    assert incidents == debts == 0


def test_two_verified_successes_preserve_history_and_create_one_duplicate_debt(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-late-dup-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-late-dup")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            original_batch, lines, entries = await _submitted_batch(
                session, graph, checker, adapter
            )
            original = lines[0]
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-dup-failed-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            await _add_new_bank_version(session, graph)
            replacement, children = await retry_failed_payout_lines(
                session,
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            await approve_payout_batch(session, batch_id=replacement.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session,
                batch_id=replacement.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            child = children[0]
            intent_id = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == child.id
                )
            )
            await session.commit()
            workers = async_sessionmaker(session.bind, expire_on_commit=False)
            await process_payout_submission_intent(workers, intent_id=intent_id, adapter=adapter)
            child = await session.get(PayoutBatchLine, child.id)
            await session.refresh(child)
            original = await session.get(PayoutBatchLine, original.id)
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"r22-old-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=1),
            )
            await session.commit()
            contingent_status = await session.scalar(select(PayoutRecoveryIncident.status))
            debt_before = int(
                await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0
            )
            child = await session.get(PayoutBatchLine, child.id)
            await _poll(
                session,
                adapter=adapter,
                line=child,
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"r22-child-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=2),
            )
            await session.commit()
            return (
                await session.get(PayoutBatchLine, original.id),
                await session.get(PayoutBatchLine, child.id),
                await session.get(EarningsLedgerEntry, entries[0].id),
                tuple(await session.scalars(select(PayoutRecoveryIncident))),
                tuple(await session.scalars(select(PayoutDebtObligation))),
                await session.get(
                    DriverCurrencyDebtAccount,
                    (await session.scalar(select(DriverCurrencyDebtAccount.id))),
                ),
                contingent_status,
                debt_before,
            )

    original, child, ledger, incidents, debts, account, contingent, debt_before = asyncio.run(
        exercise()
    )
    assert original.status == child.status == "succeeded"
    assert original.reservation_active is child.reservation_active is False
    assert ledger.status == "paid"
    assert contingent == "contingent" and debt_before == 0
    assert len(incidents) == len(debts) == 1
    assert incidents[0].kind == "duplicate_cash"
    assert incidents[0].status == "debt_activated"
    assert debts[0].outstanding_amount == account.outstanding_amount == Decimal("100.00")


def test_confirmed_fraud_cancels_pre_call_chain_and_nets_released_credit(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-safe-{uuid4().hex[:8]}")

    async def reserve():
        async with postgis_db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await session.commit()
            return entry.id, lines[0].id

    entry_id, line_id = asyncio.run(reserve())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def confirm():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed payout fraud.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
            return (
                await session.get(PayoutBatchLine, line_id),
                await session.get(EarningsLedgerEntry, entry_id),
                await session.scalar(select(PayoutRecoveryIncident)),
                await driver_money_balance(
                    session,
                    driver_profile_id=graph.profile.id,
                    currency="NGN",
                ),
            )

    line, credit, incident, balance = asyncio.run(confirm())
    assert line.status == "void" and line.reservation_active is False
    assert credit.status == "reversed"
    assert incident.kind == "confirmed_fraud" and incident.status == "closed"
    assert balance.released_available == balance.carry_forward_debt == Decimal("0.00")
    assert balance.batch_payable == Decimal("0.00")


def test_confirmed_fraud_failed_net_reopens_as_debt_on_late_success(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-unknown-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-fraud-unknown")

    class AcceptedWithoutReceipt(FakeDisbursementAdapter):
        async def submit_batch(self, *, batch_id, instructions):
            await super().submit_batch(batch_id=batch_id, instructions=instructions)
            raise TimeoutError("provider accepted before response")

    adapter = AcceptedWithoutReceipt()

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            batch, lines, entries = await _submitted_batch(session, graph, checker, adapter)
            intent_id = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == lines[0].id
                )
            )
            return batch.id, lines[0].id, entries[0].id, intent_id

    _, line_id, entry_id, intent_id = asyncio.run(prepare())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def confirm_and_converge():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed unknown payout fraud.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
            incident_before = await session.scalar(select(PayoutRecoveryIncident))
            before_status = incident_before.status
            debt_before = int(
                await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0
            )
            workers = async_sessionmaker(session.bind, expire_on_commit=False)
            lookup = await process_payout_submission_intent(
                workers, intent_id=intent_id, adapter=adapter
            )
            line = await session.get(PayoutBatchLine, line_id)
            await _poll(
                session,
                adapter=adapter,
                line=line,
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-fraud-terminal-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=1),
            )
            await session.commit()
            failed_incident = await session.get(PayoutRecoveryIncident, incident_before.id)
            failed_line = await session.get(PayoutBatchLine, line_id)
            failed_credit = await session.get(EarningsLedgerEntry, entry_id)
            failed_debt = await session.scalar(select(PayoutDebtObligation))
            failed_account = await session.scalar(select(DriverCurrencyDebtAccount))
            failed_balance = await driver_money_balance(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
            )
            failed_snapshot = (
                failed_incident.status,
                failed_line.status,
                failed_line.reservation_active,
                failed_credit.status,
                failed_debt.outstanding_amount,
                failed_account.outstanding_amount,
                failed_balance.released_available,
                failed_balance.terminal_failed,
                failed_balance.carry_forward_debt,
                failed_balance.batch_payable,
            )
            await _poll(
                session,
                adapter=adapter,
                line=failed_line,
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"r22-fraud-late-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=2),
            )
            await session.commit()
            return (
                before_status,
                debt_before,
                lookup,
                failed_snapshot,
                await session.get(PayoutBatchLine, line_id),
                await session.get(EarningsLedgerEntry, entry_id),
                tuple(await session.scalars(select(PayoutRecoveryIncident))),
                tuple(await session.scalars(select(PayoutDebtObligation))),
                await session.scalar(select(DriverCurrencyDebtAccount)),
            )

    before, debt_before, lookup, failed, line, credit, incidents, debts, account = asyncio.run(
        confirm_and_converge()
    )
    assert before == "contingent" and debt_before == 0
    assert lookup == "resolved"
    assert failed == (
        "closed",
        "failed",
        False,
        "available",
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert line.status == "succeeded" and line.reservation_active is False
    assert credit.status == "paid"
    confirmed = next(item for item in incidents if item.kind == "confirmed_fraud")
    late_cash = next(item for item in incidents if item.kind == "duplicate_cash")
    active_debt = next(item for item in debts if item.outstanding_amount > 0)
    assert confirmed.status == "closed"
    assert late_cash.status == "debt_activated"
    assert len(incidents) == len(debts) == 2
    assert active_debt.outstanding_amount == account.outstanding_amount == Decimal("100.00")


@pytest.mark.parametrize(
    "replacement_outcome",
    ["failed", "succeeded", "old_succeeds_child_fails"],
)
def test_confirmed_fraud_converges_across_complete_replacement_chain(
    postgis_db_sessionmaker,
    replacement_outcome,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-chain-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-fraud-chain")
    adapter = FakeDisbursementAdapter()

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            original_batch, lines, entries = await _submitted_batch(
                session, graph, checker, adapter
            )
            await _poll(
                session,
                adapter=adapter,
                line=lines[0],
                reconciler_id=reconciler.id,
                outcome="failed",
                event=f"r22-chain-root-failed-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            await _add_new_bank_version(session, graph)
            replacement, children = await retry_failed_payout_lines(
                session,
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            await approve_payout_batch(
                session,
                batch_id=replacement.id,
                actor_user_id=checker.id,
            )
            await submit_payout_batch(
                session,
                batch_id=replacement.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            intent_id = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == children[0].id
                )
            )
            await session.commit()
            workers = async_sessionmaker(session.bind, expire_on_commit=False)
            assert (
                await process_payout_submission_intent(
                    workers,
                    intent_id=intent_id,
                    adapter=adapter,
                )
                == "resolved"
            )
            return lines[0].id, children[0].id, entries[0].id

    original_id, child_id, entry_id = asyncio.run(prepare())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def confirm_and_reconcile():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                now=NOW + timedelta(seconds=1),
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed across the replacement chain.",
                now=NOW + timedelta(seconds=2),
            )
            await session.commit()
            incident = await session.scalar(select(PayoutRecoveryIncident))
            assert incident.status == "contingent"
            incident_id = incident.id
            child = await session.get(PayoutBatchLine, child_id)
            provider_outcome = replacement_outcome
            if replacement_outcome == "old_succeeds_child_fails":
                original = await session.get(PayoutBatchLine, original_id)
                await _poll(
                    session,
                    adapter=adapter,
                    line=original,
                    reconciler_id=reconciler.id,
                    outcome="succeeded",
                    event=f"r22-chain-root-late-success-{uuid4().hex}",
                    occurred_at=NOW + timedelta(seconds=30),
                )
                await session.commit()
                child = await session.get(PayoutBatchLine, child_id)
                provider_outcome = "failed"
            await _poll(
                session,
                adapter=adapter,
                line=child,
                reconciler_id=reconciler.id,
                outcome=provider_outcome,
                event=f"r22-chain-child-{replacement_outcome}-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=1),
            )
            await session.commit()
            return (
                await session.get(PayoutBatchLine, original_id),
                await session.get(PayoutBatchLine, child_id),
                await session.get(EarningsLedgerEntry, entry_id),
                await session.get(PayoutRecoveryIncident, incident_id),
                await session.scalar(select(PayoutDebtObligation)),
                await session.scalar(select(DriverCurrencyDebtAccount)),
                await driver_money_balance(
                    session,
                    driver_profile_id=graph.profile.id,
                    currency="NGN",
                ),
                int(await session.scalar(select(func.count(PayoutRecoveryIncident.id))) or 0),
                int(await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0),
            )

    original, child, ledger, incident, debt, account, balance, incident_count, debt_count = (
        asyncio.run(confirm_and_reconcile())
    )
    assert original.status == (
        "succeeded" if replacement_outcome == "old_succeeds_child_fails" else "failed"
    )
    assert original.reservation_active is False
    assert child.status == (
        "failed" if replacement_outcome == "old_succeeds_child_fails" else replacement_outcome
    )
    assert child.reservation_active is False
    assert incident.exposure_line_id == child.id
    if replacement_outcome in {"succeeded", "old_succeeds_child_fails"}:
        assert ledger.status == "paid"
        assert incident.status == "debt_activated"
        assert debt.outstanding_amount == account.outstanding_amount == Decimal("100.00")
        assert balance.cash_paid == balance.carry_forward_debt == Decimal("100.00")
        assert debt_count == 1
        assert incident_count == (2 if replacement_outcome == "old_succeeds_child_fails" else 1)
    else:
        assert ledger.status == "available"
        assert incident.status == "closed"
        assert debt.outstanding_amount == account.outstanding_amount == Decimal("0.00")
        assert (
            balance.released_available
            == balance.terminal_failed
            == balance.carry_forward_debt
            == balance.batch_payable
            == Decimal("0.00")
        )
        assert incident_count == debt_count == 1


def test_confirmed_fraud_after_verified_success_activates_one_debt(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-paid-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-fraud-paid")
    adapter = FakeDisbursementAdapter()

    async def pay():
        async with postgis_db_sessionmaker() as session:
            _, lines, entries = await _submitted_batch(session, graph, checker, adapter)
            await _poll(
                session,
                adapter=adapter,
                line=lines[0],
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"r22-fraud-paid-{uuid4().hex}",
                occurred_at=NOW,
            )
            await session.commit()
            return entries[0].id

    entry_id = asyncio.run(pay())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def confirm():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed paid fraud.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()
            return (
                await session.get(EarningsLedgerEntry, entry_id),
                await session.scalar(select(PayoutRecoveryIncident)),
                await session.scalar(select(PayoutDebtObligation)),
                await session.scalar(select(DriverCurrencyDebtAccount)),
            )

    ledger, incident, debt, account = asyncio.run(confirm())
    assert ledger.status == "paid"
    assert incident.status == "debt_activated"
    assert debt.outstanding_amount == account.outstanding_amount == Decimal("100.00")


def test_confirmed_fraud_racing_verified_success_converges_once(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-race-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-fraud-race")
    adapter = FakeDisbursementAdapter()

    async def prepare():
        async with postgis_db_sessionmaker() as session:
            _, lines, entries = await _submitted_batch(session, graph, checker, adapter)
            return lines[0].id, lines[0].provider_transfer_reference, entries[0].id

    line_id, provider_reference, entry_id = asyncio.run(prepare())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def acknowledge():
        async with postgis_db_sessionmaker() as session:
            await acknowledge_fraud_flag(
                session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
            )
            await session.commit()

    asyncio.run(acknowledge())
    adapter.set_poll_result(
        provider_transfer_reference=provider_reference,
        provider_event_id=f"r22-race-success-{uuid4().hex}",
        outcome="succeeded",
        occurred_at=NOW + timedelta(seconds=2),
    )

    async def confirm():
        async with postgis_db_sessionmaker() as session:
            await resolve_fraud_flag(
                session,
                flag_id=flag.id,
                actor_user_id=graph.admin.id,
                outcome="confirmed",
                resolution_note="Confirmed while provider finality races.",
                now=NOW + timedelta(seconds=1),
            )
            await session.commit()

    async def reconcile():
        async with postgis_db_sessionmaker() as session:
            await poll_payout_line(
                session,
                line_id=line_id,
                actor_user_id=reconciler.id,
                adapter=adapter,
            )
            await session.commit()

    async def race():
        await asyncio.wait_for(asyncio.gather(confirm(), reconcile()), timeout=10)
        async with postgis_db_sessionmaker() as session:
            return (
                await session.get(PayoutBatchLine, line_id),
                await session.get(EarningsLedgerEntry, entry_id),
                tuple(await session.scalars(select(PayoutRecoveryIncident))),
                tuple(await session.scalars(select(PayoutDebtObligation))),
                await session.scalar(select(DriverCurrencyDebtAccount)),
            )

    line, ledger, incidents, debts, account = asyncio.run(race())
    assert line.status == "succeeded" and ledger.status == "paid"
    assert len(incidents) == len(debts) == 1
    assert incidents[0].status == "debt_activated"
    assert debts[0].outstanding_amount == account.outstanding_amount == Decimal("100.00")


def test_confirmed_fraud_recovery_failure_rolls_back_every_money_state(
    postgis_db_sessionmaker,
    monkeypatch,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-fraud-rollback-{uuid4().hex[:8]}")

    async def reserve():
        async with postgis_db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await session.commit()
            return entry.id, lines[0].id

    entry_id, line_id = asyncio.run(reserve())
    flag = create_flag(postgis_db_sessionmaker, graph)

    async def fail_settlement(*_args, **_kwargs):
        raise RuntimeError("injected recovery failure")

    monkeypatch.setattr(
        disbursement_service,
        "settle_recovery_incident_from_credit",
        fail_settlement,
    )

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            with pytest.raises(RuntimeError, match="injected recovery failure"):
                await acknowledge_fraud_flag(
                    session, flag_id=flag.id, actor_user_id=graph.admin.id, now=NOW
                )
                await resolve_fraud_flag(
                    session,
                    flag_id=flag.id,
                    actor_user_id=graph.admin.id,
                    outcome="confirmed",
                    resolution_note="Rollback this confirmation.",
                    now=NOW + timedelta(seconds=1),
                )
            await session.rollback()
        async with postgis_db_sessionmaker() as session:
            return (
                await session.get(type(flag), flag.id),
                await session.get(PayoutBatchLine, line_id),
                await session.get(EarningsLedgerEntry, entry_id),
                int(await session.scalar(select(func.count(PayoutRecoveryIncident.id))) or 0),
                int(await session.scalar(select(func.count(PayoutDebtObligation.id))) or 0),
                int(
                    await session.scalar(
                        select(func.count(EarningsLedgerEntry.id)).where(
                            EarningsLedgerEntry.source_fraud_flag_id == flag.id
                        )
                    )
                    or 0
                ),
            )

    persisted_flag, line, credit, incidents, debts, reversals = asyncio.run(exercise())
    assert persisted_flag.status == "open"
    assert line.status == "reserved" and line.reservation_active is True
    assert credit.status == "available"
    assert incidents == debts == reversals == 0


def test_0084_migration_guards_round_trip_and_owned_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def inspect_and_seed() -> list:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                diffs = await connection.run_sync(
                    lambda sync_connection: compare_metadata(
                        MigrationContext.configure(
                            sync_connection,
                            opts={"compare_type": False, "compare_server_default": False},
                        ),
                        Base.metadata,
                    )
                )
            owned = [
                diff
                for diff in diffs
                if any(
                    name in repr(diff)
                    for name in (
                        "payout_batch_lines",
                        "payout_submission_intents",
                        "payout_recovery_incidents",
                        "payout_debt_obligations",
                    )
                )
            ]
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL session_replication_role = replica"))
                await connection.execute(
                    text(
                        "INSERT INTO payout_batches "
                        "(id, status, currency, total_amount, instruction_set_fingerprint, "
                        "created_by_user_id) VALUES "
                        "('84000000-0000-0000-0000-000000000001', 'reserved', 'NGN', 1, "
                        "repeat('a', 64), '84000000-0000-0000-0000-000000000002')"
                    )
                )
                for line_id, predecessor, status, reference, active in (
                    (
                        "84000000-0000-0000-0000-000000000003",
                        "NULL",
                        "failed",
                        "'legacy-r22-root'",
                        "false",
                    ),
                    (
                        "84000000-0000-0000-0000-000000000004",
                        "'84000000-0000-0000-0000-000000000003'",
                        "reserved",
                        "NULL",
                        "true",
                    ),
                ):
                    await connection.execute(
                        text(
                            "INSERT INTO payout_batch_lines "
                            "(id, batch_id, ledger_entry_id, predecessor_line_id, "
                            "payee_version_id, bank_account_version_id, amount, currency, "
                            "instruction, instruction_fingerprint, idempotency_key, status, "
                            "provider_transfer_reference, reservation_active) VALUES "
                            f"('{line_id}', '84000000-0000-0000-0000-000000000001', "
                            "'84000000-0000-0000-0000-000000000005', "
                            f"{predecessor}, "
                            "'84000000-0000-0000-0000-000000000006', "
                            "'84000000-0000-0000-0000-000000000007', 1, 'NGN', "
                            "'{}'::jsonb, repeat('b', 64), "
                            f"repeat('{line_id[-1]}', 64), '{status}', {reference}, {active})"
                        )
                    )
                await connection.execute(
                    text(
                        "INSERT INTO payout_recovery_incidents "
                        "(id, ledger_entry_id, chain_root_line_id, exposure_line_id, "
                        "created_by_user_id, kind, status, amount, currency, dedupe_key) "
                        "VALUES ('84000000-0000-0000-0000-000000000008', "
                        "'84000000-0000-0000-0000-000000000005', "
                        "'84000000-0000-0000-0000-000000000003', "
                        "'84000000-0000-0000-0000-000000000004', "
                        "'84000000-0000-0000-0000-000000000002', "
                        "'duplicate_cash', 'contingent', 1, 'NGN', repeat('8', 64))"
                    )
                )
            with pytest.raises(DBAPIError, match="identity is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payout_batch_lines SET amount = 2 "
                            "WHERE id = '84000000-0000-0000-0000-000000000003'"
                        )
                    )
            with pytest.raises(DBAPIError, match="state transition is invalid"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payout_batch_lines "
                            "SET status = 'reserved', reservation_active = true "
                            "WHERE id = '84000000-0000-0000-0000-000000000003'"
                        )
                    )
            with pytest.raises(DBAPIError, match="reference is immutable"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "UPDATE payout_batch_lines "
                            "SET provider_transfer_reference = 'rewritten' "
                            "WHERE id = '84000000-0000-0000-0000-000000000003'"
                        )
                    )
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "DELETE FROM payout_recovery_incidents "
                            "WHERE id = '84000000-0000-0000-0000-000000000008'"
                        )
                    )
            return owned
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "head", monkeypatch)
        downgrade_to(migration_url, "0083_payout_submission_intents", monkeypatch)
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(inspect_and_seed()) == []
        with pytest.raises(RuntimeError, match="0084 downgrade blocked"):
            downgrade_to(migration_url, "0083_payout_submission_intents", monkeypatch)
    finally:
        asyncio.run(drop_database(migration_url))
