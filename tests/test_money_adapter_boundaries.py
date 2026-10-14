"""Fail-closed policy and synthetic-provider contracts used by money simulations."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from app.adapters.budget.provider import BudgetPolicyContext, FixedBudgetPolicyAdapter
from app.adapters.disbursement.provider import (
    DisbursementInstruction,
    FakeDisbursementAdapter,
    ProviderLookupStatus,
)
from app.adapters.payments.provider import FakePaymentGatewayAdapter, PaymentWebhookPayloadError


def budget(**changes):
    return FixedBudgetPolicyAdapter(
        **{
            "policy_id": "synthetic",
            "policy_revision": "1",
            "policy_source": "synthetic_test",
            "alert_ratio": Decimal("0.8"),
            "pause_ratio": Decimal("1"),
            "resume_ratio": Decimal("0.5"),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"policy_source": "unapproved"}, "invalid_budget_policy_source"),
        ({"resume_ratio": Decimal("0")}, "invalid_budget_policy_threshold_order"),
        ({"resume_ratio": Decimal("0.9")}, "invalid_budget_policy_threshold_order"),
        ({"pause_ratio": Decimal("0.8")}, "invalid_budget_policy_threshold_order"),
        ({"urgent_ratio": Decimal("0.8")}, "invalid_budget_policy_threshold_order"),
        ({"urgent_ratio": Decimal("1")}, "invalid_budget_policy_threshold_order"),
    ],
)
def test_unapproved_or_unordered_budget_policy_is_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        budget(**changes)


def test_daily_only_budget_and_missing_budget_fail_closed():
    async def run():
        context = BudgetPolicyContext(
            uuid4(), "NGN", None, Decimal("100"), Decimal("0"), Decimal("100")
        )
        decision = await budget().evaluate(context)
        assert decision.budget_basis == "daily"
        assert decision.should_pause and not decision.resume_allowed
        with pytest.raises(ValueError, match="requires_budget"):
            await budget().evaluate(replace(context, configured_daily_budget_amount=None))

    asyncio.run(run())


def test_synthetic_transfer_replay_rejects_conflicting_effects():
    async def run():
        adapter = FakeDisbursementAdapter()
        first = DisbursementInstruction("first", "key-first", {}, "fingerprint-first")
        second = DisbursementInstruction("second", "key-second", {}, "fingerprint-second")
        original = await adapter.submit_batch(batch_id="batch-first", instructions=(first,))
        replay = await adapter.submit_batch(batch_id="retry", instructions=(first,))
        assert replay == original
        with pytest.raises(ValueError, match="different instruction"):
            await adapter.submit_batch(
                batch_id="retry", instructions=(replace(first, instruction_fingerprint="changed"),)
            )
        await adapter.submit_batch(batch_id="batch-second", instructions=(second,))
        with pytest.raises(ValueError, match="conflicting provider submissions"):
            await adapter.submit_batch(batch_id="combined", instructions=(first, second))
        assert (
            await adapter.lookup_line(
                idempotency_key="key-first", instruction_fingerprint="changed"
            )
        ).status == ProviderLookupStatus.UNKNOWN
        assert (
            await adapter.lookup_line(
                idempotency_key="key-first", instruction_fingerprint="fingerprint-first"
            )
        ).provider_transfer_reference == "fake-line-first"

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["pending", "succeeded"])
def test_synthetic_transfer_webhook_rejects_unsettled_outcome_and_normalizes_utc(outcome):
    adapter = FakeDisbursementAdapter()
    payload = json.dumps(
        {
            "occurred_at": "2026-10-14T12:00:00",
            "outcome": outcome,
            "provider_transfer_reference": "transfer",
            "provider_event_id": "event",
        }
    ).encode()

    async def run():
        if outcome == "pending":
            with pytest.raises(ValueError, match="payload is invalid"):
                await adapter.verify_webhook(
                    payload=payload, signature=adapter.sign_webhook(payload)
                )
        else:
            event = await adapter.verify_webhook(
                payload=payload, signature=adapter.sign_webhook(payload)
            )
            assert event.occurred_at.isoformat() == "2026-10-14T12:00:00+00:00"
            assert event.outcome == "succeeded"

    asyncio.run(run())


@pytest.mark.parametrize("event_type", ["pending", "payment_confirmed"])
def test_synthetic_payment_webhook_preserves_terminal_authority(event_type):
    adapter = FakePaymentGatewayAdapter()
    payload = json.dumps(
        {
            "occurred_at": "2026-10-14T12:00:00",
            "event_type": event_type,
            "amount": "12.50",
            "currency": "ngn",
            "payer_name": "Synthetic",
            "provider_event_id": "event",
            "external_transaction_id": "transaction",
            "commercial_terms_id": "terms",
            "organization_id": "organization",
        }
    ).encode()

    async def run():
        if event_type == "pending":
            with pytest.raises(PaymentWebhookPayloadError):
                await adapter.parse_webhook(payload, adapter.sign_webhook(payload))
            assert adapter.transactions == {}
        else:
            event = await adapter.parse_webhook(payload, adapter.sign_webhook(payload))
            assert event.occurred_at.isoformat() == "2026-10-14T12:00:00+00:00"
            assert event.amount == Decimal("12.50") and event.currency == "NGN"
            assert await adapter.verify_transaction("transaction") == event

    asyncio.run(run())
