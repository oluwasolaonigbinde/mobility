import asyncio
import hashlib
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_mny03a_earnings_release import build_graph, create_flag

from app.adapters.crypto import EnvelopeCryptoProvider
from app.adapters.disbursement import DisabledDisbursementAdapter, FakeDisbursementAdapter
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.disbursement import PayoutBatch, PayoutBatchLine
from app.models.payout import EarningsLedgerEntry
from app.models.trip_analytics import FraudFlag
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    reserve_payout_batch,
    submit_payout_batch,
)
from app.services.fraud_holds import lock_fraud_hold_scope
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_verified_bank_account_version,
    create_pilot_payee,
)


async def _seed_authority(session, graph, *, amount="100.00"):
    payee, _ = await create_pilot_payee(
        session,
        driver_profile_id=graph.profile.id,
        actor_user_id=graph.admin.id,
    )
    await add_verified_bank_account_version(
        session,
        payee_id=payee.id,
        details=VerifiedBankAccountDetails(
            account_name="Ada Batch",
            account_number="0123456789",
            bank_code="058",
        ),
        verification_reference=f"batch-provider-evidence-{uuid4().hex}",
        actor_user_id=graph.admin.id,
        crypto=EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1),
    )
    entry = EarningsLedgerEntry(
        payout_calculation_id=None,
        driver_profile_id=graph.profile.id,
        driver_user_id=graph.driver.id,
        campaign_id=graph.campaign.id,
        trip_session_id=graph.trip.id,
        vehicle_id=graph.vehicle.id,
        entry_type="adjustment",
        status="available",
        amount=Decimal(amount),
        currency="NGN",
        occurred_at=graph.trip.ended_at,
        ledger_metadata={},
    )
    session.add(entry)
    await session.flush()
    return entry


def test_batch_reservation_approval_submission_and_retry_are_frozen(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"batch-{uuid4().hex[:8]}")
    checker = type(graph.admin)(
        email=f"batch-checker-{uuid4().hex}@example.com",
        password_hash=graph.admin.password_hash,
        full_name="Batch Checker",
        role="admin",
        status="active",
    )
    fake = FakeDisbursementAdapter()

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(checker)
            await session.flush()
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="ngn", actor_user_id=graph.admin.id
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            with pytest.raises(AppError) as same_admin:
                await approve_payout_batch(session, batch_id=batch.id, actor_user_id=graph.admin.id)
            assert same_admin.value.code == "PAYOUT_BATCH_MAKER_CHECKER_REQUIRED"
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            frozen = (lines[0].instruction.copy(), lines[0].idempotency_key)
            await submit_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
            )
            await submit_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=fake,
            )
            submitted_audits = int(
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.action == "admin.payout_batch.submitted",
                        AuditEvent.entity_id == str(batch.id),
                    )
                )
                or 0
            )
            await session.commit()
            return batch, lines[0], frozen, submitted_audits

    batch, line, frozen, submitted_audits = asyncio.run(exercise())
    assert batch.status == "submitted"
    assert batch.total_amount == Decimal("100.00")
    assert line.instruction == frozen[0]
    assert line.idempotency_key == frozen[1]
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == fake.calls[1][1]
    assert submitted_audits == 1


