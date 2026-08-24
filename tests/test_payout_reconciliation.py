import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import create_test_user
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.adapters.disbursement import (
    FakeDisbursementAdapter,
    ProviderSubmission,
)
from app.core.errors import AppError
from app.models.disbursement import (
    PayoutBatch,
    PayoutBatchLine,
    PayoutLineReconciliationEvent,
)
from app.models.payout import EarningsLedgerEntry
from app.models.user import UserRole
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    poll_payout_line,
    reconcile_payout_webhook,
    reserve_payout_batch,
    retry_failed_payout_lines,
    submit_payout_batch,
    void_payout_batch,
)


def _admins(db_sessionmaker, tag: str):
    checker = create_test_user(
        db_sessionmaker,
        email=f"reconcile-checker-{tag}-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    reconciler = create_test_user(
        db_sessionmaker,
        email=f"reconcile-worker-{tag}-{uuid4().hex}@example.com",
        role=UserRole.ADMIN,
    )
    return checker, reconciler


async def _submitted_batch(session, graph, checker, fake, *, line_count=1):
    entries = [
        await _seed_authority(session, graph, amount=str(100 + index))
        for index in range(line_count)
    ]
    batch = await create_payout_batch_draft(session, currency="NGN", actor_user_id=graph.admin.id)
    batch, lines = await reserve_payout_batch(
        session,
        batch_id=batch.id,
        ledger_entry_ids=tuple(entry.id for entry in entries),
        actor_user_id=graph.admin.id,
    )
    await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
    batch, lines = await submit_payout_batch(
        session,
        batch_id=batch.id,
        actor_user_id=graph.admin.id,
        adapter=fake,
    )
    return batch, lines, entries


def test_line_level_partial_reconciliation_retry_and_paid_finality(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"partial-{uuid4().hex[:8]}")
    checker, reconciler = _admins(db_sessionmaker, "partial")
    fake = FakeDisbursementAdapter()
    now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)

    async def exercise():
        async with db_sessionmaker() as session:
            batch, lines, _entries = await _submitted_batch(
                session, graph, checker, fake, line_count=2
            )
            first, second = lines
            success_payload = json.dumps(
                {
                    "provider_transfer_reference": first.provider_transfer_reference,
                    "provider_event_id": "evt-success-first",
                    "outcome": "succeeded",
                    "occurred_at": now.isoformat(),
                },
                sort_keys=True,
            ).encode()
            await reconcile_payout_webhook(
                session,
                payload=success_payload,
                signature=fake.sign_webhook(success_payload),
                adapter=fake,
            )
            await session.flush()
            first_ledger = await session.get(EarningsLedgerEntry, first.ledger_entry_id)
            second_ledger = await session.get(EarningsLedgerEntry, second.ledger_entry_id)
            assert first_ledger.status == "paid"
            assert second_ledger.status == "available"
            assert batch.status == "submitted"

            fake.set_poll_result(
                provider_transfer_reference=second.provider_transfer_reference,
                provider_event_id="evt-failed-second",
                outcome="failed",
                occurred_at=now,
            )
            with pytest.raises(AppError) as maker_denied:
                await poll_payout_line(
                    session,
                    line_id=second.id,
                    actor_user_id=graph.admin.id,
                    adapter=fake,
                )
            assert maker_denied.value.code == "PAYOUT_RECONCILER_SEPARATION_REQUIRED"
            assert fake.poll_calls == []
            await poll_payout_line(
                session,
                line_id=second.id,
                actor_user_id=reconciler.id,
                adapter=fake,
            )
            assert batch.status == "reconciled"
            assert fake.poll_calls == [second.provider_transfer_reference]
            assert second.status == "failed"
            assert second_ledger.status == "available"
            frozen_retry = (second.idempotency_key, second.provider_transfer_reference)
            await retry_failed_payout_lines(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
            )
            assert second.status == "submitted"
            assert (second.idempotency_key, second.provider_transfer_reference) == frozen_retry
            fake.set_poll_result(
                provider_transfer_reference=second.provider_transfer_reference,
                provider_event_id="evt-success-second",
                outcome="succeeded",
                occurred_at=now + timedelta(minutes=1),
            )
            await poll_payout_line(
                session,
                line_id=second.id,
                actor_user_id=reconciler.id,
                adapter=fake,
            )
            await session.commit()
            return (
                batch.id,
                first.id,
                second.id,
                first.ledger_entry_id,
                second.ledger_entry_id,
            )

    batch_id, first_id, second_id, first_entry_id, second_entry_id = asyncio.run(exercise())

    async def verify():
        async with db_sessionmaker() as session:
            batch = await session.get(PayoutBatch, batch_id)
            lines = [
                await session.get(PayoutBatchLine, first_id),
                await session.get(PayoutBatchLine, second_id),
            ]
            ledgers = [
                await session.get(EarningsLedgerEntry, first_entry_id),
                await session.get(EarningsLedgerEntry, second_entry_id),
            ]
            events = int(
                await session.scalar(select(func.count(PayoutLineReconciliationEvent.id))) or 0
            )
            return batch, lines, ledgers, events

    batch, lines, ledgers, event_count = asyncio.run(verify())
    assert batch.status == "completed"
    assert [line.status for line in lines] == ["succeeded", "succeeded"]
    assert [ledger.status for ledger in ledgers] == ["paid", "paid"]
    assert event_count == 3


