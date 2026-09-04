import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, update

from app.adapters.disbursement import (
    FakeDisbursementAdapter,
    ProviderLookup,
    ProviderLookupStatus,
    ProviderSubmission,
)
from app.jobs.disbursements import sweep_disbursement_intents
from app.models.disbursement import (
    PayoutBatch,
    PayoutBatchLine,
    PayoutSubmissionAttempt,
    PayoutSubmissionIntent,
    PayoutSubmissionObservation,
)
from app.models.payout import EarningsLedgerEntry
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    process_payout_submission_intent,
    reserve_payout_batch,
    submit_payout_batch,
)
from tests.test_mny03a_earnings_release import build_graph
from tests.test_payout_batches import _seed_authority


async def _prepare_batch(sessionmaker, graph, adapter, *, line_count: int = 1):
    checker = type(graph.admin)(
        email=f"intent-checker-{uuid4().hex}@example.com",
        password_hash=graph.admin.password_hash,
        full_name="Intent Checker",
        role="admin",
        status="active",
    )
    async with sessionmaker() as session:
        session.add(checker)
        await session.flush()
        entries = [await _seed_authority(session, graph)]
        for index in range(1, line_count):
            entry = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="adjustment",
                status="available",
                amount=Decimal(100 + index),
                currency="NGN",
                occurred_at=graph.trip.ended_at,
                ledger_metadata={},
            )
            session.add(entry)
            entries.append(entry)
        await session.flush()
        batch = await create_payout_batch_draft(
            session, currency="NGN", actor_user_id=graph.admin.id
        )
        _, lines = await reserve_payout_batch(
            session,
            batch_id=batch.id,
            ledger_entry_ids=tuple(entry.id for entry in entries),
            actor_user_id=graph.admin.id,
        )
        await approve_payout_batch(
            session, batch_id=batch.id, actor_user_id=checker.id
        )
        await submit_payout_batch(
            session,
            batch_id=batch.id,
            actor_user_id=graph.admin.id,
            adapter=adapter,
        )
        intent_ids = tuple(
            await session.scalars(
                select(PayoutSubmissionIntent.id)
                .where(
                    PayoutSubmissionIntent.payout_batch_line_id.in_(
                        [line.id for line in lines]
                    )
                )
                .order_by(PayoutSubmissionIntent.payout_batch_line_id)
            )
        )
        await session.commit()
        return batch.id, tuple(line.id for line in lines), intent_ids


def test_committed_intent_is_processed_once_and_resolved_line_never_replays(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"intent-once-{uuid4().hex[:8]}")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        batch_id, line_ids, intent_ids = await _prepare_batch(
            db_sessionmaker, graph, adapter
        )
        ctx = {"sessionmaker": db_sessionmaker, "disbursement_adapter": adapter}
        first = await sweep_disbursement_intents(ctx)
        second = await sweep_disbursement_intents(ctx)
        async with db_sessionmaker() as session:
            batch = await session.get(PayoutBatch, batch_id)
            line = await session.get(PayoutBatchLine, line_ids[0])
            intent = await session.get(PayoutSubmissionIntent, intent_ids[0])
            attempts = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionAttempt.id)).where(
                        PayoutSubmissionAttempt.intent_id == intent_ids[0]
                    )
                )
                or 0
            )
            observations = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionObservation.id)).where(
                        PayoutSubmissionObservation.intent_id == intent_ids[0]
                    )
                )
                or 0
            )
            return first, second, batch, line, intent, attempts, observations

    first, second, batch, line, intent, attempts, observations = asyncio.run(exercise())
    assert first == {"selected": 1, "processed": 1, "failed": 0}
    assert second == {"selected": 0, "processed": 0, "failed": 0}
    assert len(adapter.calls) == 1
    assert batch.status == "submitted"
    assert line.status == "submitted"
    assert intent.state == "resolved"
    assert attempts == observations == 1


def test_accepted_without_receipt_enters_query_only_and_unknown_never_resubmits(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"intent-unknown-{uuid4().hex[:8]}")

    class AcceptedWithoutReceipt(FakeDisbursementAdapter):
        async def submit_batch(self, *, batch_id, instructions):
            await super().submit_batch(batch_id=batch_id, instructions=instructions)
            raise TimeoutError("provider accepted before the connection timed out")

    adapter = AcceptedWithoutReceipt()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(db_sessionmaker, graph, adapter)
        intent_id = intent_ids[0]
        async with db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            adapter.set_lookup_result(
                idempotency_key=intent.idempotency_key,
                result=ProviderLookup(status=ProviderLookupStatus.UNKNOWN),
            )
        states = [
            await process_payout_submission_intent(
                db_sessionmaker, intent_id=intent_id, adapter=adapter
            )
        ]
        states.append(
            await process_payout_submission_intent(
                db_sessionmaker, intent_id=intent_id, adapter=adapter
            )
        )
        del adapter.lookup_results[next(iter(adapter.lookup_results))]
        states.append(
            await process_payout_submission_intent(
                db_sessionmaker, intent_id=intent_id, adapter=adapter
            )
        )
        async with db_sessionmaker() as session:
            intent = await session.get(PayoutSubmissionIntent, intent_id)
            actions = tuple(
                await session.scalars(
                    select(PayoutSubmissionAttempt.action)
                    .where(PayoutSubmissionAttempt.intent_id == intent_id)
                    .order_by(PayoutSubmissionAttempt.generation)
                )
            )
            outcomes = tuple(
                await session.scalars(
                    select(PayoutSubmissionObservation.outcome)
                    .where(PayoutSubmissionObservation.intent_id == intent_id)
                    .order_by(PayoutSubmissionObservation.generation)
                )
            )
            return states, intent, actions, outcomes

    states, intent, actions, outcomes = asyncio.run(exercise())
    assert states == ["query_only", "query_only", "resolved"]
    assert len(adapter.calls) == 1
    assert intent.state == "resolved"
    assert actions == ("submit", "query", "query")
    assert outcomes == ("unknown", "unknown", "found")


