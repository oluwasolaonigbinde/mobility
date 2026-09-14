import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph
from test_payout_batches import _seed_authority

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.disbursement import PayoutBatch, PayoutBatchLine
from app.services.disbursements import create_payout_batch_draft, reserve_payout_batch


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_draft_identity_and_exact_reservation_recover_lost_responses(request, fixture_name):
    db_sessionmaker = request.getfixturevalue(fixture_name)
    graph = build_graph(db_sessionmaker, f"selection-{uuid4().hex[:8]}")

    async def exercise():
        request_id = uuid4()
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph, amount="100.07")
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id, request_id=request_id
            )
            await session.commit()
            entry_id = entry.id
            assert batch.id == request_id
        async with db_sessionmaker() as session:
            replay = await create_payout_batch_draft(
                session, currency="ngn", actor_user_id=graph.admin.id, request_id=request_id
            )
            assert replay.id == request_id
            _, lines = await reserve_payout_batch(
                session,
                batch_id=request_id,
                ledger_entry_ids=(entry_id,),
                actor_user_id=graph.admin.id,
            )
            line_id = lines[0].id
            await session.commit()
        async with db_sessionmaker() as session:
            batch, replay_lines = await reserve_payout_batch(
                session,
                batch_id=request_id,
                ledger_entry_ids=(entry_id,),
                actor_user_id=graph.admin.id,
            )
            assert replay_lines[0].id == line_id
            assert batch.total_amount == Decimal("100.07")
            assert (
                await session.scalar(
                    select(func.count(PayoutBatchLine.id)).where(
                        PayoutBatchLine.batch_id == request_id
                    )
                )
                == 1
            )
            for action in ("created", "reserved"):
                assert (
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.entity_id == str(request_id),
                            AuditEvent.action == f"admin.payout_batch.{action}",
                        )
                    )
                    == 1
                )
            with pytest.raises(AppError):
                await create_payout_batch_draft(
                    session, currency="USD", actor_user_id=graph.admin.id, request_id=request_id
                )
            with pytest.raises(AppError):
                await reserve_payout_batch(
                    session,
                    batch_id=request_id,
                    ledger_entry_ids=(uuid4(),),
                    actor_user_id=graph.admin.id,
                )
            assert (
                await session.scalar(select(PayoutBatch.id).where(PayoutBatch.id == request_id))
                == request_id
            )

    asyncio.run(exercise())


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_advisory_selection_is_exact_paged_and_does_not_decrypt_or_write(request, fixture_name):
    from test_payout_debt import _debt, _ledger

    from app.services.payout_debt import allocate_available_credit_to_debt
    from app.services.payout_operations import eligible_payment_entries

    sessions = request.getfixturevalue(fixture_name)
    graph = build_graph(sessions, f"selection-view-{uuid4().hex[:8]}")

    async def exercise():
        async with sessions() as session:
            credit = await _seed_authority(session, graph, amount="100.07")
            session.add(_ledger(graph, amount="0.03", status="available", currency="USD"))
            await _debt(session, graph, "20.02")
            await session.commit()
            before = await session.scalar(select(func.count(AuditEvent.id)))
            page = await eligible_payment_entries(session, limit=1, currency="NGN")
            assert page["total"] == 1
            row = page["items"][0]
            assert row["driver_name"] == graph.driver.full_name
            assert row["payee_name"] == graph.driver.full_name
            assert row["amount"] == Decimal("100.07")
            assert row["carry_forward_debt"] == Decimal("20.02")
            assert row["destination_verified"] is True
            assert row["eligible"] is False
            assert "account_number" not in repr(page)
            assert "0123456789" not in repr(page)
            assert page["page_eligible_totals"] == []
            assert await session.scalar(select(func.count(AuditEvent.id))) == before
            assert (await eligible_payment_entries(session, offset=100))["items"] == []
            assert (await eligible_payment_entries(session, search="%"))["total"] == 0
            assert (await eligible_payment_entries(session, search=graph.driver.full_name))[
                "total"
            ] == 2
            result = await allocate_available_credit_to_debt(
                session,
                driver_profile_id=graph.profile.id,
                currency="NGN",
                actor_user_id=graph.admin.id,
            )
            fresh = await eligible_payment_entries(session, currency="NGN")
            assert fresh["items"][0]["ledger_entry_id"] == result.remainder_entry_ids[0]
            assert fresh["items"][0]["amount"] == Decimal("80.05")
            assert fresh["items"][0]["debt_deducted"] == Decimal("20.02")
            assert fresh["items"][0]["eligible"] is True
            assert fresh["page_eligible_totals"] == [
                {"currency": "NGN", "amount": Decimal("80.05")}
            ]
            assert credit.status == "reversed"

    asyncio.run(exercise())


