import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_mny03a_earnings_release import build_graph
from test_payout_reconciliation import _admins, _submitted_batch

import app.services.disbursements as disbursement_service
from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import FakeDisbursementAdapter
from app.db.base import Base
from app.models.disbursement import (
    PayoutAutomaticAlert,
    PayoutBatchLine,
    PayoutSubmissionIntent,
)
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion
from app.models.payout import EarningsLedgerEntry
from app.services.disbursements import (
    approve_payout_batch,
    poll_payout_line,
    process_payout_submission_intent,
    retry_failed_payout_lines,
    submit_payout_batch,
)
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
)
from app.services.payout_balances import driver_money_balance
from tests.database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def replacement_crypto_matches_synthetic_bank_capture(monkeypatch):
    settings = disbursement_service.get_settings().model_copy(
        update={
            "payout_crypto_keyring_b64": SecretStr(
                json.dumps({"1": base64.b64encode(b"e" * 32).decode()})
            ),
            "payout_crypto_key_version": 1,
        }
    )
    monkeypatch.setattr(disbursement_service, "get_settings", lambda: settings)


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
        reason="Focused staff payout action",
        line_id=line.id,
        actor_user_id=reconciler_id,
        adapter=adapter,
    )


async def _add_new_bank_version(session, graph) -> None:
    payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.profile.id))
    current_version = await session.scalar(
        select(func.max(PayeeBankAccountVersion.version))
        .join(PayeeBankAccount, PayeeBankAccount.id == PayeeBankAccountVersion.bank_account_id)
        .where(PayeeBankAccount.payee_id == payee.id)
    )
    await add_verified_bank_account_version(
        session,
        payee_id=payee.id,
        details=VerifiedBankAccountDetails(
            account_name="Ada Replacement",
            account_number=f"{9_876_543_209 + current_version:010d}",
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
                reason="Focused staff payout action",
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            replay, replay_lines = await retry_failed_payout_lines(
                session,
                reason="Focused staff payout action",
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
                reason="Focused staff payout action",
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
def test_late_old_success_cancels_safe_replacement_without_extra_cash(
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
                reason="Focused staff payout action",
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            child = children[0]
            if replacement_outcome in {"not_found", "failed"}:
                await approve_payout_batch(
                    session,
                    reason="Focused staff payout action",
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
                replacement.id,
            )

    original, child, ledger, _ = asyncio.run(exercise())
    assert original.status == "succeeded" and original.reservation_active is False
    assert child.status == ("failed" if replacement_outcome == "failed" else "void")
    assert child.reservation_active is False
    assert ledger.status == "paid"


@pytest.mark.parametrize("amount", ["100.00", "600000000000.00"])
def test_two_verified_successes_preserve_actual_cash_and_raise_one_alert(
    postgis_db_sessionmaker,
    amount,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"r22-late-dup-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "r22-late-dup")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            original_batch, lines, entries = await _submitted_batch(
                session, graph, checker, adapter, amount=amount
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
                reason="Focused staff payout action",
                batch_id=original_batch.id,
                actor_user_id=graph.admin.id,
                adapter=adapter,
            )
            await approve_payout_batch(
                session,
                reason="Focused staff payout action",
                batch_id=replacement.id,
                actor_user_id=checker.id,
            )
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
                await driver_money_balance(
                    session, driver_profile_id=graph.profile.id, currency="NGN"
                ),
                list(
                    await session.scalars(
                        select(PayoutAutomaticAlert).where(
                            PayoutAutomaticAlert.kind == "duplicate_payment"
                        )
                    )
                ),
            )

    original, child, ledger, balance, alerts = asyncio.run(exercise())
    assert original.status == child.status == "succeeded"
    assert original.reservation_active is child.reservation_active is False
    assert ledger.status == "paid"
    assert balance.cash_paid == Decimal(amount) * 2
    assert balance.earned_net == Decimal(amount)
    assert balance.batch_payable == 0
    assert len(alerts) == 1
    assert alerts[0].amount == Decimal(amount)
    assert alerts[0].detail["total_verified_cash"] == str(Decimal(amount) * 2)


def test_current_database_guards_and_owned_drift(monkeypatch) -> None:
    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))

    async def inspect_and_seed() -> None:
        engine = create_async_engine(migration_url, poolclass=NullPool)
        try:
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
        finally:
            await engine.dispose()

    async def compare_owned() -> list:
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
            return [
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
        finally:
            await engine.dispose()

    try:
        upgrade_to(migration_url, "0106_development_baseline", monkeypatch)
        upgrade_to(migration_url, "0106_development_baseline", monkeypatch)
        asyncio.run(inspect_and_seed())
        upgrade_to(migration_url, "head", monkeypatch)
        assert asyncio.run(compare_owned()) == []
    finally:
        asyncio.run(drop_database(migration_url))
