from dataclasses import dataclass
from typing import Protocol

from app.schemas.audience_delivery import AggregateActivationPayload


@dataclass(frozen=True)
class AdPlatformActivationRequest:
    idempotency_key: str
    payload: AggregateActivationPayload


@dataclass(frozen=True)
class AdPlatformActivationResult:
    provider_reference: str


class AdPlatformAdapter(Protocol):
    name: str
    enabled: bool
    synthetic: bool

    async def activate(
        self, request: AdPlatformActivationRequest
    ) -> AdPlatformActivationResult: ...


class DisabledAdPlatformAdapter:
    name = "disabled"
    enabled = False
    synthetic = False

    async def activate(self, request: AdPlatformActivationRequest) -> AdPlatformActivationResult:
        del request
        raise RuntimeError("disabled ad-platform adapter cannot be invoked")


class FakeAdPlatformAdapter:
    name = "synthetic-fake-ad-platform"
    enabled = True
    synthetic = True

    def __init__(self) -> None:
        self.calls: list[AdPlatformActivationRequest] = []

    async def activate(self, request: AdPlatformActivationRequest) -> AdPlatformActivationResult:
        self.calls.append(request)
        return AdPlatformActivationResult(
            provider_reference=f"fake-activation-{request.idempotency_key}"
        )


def build_ad_platform_adapter() -> AdPlatformAdapter:
    # EXT-AD-PLATFORM is deliberately absent. No environment value can turn a
    # live provider on until the external facts and a concrete adapter ship.
    return DisabledAdPlatformAdapter()
