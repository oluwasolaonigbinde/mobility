import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol


class PaymentGatewayUnavailableError(RuntimeError):
    """Raised while EXT-PAYMENT-PROVIDER is unresolved."""


class PaymentWebhookAuthenticationError(ValueError):
    """Raised when exact webhook bytes fail provider authentication."""


class PaymentWebhookPayloadError(ValueError):
    """Raised when authenticated webhook bytes do not satisfy the provider contract."""


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    idempotency_key: str
    commercial_terms_id: str
    organization_id: str
    amount: Decimal
    currency: str
    customer_reference: str
    return_url: str


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    provider_checkout_id: str
    checkout_url: str


@dataclass(frozen=True, slots=True)
class VerifiedPaymentEvent:
    provider_event_id: str
    external_transaction_id: str
    event_type: str
    commercial_terms_id: str
    amount: Decimal
    currency: str
    payer_name: str
    occurred_at: datetime
    evidence_fingerprint: str
    canonical_payload: dict


class PaymentGatewayAdapter(Protocol):
    provider_name: str

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession: ...

    async def verify_transaction(self, transaction_id: str) -> VerifiedPaymentEvent: ...

    async def parse_webhook(self, payload: bytes, signature: str) -> VerifiedPaymentEvent: ...


class DisabledPaymentGatewayAdapter:
    provider_name = "disabled"

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        del request
        raise PaymentGatewayUnavailableError(
            "EXT-PAYMENT-PROVIDER is missing; checkout creation is disabled"
        )

    async def verify_transaction(self, transaction_id: str) -> VerifiedPaymentEvent:
        del transaction_id
        raise PaymentGatewayUnavailableError(
            "EXT-PAYMENT-PROVIDER is missing; transaction verification is disabled"
        )

    async def parse_webhook(self, payload: bytes, signature: str) -> VerifiedPaymentEvent:
        del payload, signature
        raise PaymentGatewayUnavailableError(
            "EXT-PAYMENT-PROVIDER is missing; webhook verification is disabled"
        )


class FakePaymentGatewayAdapter:
    """Deterministic fake for tests and explicit local simulation only."""

    provider_name = "synthetic-gateway"

    def __init__(self, *, webhook_secret: bytes = b"synthetic-payment-webhook-secret") -> None:
        self.webhook_secret = webhook_secret
        self.checkout_calls: list[CheckoutRequest] = []
        self.transactions: dict[str, VerifiedPaymentEvent] = {}

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        self.checkout_calls.append(request)
        return CheckoutSession(
            provider_checkout_id=f"fake-checkout-{request.idempotency_key}",
            checkout_url=f"https://synthetic.invalid/checkout/{request.idempotency_key}",
        )

    def sign_webhook(self, payload: bytes) -> str:
        return hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()

    async def parse_webhook(self, payload: bytes, signature: str) -> VerifiedPaymentEvent:
        expected = self.sign_webhook(payload)
        if not hmac.compare_digest(expected, signature):
            raise PaymentWebhookAuthenticationError("Payment webhook signature is invalid")
        try:
            data = json.loads(payload)
            occurred_at = datetime.fromisoformat(str(data["occurred_at"]).replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            event_type = str(data["event_type"])
            if event_type not in {"payment_confirmed", "payment_failed"}:
                raise ValueError
            amount = Decimal(str(data["amount"]))
            currency = str(data["currency"]).strip().upper()
            canonical = {
                "provider_event_id": str(data["provider_event_id"]),
                "external_transaction_id": str(data["external_transaction_id"]),
                "event_type": event_type,
                "commercial_terms_id": str(data["commercial_terms_id"]),
                "amount": f"{amount:.2f}",
                "currency": currency,
                "payer_name": str(data["payer_name"]),
                "occurred_at": occurred_at.astimezone(UTC).isoformat(),
            }
            fingerprint = hashlib.sha256(payload).hexdigest()
            event = VerifiedPaymentEvent(
                provider_event_id=canonical["provider_event_id"],
                external_transaction_id=canonical["external_transaction_id"],
                event_type=event_type,
                commercial_terms_id=canonical["commercial_terms_id"],
                amount=amount,
                currency=currency,
                payer_name=canonical["payer_name"],
                occurred_at=occurred_at.astimezone(UTC),
                evidence_fingerprint=fingerprint,
                canonical_payload=canonical,
            )
            self.transactions[event.external_transaction_id] = event
            return event
        except (KeyError, TypeError, ValueError, ArithmeticError, json.JSONDecodeError) as exc:
            raise PaymentWebhookPayloadError("Payment webhook payload is invalid") from exc

    async def verify_transaction(self, transaction_id: str) -> VerifiedPaymentEvent:
        try:
            return self.transactions[transaction_id]
        except KeyError as exc:
            raise ValueError("Synthetic transaction has no verified result") from exc