def test_unknown_intents_rotate_so_later_pending_lines_are_not_starved(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"intent-fair-{uuid4().hex[:8]}")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        _, _, intent_ids = await _prepare_batch(
            db_sessionmaker, graph, adapter, line_count=101
        )
        ordered_ids = tuple(sorted(intent_ids))
        old = datetime(2020, 1, 1, tzinfo=UTC)
        async with db_sessionmaker() as session:
            unknown_intents = tuple(
                await session.scalars(
                    select(PayoutSubmissionIntent).where(
                        PayoutSubmissionIntent.id.in_(ordered_ids[:100])
                    )
                )
            )
            for intent in unknown_intents:
                adapter.set_lookup_result(
                    idempotency_key=intent.idempotency_key,
                    result=ProviderLookup(status=ProviderLookupStatus.UNKNOWN),
                )
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id.in_(ordered_ids[:100]))
                .values(state="query_only", updated_at=old)
            )
            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == ordered_ids[100])
                .values(updated_at=old)
            )
            await session.commit()
        ctx = {"sessionmaker": db_sessionmaker, "disbursement_adapter": adapter}
        first = await sweep_disbursement_intents(ctx)
        second = await sweep_disbursement_intents(ctx)
        async with db_sessionmaker() as session:
            pending_tail = await session.get(PayoutSubmissionIntent, ordered_ids[100])
            return first, second, pending_tail

    first, second, pending_tail = asyncio.run(exercise())
    assert first == {"selected": 100, "processed": 100, "failed": 0}
    assert second == {"selected": 100, "processed": 100, "failed": 0}
    assert pending_tail.state == "resolved"
    assert len(adapter.calls) == 1


def test_partial_batch_progress_is_per_line_and_duplicate_reference_never_replays(
    db_sessionmaker,
) -> None:
    graph = build_graph(db_sessionmaker, f"intent-partial-{uuid4().hex[:8]}")
    duplicate_reference = f"same-provider-reference-{uuid4().hex}"

    class DuplicateReferenceAdapter(FakeDisbursementAdapter):
        async def submit_batch(self, *, batch_id, instructions):
            self.calls.append((batch_id, instructions))
            return ProviderSubmission(
                provider_reference=f"provider-submission-{batch_id}",
                line_references={instructions[0].line_id: duplicate_reference},
            )

        async def lookup_line(self, *, idempotency_key, instruction_fingerprint):
            del idempotency_key, instruction_fingerprint
            return ProviderLookup(
                status=ProviderLookupStatus.FOUND,
                provider_submission_reference="provider-submission-duplicate",
                provider_transfer_reference=duplicate_reference,
            )

    adapter = DuplicateReferenceAdapter()

    async def exercise():
        batch_id, line_ids, intent_ids = await _prepare_batch(
            db_sessionmaker, graph, adapter, line_count=2
        )
        outcomes = []
        for intent_id in intent_ids:
            outcomes.append(
                await process_payout_submission_intent(
                    db_sessionmaker, intent_id=intent_id, adapter=adapter
                )
            )
        outcomes.append(
            await process_payout_submission_intent(
                db_sessionmaker, intent_id=intent_ids[1], adapter=adapter
            )
        )
        async with db_sessionmaker() as session:
            batch = await session.get(PayoutBatch, batch_id)
            lines = tuple(
                await session.scalars(
                    select(PayoutBatchLine)
                    .where(PayoutBatchLine.id.in_(line_ids))
                    .order_by(PayoutBatchLine.id)
                )
            )
            intents = tuple(
                await session.scalars(
                    select(PayoutSubmissionIntent)
                    .where(PayoutSubmissionIntent.id.in_(intent_ids))
                    .order_by(PayoutSubmissionIntent.payout_batch_line_id)
                )
            )
            duplicate_errors = int(
                await session.scalar(
                    select(func.count(PayoutSubmissionObservation.id)).where(
                        PayoutSubmissionObservation.error_code
                        == "provider_transfer_reference_duplicate"
                    )
                )
                or 0
            )
            ledger_statuses = tuple(
                await session.scalars(
                    select(EarningsLedgerEntry.status)
                    .where(
                        EarningsLedgerEntry.id.in_([line.ledger_entry_id for line in lines])
                    )
                    .order_by(EarningsLedgerEntry.id)
                )
            )
            return outcomes, batch, lines, intents, duplicate_errors, ledger_statuses

    outcomes, batch, lines, intents, duplicate_errors, ledger_statuses = asyncio.run(
        exercise()
    )
    assert outcomes == ["resolved", "query_only", "query_only"]
    assert len(adapter.calls) == 2
    assert batch.status == "submitted"
    assert [line.status for line in lines] == ["submitted", "reserved"]
    assert [intent.state for intent in intents] == ["resolved", "query_only"]
    assert duplicate_errors == 2
    assert ledger_statuses == ("available", "available")
    assert batch.total_amount == Decimal("201.00")