def test_multi_line_reservation_freezes_exact_total_hashes_and_keys(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"batch-multi-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            first = await _seed_authority(session, graph, amount="10.01")
            second = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="adjustment",
                status="available",
                amount=Decimal("20.29"),
                currency="NGN",
                occurred_at=graph.trip.ended_at,
                ledger_metadata={},
            )
            session.add(second)
            await session.flush()
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(second.id, first.id),
                actor_user_id=graph.admin.id,
            )
            return batch, lines

    batch, lines = asyncio.run(exercise())
    assert batch.total_amount == Decimal("30.30")
    assert [line.ledger_entry_id for line in lines] == sorted(
        [line.ledger_entry_id for line in lines], key=str
    )
    assert sorted(line.amount for line in lines) == [Decimal("10.01"), Decimal("20.29")]
    for line in lines:
        instruction_bytes = json.dumps(
            line.instruction, sort_keys=True, separators=(",", ":")
        ).encode()
        assert line.instruction_fingerprint == hashlib.sha256(instruction_bytes).hexdigest()
        idempotency_bytes = json.dumps(
            {
                "scope": "cardvert-payout-line-v1",
                "batch_id": str(batch.id),
                "instruction_fingerprint": line.instruction_fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        assert line.idempotency_key == hashlib.sha256(idempotency_bytes).hexdigest()
    batch_bytes = json.dumps(
        {
            "currency": "NGN",
            "total_amount": "30.30",
            "line_fingerprints": sorted(line.instruction_fingerprint for line in lines),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert batch.instruction_set_fingerprint == hashlib.sha256(batch_bytes).hexdigest()


@pytest.mark.parametrize(
    "tamper",
    [
        "line_amount",
        "line_currency",
        "payee_version_id",
        "bank_account_version_id",
        "idempotency_key",
        "batch_total",
        "batch_fingerprint",
    ],
)
def test_frozen_columns_tamper_blocks_approval(db_sessionmaker, tamper: str) -> None:
    graph = build_graph(db_sessionmaker, f"tamper-{tamper}-{uuid4().hex[:6]}")
    checker = type(graph.admin)(
        email=f"tamper-checker-{uuid4().hex}@example.com",
        password_hash=graph.admin.password_hash,
        full_name="Tamper Checker",
        role="admin",
        status="active",
    )

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(checker)
            await session.flush()
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
            line = lines[0]
            if tamper == "line_amount":
                line.amount = Decimal("99.00")
            elif tamper == "line_currency":
                line.currency = "USD"
            elif tamper == "payee_version_id":
                line.payee_version_id = uuid4()
            elif tamper == "bank_account_version_id":
                line.bank_account_version_id = uuid4()
            elif tamper == "idempotency_key":
                line.idempotency_key = "f" * 64
            elif tamper == "batch_total":
                batch.total_amount = Decimal("99.00")
            else:
                batch.instruction_set_fingerprint = "f" * 64
            with pytest.raises(AppError) as changed:
                await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            assert changed.value.code in {"PAYOUT_INSTRUCTION_CHANGED", "PAYOUT_BATCH_CHANGED"}

    asyncio.run(exercise())


def test_reservation_refuses_authoritative_active_hold_and_rolls_back(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"held-{uuid4().hex[:8]}")
    create_flag(db_sessionmaker, graph)

    async def exercise():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            with pytest.raises(AppError) as held:
                await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(entry.id,),
                    actor_user_id=graph.admin.id,
                )
            assert held.value.code == "PAYOUT_ENTRY_HELD"
            await session.rollback()
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count(PayoutBatchLine.id))) or 0)

    assert asyncio.run(exercise()) == 0


def test_reservation_is_whole_batch_and_rejects_mixed_currency(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"atomic-{uuid4().hex[:8]}")

    async def exercise():
        async with db_sessionmaker() as session:
            good = await _seed_authority(session, graph)
            bad = EarningsLedgerEntry(
                payout_calculation_id=None,
                driver_profile_id=graph.profile.id,
                driver_user_id=graph.driver.id,
                campaign_id=graph.campaign.id,
                trip_session_id=graph.trip.id,
                vehicle_id=graph.vehicle.id,
                entry_type="adjustment",
                status="available",
                amount=Decimal("20.00"),
                currency="USD",
                occurred_at=graph.trip.ended_at,
                ledger_metadata={},
            )
            session.add(bad)
            await session.flush()
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            with pytest.raises(AppError) as invalid:
                await reserve_payout_batch(
                    session,
                    batch_id=batch.id,
                    ledger_entry_ids=(good.id, bad.id),
                    actor_user_id=graph.admin.id,
                )
            assert invalid.value.code == "PAYOUT_ENTRY_INELIGIBLE"
            await session.rollback()
        async with db_sessionmaker() as session:
            return int(await session.scalar(select(func.count(PayoutBatchLine.id))) or 0)

    assert asyncio.run(exercise()) == 0


def test_frozen_instruction_tamper_blocks_approval(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"tamper-{uuid4().hex[:8]}")
    checker = type(graph.admin)(
        email=f"tamper-checker-{uuid4().hex}@example.com",
        password_hash=graph.admin.password_hash,
        full_name="Tamper Checker",
        role="admin",
        status="active",
    )

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(checker)
            await session.flush()
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
            lines[0].instruction = {**lines[0].instruction, "amount": "999.00"}
            with pytest.raises(AppError) as tampered:
                await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            assert tampered.value.code == "PAYOUT_INSTRUCTION_CHANGED"

    asyncio.run(exercise())


