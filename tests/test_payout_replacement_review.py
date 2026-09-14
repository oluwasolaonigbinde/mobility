import asyncio
import base64
import json
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority
from test_payout_reconciliation import _admins, _submitted_batch
from test_r22_conservation_postgresql import NOW, _add_new_bank_version, _poll

import app.services.disbursements as disbursements
from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import FakeDisbursementAdapter
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.disbursement import PayoutBatch, PayoutBatchLine, PayoutSubmissionIntent
from app.models.fraud_assessment import FraudAssessment
from app.models.payee import Payee, PayeeBankAccountVersion
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    read_verified_bank_account,
    rewrap_bank_account,
)
from app.services.payout_operations import campaign_money_position


@pytest.fixture(autouse=True)
def configured_synthetic_crypto(monkeypatch):
    settings = disbursements.get_settings().model_copy(
        update={
            "payout_crypto_keyring_b64": SecretStr(
                json.dumps(
                    {
                        "1": base64.b64encode(b"e" * 32).decode(),
                        "2": base64.b64encode(b"f" * 32).decode(),
                    }
                )
            ),
            "payout_crypto_key_version": 2,
        }
    )
    monkeypatch.setattr(disbursements, "get_settings", lambda: settings)


async def _fail(session, graph, checker, reconciler, adapter):
    batch, lines, entries = await _submitted_batch(session, graph, checker, adapter)
    await _poll(
        session,
        adapter=adapter,
        line=lines[0],
        reconciler_id=reconciler.id,
        outcome="failed",
        event=f"review-fail-{uuid4().hex}",
        occurred_at=NOW,
    )
    await session.commit()
    return batch, lines[0], entries[0]


@pytest.mark.parametrize("recapture", ["rewrap", "identical_details", "name_only"])
def test_terminal_failure_rejects_semantically_unchanged_destination(
    postgis_db_sessionmaker, recapture
):
    sessions = postgis_db_sessionmaker
    graph = build_graph(sessions, f"review-identity-{uuid4().hex[:8]}")
    checker, reconciler = _admins(sessions, "review-identity")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with sessions() as session:
            batch, original, _ = await _fail(session, graph, checker, reconciler, adapter)
            if recapture == "rewrap":
                bank = await session.get(PayeeBankAccountVersion, original.bank_account_version_id)
                await rewrap_bank_account(
                    session,
                    bank_account_id=bank.bank_account_id,
                    actor_user_id=graph.admin.id,
                    crypto=EnvelopeCryptoProvider(
                        keys={1: b"e" * 32, 2: b"f" * 32}, active_key_version=2
                    ),
                )
            elif recapture == "identical_details":
                await _seed_authority(session, graph, amount="1.00")
            else:
                payee = await session.scalar(
                    select(Payee).where(Payee.subject_id == graph.profile.id)
                )
                await add_verified_bank_account_version(
                    session,
                    payee_id=payee.id,
                    details=VerifiedBankAccountDetails(
                        account_name="Ada Renamed",
                        account_number="0123456789",
                        bank_code="058",
                    ),
                    verification_reference=f"review-rename-{uuid4().hex}",
                    actor_user_id=graph.admin.id,
                    crypto=EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1),
                )
            await session.commit()
            batch_count = await session.scalar(select(func.count(PayoutBatch.id)))
            with pytest.raises(AppError) as denied:
                await disbursements.retry_failed_payout_lines(
                    session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=adapter
                )
            assert denied.value.code == "PAYOUT_RESOLVED_LINES_NOT_RETRYABLE"
            assert await session.scalar(select(func.count(PayoutBatch.id))) == batch_count
            assert (
                await session.scalar(
                    select(func.count(PayoutBatchLine.id)).where(
                        PayoutBatchLine.predecessor_line_id == original.id
                    )
                )
                == 0
            )

    asyncio.run(exercise())


def test_terminal_failure_replacement_uses_changed_verified_destination(postgis_db_sessionmaker):
    sessions = postgis_db_sessionmaker
    graph = build_graph(sessions, f"review-changed-{uuid4().hex[:8]}")
    checker, reconciler = _admins(sessions, "review-changed")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with sessions() as session:
            batch, original, entry = await _fail(session, graph, checker, reconciler, adapter)
            await _add_new_bank_version(session, graph)
            await session.commit()
            replacement, children = await disbursements.retry_failed_payout_lines(
                session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=adapter
            )
            await session.commit()
            assert replacement.id != batch.id
            assert replacement.status == "reserved"
            assert len(children) == 1
            child = children[0]
            assert child.predecessor_line_id == original.id
            assert child.ledger_entry_id == entry.id
            assert child.amount == original.amount
            assert child.bank_account_version_id != original.bank_account_version_id
            assert child.idempotency_key != original.idempotency_key
            crypto = EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1)
            before, after = [
                await read_verified_bank_account(
                    session,
                    bank_account_version_id=version_id,
                    actor_user_id=graph.admin.id,
                    crypto=crypto,
                    purpose="review_changed_destination_assertion",
                )
                for version_id in (original.bank_account_version_id, child.bank_account_version_id)
            ]
            assert (before.bank_code, before.account_number) != (
                after.bank_code,
                after.account_number,
            )
            again, same_children = await disbursements.retry_failed_payout_lines(
                session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=adapter
            )
            assert again.id == replacement.id
            assert [line.id for line in same_children] == [child.id]

    asyncio.run(exercise())


