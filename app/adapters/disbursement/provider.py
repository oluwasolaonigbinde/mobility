import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


class DisbursementUnavailableError(RuntimeError):
    """Raised when no approved automated-disbursement provider is configured."""


@dataclass(frozen=True, slots=True)
class DisbursementInstruction:
    line_id: str
    idempotency_key: str
    instruction: dict[str, str]


@dataclass(frozen=True, slots=True)
class ProviderSubmission:
    provider_reference: str
    line_references: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VerifiedLineEvidence:
    provider_transfer_reference: str
    provider_event_id: str
    outcome: str
    occurred_at: datetime
    evidence_fingerprint: str


class DisbursementAdapter(Protocol):
    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission: ...

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence: ...

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence: ...


class DisabledDisbursementAdapter:
    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        del batch_id, instructions
        raise DisbursementUnavailableError(
            "EXT-DISBURSEMENT-PROVIDER is missing; submission is disabled"
        )

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence:
        del payload, signature
        raise DisbursementUnavailableError(
            "EXT-DISBURSEMENT-PROVIDER is missing; webhook verification is disabled"
        )

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence:
        del provider_transfer_reference
        raise DisbursementUnavailableError(
            "EXT-DISBURSEMENT-PROVIDER is missing; authenticated polling is disabled"
        )


class FakeDisbursementAdapter:
    """Deterministic fake for explicit test/local injection only."""

    def __init__(self, *, webhook_secret: bytes = b"synthetic-fake-provider-secret") -> None:
        self.calls: list[tuple[str, tuple[DisbursementInstruction, ...]]] = []
        self.poll_calls: list[str] = []
        self.webhook_secret = webhook_secret
        self.poll_results: dict[str, VerifiedLineEvidence] = {}

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        self.calls.append((batch_id, instructions))
        return ProviderSubmission(
            provider_reference=f"fake-batch-{batch_id}",
            line_references={
                instruction.line_id: f"fake-line-{instruction.line_id}"
                for instruction in instructions
            },
        )

    def sign_webhook(self, payload: bytes) -> str:
        return hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence:
        expected = self.sign_webhook(payload)
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Provider webhook signature is invalid")
        try:
            data = json.loads(payload)
            occurred_at = datetime.fromisoformat(str(data["occurred_at"]).replace("Z", "+00:00"))
            outcome = str(data["outcome"])
            if outcome not in {"succeeded", "failed"}:
                raise ValueError
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            return VerifiedLineEvidence(
                provider_transfer_reference=str(data["provider_transfer_reference"]),
                provider_event_id=str(data["provider_event_id"]),
                outcome=outcome,
                occurred_at=occurred_at,
                evidence_fingerprint=hashlib.sha256(payload).hexdigest(),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Provider webhook payload is invalid") from exc

    def set_poll_result(
        self,
        *,
        provider_transfer_reference: str,
        provider_event_id: str,
        outcome: str,
        occurred_at: datetime,
    ) -> None:
        payload = {
            "provider_transfer_reference": provider_transfer_reference,
            "provider_event_id": provider_event_id,
            "outcome": outcome,
            "occurred_at": occurred_at.astimezone(UTC).isoformat(),
        }
        self.poll_results[provider_transfer_reference] = VerifiedLineEvidence(
            provider_transfer_reference=provider_transfer_reference,
            provider_event_id=provider_event_id,
            outcome=outcome,
            occurred_at=occurred_at,
            evidence_fingerprint=hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence:
        self.poll_calls.append(provider_transfer_reference)
        try:
            return self.poll_results[provider_transfer_reference]
        except KeyError as exc:
            raise ValueError("Authenticated provider poll has no result") from exc
