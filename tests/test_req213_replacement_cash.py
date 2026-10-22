"""REQ-213: reduced-net replacement and late ancestor cash retain one authority."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority
from test_r22_conservation_postgresql import _add_new_bank_version, _poll
from test_r22_conservation_postgresql import (
    replacement_crypto_matches_synthetic_bank_capture as bank_crypto,  # noqa: F401
)

from app.adapters.disbursement import FakeDisbursementAdapter
from app.models.disbursement import PayoutSubmissionIntent
from app.services.disbursements import (
    approve_payout_batch,
    claim_payout_submission_intent,
    create_payout_batch_draft,
    process_payout_submission_intent,
    reserve_payout_batch,
    retry_failed_payout_lines,
    submit_payout_batch,
)
from app.services.payout_adjustments import record_negative_adjustment
from app.services.payout_balances import driver_money_balance

pytestmark = pytest.mark.usefixtures("bank_crypto")


@pytest.mark.parametrize("uncertain_descendant", [False, True])
def test_reduced_replacement_and_deep_pending_descendant_after_ancestor_success(
    postgis_db_sessionmaker, uncertain_descendant
):
    db = postgis_db_sessionmaker
    graph = build_graph(db, "net-chain-" + uuid4().hex[:8])
    fake = FakeDisbursementAdapter()
    now = datetime.now(UTC)

    async def exercise():
        async with db() as session:
            source = await _seed_authority(session, graph)
            await record_negative_adjustment(
                session,
                source_entry_id=source.id,
                request_id=uuid4(),
                amount=Decimal("20"),
                currency="NGN",
                reason="Correct original gross award",
                actor_user_id=graph.admin.id,
            )
            root_batch = await create_payout_batch_draft(
                session,
                currency="NGN",
                actor_user_id=graph.admin.id,
                reason="Prepare corrected payout",
            )
            root_batch, roots = await reserve_payout_batch(
                session,
                batch_id=root_batch.id,
                ledger_entry_ids=(source.id,),
                actor_user_id=graph.admin.id,
                reason="Reserve eighty net",
            )
            root = roots[0]
            assert root.amount == Decimal("80.00")

            async def send(batch, line):
                await approve_payout_batch(
                    session,
                    batch_id=batch.id,
                    actor_user_id=graph.admin.id,
                    reason="Checked net replacement",
                )
                await submit_payout_batch(
                    session, batch_id=batch.id, actor_user_id=graph.admin.id, adapter=fake
                )
                intent = await session.scalar(
                    select(PayoutSubmissionIntent).where(
                        PayoutSubmissionIntent.payout_batch_line_id == line.id
                    )
                )
                await session.commit()
                assert (
                    await process_payout_submission_intent(db, intent_id=intent.id, adapter=fake)
                    == "resolved"
                )
                await session.refresh(line)

            await send(root_batch, root)
            await _poll(
                session,
                adapter=fake,
                line=root,
                reconciler_id=graph.admin.id,
                outcome="failed",
                event="root-terminal-failure",
                occurred_at=now,
            )
            await session.commit()
            await record_negative_adjustment(
                session,
                source_entry_id=source.id,
                request_id=uuid4(),
                amount=Decimal("10"),
                currency="NGN",
                reason="Correct the remaining trip entitlement",
                actor_user_id=graph.admin.id,
            )
            await _add_new_bank_version(session, graph)
            child_batch, children = await retry_failed_payout_lines(
                session,
                batch_id=root_batch.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
                reason="Use corrected bank and seventy net",
            )
            child = children[0]
            assert child.amount == Decimal("70.00") and child.instruction["amount"] == "70.00"
            await send(child_batch, child)
            await _poll(
                session,
                adapter=fake,
                line=child,
                reconciler_id=graph.admin.id,
                outcome="failed",
                event="child-terminal-failure",
                occurred_at=now + timedelta(seconds=1),
            )
            await session.commit()
            await _add_new_bank_version(session, graph)
            grand_batch, grandchildren = await retry_failed_payout_lines(
                session,
                batch_id=child_batch.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
                reason="Replace failed seventy net to new bank",
            )
            grand = grandchildren[0]
            assert grand.amount == Decimal("70.00") and grand.predecessor_line_id == child.id
            await approve_payout_batch(
                session,
                batch_id=grand_batch.id,
                actor_user_id=graph.admin.id,
                reason="Checked final replacement",
            )
            await submit_payout_batch(
                session, batch_id=grand_batch.id, actor_user_id=graph.admin.id, adapter=fake
            )
            intent = await session.scalar(
                select(PayoutSubmissionIntent).where(
                    PayoutSubmissionIntent.payout_batch_line_id == grand.id
                )
            )
            await session.commit()
            if uncertain_descendant:
                claim = await claim_payout_submission_intent(db, intent_id=intent.id, adapter=fake)
                assert claim and claim.action == "submit"
            await _poll(
                session,
                adapter=fake,
                line=root,
                reconciler_id=graph.admin.id,
                outcome="succeeded",
                event="late-root-success",
                occurred_at=now + timedelta(minutes=1),
            )
            await session.commit()
            await session.refresh(grand)
            await session.refresh(intent)
            assert grand.status == ("reserved" if uncertain_descendant else "void")
            assert grand.reservation_active is uncertain_descendant
            assert intent.state == ("claimed" if uncertain_descendant else "cancelled")
            balance = await driver_money_balance(
                session, driver_profile_id=graph.profile.id, currency="NGN"
            )
            assert balance.earned_net == Decimal("70.00") and balance.cash_paid == Decimal("80.00")
            assert balance.batch_payable == 0
            assert len(fake.calls) == 2

    asyncio.run(exercise())