def test_signed_webhook_duplicate_reordered_and_forged_evidence(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"webhook-{uuid4().hex[:8]}")
    checker, reconciler = _admins(db_sessionmaker, "webhook")
    fake = FakeDisbursementAdapter()
    now = datetime(2026, 8, 23, 11, 0, tzinfo=UTC)

    async def exercise():
        async with db_sessionmaker() as session:
            batch, lines, _entries = await _submitted_batch(session, graph, checker, fake)
            line = lines[0]
            success_payload = json.dumps(
                {
                    "provider_transfer_reference": line.provider_transfer_reference,
                    "provider_event_id": "webhook-success",
                    "outcome": "succeeded",
                    "occurred_at": now.isoformat(),
                },
                sort_keys=True,
            ).encode()
            with pytest.raises(AppError) as forged:
                await reconcile_payout_webhook(
                    session,
                    payload=success_payload,
                    signature="forged",
                    adapter=fake,
                )
            assert forged.value.code == "DISBURSEMENT_WEBHOOK_INVALID"
            first = await reconcile_payout_webhook(
                session,
                payload=success_payload,
                signature=fake.sign_webhook(success_payload),
                adapter=fake,
            )
            duplicate = await reconcile_payout_webhook(
                session,
                payload=success_payload,
                signature=fake.sign_webhook(success_payload),
                adapter=fake,
            )
            fake.set_poll_result(
                provider_transfer_reference=line.provider_transfer_reference,
                provider_event_id="older-failure",
                outcome="failed",
                occurred_at=now - timedelta(minutes=1),
            )
            _, _, ignored = await poll_payout_line(
                session,
                line_id=line.id,
                actor_user_id=reconciler.id,
                adapter=fake,
            )
            await session.commit()
            ledger = await session.get(EarningsLedgerEntry, line.ledger_entry_id)
            return batch, line, ledger, first[2].id, duplicate[2].id, ignored.applied

    batch, line, ledger, first_event, duplicate_event, ignored_applied = asyncio.run(exercise())
    assert batch.status == "completed"
    assert line.status == "succeeded"
    assert ledger.status == "paid"
    assert first_event == duplicate_event
    assert ignored_applied is False


def test_provider_must_return_one_unique_reference_per_line(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"duplicate-ref-{uuid4().hex[:8]}")
    checker, _ = _admins(db_sessionmaker, "duplicate-ref")

    class DuplicateReferenceAdapter(FakeDisbursementAdapter):
        async def submit_batch(self, *, batch_id, instructions):
            return ProviderSubmission(
                provider_reference=f"duplicate-batch-{batch_id}",
                line_references={
                    instruction.line_id: "same-provider-reference" for instruction in instructions
                },
            )

    async def exercise():
        async with db_sessionmaker() as session:
            entries = [await _seed_authority(session, graph) for _ in range(2)]
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            _, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=tuple(entry.id for entry in entries),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            with pytest.raises(AppError) as invalid:
                await submit_payout_batch(
                    session,
                    batch_id=batch.id,
                    actor_user_id=graph.admin.id,
                    adapter=DuplicateReferenceAdapter(),
                )
            assert invalid.value.code == "DISBURSEMENT_PROVIDER_RESPONSE_INVALID"
            return lines

    lines = asyncio.run(exercise())
    assert all(line.status == "reserved" for line in lines)
    assert all(line.provider_transfer_reference is None for line in lines)


