"""Fail-closed policy and synthetic-provider contracts used by money simulations."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal

import pytest

from app.adapters.disbursement.provider import (
    DisbursementInstruction,
    FakeDisbursementAdapter,
    ProviderLookupStatus,
)
from app.adapters.payments.provider import FakePaymentGatewayAdapter, PaymentWebhookPayloadError


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