def test_submission_fails_closed_without_approved_provider(db_sessionmaker) -> None:
    graph = build_graph(db_sessionmaker, f"disabled-{uuid4().hex[:8]}")
    checker = type(graph.admin)(
        email=f"disabled-checker-{uuid4().hex}@example.com",
        password_hash=graph.admin.password_hash,
        full_name="Disabled Checker",
        role="admin",
        status="active",
    )

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(checker)
            await session.flush()
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            with pytest.raises(AppError) as unavailable:
                await submit_payout_batch(
                    session,
                    batch_id=batch.id,
                    actor_user_id=graph.admin.id,
                    adapter=DisabledDisbursementAdapter(),
                )
            assert unavailable.value.code == "DISBURSEMENT_PROVIDER_UNAVAILABLE"

    asyncio.run(exercise())


def test_postgres_concurrent_batches_have_one_reservation_winner(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"race-{uuid4().hex[:8]}")

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            first = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            second = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await session.commit()

        async def attempt(batch_id):
            async with postgis_db_sessionmaker() as session:
                try:
                    await reserve_payout_batch(
                        session,
                        batch_id=batch_id,
                        ledger_entry_ids=(entry.id,),
                        actor_user_id=graph.admin.id,
                    )
                    await session.commit()
                    return "won", "reserved", 1
                except AppError as exc:
                    stored = await session.get(PayoutBatch, batch_id)
                    partials = int(
                        await session.scalar(
                            select(func.count(PayoutBatchLine.id)).where(
                                PayoutBatchLine.batch_id == batch_id
                            )
                        )
                        or 0
                    )
                    return exc.code, stored.status, partials

        results = await asyncio.gather(attempt(first.id), attempt(second.id))
        async with postgis_db_sessionmaker() as session:
            count = int(
                await session.scalar(
                    select(func.count(PayoutBatchLine.id)).where(
                        PayoutBatchLine.ledger_entry_id == entry.id,
                        PayoutBatchLine.reservation_active.is_(True),
                    )
                )
                or 0
            )
        return results, count

    results, count = asyncio.run(exercise())
    assert sorted(result[0] for result in results) == [
        "PAYOUT_ENTRY_ALREADY_RESERVED",
        "won",
    ]
    loser = next(result for result in results if result[0] != "won")
    assert loser == ("PAYOUT_ENTRY_ALREADY_RESERVED", "draft", 0)
    assert count == 1


def test_postgres_hold_creation_serializes_before_reservation(
    postgis_db_sessionmaker,
) -> None:
    graph = build_graph(postgis_db_sessionmaker, f"hold-race-{uuid4().hex[:8]}")

    async def exercise():
        async with postgis_db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            await session.commit()

        async def reserve_while_hold_transaction_is_open():
            async with postgis_db_sessionmaker() as session:
                try:
                    await reserve_payout_batch(
                        session,
                        batch_id=batch.id,
                        ledger_entry_ids=(entry.id,),
                        actor_user_id=graph.admin.id,
                    )
                except AppError as exc:
                    return exc.code
                await session.commit()
                return "reserved"

        async with postgis_db_sessionmaker() as hold_session:
            await lock_fraud_hold_scope(hold_session, graph.trip.id)
            hold_session.add(
                FraudFlag(
                    trip_session_id=graph.trip.id,
                    trip_analytics_id=graph.analytics.id,
                    assignment_id=graph.assignment.id,
                    campaign_id=graph.campaign.id,
                    driver_profile_id=graph.profile.id,
                    vehicle_id=graph.vehicle.id,
                    flag_type="impossible_speed",
                    severity="high",
                    status="open",
                    description="Concurrent authoritative hold.",
                    evidence={"test": True},
                    detected_at=graph.trip.ended_at,
                )
            )
            await hold_session.flush()
            reservation = asyncio.create_task(reserve_while_hold_transaction_is_open())
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(reservation), timeout=0.1)
            await hold_session.commit()
        result = await reservation
        async with postgis_db_sessionmaker() as session:
            line_count = int(await session.scalar(select(func.count(PayoutBatchLine.id))) or 0)
        return result, line_count

    result, line_count = asyncio.run(exercise())
    assert result == "PAYOUT_ENTRY_HELD"
    assert line_count == 0
