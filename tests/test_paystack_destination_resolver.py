"""Frozen Paystack payout destination wiring."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.adapters.disbursement import DisbursementInstruction
from app.core.errors import AppError
from app.services import paystack_disbursements


def instruction(payload) -> DisbursementInstruction:
    return DisbursementInstruction(
        line_id="line-1",
        idempotency_key="key-1",
        instruction=payload,
        instruction_fingerprint="f" * 64,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"payee_version_id": None, "bank_account_version_id": str(uuid4())},
        {"payee_version_id": "not-a-uuid", "bank_account_version_id": str(uuid4())},
    ],
)
def test_destination_resolver_rejects_missing_or_invalid_frozen_authority(
    monkeypatch, payload
) -> None:
    monkeypatch.setattr(paystack_disbursements, "EnvelopeCryptoProvider", lambda **_: object())
    resolver = paystack_disbursements.build_paystack_destination_resolver(
        SimpleNamespace(payout_crypto_keys={}, payout_crypto_key_version=1),
        lambda: None,
    )

    with pytest.raises(AppError) as error:
        asyncio.run(resolver(instruction(payload)))

    assert error.value.code == "PAYOUT_DESTINATION_INSTRUCTION_INVALID"


def test_destination_resolver_reads_exact_frozen_versions_and_commits_audit(
    monkeypatch,
) -> None:
    payee_version_id = uuid4()
    bank_account_version_id = uuid4()
    crypto = object()
    seen = {}

    class Session:
        commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            self.commits += 1

    session = Session()

    async def read(_session, **kwargs):
        seen.update(kwargs)
        assert _session is session
        return SimpleNamespace(
            account_name="Synthetic Driver",
            account_number="0000000001",
            bank_code="999",
        )

    monkeypatch.setattr(paystack_disbursements, "EnvelopeCryptoProvider", lambda **_: crypto)
    monkeypatch.setattr(paystack_disbursements, "read_frozen_payout_bank_account", read)
    resolver = paystack_disbursements.build_paystack_destination_resolver(
        SimpleNamespace(payout_crypto_keys={}, payout_crypto_key_version=1),
        lambda: session,
    )

    destination = asyncio.run(
        resolver(
            instruction(
                {
                    "payee_version_id": str(payee_version_id),
                    "bank_account_version_id": str(bank_account_version_id),
                }
            )
        )
    )

    assert seen == {
        "payee_version_id": payee_version_id,
        "bank_account_version_id": bank_account_version_id,
        "crypto": crypto,
    }
    assert session.commits == 1
    assert destination.account_name == "Synthetic Driver"
    assert destination.account_number == "0000000001"
    assert destination.bank_code == "999"
