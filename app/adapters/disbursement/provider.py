import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class DisbursementUnavailableError(RuntimeError):
    """Raised when no approved automated-disbursement provider is configured."""


class ProviderLookupStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DisbursementProviderCapabilities:
    provider_name: str
    lookup_by_idempotency_key: bool
    semantic_same_key_idempotency: bool


@dataclass(frozen=True, slots=True)
class DisbursementInstruction:
    line_id: str
    idempotency_key: str
    instruction: dict[str, str]
    instruction_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProviderSubmission:
    provider_reference: str
    line_references: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderLookup:
    status: ProviderLookupStatus
    provider_submission_reference: str | None = None
    provider_transfer_reference: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedLineEvidence:
    provider_transfer_reference: str
    provider_event_id: str
    outcome: str
    occurred_at: datetime
    evidence_fingerprint: str


class DisbursementAdapter(Protocol):
    @property
    def capabilities(self) -> DisbursementProviderCapabilities: ...

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission: ...

    async def lookup_line(
        self,
        *,
        idempotency_key: str,
        instruction_fingerprint: str,
    ) -> ProviderLookup: ...

    async def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedLineEvidence: ...

    async def poll_line(self, *, provider_transfer_reference: str) -> VerifiedLineEvidence: ...


class DisabledDisbursementAdapter:
    capabilities = DisbursementProviderCapabilities(
        provider_name="disabled",
        lookup_by_idempotency_key=False,
        semantic_same_key_idempotency=False,
    )

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

    async def lookup_line(
        self,
        *,
        idempotency_key: str,
        instruction_fingerprint: str,
    ) -> ProviderLookup:
        del idempotency_key, instruction_fingerprint
        raise DisbursementUnavailableError(
            "EXT-DISBURSEMENT-PROVIDER is missing; lookup is disabled"
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

    capabilities = DisbursementProviderCapabilities(
        provider_name="fake",
        lookup_by_idempotency_key=True,
        semantic_same_key_idempotency=True,
    )

    def __init__(self, *, webhook_secret: bytes = b"synthetic-fake-provider-secret") -> None:
        self.calls: list[tuple[str, tuple[DisbursementInstruction, ...]]] = []
        self.poll_calls: list[str] = []
        self.webhook_secret = webhook_secret
        self.poll_results: dict[str, VerifiedLineEvidence] = {}
        self.lookup_results: dict[str, ProviderLookup] = {}
        self._effects: dict[str, tuple[str, str, str]] = {}

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        self.calls.append((batch_id, instructions))
        line_references: dict[str, str] = {}
        submission_references: set[str] = set()
        for instruction in instructions:
            existing = self._effects.get(instruction.idempotency_key)
            if existing is not None:
                fingerprint, submission_reference, transfer_reference = existing
                if fingerprint != instruction.instruction_fingerprint:
                    raise ValueError("An idempotency key was reused for a different instruction")
            else:
                submission_reference = f"fake-batch-{batch_id}"
                transfer_reference = f"fake-line-{instruction.line_id}"
                self._effects[instruction.idempotency_key] = (
                    instruction.instruction_fingerprint,
                    submission_reference,
                    transfer_reference,
                )
            line_references[instruction.line_id] = transfer_reference
            submission_references.add(submission_reference)
        if len(submission_references) > 1:
            raise ValueError("A batch replay resolved to conflicting provider submissions")
        return ProviderSubmission(
            provider_reference=next(iter(submission_references), f"fake-batch-{batch_id}"),
            line_references=line_references,
        )

    def set_lookup_result(self, *, idempotency_key: str, result: ProviderLookup) -> None:
        self.lookup_results[idempotency_key] = result

    async def lookup_line(
        self,
        *,
        idempotency_key: str,
        instruction_fingerprint: str,
    ) -> ProviderLookup:
        override = self.lookup_results.get(idempotency_key)
        if override is not None:
            return override
        existing = self._effects.get(idempotency_key)
        if existing is None:
            return ProviderLookup(status=ProviderLookupStatus.NOT_FOUND)
        fingerprint, submission_reference, transfer_reference = existing
        if fingerprint != instruction_fingerprint:
            return ProviderLookup(status=ProviderLookupStatus.UNKNOWN)
        return ProviderLookup(
            status=ProviderLookupStatus.FOUND,
            provider_submission_reference=submission_reference,
            provider_transfer_reference=transfer_reference,
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
