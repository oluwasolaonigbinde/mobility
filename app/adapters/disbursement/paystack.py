"""Paystack transfer adapter built from Paystack's public API documentation."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.disbursement.provider import (
    DisabledDisbursementAdapter,
    DisbursementInstruction,
    DisbursementProviderCapabilities,
    DisbursementUnavailableError,
    ProviderLookup,
    ProviderLookupStatus,
    ProviderSubmission,
    VerifiedLineEvidence,
)
from app.adapters.payments.paystack import (
    PAYSTACK_PROVIDER_NAME,
    PaystackClient,
    PaystackError,
    PaystackNotFoundError,
    PaystackOutcomeUnknownError,
    PaystackRejectedError,
    canonical_fingerprint,
    from_subunits,
    parse_paystack_time,
    paystack_currency,
    to_subunits,
)
from app.core.config import Settings

TRANSFER_REASON = "Cardvert driver payout"
_EVENT_OUTCOMES = {
    "transfer.success": "succeeded",
    "transfer.failed": "failed",
    "transfer.reversed": "failed",
}
_STATUS_EVENTS = {
    "success": "transfer.success",
    "failed": "transfer.failed",
    "reversed": "transfer.reversed",
}


@dataclass(frozen=True, slots=True)
class TransferDestination:
    account_name: str = field(repr=False)
    account_number: str = field(repr=False)
    bank_code: str = field(repr=False)

    def __repr__(self) -> str:
        return "TransferDestination(<redacted>)"


# Must return the verified account for exactly instruction["bank_account_version_id"]
# under instruction["payee_version_id"] (the frozen payout line), never the payee's
# current account. Reading it is an audited plaintext access owned by the caller.
DestinationResolver = Callable[[DisbursementInstruction], Awaitable[TransferDestination]]


def paystack_transfer_reference(idempotency_key: str) -> str:
    """Deterministic 50-character reference; Paystack caps references at 50."""
    if not idempotency_key:
        raise ValueError("Idempotency key is required")
    return "cvp_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:46]


class PaystackDisbursementAdapter:
    def __init__(
        self,
        client: PaystackClient,
        *,
        destination_resolver: DestinationResolver | None = None,
    ) -> None:
        self.client = client
        self._destination_resolver = destination_resolver

    @property
    def capabilities(self) -> DisbursementProviderCapabilities:
        # "Submission not wired" guard: without an audited destination resolver the
        # service's capability check refuses submission before any intent exists.
        wired = self._destination_resolver is not None
        return DisbursementProviderCapabilities(
            provider_name=PAYSTACK_PROVIDER_NAME,
            lookup_by_idempotency_key=wired,
            semantic_same_key_idempotency=wired,
        )

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        del batch_id
        if self._destination_resolver is None:
            raise DisbursementUnavailableError("Paystack transfer destinations are not wired")
        if len(instructions) != 1:
            raise ValueError("Paystack transfers are submitted one line at a time")
        instruction = instructions[0]
        amount = to_subunits(Decimal(instruction.instruction["amount"]))
        currency = instruction.instruction["currency"]
        reference = paystack_transfer_reference(instruction.idempotency_key)
        destination = await self._destination_resolver(instruction)
        recipient = await self.client.request(
            "POST",
            "/transferrecipient",
            json_body={
                "type": "nuban",
                "name": destination.account_name,
                "account_number": destination.account_number,
                "bank_code": destination.bank_code,
                "currency": currency,
            },
        )
        recipient_code = self._matching_recipient(recipient, destination, currency)
        transfer = await self.client.request(
            "POST",
            "/transfer",
            json_body={
                "source": "balance",
                "amount": amount,
                "recipient": recipient_code,
                "reference": reference,
                "reason": TRANSFER_REASON,
                "currency": currency,
            },
        )
        if (
            not isinstance(transfer, dict)
            or transfer.get("domain") != self.client.mode
            or transfer.get("reference") != reference
            or transfer.get("amount") != amount
            or transfer.get("currency") != currency
            or not isinstance(transfer.get("transfer_code"), str)
            or not transfer["transfer_code"]
        ):
            raise PaystackOutcomeUnknownError("Paystack transfer response is malformed")
        transfer_code = transfer["transfer_code"]
        return ProviderSubmission(
            provider_reference=transfer_code,
            line_references={instruction.line_id: transfer_code},
        )

    def _matching_recipient(
        self, recipient: object, destination: TransferDestination, currency: str
    ) -> str:
        details = recipient.get("details") if isinstance(recipient, dict) else None
        if (
            not isinstance(recipient, dict)
            or not isinstance(details, dict)
            or recipient.get("domain") != self.client.mode
            or recipient.get("active") is not True
            or recipient.get("currency") != currency
            or details.get("account_number") != destination.account_number
            or details.get("bank_code") != destination.bank_code
            or not isinstance(recipient.get("recipient_code"), str)
            or not recipient["recipient_code"]
        ):
            raise PaystackRejectedError("Paystack recipient does not match the frozen destination")
        return recipient["recipient_code"]

    async def lookup_line(
        self,
        *,
        idempotency_key: str,
        instruction_fingerprint: str,
    ) -> ProviderLookup:
        # The key is derived from the instruction fingerprint, so the reference binds both.
        del instruction_fingerprint
        reference = paystack_transfer_reference(idempotency_key)
        try:
            data = await self.client.request("GET", f"/transfer/verify/{reference}")
        except PaystackNotFoundError:
            return ProviderLookup(status=ProviderLookupStatus.NOT_FOUND)
        except PaystackError:
            return ProviderLookup(status=ProviderLookupStatus.UNKNOWN)
        if (
            not isinstance(data, dict)
            or data.get("domain") != self.client.mode
            or data.get("reference") != reference
            or not isinstance(data.get("transfer_code"), str)
            or not data["transfer_code"]
        ):
            return ProviderLookup(status=ProviderLookupStatus.UNKNOWN)
        return ProviderLookup(
            status=ProviderLookupStatus.FOUND,
            provider_submission_reference=data["transfer_code"],
            provider_transfer_reference=data["transfer_code"],
        )

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence:
        if not self.client.verify_signature(payload, signature):
            raise ValueError("Provider webhook signature is invalid")
        try:
            body = json.loads(payload)
            event = body["event"]
            if event not in _EVENT_OUTCOMES:
                raise ValueError
            data = body["data"]
            if not isinstance(data, dict):
                raise ValueError
            return self._evidence(data, event)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError("Provider webhook payload is invalid") from exc

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence:
        data = await self.client.request(
            "GET", f"/transfer/{quote(provider_transfer_reference, safe='')}"
        )
        if not isinstance(data, dict) or data.get("transfer_code") != provider_transfer_reference:
            raise PaystackOutcomeUnknownError("Paystack transfer response is malformed")
        event = _STATUS_EVENTS.get(data.get("status"))
        if event is None:
            raise PaystackOutcomeUnknownError("Paystack transfer is not final")
        try:
            return self._evidence(data, event)
        except PaystackError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise PaystackOutcomeUnknownError("Paystack transfer response is malformed") from exc

    def _evidence(self, data: dict[str, Any], event: str) -> VerifiedLineEvidence:
        self.client.require_domain(data)
        if _STATUS_EVENTS.get(data["status"]) != event:
            raise ValueError("Paystack transfer status does not match the event")
        transfer_code = data["transfer_code"]
        reference = data["reference"]
        if not isinstance(transfer_code, str) or not transfer_code:
            raise ValueError("Paystack transfer code is missing")
        if not isinstance(reference, str) or not reference:
            raise ValueError("Paystack transfer reference is missing")
        amount_subunits = to_subunits(from_subunits(data["amount"]))
        currency = paystack_currency(data["currency"])
        outcome = _EVENT_OUTCOMES[event]
        provider_event_id = f"{event}:{transfer_code}"
        return VerifiedLineEvidence(
            provider_transfer_reference=transfer_code,
            provider_event_id=provider_event_id,
            outcome=outcome,
            occurred_at=parse_paystack_time(
                data.get("updatedAt"),
                data.get("updated_at"),
                data.get("transferred_at"),
                data.get("createdAt"),
                data.get("created_at"),
            ),
            evidence_fingerprint=canonical_fingerprint(
                {
                    "provider_event_id": provider_event_id,
                    "transfer_code": transfer_code,
                    "reference": reference,
                    "outcome": outcome,
                    "amount_subunits": amount_subunits,
                    "currency": currency,
                }
            ),
        )


def build_disbursement_adapter(
    settings: Settings,
    *,
    destination_resolver: DestinationResolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PaystackDisbursementAdapter | DisabledDisbursementAdapter:
    if settings.paystack_secret_key is None:
        return DisabledDisbursementAdapter()
    return PaystackDisbursementAdapter(
        PaystackClient(settings.paystack_secret_key.get_secret_value(), transport=transport),
        destination_resolver=destination_resolver,
    )