def test_concurrent_draft_retry_has_one_durable_winner(postgis_db_sessionmaker):
    sessions = postgis_db_sessionmaker
    graph = build_graph(sessions, f"draft-race-{uuid4().hex[:8]}")
    request_id = uuid4()

    async def exercise():
        async def create():
            async with sessions() as session:
                batch = await create_payout_batch_draft(
                    session, currency="NGN", actor_user_id=graph.admin.id, request_id=request_id
                )
                await session.commit()
                return batch.id

        assert await asyncio.gather(create(), create()) == [request_id, request_id]
        async with sessions() as session:
            assert await session.scalar(select(func.count(PayoutBatch.id))) == 1
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.payout_batch.created"
                    )
                )
                == 1
            )

    asyncio.run(exercise())


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_batch_summaries_and_detail_distinguish_queued_unknown_and_verified_history(
    request, fixture_name
):
    from test_payout_reconciliation import _admins

    from app.adapters.disbursement import FakeDisbursementAdapter
    from app.models.disbursement import PayoutSubmissionIntent
    from app.services.disbursements import approve_payout_batch, submit_payout_batch
    from app.services.payout_operations import (
        payout_batch_detail,
        payout_batch_summaries,
        payout_line_history,
    )

    sessions = request.getfixturevalue(fixture_name)
    graph = build_graph(sessions, f"batch-view-{uuid4().hex[:8]}")
    checker, _ = _admins(sessions, "batch-view")

    async def exercise():
        async with sessions() as session:
            entries = [
                await _seed_authority(session, graph, amount="0.10"),
                await _seed_authority(session, graph, amount="0.20"),
            ]
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
            await submit_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=FakeDisbursementAdapter(),
            )
            summary = await payout_batch_summaries(session)
            row = summary["items"][0]
            assert row["maker_name"] == graph.admin.full_name
            assert row["checker_name"] == checker.full_name
            assert row["outcomes"] == {"queued": 2}
            assert row["total_amount"] == Decimal("0.30")
            assert "lines" not in row
            detail = await payout_batch_detail(session, batch_id=batch.id, limit=1)
            assert detail["total"] == 2
            assert len(detail["lines"]) == 1
            assert detail["lines"][0]["outcome"] == "queued"
            history = await payout_line_history(session, line_id=lines[0].id)
            assert history["items"] == []
            assert history["latest_submission_outcome"] is None
            intent = await session.scalar(
                select(PayoutSubmissionIntent).where(
                    PayoutSubmissionIntent.payout_batch_line_id == lines[0].id
                )
            )
            # Query-only is an allowed persisted unknown state, never failure or cash.
            from sqlalchemy import update

            await session.execute(
                update(PayoutSubmissionIntent)
                .where(PayoutSubmissionIntent.id == intent.id)
                .values(state="query_only")
            )
            changed = await payout_batch_summaries(session)
            assert changed["items"][0]["outcomes"] == {"queued": 1, "provider_unknown": 1}
            assert all(entry.status == "available" for entry in entries)
            assert (await payout_batch_summaries(session, offset=5))["items"] == []
            assert (await payout_batch_summaries(session, batch_status="draft"))["total"] == 0
            with pytest.raises(AppError):
                await payout_batch_detail(session, batch_id=uuid4())
            with pytest.raises(AppError):
                await payout_line_history(session, line_id=uuid4())
            with pytest.raises(AppError):
                await payout_batch_summaries(session, limit=101)

    asyncio.run(exercise())


@pytest.mark.parametrize("fixture_name", ["db_sessionmaker", "postgis_db_sessionmaker"])
def test_approval_bank_reveal_refuses_stale_version_before_decryption(request, fixture_name):
    db_sessionmaker = request.getfixturevalue(fixture_name)
    from app.adapters.crypto import EnvelopeCryptoProvider
    from app.models.payee import Payee, PayeeBankAccountVersion
    from app.services.payees import (
        VerifiedBankAccountDetails,
        add_verified_bank_account_version,
        read_verified_bank_account,
    )

    graph = build_graph(db_sessionmaker, f"bank-current-{uuid4().hex[:8]}")
    crypto = EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1)

    async def exercise():
        async with db_sessionmaker() as session:
            await _seed_authority(session, graph)
            payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.profile.id))
            old = await session.scalar(select(PayeeBankAccountVersion))
            latest = await add_verified_bank_account_version(
                session,
                payee_id=payee.id,
                details=VerifiedBankAccountDetails(
                    account_name="Ada Batch", account_number="9876543210", bank_code="058"
                ),
                verification_reference=f"current-{uuid4()}",
                actor_user_id=graph.admin.id,
                crypto=crypto,
            )
            with pytest.raises(AppError) as error:
                await read_verified_bank_account(
                    session,
                    bank_account_version_id=old.id,
                    actor_user_id=graph.admin.id,
                    crypto=crypto,
                    purpose="person_payee_approval",
                )
            assert error.value.code == "BANK_ACCOUNT_VERSION_STALE"
            current = await read_verified_bank_account(
                session,
                bank_account_version_id=latest.id,
                actor_user_id=graph.admin.id,
                crypto=crypto,
                purpose="person_payee_approval",
            )
            assert current.account_number == "9876543210"
            historical = await read_verified_bank_account(
                session,
                bank_account_version_id=old.id,
                actor_user_id=graph.admin.id,
                crypto=crypto,
                purpose="payout_reconciliation",
            )
            assert historical.account_number == "0123456789"

    asyncio.run(exercise())


def test_selection_and_reservation_deny_stale_assessment(db_sessionmaker):
    from app.models.fraud_assessment import FraudAssessment
    from app.services.payout_operations import eligible_payment_entries

    graph = build_graph(db_sessionmaker, f"stale-select-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            assessment = await session.scalar(
                select(FraudAssessment).where(FraudAssessment.trip_session_id == graph.trip.id)
            )
            assessment.inputs_fingerprint = "0" * 64
            await session.flush()
            projection = await eligible_payment_entries(session)
            assert not projection["items"][0]["eligible"]
            with pytest.raises(AppError) as error:
                await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(entry.id,),
                    actor_user_id=graph.admin.id,
                )
            assert error.value.code == "PAYOUT_ASSESSMENT_NOT_CURRENT"
            assert await session.scalar(select(func.count(PayoutBatchLine.id))) == 0

    asyncio.run(exercise())