def test_replacement_stale_assessment_denies_every_line_before_construction(
    postgis_db_sessionmaker, monkeypatch
):
    sessions = postgis_db_sessionmaker
    graphs = [
        build_graph(sessions, f"review-stale-{index}-{uuid4().hex[:8]}") for index in range(2)
    ]
    checker, reconciler = _admins(sessions, "review-stale")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with sessions() as session:
            entries = [await _seed_authority(session, graph) for graph in graphs]
            batch = await disbursements.create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graphs[0].admin.id
            )
            _, lines = await disbursements.reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=tuple(e.id for e in entries),
                actor_user_id=graphs[0].admin.id,
            )
            await disbursements.approve_payout_batch(
                session, batch_id=batch.id, actor_user_id=checker.id
            )
            await disbursements.submit_payout_batch(
                session, batch_id=batch.id, actor_user_id=graphs[0].admin.id, adapter=adapter
            )
            intents = list(await session.scalars(select(PayoutSubmissionIntent.id)))
            await session.commit()
            for intent in intents:
                assert (
                    await disbursements.process_payout_submission_intent(
                        sessions, intent_id=intent, adapter=adapter
                    )
                    == "resolved"
                )
            for line in lines:
                await session.refresh(line)
                assert line.status == "submitted"
            for line in lines:
                await _poll(
                    session,
                    adapter=adapter,
                    line=line,
                    reconciler_id=reconciler.id,
                    outcome="failed",
                    event=f"stale-failed-{uuid4().hex}",
                    occurred_at=NOW,
                )
                await session.commit()
            assert all(line.status == "failed" for line in lines), [
                (line.status, line.provider_transfer_reference) for line in lines
            ]
            for graph in graphs:
                await _add_new_bank_version(session, graph)
            stale = await session.scalar(
                select(FraudAssessment).where(FraudAssessment.trip_session_id == graphs[1].trip.id)
            )
            stale.inputs_fingerprint = "0" * 64
            await session.commit()
            counts = tuple(
                [
                    await session.scalar(select(func.count(model.id)))
                    for model in (PayoutBatch, PayoutBatchLine, AuditEvent)
                ]
            )
            constructed = []
            original_class = disbursements.PayoutBatchLine
            from sqlalchemy import event

            def observe(_target, _args, _kwargs):
                constructed.append(True)

            event.listen(original_class, "init", observe)
            try:
                with pytest.raises(AppError) as denied:
                    await disbursements.retry_failed_payout_lines(
                        session,
                        batch_id=batch.id,
                        actor_user_id=graphs[0].admin.id,
                        adapter=adapter,
                    )
                assert denied.value.code == "PAYOUT_ASSESSMENT_NOT_CURRENT"
                assert constructed == []
                assert (
                    tuple(
                        [
                            await session.scalar(select(func.count(model.id)))
                            for model in (PayoutBatch, PayoutBatchLine, AuditEvent)
                        ]
                    )
                    == counts
                )
            finally:
                event.remove(original_class, "init", observe)

    asyncio.run(exercise())


def test_campaign_exposure_survives_late_predecessor_success_and_counts_both_verified_transfers(
    postgis_db_sessionmaker,
):
    sessions = postgis_db_sessionmaker
    graph = build_graph(sessions, f"review-exposure-{uuid4().hex[:8]}")
    checker, reconciler = _admins(sessions, "review-exposure")
    adapter = FakeDisbursementAdapter()

    async def exercise():
        async with sessions() as session:
            batch, original, _ = await _fail(session, graph, checker, reconciler, adapter)
            await _add_new_bank_version(session, graph)
            replacement, children = await disbursements.retry_failed_payout_lines(
                session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=adapter
            )
            await disbursements.approve_payout_batch(
                session, batch_id=replacement.id, actor_user_id=checker.id
            )
            await disbursements.submit_payout_batch(
                session, batch_id=replacement.id, actor_user_id=graph.admin.id, adapter=adapter
            )
            intent = await session.scalar(
                select(PayoutSubmissionIntent.id).where(
                    PayoutSubmissionIntent.payout_batch_line_id == children[0].id
                )
            )
            await session.commit()
            await disbursements.process_payout_submission_intent(
                sessions, intent_id=intent, adapter=adapter
            )
            await session.refresh(children[0])
            await _poll(
                session,
                adapter=adapter,
                line=original,
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"old-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=1),
            )
            await session.commit()
            before = (await campaign_money_position(session, campaign_id=graph.campaign.id))[
                "items"
            ][0]
            assert before["cash_paid"] == Decimal("100.00")
            assert before["in_flight"] == Decimal("100.00")
            assert before["provider_verified_paid"] == Decimal("100.00")
            await _poll(
                session,
                adapter=adapter,
                line=children[0],
                reconciler_id=reconciler.id,
                outcome="succeeded",
                event=f"child-success-{uuid4().hex}",
                occurred_at=NOW + timedelta(minutes=2),
            )
            await session.commit()
            after = (await campaign_money_position(session, campaign_id=graph.campaign.id))[
                "items"
            ][0]
            assert after["cash_paid"] == Decimal("100.00")
            assert after["earned_net"] == Decimal("100.00")
            assert after["in_flight"] == Decimal("0.00")
            assert after["provider_verified_paid"] == Decimal("200.00")
            assert after["driver_wide_debt"] == Decimal("100.00")

    asyncio.run(exercise())
