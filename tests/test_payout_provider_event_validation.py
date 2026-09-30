"""Fail-closed validation for authenticated payout provider evidence."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.adapters.disbursement import (
    DisbursementProviderCapabilities,
    VerifiedLineEvidence,
)
from app.adapters.disbursement.provider import DisbursementUnavailableError
from app.core.errors import AppError
from app.services.disbursements import ingest_payout_provider_webhook


def evidence() -> VerifiedLineEvidence:
    return VerifiedLineEvidence(
        provider_transfer_reference="TRF_synthetic",
        provider_event_id="transfer.success:TRF_synthetic",
        outcome="succeeded",
        occurred_at=datetime(2026, 9, 30, tzinfo=UTC),
        evidence_fingerprint="a" * 64,
        provider_reference="cvp_synthetic",
        amount="100.00",
        currency="NGN",
        provider_event_type="transfer.success",
    )


class Adapter:
    def __init__(self, result, provider="paystack") -> None:
        self.result = result
        self.capabilities = DisbursementProviderCapabilities(
            provider_name=provider,
            lookup_by_idempotency_key=True,
            semantic_same_key_idempotency=True,
        )

    async def verify_webhook(self, **_kwargs):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class UnusedSession:
    async def scalar(self, _statement):
        raise AssertionError("malformed evidence must be rejected before database access")


@pytest.mark.parametrize(
    ("changes", "provider"),
    [
        ({}, " "),
        ({"provider_event_id": " "}, "paystack"),
        ({"provider_event_id": "x" * 256}, "paystack"),
        ({"provider_transfer_reference": " "}, "paystack"),
        ({"provider_transfer_reference": "x" * 256}, "paystack"),
        ({"outcome": "pending"}, "paystack"),
        ({"provider_event_type": None}, "paystack"),
        ({"provider_event_type": "x" * 65}, "paystack"),
        ({"provider_reference": None}, "paystack"),
        ({"provider_reference": "x" * 101}, "paystack"),
        ({"amount": None}, "paystack"),
        ({"amount": "0.00"}, "paystack"),
        ({"currency": None}, "paystack"),
        ({"currency": "NG"}, "paystack"),
        ({"occurred_at": datetime(2026, 9, 30)}, "paystack"),
        ({"evidence_fingerprint": "not-hex".ljust(64, "z")}, "paystack"),
    ],
)
def test_authenticated_malformed_payout_evidence_is_rejected_before_persistence(changes, provider):
    verified = replace(evidence(), **changes)

    with pytest.raises(AppError) as error:
        asyncio.run(
            ingest_payout_provider_webhook(
                UnusedSession(),
                payload=b"synthetic",
                signature="synthetic",
                adapter=Adapter(verified, provider),
            )
        )

    assert error.value.code == "DISBURSEMENT_WEBHOOK_INVALID"
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    ("failure", "expected", "status_code"),
    [
        (DisbursementUnavailableError("disabled"), "DISBURSEMENT_PROVIDER_UNAVAILABLE", 503),
        (ValueError("invalid signature"), "DISBURSEMENT_WEBHOOK_INVALID", 401),
    ],
)
def test_payout_webhook_authentication_failures_never_reach_persistence(
    failure, expected, status_code
):
    with pytest.raises(AppError) as error:
        asyncio.run(
            ingest_payout_provider_webhook(
                SimpleNamespace(),
                payload=b"synthetic",
                signature="synthetic",
                adapter=Adapter(failure),
            )
        )

    assert error.value.code == expected
    assert error.value.status_code == status_code
