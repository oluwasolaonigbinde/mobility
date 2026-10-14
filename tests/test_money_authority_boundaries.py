"""Money refusal and frozen-authority boundaries, without provider calls."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from conftest import create_test_user
from sqlalchemy import func, select
from test_billing_corrections import _fixture
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.billing import CampaignFinancialAuthorization
from app.models.disbursement import PayoutBatch, PayoutBatchLine
from app.models.payout import EarningsLedgerEntry
from app.services import disbursements, payees
from app.services.billing.authority import record_subsidy_authorization
from app.services.billing.settlements import _validate_refund_cancellation


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_name", " "),
        ("account_name", "x" * 161),
        ("account_number", "123"),
        ("account_number", "abcdefghij"),
        ("account_number", "\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff10"),
        ("bank_code", "ab1"),
        ("bank_code", "12"),
        ("bank_code", "\uff10\uff15\uff18"),
    ],
)
def test_verified_bank_details_reject_ambiguous_or_invalid_destination(field, value):
    values = {
        "account_name": "Synthetic Driver",
        "account_number": "0123456789",
        "bank_code": "058",
    }
    with pytest.raises(AppError) as caught:
        payees._validate_details(payees.VerifiedBankAccountDetails(**{**values, field: value}))
    assert caught.value.code == "BANK_ACCOUNT_DETAILS_INVALID"


@pytest.mark.parametrize("reference", [None, "short", "x" * 513, "x" * 31 + " ", "\ud800"])
def test_bank_verification_reference_cannot_be_empty_structured_or_malformed(reference):
    with pytest.raises(AppError) as caught:
        payees.verification_reference_hash(reference)
    assert caught.value.code == "VERIFICATION_REFERENCE_INVALID"


@pytest.mark.parametrize("purpose", ["", "private free text", "x" * 200])
def test_bank_read_requires_a_bounded_machine_purpose(purpose):
    with pytest.raises(AppError) as caught:
        payees._normalize_purpose(purpose)
    assert caught.value.code == "BANK_ACCOUNT_READ_PURPOSE_INVALID"


def test_corrupt_bank_envelope_is_a_safe_domain_error():
    with pytest.raises(AppError) as caught:
        payees._parse_envelope({"plaintext": "synthetic-private"})
    assert caught.value.code == "BANK_ACCOUNT_DECRYPTION_FAILED"
    assert "synthetic-private" not in str(caught.value)


def frozen_batch():
    batch = PayoutBatch(id=uuid4(), currency="NGN", status="reserved")
    line = disbursements.build_frozen_payout_line(
        batch_id=batch.id,
        entry=EarningsLedgerEntry(id=uuid4(), amount=Decimal("125.00"), currency="NGN"),
        payee_version=SimpleNamespace(id=uuid4()),
        account_version=SimpleNamespace(id=uuid4()),
    )
    disbursements.freeze_batch_instruction_set(batch, [line])
    return batch, line


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("empty", "PAYOUT_BATCH_EMPTY"),
        ("instruction", "PAYOUT_INSTRUCTION_CHANGED"),
        ("amount", "PAYOUT_INSTRUCTION_CHANGED"),
        ("idempotency", "PAYOUT_INSTRUCTION_CHANGED"),
        ("batch_total", "PAYOUT_BATCH_CHANGED"),
        ("batch_fingerprint", "PAYOUT_BATCH_CHANGED"),
    ],
)
def test_frozen_payout_authority_rejects_independent_tampering(mutation, code):
    batch, line = frozen_batch()
    disbursements._assert_frozen(batch, (line,))
    lines = (line,)
    if mutation == "empty":
        lines = ()
    elif mutation == "instruction":
        line.instruction = {**line.instruction, "amount": "999.00"}
    elif mutation == "amount":
        line.amount = Decimal("126.00")
    elif mutation == "idempotency":
        line.idempotency_key = "reused-other-key"
    elif mutation == "batch_total":
        batch.total_amount = Decimal("0")
    else:
        batch.instruction_set_fingerprint = "changed"
    with pytest.raises(AppError) as caught:
        disbursements._assert_frozen(batch, lines)
    assert caught.value.code == code


@pytest.mark.parametrize("broken", ["cycle", "missing"])
def test_replacement_chain_never_guesses_missing_or_cyclic_authority(broken):
    first = PayoutBatchLine(id=uuid4())
    second = PayoutBatchLine(id=uuid4(), predecessor_line_id=first.id)
    first.predecessor_line_id = second.id if broken == "cycle" else uuid4()
    with pytest.raises(
        RuntimeError, match="cycle" if broken == "cycle" else "lost its predecessor"
    ):
        disbursements._chain_root_id(second, {first.id: first, second.id: second})


@pytest.mark.parametrize(
    "intent_state,allowed",
    [
        (None, True),
        ("pending", True),
        ("claimed", False),
        ("query_only", False),
        ("resolved", False),
        ("cancelled", False),
    ],
)
def test_only_provably_uncalled_reserved_transfer_can_be_cancelled(intent_state, allowed):
    now = datetime(2026, 10, 14, tzinfo=UTC)
    line = PayoutBatchLine(status="reserved", reservation_active=True)
    intent = None if intent_state is None else SimpleNamespace(state=intent_state, resolved_at=None)
    assert disbursements._cancel_uncalled_line(line, intent, cancelled_at=now) is allowed
    assert line.status == ("void" if allowed else "reserved")
    assert line.reservation_active is not allowed
    if intent is not None:
        assert intent.state == ("cancelled" if allowed else intent_state)
        assert intent.resolved_at == (now if allowed else None)


def test_draft_currency_and_retry_authority_leave_no_extra_batches(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="draft-boundary@example.com", role="admin")

    async def run():
        async with db_sessionmaker() as session:
            for currency in ("N", "123", "NGNN"):
                with pytest.raises(AppError) as caught:
                    await disbursements.create_payout_batch_draft(
                        session, currency=currency, actor_user_id=admin.id
                    )
                assert caught.value.code == "PAYOUT_BATCH_CURRENCY_INVALID"
            request_id = uuid4()
            batch = await disbursements.create_payout_batch_draft(
                session, currency=" ngn ", actor_user_id=admin.id, request_id=request_id
            )
            replay = await disbursements.create_payout_batch_draft(
                session, currency="NGN", actor_user_id=admin.id, request_id=request_id
            )
            assert replay.id == batch.id
            with pytest.raises(AppError) as caught:
                await disbursements.create_payout_batch_draft(
                    session, currency="USD", actor_user_id=admin.id, request_id=request_id
                )
            assert caught.value.code == "PAYOUT_DRAFT_RETRY_CONFLICT"
            assert await session.scalar(select(func.count()).select_from(PayoutBatch)) == 1
            assert batch.currency == "NGN" and batch.total_amount == 0
            for selected in ((), (uuid4(),) * 2):
                with pytest.raises(AppError) as caught:
                    await disbursements.reserve_payout_batch(
                        session,
                        batch_id=batch.id,
                        ledger_entry_ids=selected,
                        actor_user_id=admin.id,
                    )
                assert caught.value.code == "PAYOUT_BATCH_ENTRIES_INVALID"

    asyncio.run(run())


def test_non_reversal_never_creates_debt_or_queries_accounts():
    from app.services.payout_debt import record_reversal_obligation

    session = AsyncMock()
    with pytest.raises(ValueError, match="Only a reversal"):
        asyncio.run(
            record_reversal_obligation(
                session, reversal_entry=EarningsLedgerEntry(entry_type="trip_payout")
            )
        )
    session.scalar.assert_not_awaited()


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"subsidy_reference": " "}, "SUBSIDY_REFERENCE_REQUIRED"),
        ({"reason": " "}, "FINANCIAL_AUTHORITY_REASON_REQUIRED"),
        ({"subsidy_amount": "0.00"}, "INVALID_FINANCIAL_AUTHORITY_AMOUNT"),
        ({"max_driver_liability": "0.00"}, "INVALID_FINANCIAL_AUTHORITY_AMOUNT"),
        ({"max_driver_liability": "101.00"}, "DRIVER_LIABILITY_EXCEEDS_AUTHORITY"),
    ],
)
def test_subsidy_requires_positive_bounded_documented_authority(db_sessionmaker, overrides, code):
    admin, owner, _, campaign = _fixture(db_sessionmaker, "subsidy-boundary")

    async def scenario():
        async with db_sessionmaker() as session:
            await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="SUBSIDY-BOUNDARY"
            )
            arguments = dict(
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                subsidy_amount="100.00",
                max_driver_liability="50.00",
                subsidy_reference="synthetic-evidence",
                reason="Approved",
            )
            with pytest.raises(AppError) as caught:
                await record_subsidy_authorization(session, **{**arguments, **overrides})
            assert caught.value.code == code
            assert (
                await session.scalar(
                    select(func.count()).select_from(CampaignFinancialAuthorization)
                )
                == 0
            )

    asyncio.run(scenario())


def test_subsidy_retry_converges_and_cannot_reduce_accepted_authority(db_sessionmaker):
    admin, owner, _, campaign = _fixture(db_sessionmaker, "subsidy-retry")

    async def scenario():
        async with db_sessionmaker() as session:
            await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="SUBSIDY-RETRY"
            )
            arguments = dict(
                campaign_id=campaign.id,
                actor_user_id=admin.id,
                subsidy_amount="100.00",
                max_driver_liability="50.00",
                subsidy_reference="synthetic-evidence",
                reason="Approved",
            )
            first = await record_subsidy_authorization(session, **arguments)
            assert (await record_subsidy_authorization(session, **arguments)).id == first.id
            for reduction in ({"subsidy_amount": "99.00"}, {"max_driver_liability": "49.00"}):
                with pytest.raises(AppError) as caught:
                    await record_subsidy_authorization(session, **{**arguments, **reduction})
                assert caught.value.code == "FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE"
            assert (
                await session.scalar(
                    select(func.count()).select_from(CampaignFinancialAuthorization)
                )
                == 1
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("commercial_terms_id", uuid4(), "REFUND_CANCELLATION_MISMATCH"),
        ("campaign_id", uuid4(), "REFUND_CANCELLATION_MISMATCH"),
        ("organization_id", uuid4(), "REFUND_CANCELLATION_MISMATCH"),
        ("currency", "USD", "REFUND_CANCELLATION_MISMATCH"),
        ("disposition", "no_refund", "REFUND_CANCELLATION_NOT_DUE"),
        ("refundable_amount", Decimal("0.00"), "REFUND_CANCELLATION_NOT_DUE"),
        ("funding_authorized_at", None, "REFUND_CANCELLATION_MISMATCH"),
        ("refund_eligibility_ends_at", None, "REFUND_CANCELLATION_MISMATCH"),
        ("cutoff_at", datetime(2026, 10, 14, 12, tzinfo=UTC), "REFUND_CANCELLATION_MISMATCH"),
    ],
)
def test_cash_refund_refuses_mismatched_or_expired_frozen_cancellation(field, value, code):
    terms = SimpleNamespace(
        id=uuid4(), campaign_id=uuid4(), organization_id=uuid4(), currency="NGN"
    )
    end = datetime(2026, 10, 14, 12, tzinfo=UTC)
    cancellation = SimpleNamespace(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        organization_id=terms.organization_id,
        currency=terms.currency,
        disposition="cash_refund_due",
        refundable_amount=Decimal("100.00"),
        funding_authorized_at=end - timedelta(hours=24),
        refund_eligibility_ends_at=end,
        cutoff_at=end - timedelta(seconds=1),
    )
    assert _validate_refund_cancellation(cancellation, terms) is cancellation
    setattr(cancellation, field, value)
    with pytest.raises(AppError) as caught:
        _validate_refund_cancellation(cancellation, terms)
    assert caught.value.code == code
