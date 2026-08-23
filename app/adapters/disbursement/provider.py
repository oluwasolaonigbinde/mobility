from dataclasses import dataclass
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


class DisbursementAdapter(Protocol):
    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission: ...


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


class FakeDisbursementAdapter:
    """Deterministic fake for explicit test/local injection only."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[DisbursementInstruction, ...]]] = []

    async def submit_batch(
        self,
        *,
        batch_id: str,
        instructions: tuple[DisbursementInstruction, ...],
    ) -> ProviderSubmission:
        self.calls.append((batch_id, instructions))
        return ProviderSubmission(provider_reference=f"fake-batch-{batch_id}")