def test_void_releases_only_pre_provider_reservations(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"void-{uuid4().hex[:8]}")
    checker, _ = _admins(db_sessionmaker, "void")
    fake = FakeDisbursementAdapter()

    async def exercise():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await void_payout_batch(session, batch_id=batch.id, actor_user_id=graph.admin.id)
            replacement = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await reserve_payout_batch(
                session,
                batch_id=replacement.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(session, batch_id=replacement.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session,
                batch_id=replacement.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
            )
            with pytest.raises(AppError) as unsafe:
                await void_payout_batch(
                    session, batch_id=replacement.id, actor_user_id=graph.admin.id
                )
            assert unsafe.value.code == "PAYOUT_BATCH_VOID_UNSAFE"
            await session.commit()
            return batch, lines[0], entry

    batch, line, entry = asyncio.run(exercise())
    assert batch.status == "void"
    assert line.status == "void"
    assert line.reservation_active is False
    assert entry.status == "available"


def test_postgres_submit_and_void_serialize_to_one_safe_winner(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"void-race-{uuid4().hex[:8]}")
    checker, _ = _admins(postgis_db_sessionmaker, "void-race")
    fake = FakeDisbursementAdapter()

    async def exercise():
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
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            await session.commit()

        async def submit():
            async with postgis_db_sessionmaker() as session:
                try:
                    await submit_payout_batch(
                        session,
                        batch_id=batch.id,
                        actor_user_id=graph.admin.id,
                        adapter=fake,
                    )
                    await session.commit()
                    return "submitted"
                except AppError as exc:
                    return exc.code

        async def void():
            async with postgis_db_sessionmaker() as session:
                try:
                    await void_payout_batch(
                        session, batch_id=batch.id, actor_user_id=graph.admin.id
                    )
                    await session.commit()
                    return "voided"
                except AppError as exc:
                    return exc.code

        outcomes = await asyncio.gather(submit(), void())
        async with postgis_db_sessionmaker() as session:
            stored_batch = await session.get(PayoutBatch, batch.id)
            stored_line = await session.get(PayoutBatchLine, lines[0].id)
            stored_ledger = await session.get(EarningsLedgerEntry, entry.id)
            return outcomes, stored_batch, stored_line, stored_ledger

    outcomes, batch, line, ledger = asyncio.run(exercise())
    assert sum(result in {"submitted", "voided"} for result in outcomes) == 1
    assert ledger.status == "available"
    if batch.status == "void":
        assert line.status == "void"
        assert line.reservation_active is False
        assert line.provider_transfer_reference is None
    else:
        assert batch.status == "submitted"
        assert line.status == "submitted"
        assert line.reservation_active is True
        assert line.provider_transfer_reference is not None


def test_postgres_webhook_and_poll_converge_to_one_paid_transition(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"reconcile-race-{uuid4().hex[:8]}")
    checker, reconciler = _admins(postgis_db_sessionmaker, "reconcile-race")
    fake = FakeDisbursementAdapter()
    occurred_at = datetime(2026, 8, 23, 13, 0, tzinfo=UTC)

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            batch, lines, entries = await _submitted_batch(session, graph, checker, fake)
            batch_id = batch.id
            line_id = lines[0].id
            ledger_entry_id = entries[0].id
            provider_reference = lines[0].provider_transfer_reference
            await session.commit()

        payload = json.dumps(
            {
                "provider_transfer_reference": provider_reference,
                "provider_event_id": "race-webhook-success",
                "outcome": "succeeded",
                "occurred_at": occurred_at.isoformat(),
            },
            sort_keys=True,
        ).encode()
        fake.set_poll_result(
            provider_transfer_reference=provider_reference,
            provider_event_id="race-poll-success",
            outcome="succeeded",
            occurred_at=occurred_at,
        )

        async def webhook():
            async with postgis_db_sessionmaker() as session:
                await reconcile_payout_webhook(
                    session,
                    payload=payload,
                    signature=fake.sign_webhook(payload),
                    adapter=fake,
                )
                await session.commit()
                return "webhook"

        async def poll():
            async with postgis_db_sessionmaker() as session:
                await poll_payout_line(
                    session,
                    line_id=line_id,
                    actor_user_id=reconciler.id,
                    adapter=fake,
                )
                await session.commit()
                return "poll"

        outcomes = await asyncio.gather(webhook(), poll())
        async with postgis_db_sessionmaker() as session:
            stored_batch = await session.get(PayoutBatch, batch_id)
            stored_line = await session.get(PayoutBatchLine, line_id)
            stored_ledger = await session.get(EarningsLedgerEntry, ledger_entry_id)
            events = tuple(
                (
                    await session.scalars(
                        select(PayoutLineReconciliationEvent).where(
                            PayoutLineReconciliationEvent.line_id == line_id
                        )
                    )
                ).all()
            )
            return outcomes, stored_batch, stored_line, stored_ledger, events

    outcomes, batch, line, ledger, events = asyncio.run(exercise())
    assert set(outcomes) == {"webhook", "poll"}
    assert batch.status == "completed"
    assert line.status == "succeeded"
    assert ledger.status == "paid"
    assert len(events) == 2
    assert sum(event.applied for event in events) == 1
